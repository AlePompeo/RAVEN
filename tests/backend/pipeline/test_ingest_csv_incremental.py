# SPDX-License-Identifier: Apache-2.0
"""Fix round 1, tema D: lettura incrementale del CSV (nessuna riscrittura di raw a ogni poll)."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from backend.core.manifest import Manifest, load_manifest
from backend.pipeline.metrics import PipelineMetrics
from backend.pipeline.pipeline import Pipeline, ingest_once
from backend.pipeline.processors import TelemetryProcessor
from backend.pipeline.queues import MemoryQueue
from backend.pipeline.store import ParquetStore
from backend.plugins.ingest_csv.plugin import CsvIngestSource

ROOT = Path(__file__).resolve().parents[3]
HEADER = "t_utc,site_id,power_w\n"
NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)


@pytest.fixture
def manifest() -> Manifest:
    return load_manifest(ROOT / "backend/plugins/ingest_csv/manifest.toml")


def line(i: int) -> str:
    return f"2026-10-13T10:00:{i:02d}Z,s1,{i}\n"


def make(tmp_path: Path, n: int) -> Path:
    p = tmp_path / "t.csv"
    p.write_text(HEADER + "".join(line(i) for i in range(n)), encoding="utf-8")
    return p


def append(path: Path, text: str) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(text)


async def collect(src: CsvIngestSource) -> list[dict[str, Any]]:
    return [dict(r) async for r in src.read()]


async def test_second_poll_of_unchanged_file_emits_nothing(
    manifest: Manifest, tmp_path: Path
) -> None:
    src = CsvIngestSource(manifest, path=make(tmp_path, 2))
    assert len(await collect(src)) == 2
    assert await collect(src) == []
    assert await collect(src) == []


async def test_appended_rows_emit_only_the_new_ones(manifest: Manifest, tmp_path: Path) -> None:
    f = make(tmp_path, 2)
    src = CsvIngestSource(manifest, path=f)
    await collect(src)
    append(f, line(2) + line(3))
    assert [r["power_w"] for r in await collect(src)] == [2.0, 3.0]
    assert await collect(src) == []


async def test_partial_last_line_waits_for_its_newline(manifest: Manifest, tmp_path: Path) -> None:
    f = make(tmp_path, 1)
    src = CsvIngestSource(manifest, path=f)
    await collect(src)
    append(f, "2026-10-13T10:00:05Z,s1,")  # scrittura in corso
    assert await collect(src) == []
    append(f, "5\n")
    assert [r["power_w"] for r in await collect(src)] == [5.0]


async def test_truncated_or_rotated_file_is_reread_from_start(
    manifest: Manifest, tmp_path: Path
) -> None:
    f = make(tmp_path, 5)
    src = CsvIngestSource(manifest, path=f)
    await collect(src)
    f.write_text(HEADER + line(40), encoding="utf-8")  # piu' piccolo
    assert [r["power_w"] for r in await collect(src)] == [40.0]
    # rotazione a dimensione maggiore e contenuto diverso
    f.write_text(HEADER + line(41) + line(42), encoding="utf-8")
    assert [r["power_w"] for r in await collect(src)] == [41.0, 42.0]


async def test_rotation_with_same_size_is_detected_by_content_hash(
    manifest: Manifest, tmp_path: Path
) -> None:
    f = make(tmp_path, 3)
    src = CsvIngestSource(manifest, path=f)
    await collect(src)
    size = f.stat().st_size
    f.write_text(f.read_text(encoding="utf-8").replace("s1", "s2"), encoding="utf-8")
    assert f.stat().st_size == size
    assert [r["site_id"] for r in await collect(src)] == ["s2", "s2", "s2"]


async def test_max_rows_is_per_poll_and_polls_continue(manifest: Manifest, tmp_path: Path) -> None:
    src = CsvIngestSource(manifest, path=make(tmp_path, 10), max_rows=4)
    assert [len(await collect(src)) for _ in range(4)] == [4, 4, 2, 0]


async def test_fetch_preview_does_not_consume_state(manifest: Manifest, tmp_path: Path) -> None:
    src = CsvIngestSource(manifest, path=make(tmp_path, 2))
    assert len((await src.fetch({}))["preview"]) == 2
    assert len(await collect(src)) == 2


async def test_reset_forces_full_reread(manifest: Manifest, tmp_path: Path) -> None:
    src = CsvIngestSource(manifest, path=make(tmp_path, 1))
    await collect(src)
    src.reset()
    assert len(await collect(src)) == 1


async def test_repolling_does_not_rewrite_raw(manifest: Manifest, tmp_path: Path) -> None:
    f = make(tmp_path, 3)
    src = CsvIngestSource(manifest, path=f, source_id="csv-a")
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
    for _ in range(5):  # cinque poll dello stesso file
        await ingest_once(src, queue, metrics, lambda: NOW)
        await pipe.drain_once()
    assert store.read("raw").num_rows == 3
    append(f, line(3))
    await ingest_once(src, queue, metrics, lambda: NOW)
    await pipe.drain_once()
    assert store.read("raw").num_rows == 4 and store.read("clean").num_rows == 4
