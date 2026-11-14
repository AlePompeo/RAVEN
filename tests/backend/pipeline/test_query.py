# SPDX-License-Identifier: Apache-2.0
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pydantic
import pytest

from backend.core.ports import QueryEngine
from backend.pipeline.query import DuckDbQueryEngine
from backend.pipeline.query_spec import LatestSamples, UnknownQuery
from backend.pipeline.store import ParquetStore

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)


def row(
    source: str, site: str, t: datetime, power: float, recv: datetime | None = None
) -> dict[str, Any]:
    return {
        "source_id": source,
        "site_id": site,
        "t_utc": t,
        "schema_version": "1.0.0",
        "power_w": power,
        "link_margin_db": 1.5,
        "sun_az_deg": None,
        "sun_el_deg": None,
        "earth_az_deg": None,
        "earth_el_deg": None,
        "received_utc": recv or t + timedelta(seconds=1),
        "raw_file_id": "part-x",
    }


@pytest.fixture
def store(tmp_path: Path) -> ParquetStore:
    s = ParquetStore(tmp_path / "store", clock=lambda: NOW)
    rows_a = [row("a", "s1", NOW - timedelta(minutes=m), 100.0 + m) for m in range(10)]
    rows_a += [row("a", "s2", NOW - timedelta(minutes=m), 50.0) for m in range(3)]
    rows_a += [row("a", "s1", NOW - timedelta(hours=5), 10.0)]
    s.write("clean", "a", rows_a)
    # sorgente "b": silenziosa da 2 ore
    s.write("clean", "b", [row("b", "s1", NOW - timedelta(hours=2), 7.0)])
    return s


@pytest.fixture
def engine(store: ParquetStore) -> DuckDbQueryEngine:
    return DuckDbQueryEngine(store, clock=lambda: NOW)


def test_conforms_and_lists_predefined_queries(engine: DuckDbQueryEngine) -> None:
    assert isinstance(engine, QueryEngine)
    assert sorted(engine.names()) == ["latest_samples", "power_hourly", "stale_sources"]


def test_latest_samples_per_site_ordered_desc(engine: DuckDbQueryEngine) -> None:
    rows = engine.query("latest_samples", {"site_id": "s1", "source_id": "a", "limit": 3})
    assert [r["power_w"] for r in rows] == [100.0, 101.0, 102.0]
    assert rows[0]["t_utc"] == "2026-10-13T11:59:00.000000Z" or rows[0]["t_utc"].endswith("Z")
    assert rows[0]["t_utc"] > rows[1]["t_utc"]
    assert {r["site_id"] for r in rows} == {"s1"}


def test_latest_samples_without_site_is_n_per_site(engine: DuckDbQueryEngine) -> None:
    rows = engine.query("latest_samples", {"source_id": "a", "limit": 2})
    assert sorted(r["site_id"] for r in rows) == ["s1", "s1", "s2", "s2"]


def test_power_hourly_aggregate_and_window(engine: DuckDbQueryEngine) -> None:
    rows = engine.query("power_hourly", {"site_id": "s1", "source_id": "a", "hours": 3})
    assert len(rows) <= 3
    total = sum(r["n"] for r in rows)
    assert total == 10  # la riga di 5 ore fa e' fuori finestra
    first = rows[0]
    assert (
        first["hour_utc"].endswith("Z")
        and first["power_w_min"] <= first["power_w_mean"] <= first["power_w_max"]
    )
    wide = engine.query("power_hourly", {"site_id": "s1", "source_id": "a", "hours": 24})
    assert sum(r["n"] for r in wide) == 11


def test_stale_sources_uses_injected_clock(engine: DuckDbQueryEngine) -> None:
    stale = engine.query("stale_sources", {"threshold_s": 3600})
    assert [r["source_id"] for r in stale] == ["b"]
    assert stale[0]["silent_s"] == pytest.approx(7200 - 1, abs=1)
    later = DuckDbQueryEngine(engine._store, clock=lambda: NOW + timedelta(minutes=10))
    both = later.query("stale_sources", {"threshold_s": 300})
    assert [r["source_id"] for r in both] == ["b", "a"]  # piu' silenziosa per prima


def test_empty_store_returns_no_rows(tmp_path: Path) -> None:
    e = DuckDbQueryEngine(ParquetStore(tmp_path / "s"), clock=lambda: NOW)
    for name, params in (
        ("latest_samples", {}),
        ("power_hourly", {"site_id": "s1"}),
        ("stale_sources", {}),
    ):
        assert e.query(name, params) == []


def test_engine_row_cap_applies(store: ParquetStore) -> None:
    e = DuckDbQueryEngine(store, clock=lambda: NOW, max_rows=3)
    assert len(e.query("latest_samples", {"limit": 50})) == 3


@pytest.mark.parametrize(
    "evil",
    [
        "x' OR '1'='1",
        "s1'; DROP TABLE clean;--",
        "s1\x00",
        "../../etc/passwd",
        "s 1",
        "",
        "a" * 65,
        "s1) UNION SELECT * FROM read_csv('/etc/passwd')--",
    ],
)
def test_injection_rejected_by_validation(engine: DuckDbQueryEngine, evil: str) -> None:
    with pytest.raises(pydantic.ValidationError):
        engine.query("latest_samples", {"site_id": evil})
    with pytest.raises(pydantic.ValidationError):
        engine.query("power_hourly", {"site_id": evil})


def test_injection_is_inert_even_if_validation_were_bypassed(engine: DuckDbQueryEngine) -> None:
    hostile = LatestSamples.model_construct(site_id="x' OR '1'='1", source_id=None, limit=100)
    assert engine.execute_validated("latest_samples", hostile) == []
    hostile2 = LatestSamples.model_construct(site_id=None, source_id="a' OR 1=1 --", limit=100)
    assert engine.execute_validated("latest_samples", hostile2) == []


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": -1},
        {"limit": 10_000},
        {"limit": "abc"},
        {"limit": "1; DROP"},
        {"unknown": 1},
        {"limit": 1.5},
    ],
)
def test_bad_params_rejected(engine: DuckDbQueryEngine, params: dict[str, Any]) -> None:
    with pytest.raises(pydantic.ValidationError):
        engine.query("latest_samples", params)


@pytest.mark.parametrize(
    "name", ["select 1", "latest_samples; select 1", "../x", "", "LATEST_SAMPLES", "drop table x"]
)
def test_no_free_sql_only_known_names(engine: DuckDbQueryEngine, name: str) -> None:
    with pytest.raises(UnknownQuery):
        engine.query(name, {})


def test_connection_is_readonly_locked_and_confined(
    engine: DuckDbQueryEngine, store: ParquetStore, tmp_path: Path
) -> None:
    outside = tmp_path / "outside.parquet"
    pq.write_table(pa.table({"x": [1]}), outside)
    files = store.visible_files("clean")
    con = engine.connect_for_test(files)
    try:
        # file fuori dalla directory dello store: negato
        with pytest.raises(duckdb.PermissionException):
            con.execute("SELECT * FROM read_parquet(?)", [str(outside)]).fetchall()
        with pytest.raises(duckdb.PermissionException):
            con.execute("SELECT * FROM read_csv('/etc/passwd')").fetchall()
        # la configurazione non si puo' riaprire
        with pytest.raises(duckdb.InvalidInputException):
            con.execute("SET enable_external_access=true")
        with pytest.raises(duckdb.InvalidInputException):
            con.execute("SET allowed_directories=['/']")
        # sola lettura: nessuna scrittura
        with pytest.raises(duckdb.Error):
            con.execute("CREATE TABLE t(a INT)")
        with pytest.raises(duckdb.Error):
            con.execute(
                f"COPY (SELECT 1) TO '{store.root}/x.csv'"
            )  # nuovo file nello store: negato
        # ma i file dello store si leggono
        assert con.execute("SELECT count(*) FROM read_parquet(?)", [files]).fetchone()[0] == 15
    finally:
        con.close()
    assert not (store.root / "x.csv").exists()
