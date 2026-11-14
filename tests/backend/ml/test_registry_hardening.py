# SPDX-License-Identifier: Apache-2.0
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from backend.core.errors import ModelIntegrityError, ModelRegistryError
from backend.ml import registry as regmod
from backend.ml.registry import FileModelRegistry

ROOT = Path(__file__).resolve().parents[3]


def card(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "seed": 1,
        "dataset_sha256": "b" * 64,
        "library_versions": {"x": "1"},
        "metrics": {"skill": 0.8},
        "threshold": {"skill": 0.5},
    }
    base.update(over)
    return base


def rewrite_card(root: Path, v: str, **changes: Any) -> None:
    p = root / v / "model_card.json"
    data = json.loads(p.read_text())
    data.update(changes)
    p.write_text(json.dumps(data))


# -- (5) apertura sicura ---------------------------------------------------------------------
def test_symlink_swapped_card_refused(tmp_path: Path) -> None:
    reg = FileModelRegistry(tmp_path / "m")
    v = reg.save(b"x", card())
    other = tmp_path / "other.json"
    other.write_text((tmp_path / "m" / v / "model_card.json").read_text())
    (tmp_path / "m" / v / "model_card.json").unlink()
    (tmp_path / "m" / v / "model_card.json").symlink_to(other)
    with pytest.raises(ModelIntegrityError):
        reg.load(v)


def test_symlinked_version_dir_refused_everywhere(tmp_path: Path) -> None:
    reg = FileModelRegistry(tmp_path / "m")
    v = reg.save(b"x", card())
    real = tmp_path / "elsewhere"
    (tmp_path / "m" / v).rename(real)
    (tmp_path / "m" / v).symlink_to(real, target_is_directory=True)
    with pytest.raises(ModelIntegrityError):
        reg.load(v)
    with pytest.raises(ModelIntegrityError):
        reg.promote(v, approver="a", approved=True)
    assert reg.list_versions() == []


def test_fifo_model_refused_without_blocking(tmp_path: Path) -> None:
    reg = FileModelRegistry(tmp_path / "m")
    v = reg.save(b"x", card())
    m = tmp_path / "m" / v / "model.bin"
    m.unlink()
    os.mkfifo(m)
    with pytest.raises(ModelIntegrityError):
        reg.load(v)


# -- (6) promoted_version incrociato con la card ---------------------------------------------
def promoted(tmp_path: Path) -> tuple[FileModelRegistry, str]:
    reg = FileModelRegistry(tmp_path / "m")
    v = reg.save(b"model", card())
    reg.promote(v, approver="a", approved=True)
    return reg, v


def test_promoted_version_fails_closed_on_metric_tamper(tmp_path: Path) -> None:
    reg, v = promoted(tmp_path)
    assert reg.promoted_version() == v
    rewrite_card(tmp_path / "m", v, metrics={"skill": 0.1})
    with pytest.raises(ModelIntegrityError):
        FileModelRegistry(tmp_path / "m").promoted_version()


def test_promoted_version_fails_closed_on_status_tamper(tmp_path: Path) -> None:
    reg, v = promoted(tmp_path)
    rewrite_card(tmp_path / "m", v, status="candidate")
    with pytest.raises(ModelIntegrityError):
        reg.promoted_version()


def test_promoted_version_fails_closed_on_corrupt_model(tmp_path: Path) -> None:
    reg, v = promoted(tmp_path)
    (tmp_path / "m" / v / "model.bin").write_bytes(b"evil!")
    with pytest.raises(ModelIntegrityError):
        reg.promoted_version()


def test_forged_promotions_file_fails_closed(tmp_path: Path) -> None:
    reg, _ = promoted(tmp_path)
    v2 = reg.save(b"other", card())
    (tmp_path / "m" / "promotions.json").write_text(json.dumps({"stack": ["v0001", v2]}))
    with pytest.raises(ModelIntegrityError):
        reg.promoted_version()


# -- (4) niente rilettura/hash a ogni chiamata ----------------------------------------------
def test_promoted_card_does_not_rehash_every_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, v = promoted(tmp_path)
    calls = 0
    real = regmod._sha256_hex

    def counting(data: bytes) -> str:
        nonlocal calls
        calls += 1
        return real(data)

    monkeypatch.setattr(regmod, "_sha256_hex", counting)
    for _ in range(5):
        c, _ = FileModelRegistry(tmp_path / "m").promoted_card()  # istanze nuove
        assert c["version"] == v
    assert calls <= 1
    before = calls
    p = tmp_path / "m" / v / "model.bin"
    p.write_bytes(b"tampered-but-longer")  # cambia size/mtime: va riverificato e rifiutato
    with pytest.raises(ModelIntegrityError):
        FileModelRegistry(tmp_path / "m").promoted_card()
    assert calls > before


# -- (1) tetti e pulizia ---------------------------------------------------------------------
def test_candidate_cap_prunes_oldest_non_promoted(tmp_path: Path) -> None:
    reg = FileModelRegistry(tmp_path / "m", max_candidates=2)
    v1 = reg.save(b"1", card())
    v2 = reg.save(b"2", card())
    reg.promote(v1, approver="a", approved=True)
    reg.promote(v2, approver="a", approved=True)
    ids = [reg.save(bytes([i]), card()) for i in range(3, 7)]
    left = [c["version"] for c in reg.list_versions()]
    assert v1 in left and v2 in left  # promossi e precedente promosso mai potati
    assert left == [v1, v2, *ids[-2:]]
    assert reg.promoted_version() == v2


def test_candidate_cap_from_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ML_MAX_CANDIDATES", "1")
    reg = FileModelRegistry(tmp_path / "m")
    reg.save(b"1", card())
    reg.save(b"2", card())
    assert [c["version"] for c in reg.list_versions()] == ["v0002"]


@pytest.mark.parametrize("bad", ["0", "-1", "x", "1.5"])
def test_candidate_cap_env_validated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad: str
) -> None:
    monkeypatch.setenv("ML_MAX_CANDIDATES", bad)
    with pytest.raises(ModelRegistryError):
        FileModelRegistry(tmp_path / "m")


def test_default_candidate_cap_is_50(tmp_path: Path) -> None:
    assert FileModelRegistry(tmp_path / "m").max_candidates == 50


def test_stale_tmp_dirs_cleaned_at_open_and_by_pid(tmp_path: Path) -> None:
    root = tmp_path / "m"
    root.mkdir()
    old = root / ".tmp-111-aaaa"
    fresh = root / ".tmp-222-bbbb"
    for d in (old, fresh):
        d.mkdir()
        (d / "model.bin").write_bytes(b"x")
    past = time.time() - 7200
    os.utime(old, (past, past))
    reg = FileModelRegistry(root)
    assert not old.exists() and fresh.exists()  # il recente puo' essere di un altro scrittore
    reg.cleanup_tmp(pid=222)
    assert not fresh.exists()


def test_cleanup_tmp_never_follows_symlinks(tmp_path: Path) -> None:
    root = tmp_path / "m"
    root.mkdir()
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "keep").write_text("1")
    (root / ".tmp-5-x").symlink_to(victim, target_is_directory=True)
    FileModelRegistry(root).cleanup_tmp(pid=5)
    assert (victim / "keep").exists()


def test_version_overflow_refused_cleanly(tmp_path: Path) -> None:
    reg = FileModelRegistry(tmp_path / "m")
    (tmp_path / "m" / "v99999999").mkdir()
    with pytest.raises(ModelRegistryError):
        reg.save(b"x", card())
    assert not any(p.name.startswith("v1000") for p in (tmp_path / "m").iterdir())


# -- (7) concorrenza tra processi -------------------------------------------------------------
SAVER = """
import sys
sys.path.insert(0, sys.argv[1])
from backend.ml.registry import FileModelRegistry
r = FileModelRegistry(sys.argv[2], max_candidates=1000)
for i in range(int(sys.argv[3])):
    print(r.save(("m%s-%d" % (sys.argv[4], i)).encode(), {
        "seed": 1, "dataset_sha256": "c" * 64, "library_versions": {"x": "1"},
        "metrics": {"skill": 0.9}, "threshold": {"skill": 0.5}}))
"""
PROMOTER = """
import sys, time
sys.path.insert(0, sys.argv[1])
from backend.ml.registry import FileModelRegistry
from backend.core.errors import ModelRegistryError
r = FileModelRegistry(sys.argv[2], max_candidates=1000)
done = 0
for _ in range(3000):
    for c in r.list_versions():
        if c["status"] == "candidate":
            try:
                r.promote(c["version"], approver="p", approved=True)
                done += 1
            except ModelRegistryError:
                pass
    time.sleep(0.01)
    if done >= 5:
        break
print(done)
"""


def spawn(script: str, *args: str) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, "-I", "-c", script, str(ROOT), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def test_concurrent_saves_get_unique_versions(tmp_path: Path) -> None:
    root = str(tmp_path / "m")
    FileModelRegistry(root)
    procs = [spawn(SAVER, root, "8", str(i)) for i in range(6)]
    seen: list[str] = []
    for p in procs:
        out, err = p.communicate(timeout=120)
        assert p.returncode == 0, err[-1500:]
        seen += out.split()
    assert len(seen) == 48 and len(set(seen)) == 48
    reg = FileModelRegistry(root, max_candidates=1000)
    assert len(reg.list_versions()) == 48
    blobs = {reg.load(v)[0] for v in seen}
    assert len(blobs) == 48  # nessuna versione ha sovrascritto un'altra


def test_promote_races_with_save(tmp_path: Path) -> None:
    root = str(tmp_path / "m")
    FileModelRegistry(root)
    savers = [spawn(SAVER, root, "6", str(i)) for i in range(3)]
    prom = spawn(PROMOTER, root)
    for p in savers:
        assert p.wait(timeout=120) == 0
    _, err = prom.communicate(timeout=120)
    assert prom.returncode == 0, err[-1500:]
    reg = FileModelRegistry(root, max_candidates=1000)
    stack = json.loads((tmp_path / "m" / "promotions.json").read_text())["stack"]
    assert len(stack) == len(set(stack)) and len(stack) >= 1
    assert reg.promoted_version() == stack[-1]
    for v in stack:
        assert reg.load(v)[1]["status"] == "promoted"
    assert len(reg.list_versions()) == 18


def test_readers_never_see_inconsistent_state_during_promote_and_rollback(tmp_path: Path) -> None:
    import threading

    reg = FileModelRegistry(tmp_path / "m", max_candidates=100)
    ids = [reg.save(f"m{i}".encode(), card()) for i in range(10)]
    reg.promote(ids[0], approver="a", approved=True)
    stop = threading.Event()
    errors: list[BaseException] = []
    seen: set[str | None] = set()

    def reader() -> None:
        r = FileModelRegistry(tmp_path / "m", max_candidates=100)
        while not stop.is_set():
            try:
                seen.add(r.promoted_version())
            except BaseException as e:  # noqa: BLE001
                errors.append(e)
                return

    threads = [threading.Thread(target=reader) for _ in range(3)]
    for t in threads:
        t.start()
    try:
        for v in ids[1:]:
            reg.promote(v, approver="a", approved=True)
            reg.rollback(approver="a")
    finally:
        stop.set()
        for t in threads:
            t.join(10)
    assert errors == []
    assert seen <= set(ids)


def test_promote_recovers_card_promoted_but_not_in_stack(tmp_path: Path) -> None:
    reg = FileModelRegistry(tmp_path / "m")
    v = reg.save(b"x", card())
    rewrite_card(tmp_path / "m", v, status="promoted")  # crash dopo la card, prima dello stack
    assert reg.promoted_version() is None
    reg.promote(v, approver="a", approved=True)
    assert reg.promoted_version() == v


def test_promoted_snapshot_returns_verified_blob_and_key(tmp_path: Path) -> None:
    reg = FileModelRegistry(tmp_path / "m")
    v = reg.save(b"model-bytes", card())
    reg.promote(v, approver="a", approved=True)
    blob, c, key = reg.promoted_snapshot()  # type: ignore[misc]
    assert blob == b"model-bytes" and c["version"] == v
    assert key[0] == v and len(key) == 6  # versione, sha, ino, size, mtime_ns, ctime_ns
    assert FileModelRegistry(tmp_path / "e").promoted_snapshot() is None
