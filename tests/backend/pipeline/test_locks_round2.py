# SPDX-License-Identifier: Apache-2.0
"""Fix round 2, N5: ordine dei lock curated -> clean -> raw, curated sotto lock, retention coerente."""

import subprocess
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from backend.pipeline import store as store_mod
from backend.pipeline.store import LayerBusy, LockOrderError, ParquetStore

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[3]


def raw_row(t: datetime) -> dict[str, Any]:
    return {"received_utc": t, "payload_json": "{}"}


def crow(t: datetime, raw: str) -> dict[str, Any]:
    return {
        "source_id": "a", "site_id": "s", "t_utc": t, "schema_version": "1.0.0",
        "power_w": 1.0, "link_margin_db": None, "sun_az_deg": None, "sun_el_deg": None,
        "earth_az_deg": None, "earth_el_deg": None, "received_utc": t, "raw_file_id": raw,
    }  # fmt: skip


@pytest.fixture
def store(tmp_path: Path) -> ParquetStore:
    return ParquetStore(tmp_path / "store", clock=lambda: NOW)


def test_lock_order_is_enforced(store: ParquetStore) -> None:
    assert store_mod.LOCK_ORDER == ("curated", "clean", "raw")
    with (
        store._layer_lock("curated") as a,
        store._layer_lock("clean") as b,
        store._layer_lock("raw") as c,
    ):
        assert a and b and c
    with store._layer_lock("raw"), pytest.raises(LockOrderError), store._layer_lock("curated"):
        pass
    with store._layer_lock("clean"), pytest.raises(LockOrderError), store._layer_lock("clean"):
        pass
    with store._layer_lock("curated") as ok:
        assert ok  # i lock sono stati rilasciati anche dopo l'errore


def test_retention_does_not_delete_raw_while_curated_rebuild_is_in_progress(
    store: ParquetStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = NOW - timedelta(days=10)
    (raw_id,) = store.write("raw", "a", [raw_row(old)])
    store.write(
        "clean", "a", [crow(NOW, raw_id)]
    )  # clean ricorda il raw; curated non esiste ancora
    entered, release = threading.Event(), threading.Event()
    real = store_mod._atomic_write

    def slow(table: Any, final: Path, metadata: Any = None) -> None:
        if final.name == "part-agg.parquet":
            entered.set()
            release.wait(5)
        real(table, final, metadata)

    monkeypatch.setattr(store_mod, "_atomic_write", slow)
    t = threading.Thread(target=lambda: store.build_curated("a", NOW.date().isoformat()))
    t.start()
    assert entered.wait(5)
    assert store.apply_retention({"raw": 5}) == 0  # rimandata: il curated e' in ricostruzione
    release.set()
    t.join(10)
    monkeypatch.undo()
    cur = store.read("curated").to_pylist()[0]
    assert all(store.resolve_raw_ids(cur["raw_file_ids"]).values())  # nessun riferimento pendente
    assert store.apply_retention({"raw": 5}) == 0  # e adesso e' protetto dal lineage


HOLD = (
    "import fcntl, sys\n"
    "fd = open(sys.argv[1], 'a')\n"
    "fcntl.flock(fd, fcntl.LOCK_EX)\n"
    "print('locked', flush=True)\n"
    "sys.stdin.readline()\n"
)


def test_build_curated_raises_busy_when_lock_is_held_elsewhere(store: ParquetStore) -> None:
    store.write("clean", "a", [crow(NOW, "x")])
    lock = store.lock_path("curated")
    lock.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.Popen(
        [sys.executable, "-c", HOLD, str(lock)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, cwd=ROOT,
    )  # fmt: skip
    try:
        assert p.stdout is not None and p.stdout.readline().strip() == "locked"
        with pytest.raises(LayerBusy):
            store.build_curated("a", NOW.date().isoformat())
        assert not store.visible_files("curated")
    finally:
        assert p.stdin is not None
        p.stdin.write("\n")
        p.stdin.flush()
        p.wait(10)
    assert store.build_curated("a", NOW.date().isoformat()) is not None


async def test_busy_curate_keeps_partition_dirty(tmp_path: Path) -> None:
    from backend.pipeline.service import PipelineService

    svc = PipelineService(tmp_path / "p", clock=lambda: NOW)
    svc.store.write("clean", "a", [crow(NOW, "x")])
    svc.pipeline._dirty.add(("a", NOW.date().isoformat()))
    with svc.store._layer_lock("curated"):
        assert await svc.pipeline.curate_once() == 0
        assert ("a", NOW.date().isoformat()) in svc.pipeline._dirty
    assert await svc.pipeline.curate_once() == 1
    await svc.aclose()


RETENTION = (
    "import sys, time, pathlib\n"
    "from datetime import datetime, UTC\n"
    "from backend.pipeline.store import ParquetStore\n"
    "s = ParquetStore(sys.argv[1], clock=lambda: datetime(2026, 10, 13, 12, tzinfo=UTC))\n"
    "pathlib.Path(sys.argv[2]).touch()\n"
    "go = pathlib.Path(sys.argv[3])\n"
    "while not go.exists(): time.sleep(0.001)\n"
    "for _ in range(40): s.apply_retention({'raw': 5, 'curated': 365})\n"
)
REBUILD = (
    "import sys, time, pathlib\n"
    "from backend.pipeline.store import ParquetStore, LayerBusy\n"
    "s = ParquetStore(sys.argv[1])\n"
    "pathlib.Path(sys.argv[2]).touch()\n"
    "go = pathlib.Path(sys.argv[3])\n"
    "while not go.exists(): time.sleep(0.001)\n"
    "for _ in range(40):\n"
    "    try: s.build_curated('a', '2026-10-13')\n"
    "    except LayerBusy: continue\n"
    "    ids = [i for r in s.read('curated').to_pylist() for i in r['raw_file_ids']]\n"
    "    if not all(s.resolve_raw_ids(ids).values()): sys.exit(3)\n"
)


def test_retention_and_curated_rebuild_in_two_processes_stay_consistent(
    store: ParquetStore, tmp_path: Path
) -> None:
    old = NOW - timedelta(days=10)
    (raw_id,) = store.write("raw", "a", [raw_row(old)])
    store.write("clean", "a", [crow(NOW, raw_id)])
    store.build_curated("a", NOW.date().isoformat())
    go = tmp_path / "go"
    procs, readies = [], []
    for script in (RETENTION, REBUILD):
        ready = tmp_path / f"ready-{len(readies)}"
        readies.append(ready)
        args = [sys.executable, "-c", script, str(store.root), str(ready), str(go)]
        procs.append(subprocess.Popen(args, cwd=ROOT))
    deadline = time.monotonic() + 30
    while not all(r.exists() for r in readies):  # handshake su file, nessuno sleep fisso
        assert time.monotonic() < deadline
        time.sleep(0.005)
    go.write_text("go")
    for p in procs:
        assert p.wait(60) == 0
    assert store.visible_files("raw")  # il raw referenziato non e' mai stato cancellato
    cur = store.read("curated").to_pylist()
    assert len(cur) == 1 and all(store.resolve_raw_ids(cur[0]["raw_file_ids"]).values())
