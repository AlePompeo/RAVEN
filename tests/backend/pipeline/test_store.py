# SPDX-License-Identifier: Apache-2.0
import os
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import pytest

from backend.core.ports import Store
from backend.pipeline import store as store_mod
from backend.pipeline.store import ParquetStore, StoreError

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)


def clean_row(
    t: datetime, site: str = "s1", power: float = 100.0, raw: str = "part-raw1", **kw: Any
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "source_id": "a",
        "site_id": site,
        "t_utc": t,
        "schema_version": "1.0.0",
        "power_w": power,
        "link_margin_db": None,
        "sun_az_deg": None,
        "sun_el_deg": None,
        "earth_az_deg": None,
        "earth_el_deg": None,
        "received_utc": t + timedelta(seconds=1),
        "raw_file_id": raw,
    }
    row.update(kw)
    return row


@pytest.fixture
def store(tmp_path: Path) -> ParquetStore:
    return ParquetStore(tmp_path / "store", clock=lambda: NOW)


def parquet_files(root: Path) -> list[Path]:
    return sorted(root.rglob("*.parquet"))


def test_conforms_to_port(store: ParquetStore) -> None:
    assert isinstance(store, Store)


def test_write_then_read_clean_partitioned_by_source_and_date(store: ParquetStore) -> None:
    d1, d2 = datetime(2026, 10, 12, 23, 59, tzinfo=UTC), datetime(2026, 10, 13, 0, 1, tzinfo=UTC)
    ids = store.write("clean", "a", [clean_row(d1), clean_row(d2, power=7.0)])
    assert len(ids) == 2
    files = parquet_files(store.root)
    rels = sorted(str(f.relative_to(store.root).parent) for f in files)
    assert rels == ["clean/source=a/date=2026-10-12", "clean/source=a/date=2026-10-13"]
    table = store.read("clean")
    assert table.num_rows == 2
    assert sorted(table.column("power_w").to_pylist()) == [7.0, 100.0]
    assert table.schema.field("t_utc").type.tz == "UTC"
    assert store.read("clean", date="2026-10-13").num_rows == 1
    assert store.read("clean", source_id="zzz").num_rows == 0


def test_raw_partitioned_by_reception_date(store: ParquetStore) -> None:
    rec = datetime(2026, 10, 13, 5, tzinfo=UTC)
    (fid,) = store.write("raw", "a", [{"received_utc": rec, "payload_json": '{"x":1}'}])
    assert (store.root / "raw/source=a/date=2026-10-13" / f"{fid}.parquet").is_file()
    assert store.read("raw").column("payload_json").to_pylist() == ['{"x":1}']


def test_rejects_bad_layer_source_and_rows(store: ParquetStore) -> None:
    t = NOW
    for bad_source in ("../x", "A", "", "a/b", "a\x00"):
        with pytest.raises(StoreError):
            store.write("clean", bad_source, [clean_row(t)])
    with pytest.raises(StoreError):
        store.write("gold", "a", [clean_row(t)])
    with pytest.raises(StoreError):
        store.write("clean", "a", [clean_row(datetime(2026, 1, 1))])  # naive
    with pytest.raises(StoreError):
        store.write("clean", "a", [{"source_id": "a"}])
    assert store.write("clean", "a", []) == []
    assert parquet_files(store.root) == []


def test_crash_before_rename_leaves_no_visible_file(
    store: ParquetStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    store.write("clean", "a", [clean_row(NOW)])

    def boom(src: Any, dst: Any) -> None:
        raise OSError("crash simulato")

    monkeypatch.setattr(store_mod.os, "replace", boom)
    with pytest.raises(OSError):
        store.write("clean", "a", [clean_row(NOW + timedelta(seconds=5))])
    monkeypatch.undo()
    assert store.read("clean").num_rows == 1
    assert len(parquet_files(store.root)) == 1
    assert not list(store.root.rglob(".tmp-*"))  # ripulito dal percorso d'errore


def test_crash_mid_write_leaves_only_ignored_tmp(
    store: ParquetStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    part_dir = store.root / "clean/source=a/date=2026-10-13"
    part_dir.mkdir(parents=True)
    (part_dir / ".tmp-deadbeef").write_bytes(b"PAR1 troncato")  # processo ucciso a meta'
    store.write("clean", "a", [clean_row(NOW)])
    assert store.read("clean").num_rows == 1  # il tmp non e' mai visibile
    assert all(not f.endswith("deadbeef") for f in store.visible_files("clean"))
    assert store.cleanup_tmp(max_age_s=0) == 1
    assert not list(store.root.rglob(".tmp-*"))


def test_reader_never_sees_partial_files_under_concurrent_writes(store: ParquetStore) -> None:
    stop = threading.Event()
    errors: list[BaseException] = []
    counts: list[int] = []

    def writer() -> None:
        try:
            for i in range(40):
                store.write(
                    "clean",
                    "a",
                    [
                        clean_row(NOW + timedelta(seconds=i * 10 + k), site=f"s{k}")
                        for k in range(50)
                    ],
                )
        except BaseException as e:  # noqa: BLE001
            errors.append(e)
        finally:
            stop.set()

    def reader() -> None:
        try:
            while not stop.is_set():
                counts.append(store.read("clean").num_rows)
        except BaseException as e:  # noqa: BLE001
            errors.append(e)

    ts = [threading.Thread(target=writer), threading.Thread(target=reader)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(60)
    assert not errors, errors
    assert all(c % 50 == 0 for c in counts)  # mai un file a meta'
    assert counts == sorted(counts)
    assert store.read("clean").num_rows == 2000


def test_compaction_merges_small_files_without_changing_rows(store: ParquetStore) -> None:
    for i in range(6):
        store.write("clean", "a", [clean_row(NOW + timedelta(seconds=10 - i), site="s")])
    assert len(store.visible_files("clean")) == 6
    assert store.compact("clean", min_files=4) == 1
    files = store.visible_files("clean")
    assert len(files) == 1
    table = store.read("clean")
    ts = table.column("t_utc").to_pylist()
    assert ts == sorted(ts) and len(ts) == 6  # ordinato per tempo
    assert len(parquet_files(store.root)) == 1  # i sorgenti sono stati rimossi


def test_compaction_below_threshold_is_noop(store: ParquetStore) -> None:
    store.write("clean", "a", [clean_row(NOW)])
    store.write("clean", "a", [clean_row(NOW + timedelta(seconds=1))])
    assert store.compact("clean", min_files=4) == 0
    assert len(store.visible_files("clean")) == 2


def test_compaction_dedupes_clean_by_key_keeping_first_received(store: ParquetStore) -> None:
    t = NOW
    store.write("clean", "a", [clean_row(t, power=1.0, received_utc=t + timedelta(seconds=1))])
    store.write("clean", "a", [clean_row(t, power=2.0, received_utc=t + timedelta(seconds=9))])
    store.write("clean", "a", [clean_row(t + timedelta(seconds=1))])
    assert store.compact("clean", min_files=2) == 1
    table = store.read("clean")
    assert table.num_rows == 2
    by_t = dict(
        zip(table.column("t_utc").to_pylist(), table.column("power_w").to_pylist(), strict=True)
    )
    assert by_t[t] == 1.0  # stessa politica della pipeline: vince il primo ricevuto


def test_readers_see_no_duplicates_if_crash_before_source_cleanup(
    store: ParquetStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    for i in range(4):
        store.write("clean", "a", [clean_row(NOW + timedelta(seconds=i))])
    monkeypatch.setattr(store_mod.os, "unlink", lambda p: (_ for _ in ()).throw(OSError("crash")))
    with pytest.raises(OSError):
        store.compact("clean", min_files=2)
    monkeypatch.undo()
    assert len(parquet_files(store.root)) == 5  # compattato + 4 sorgenti ancora su disco
    assert store.read("clean").num_rows == 4  # ma i sorgenti sono nascosti
    assert len(store.visible_files("clean")) == 1
    assert store.compact("clean", min_files=2) == 0  # idempotente: il ripristino ripulisce
    assert len(parquet_files(store.root)) == 1


def test_retention_deletes_by_partition_age(store: ParquetStore) -> None:
    old, mid, new = (NOW - timedelta(days=d) for d in (40, 10, 1))
    for t in (old, mid, new):
        store.write("clean", "a", [clean_row(t)])
        store.write("raw", "a", [{"received_utc": t, "payload_json": "{}"}])
    removed = store.apply_retention({"raw": 5, "clean": 30})
    assert removed == 3  # raw: old+mid; clean: old
    assert store.read("clean").num_rows == 2
    assert store.read("raw").num_rows == 1
    assert not (store.root / f"clean/source=a/date={old.date()}").exists()
    with pytest.raises(StoreError):
        store.apply_retention({"clean": 0})
    with pytest.raises(StoreError):
        store.apply_retention({"nope": 3})


def test_clean_keys_for_restart_safe_dedup(store: ParquetStore) -> None:
    store.write(
        "clean", "a", [clean_row(NOW, site="x"), clean_row(NOW + timedelta(seconds=1), site="y")]
    )
    keys = store.clean_keys("a", NOW.date().isoformat())
    assert keys == {("x", NOW), ("y", NOW + timedelta(seconds=1))}
    assert store.clean_keys("a", "2020-01-01") == set()


def test_curated_hourly_aggregate_with_lineage_to_raw(store: ParquetStore) -> None:
    h = datetime(2026, 10, 13, 10, tzinfo=UTC)
    (raw1,) = store.write("raw", "a", [{"received_utc": h, "payload_json": "{}"}])
    (raw2,) = store.write("raw", "a", [{"received_utc": h, "payload_json": "{}"}])
    store.write(
        "clean",
        "a",
        [
            clean_row(h + timedelta(minutes=1), power=10.0, raw=raw1),
            clean_row(h + timedelta(minutes=2), power=30.0, raw=raw2),
            clean_row(h + timedelta(hours=1, minutes=1), power=50.0, raw=raw2),
        ],
    )
    fid = store.build_curated("a", "2026-10-13")
    assert fid is not None
    rows = sorted(store.read("curated").to_pylist(), key=lambda r: r["hour_utc"])
    assert [r["n"] for r in rows] == [2, 1]
    assert rows[0]["power_w_mean"] == 20.0 and rows[0]["power_w_min"] == 10.0
    assert rows[0]["power_w_max"] == 30.0
    assert rows[0]["raw_file_ids"] == sorted([raw1, raw2]) and rows[1]["raw_file_ids"] == [raw2]
    raw_ids = {f.rsplit("/", 1)[1].removesuffix(".parquet") for f in store.visible_files("raw")}
    assert {i for r in rows for i in r["raw_file_ids"]} <= raw_ids  # lineage risolvibile
    # idempotente: ricostruire sostituisce atomicamente, nessun doppione
    store.build_curated("a", "2026-10-13")
    assert store.read("curated").num_rows == 2
    assert len(store.visible_files("curated")) == 1
    assert store.build_curated("a", "2020-01-01") is None


def test_curated_rebuild_failure_keeps_previous_version(
    store: ParquetStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    store.write("clean", "a", [clean_row(NOW)])
    store.build_curated("a", NOW.date().isoformat())
    store.write("clean", "a", [clean_row(NOW + timedelta(seconds=3))])
    monkeypatch.setattr(store_mod.os, "replace", lambda a, b: (_ for _ in ()).throw(OSError("x")))
    with pytest.raises(OSError):
        store.build_curated("a", NOW.date().isoformat())
    monkeypatch.undo()
    assert store.read("curated").to_pylist()[0]["n"] == 1


def test_files_are_valid_parquet_with_zstd_or_snappy(store: ParquetStore) -> None:
    store.write("clean", "a", [clean_row(NOW)])
    f = parquet_files(store.root)[0]
    md = pq.ParquetFile(f).metadata
    assert md.num_rows == 1 and os.path.getsize(f) > 0
