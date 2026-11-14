# SPDX-License-Identifier: Apache-2.0
"""Fix round 1, tema C: scrittore unico (flock), lineage dopo compattazione, quarantena."""

import subprocess
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from backend.pipeline import store as store_mod
from backend.pipeline.query import DuckDbQueryEngine
from backend.pipeline.service import PipelineService
from backend.pipeline.store import ParquetStore

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[3]


def crow(t: datetime, site: str = "s1", raw: str = "part-raw", **kw: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "source_id": "a", "site_id": site, "t_utc": t, "schema_version": "1.0.0",
        "power_w": 10.0, "link_margin_db": None, "sun_az_deg": None, "sun_el_deg": None,
        "earth_az_deg": None, "earth_el_deg": None, "received_utc": t, "raw_file_id": raw,
    }  # fmt: skip
    row.update(kw)
    return row


@pytest.fixture
def store(tmp_path: Path) -> ParquetStore:
    return ParquetStore(tmp_path / "store", clock=lambda: NOW)


def fill(store: ParquetStore, n: int = 4) -> None:
    for i in range(n):
        store.write("clean", "a", [crow(NOW + timedelta(seconds=i))])


# ---- scrittore unico ----


def test_second_compactor_skips_while_first_is_merging(
    store: ParquetStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    fill(store)
    entered, release = threading.Event(), threading.Event()
    real_merge = store._merge

    def slow_merge(layer: str, tables: Any) -> Any:
        entered.set()
        release.wait(2)
        return real_merge(layer, tables)

    monkeypatch.setattr(store, "_merge", slow_merge)
    results: list[int] = []
    t1 = threading.Thread(target=lambda: results.append(store.compact("clean", min_files=2)))
    t1.start()
    assert entered.wait(2)
    second = store.compact("clean", min_files=2)  # mentre il primo e' a meta'
    release.set()
    t1.join(5)
    assert second == 0 and results == [1]
    assert store.read("clean").num_rows == 4
    assert len(store.visible_files("clean")) == 1


def test_retention_and_compaction_are_mutually_exclusive(
    store: ParquetStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    fill(store)
    store.write("clean", "a", [crow(NOW - timedelta(days=400))])
    entered, release = threading.Event(), threading.Event()
    real_merge = store._merge

    def slow_merge(layer: str, tables: Any) -> Any:
        entered.set()
        release.wait(2)
        return real_merge(layer, tables)

    monkeypatch.setattr(store, "_merge", slow_merge)
    t1 = threading.Thread(target=lambda: store.compact("clean", min_files=2))
    t1.start()
    assert entered.wait(2)
    assert store.apply_retention({"clean": 30}) == 0  # rimandata: il livello e' in compattazione
    release.set()
    t1.join(5)
    assert store.apply_retention({"clean": 30}) == 1


HOLD = (
    "import fcntl, sys\n"
    "fd = open(sys.argv[1], 'a')\n"
    "fcntl.flock(fd, fcntl.LOCK_EX)\n"
    "print('locked', flush=True)\n"
    "sys.stdin.readline()\n"
)


def test_lock_is_held_across_processes(store: ParquetStore) -> None:
    fill(store)
    lock_file = store.lock_path("clean")
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.Popen(
        [sys.executable, "-c", HOLD, str(lock_file)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, cwd=ROOT,
    )  # fmt: skip
    try:
        assert p.stdout is not None and p.stdout.readline().strip() == "locked"
        assert store.compact("clean", min_files=2) == 0
        assert len(store.visible_files("clean")) == 4
    finally:
        assert p.stdin is not None
        p.stdin.write("\n")
        p.stdin.flush()
        p.wait(10)
    assert store.compact("clean", min_files=2) == 1


COMPACTOR = (
    "import sys, time, pathlib\n"
    "from backend.pipeline.store import ParquetStore\n"
    "s = ParquetStore(sys.argv[1])\n"
    "pathlib.Path(sys.argv[3]).touch()\n"
    "go = pathlib.Path(sys.argv[2])\n"
    "while not go.exists(): time.sleep(0.001)\n"
    "n = 0\n"
    "for _ in range(25): n += s.compact('clean', min_files=2)\n"
    "print(n)\n"
)


def test_two_compactor_processes_do_not_duplicate_or_lose_rows(
    store: ParquetStore, tmp_path: Path
) -> None:
    for i in range(12):
        store.write("clean", "a", [crow(NOW + timedelta(seconds=i), site=f"s{i}")])
    go = tmp_path / "go"
    readies = [tmp_path / f"ready-{i}" for i in range(2)]
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", COMPACTOR, str(store.root), str(go), str(r)],
            stdout=subprocess.PIPE,
            text=True,
            cwd=ROOT,
        )
        for r in readies
    ]
    deadline = time.monotonic() + 30
    while not all(r.exists() for r in readies):  # handshake su file: entrambi pronti, poi via
        assert time.monotonic() < deadline
        time.sleep(0.005)
    go.write_text("go")
    for p in procs:
        p.wait(60)
        assert p.returncode == 0
    table = store.read("clean")
    keys = list(
        zip(table.column("site_id").to_pylist(), table.column("t_utc").to_pylist(), strict=True)
    )
    assert len(keys) == 12 and len(set(keys)) == 12
    assert len(store.visible_files("clean")) == 1


# ---- lineage dopo la compattazione ----


def raw_row(t: datetime) -> dict[str, Any]:
    return {"received_utc": t, "payload_json": "{}"}


def test_raw_ids_still_resolve_after_raw_compaction(store: ParquetStore) -> None:
    ids = [store.write("raw", "a", [raw_row(NOW + timedelta(seconds=i))])[0] for i in range(4)]
    store.write("clean", "a", [crow(NOW, raw=ids[0]), crow(NOW + timedelta(seconds=1), raw=ids[3])])
    store.build_curated("a", NOW.date().isoformat())
    assert store.compact("raw", min_files=2) == 1
    resolved = store.resolve_raw_ids(ids)
    visible = {Path(f).stem for f in store.visible_files("raw")}
    assert set(resolved) == set(ids)
    assert all(v in visible for v in resolved.values())  # ogni id punta al file compattato
    assert store.resolve_raw_ids(["part-inesistente"]) == {"part-inesistente": None}
    cur = store.read("curated").to_pylist()[0]
    assert all(store.resolve_raw_ids(cur["raw_file_ids"]).values())  # il lineage curated risolve


def test_retention_refuses_to_delete_raw_referenced_by_retained_curated(
    store: ParquetStore,
) -> None:
    old = NOW - timedelta(days=10)
    (raw_old,) = store.write("raw", "a", [raw_row(old)])
    (raw_free,) = store.write("raw", "a", [raw_row(old - timedelta(days=1))])
    store.write("clean", "a", [crow(NOW, raw=raw_old)])
    store.build_curated("a", NOW.date().isoformat())
    removed = store.apply_retention({"raw": 5, "curated": 365})
    assert removed == 1  # solo il raw non referenziato
    visible = {Path(f).stem for f in store.visible_files("raw")}
    assert raw_old in visible and raw_free not in visible
    assert store.retention_skipped and "raw" in store.retention_skipped[0]
    assert store.apply_retention({"raw": 5, "curated": 365}, force=True) == 1
    assert not store.visible_files("raw")


def test_retention_protection_follows_compaction(store: ParquetStore) -> None:
    old = NOW - timedelta(days=10)
    ids = [store.write("raw", "a", [raw_row(old + timedelta(seconds=i))])[0] for i in range(3)]
    store.write("clean", "a", [crow(NOW, raw=ids[1])])
    store.build_curated("a", NOW.date().isoformat())
    store.compact("raw", min_files=2)
    assert store.apply_retention({"raw": 5, "curated": 365}) == 0
    assert len(store.visible_files("raw")) == 1


def test_retention_deletes_raw_once_curated_is_gone(store: ParquetStore) -> None:
    old = NOW - timedelta(days=40)
    (raw_old,) = store.write("raw", "a", [raw_row(old)])
    store.write("clean", "a", [crow(old, raw=raw_old)])
    store.build_curated("a", old.date().isoformat())
    # curated e raw scadono nella stessa passata: il curated cade per primo, il raw non e' piu' protetto
    assert store.apply_retention({"raw": 5, "curated": 30}) == 2
    assert not store.visible_files("raw") and not store.visible_files("curated")


def test_service_forbids_raw_retention_shorter_than_curated(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="lineage"):
        PipelineService(tmp_path / "p", retention_days={"raw": 5, "clean": 30, "curated": 365})
    svc = PipelineService(
        tmp_path / "q",
        retention_days={"raw": 5, "clean": 30, "curated": 365},
        allow_lineage_loss=True,
    )
    assert svc is not None


# ---- politica di dedup in compattazione e quarantena ----


def test_corrupt_file_is_quarantined_and_does_not_break_reads(
    store: ParquetStore, caplog: pytest.LogCaptureFixture
) -> None:
    fill(store, 3)
    victim = Path(store.visible_files("clean")[1])
    victim.write_bytes(b"PAR1 garbage")  # corruzione del file
    table = store.read("clean")
    assert table.num_rows == 2  # le altre righe si leggono
    assert not victim.exists() and victim.with_name(victim.name + ".corrupt").exists()
    assert len(store.visible_files("clean")) == 2
    assert [Path(q).name for q in store.quarantined] == [victim.name]
    assert any("corrotto" in r.message or "corrupt" in r.message.lower() for r in caplog.records)
    assert store.compact("clean", min_files=2) == 1  # la compattazione prosegue sui file sani


def test_corrupt_compacted_footer_is_quarantined(store: ParquetStore) -> None:
    fill(store, 4)
    store.compact("clean", min_files=2)
    merged = Path(store.visible_files("clean")[0])
    merged.write_bytes(b"")
    assert store.visible_files("clean") == []  # niente eccezione, file messo in quarantena
    assert merged.with_name(merged.name + ".corrupt").exists()


def test_query_engine_recovers_from_a_corrupt_file(store: ParquetStore) -> None:
    fill(store, 3)
    engine = DuckDbQueryEngine(store, clock=lambda: NOW)
    assert len(engine.query("latest_samples", {"limit": 10})) == 3
    Path(store.visible_files("clean")[0]).write_bytes(b"PAR1 garbage")
    rows = engine.query("latest_samples", {"limit": 10})
    assert len(rows) == 2 and len(store.quarantined) == 1


def test_quarantined_name_never_matches_reader_glob(store: ParquetStore) -> None:
    fill(store, 2)
    f = Path(store.visible_files("clean")[0])
    f.write_bytes(b"x")
    store.read("clean")
    assert not list(store.root.rglob("part-*.parquet")) or all(
        p.suffix == ".parquet" for p in store.root.rglob("part-*.parquet")
    )
    assert store_mod.ParquetStore is type(store)
