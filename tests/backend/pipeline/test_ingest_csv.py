# SPDX-License-Identifier: Apache-2.0
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from backend.bootstrap import build_app
from backend.core.manifest import Manifest, load_manifest
from backend.core.ports import DataSource, IngestSource
from backend.pipeline.metrics import PipelineMetrics
from backend.pipeline.pipeline import Pipeline, ingest_once
from backend.pipeline.processors import TelemetryProcessor
from backend.pipeline.queues import MemoryQueue
from backend.pipeline.store import ParquetStore
from backend.plugins.ingest_csv.plugin import CsvIngestSource

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "backend/plugins/ingest_csv/manifest.toml"
HEADER = "t_utc,site_id,power_w,link_margin_db,sun_az_deg,sun_el_deg,earth_az_deg,earth_el_deg\n"
NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)


@pytest.fixture
def manifest() -> Manifest:
    return load_manifest(MANIFEST)


def csv_file(tmp_path: Path, body: str, header: str = HEADER) -> Path:
    p = tmp_path / "t.csv"
    p.write_text(header + body, encoding="utf-8")
    return p


async def collect(src: CsvIngestSource) -> list[dict[str, Any]]:
    return [dict(r) async for r in src.read()]


def test_manifest_declares_kind_and_in_repo_terms(manifest: Manifest) -> None:
    assert manifest.kind == "data_source" and manifest.id == "ingest-csv"
    assert (ROOT / manifest.terms_url).is_file()


def test_registered_and_conforms_to_ports(manifest: Manifest, tmp_path: Path) -> None:
    kinds = {(m.kind, m.id) for m in build_app().state.registry.manifests()}
    assert ("data_source", "ingest-csv") in kinds
    src = CsvIngestSource(manifest, path=csv_file(tmp_path, ""))
    assert isinstance(src, IngestSource) and isinstance(src, DataSource)
    assert src.source_id == "ingest-csv"


async def test_maps_columns_to_contract_shape(manifest: Manifest, tmp_path: Path) -> None:
    f = csv_file(tmp_path, "2026-10-13T10:00:00Z,s1,120.5,3.5,10,20,1,2\n")
    (r,) = await collect(CsvIngestSource(manifest, path=f))
    assert r == {
        "schema_version": "1.0.0",
        "t_utc": "2026-10-13T10:00:00Z",
        "site_id": "s1",
        "power_w": 120.5,
        "link_margin_db": 3.5,
        "sun": {"az_deg": 10.0, "el_deg": 20.0},
        "earth": {"az_deg": 1.0, "el_deg": 2.0},
    }


async def test_empty_cells_omitted_and_defaults_applied(manifest: Manifest, tmp_path: Path) -> None:
    f = csv_file(tmp_path, "2026-10-13T10:00:00Z,,50,,,,,\n", HEADER)
    src = CsvIngestSource(manifest, path=f, site_id="lunar-1", source_id="my-csv")
    (r,) = await collect(src)
    assert r == {
        "schema_version": "1.0.0",
        "t_utc": "2026-10-13T10:00:00Z",
        "site_id": "lunar-1",
        "power_w": 50.0,
    }
    assert src.source_id == "my-csv"


async def test_non_numeric_and_non_finite_cells_are_kept_as_text(
    manifest: Manifest, tmp_path: Path
) -> None:
    f = csv_file(tmp_path, "2026-10-13T10:00:00Z,s1,nan,abc,inf,,,\n")
    (r,) = await collect(CsvIngestSource(manifest, path=f))
    assert r["power_w"] == "nan" and r["link_margin_db"] == "abc"
    assert r["sun"] == {"az_deg": "inf"}
    assert not any(isinstance(v, float) and not math.isfinite(v) for v in r.values())


async def test_unknown_columns_pass_through_for_the_processor_to_reject(
    manifest: Manifest, tmp_path: Path
) -> None:
    f = csv_file(tmp_path, "2026-10-13T10:00:00Z,s1,5,evil\n", "t_utc,site_id,power_w,extra\n")
    (r,) = await collect(CsvIngestSource(manifest, path=f))
    assert r["extra"] == "evil"


async def test_max_rows_and_size_limits(manifest: Manifest, tmp_path: Path) -> None:
    body = "".join(f"2026-10-13T10:00:{i:02d}Z,s1,{i}\n" for i in range(10))
    f = csv_file(tmp_path, body, "t_utc,site_id,power_w\n")
    assert len(await collect(CsvIngestSource(manifest, path=f, max_rows=4))) == 4
    with pytest.raises(ValueError):
        await collect(CsvIngestSource(manifest, path=f, max_bytes=10))


async def test_missing_file_and_unset_path(
    manifest: Manifest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("INGEST_CSV_PATH", raising=False)
    with pytest.raises(FileNotFoundError):
        await collect(CsvIngestSource(manifest, path=tmp_path / "nope.csv"))
    with pytest.raises(FileNotFoundError):
        await collect(CsvIngestSource(manifest))
    f = csv_file(tmp_path, "2026-10-13T10:00:00Z,s1,1,,,,,\n")
    monkeypatch.setenv("INGEST_CSV_PATH", str(f))
    assert len(await collect(CsvIngestSource(manifest))) == 1


async def test_bad_source_id_rejected(manifest: Manifest, tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        CsvIngestSource(manifest, path=csv_file(tmp_path, ""), source_id="../x")


async def test_fetch_returns_bounded_preview(manifest: Manifest, tmp_path: Path) -> None:
    body = "".join(f"2026-10-13T10:00:{i:02d}Z,s1,{i}\n" for i in range(30))
    f = csv_file(tmp_path, body, "t_utc,site_id,power_w\n")
    out = await CsvIngestSource(manifest, path=f).fetch({})
    assert out["source_id"] == "ingest-csv" and len(out["preview"]) == 20


async def test_end_to_end_csv_to_clean_with_duplicates_and_bad_rows(
    manifest: Manifest, tmp_path: Path
) -> None:
    body = (
        "2026-10-13T10:00:00Z,s1,100,,,,,\n"
        "2026-10-13T10:00:00Z,s1,100,,,,,\n"  # duplicato
        "2026-10-13T10:00:01Z,s1,nan,,,,,\n"  # NaN
        "2026-10-13T10:00:02Z,s1,abc,,,,,\n"  # non numerico
        "2026-10-13T10:00:03,s1,5,,,,,\n"  # senza fuso orario
        "2026-10-13T10:00:04Z,s1,7,,,,,\n"
    )
    src = CsvIngestSource(manifest, path=csv_file(tmp_path, body), source_id="csv-a")
    store = ParquetStore(tmp_path / "store", clock=lambda: NOW)
    queue = MemoryQueue()
    metrics = PipelineMetrics(lambda: NOW)
    pipe = Pipeline(
        queue=queue,
        processor=TelemetryProcessor(now=lambda: NOW),
        store=store,
        metrics=metrics,
        clock=lambda: NOW,
    )
    assert await ingest_once(src, queue, metrics, lambda: NOW) == 6
    r = await pipe.drain_once()
    assert (r.clean_rows, r.duplicates, r.rejected) == (2, 1, 3)
    assert sorted(d["reason"] for d in queue.dead_letters()) == [
        "naive_timestamp:t_utc",
        "non_finite_value:power_w",
        "schema_violation:power_w",
    ]
    # rilettura dello stesso file (replay): idempotente
    await ingest_once(src, queue, metrics, lambda: NOW)
    r2 = await pipe.drain_once()
    assert r2.clean_rows == 0 and store.read("clean").num_rows == 2
