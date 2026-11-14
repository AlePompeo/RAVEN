# SPDX-License-Identifier: Apache-2.0
"""Fix round 2, N3: quarantena solo per corruzione Parquet verificata, mai per errori transitori."""

import errno
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from backend.pipeline import query as query_mod
from backend.pipeline import store as store_mod
from backend.pipeline.query import DuckDbQueryEngine
from backend.pipeline.query_spec import QueryError
from backend.pipeline.store import ParquetStore

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)


def crow(i: int) -> dict[str, Any]:
    t = NOW + timedelta(seconds=i)
    return {
        "source_id": "a", "site_id": "s", "t_utc": t, "schema_version": "1.0.0",
        "power_w": 1.0, "link_margin_db": None, "sun_az_deg": None, "sun_el_deg": None,
        "earth_az_deg": None, "earth_el_deg": None, "received_utc": t, "raw_file_id": "x",
    }  # fmt: skip


@pytest.fixture
def store(tmp_path: Path) -> ParquetStore:
    s = ParquetStore(tmp_path / "s", clock=lambda: NOW)
    for i in range(3):
        s.write("clean", "a", [crow(i)])
    return s


def no_corrupt(store: ParquetStore) -> bool:
    return not list(store.root.rglob("*.corrupt")) and not store.quarantined


@pytest.mark.parametrize("code", [errno.EMFILE, errno.EIO, errno.EACCES])
def test_transient_os_errors_never_rename_files(
    store: ParquetStore, monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    def boom(*a: Any, **k: Any) -> Any:
        raise OSError(code, "errore transitorio")

    monkeypatch.setattr(store_mod.pq, "read_table", boom)
    with pytest.raises(OSError):
        store.read("clean")
    monkeypatch.undo()
    assert no_corrupt(store) and store.read("clean").num_rows == 3  # i dati sono ancora li'


def test_transient_error_reading_compacted_footer_does_not_rename(
    store: ParquetStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    store.compact("clean", min_files=2)

    def boom(*a: Any, **k: Any) -> Any:
        raise OSError(errno.EIO, "I/O")

    monkeypatch.setattr(store_mod.pq, "read_schema", boom)
    store._replaces_cache.clear()
    with pytest.raises(OSError):
        store.visible_files("clean")
    monkeypatch.undo()
    assert no_corrupt(store) and store.read("clean").num_rows == 3


def test_verification_ignores_unverifiable_files(
    store: ParquetStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*a: Any, **k: Any) -> Any:
        raise OSError(errno.EMFILE, "troppi file aperti")

    monkeypatch.setattr(store_mod.pq, "ParquetFile", boom)
    assert store.quarantine_invalid("clean") == 0  # non verificabile != corrotto
    monkeypatch.undo()
    assert no_corrupt(store)


def test_truncated_parquet_is_quarantined(
    store: ParquetStore, caplog: pytest.LogCaptureFixture
) -> None:
    f = Path(store.visible_files("clean")[0])
    f.write_bytes(f.read_bytes()[: f.stat().st_size // 2])
    with caplog.at_level(logging.ERROR):
        assert store.read("clean").num_rows == 2
    assert f.with_name(f.name + ".corrupt").exists() and not f.exists()  # rinomina, mai delete
    assert len(store.quarantined) == 1


def test_quarantining_the_only_copy_logs_critical(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    s = ParquetStore(tmp_path / "s", clock=lambda: NOW)
    s.write("clean", "a", [crow(0)])
    f = Path(s.visible_files("clean")[0])
    f.write_bytes(b"PAR1 rotto")
    with caplog.at_level(logging.CRITICAL):
        s.read("clean")
    assert any(r.levelno == logging.CRITICAL for r in caplog.records)
    assert f.with_name(f.name + ".corrupt").exists()


def test_duckdb_binder_error_does_not_quarantine(
    store: ParquetStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = DuckDbQueryEngine(store, clock=lambda: NOW)
    monkeypatch.setattr(query_mod, "_SQL_LATEST", "SELECT colonna_inesistente FROM read_parquet(?)")
    with pytest.raises(QueryError):
        engine.query("latest_samples", {"limit": 5})
    assert no_corrupt(store) and len(store.visible_files("clean")) == 3


def test_query_recovers_only_after_verified_corruption(store: ParquetStore) -> None:
    engine = DuckDbQueryEngine(store, clock=lambda: NOW)
    Path(store.visible_files("clean")[0]).write_bytes(b"PAR1 rotto")
    assert len(engine.query("latest_samples", {"limit": 10})) == 2
    assert len(store.quarantined) == 1
