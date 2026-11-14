# SPDX-License-Identifier: Apache-2.0
"""Fix round 1, tema D: limiti di payload, orologi dei lease, wiring della coda, query concorrenti."""

import asyncio
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from backend.bootstrap import build_app
from backend.pipeline.metrics import PipelineMetrics
from backend.pipeline.pipeline import ingest_once
from backend.pipeline.query import DuckDbQueryEngine
from backend.pipeline.queues import (
    MAX_PAYLOAD_BYTES,
    DurableQueue,
    MemoryQueue,
    PayloadTooLarge,
    QueueConfigError,
)
from backend.pipeline.service import PipelineService, build_service_from_env
from backend.pipeline.store import ParquetStore

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "100000")
    monkeypatch.delenv("PIPELINE_DIR", raising=False)


# ---- payload ----


@pytest.mark.parametrize("kind", ["memory", "durable"])
async def test_oversize_payload_is_rejected_with_reason(kind: str, tmp_path: Path) -> None:
    q = (
        MemoryQueue(max_payload_bytes=200)
        if kind == "memory"
        else DurableQueue(tmp_path / "q.db", max_payload_bytes=200)
    )
    assert await q.put({"x": "a" * 50})
    with pytest.raises(PayloadTooLarge, match="200"):
        await q.put({"x": "a" * 500})
    assert q.stats()["depth"] == 1
    assert MAX_PAYLOAD_BYTES == 64 * 1024
    q.close()


async def test_ingest_counts_oversize_and_continues() -> None:
    class Src:
        source_id = "src"

        async def read(self) -> Any:
            yield {"power_w": 1.0}
            yield {"blob": "x" * 5000}
            yield {"power_w": 2.0}

    q = MemoryQueue(max_payload_bytes=1000)
    metrics = PipelineMetrics(lambda: NOW)
    assert await ingest_once(Src(), q, metrics, lambda: NOW) == 2
    assert metrics.snapshot()["sources"]["src"]["counters"]["ingest_oversize"] == 1


# ---- orologi dei lease ----


def test_default_lease_clocks_are_monotonic_based(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert MemoryQueue()._clock is time.monotonic
    q = DurableQueue(tmp_path / "q.db")
    before = q._clock()
    assert abs(before - time.time()) < 5  # comparabile fra processi (epoca)
    real = time.time
    monkeypatch.setattr(time, "time", lambda: real() + 10_000_000)  # salto dell'orologio di sistema
    assert abs(q._clock() - before) < 5  # i lease non ne risentono
    q.close()


def test_durable_queue_can_require_base_dir(tmp_path: Path) -> None:
    with pytest.raises(QueueConfigError, match="base_dir"):
        DurableQueue(tmp_path / "q.db", require_base_dir=True)
    DurableQueue(tmp_path / "q.db", base_dir=tmp_path, require_base_dir=True).close()


async def test_service_builds_confined_durable_queue_from_env(tmp_path: Path) -> None:
    env = {"PIPELINE_DIR": str(tmp_path / "p"), "PIPELINE_QUEUE": "durable"}
    svc = build_service_from_env(env)
    assert svc is not None and isinstance(svc.queue, DurableQueue)
    assert svc.queue._path.parent == (tmp_path / "p" / "queue").resolve()
    await svc.aclose()
    mem = build_service_from_env({"PIPELINE_DIR": str(tmp_path / "m")})
    assert mem is not None and isinstance(mem.queue, MemoryQueue)
    await mem.aclose()
    with pytest.raises(ValueError, match="PIPELINE_QUEUE"):
        build_service_from_env({"PIPELINE_DIR": str(tmp_path / "x"), "PIPELINE_QUEUE": "kafka"})


# ---- DuckDB: estensioni ----


def test_duckdb_connection_disables_extensions(tmp_path: Path) -> None:
    import duckdb

    store = ParquetStore(tmp_path / "s", clock=lambda: NOW)
    engine = DuckDbQueryEngine(store, clock=lambda: NOW)
    con = engine.connect_for_test([])
    try:
        rows = dict(
            con.execute(
                "SELECT name, value FROM duckdb_settings() WHERE name IN "
                "('allow_community_extensions','autoload_known_extensions',"
                "'autoinstall_known_extensions','lock_configuration','enable_external_access')"
            ).fetchall()
        )
        assert rows == {
            "allow_community_extensions": "false",
            "autoload_known_extensions": "false",
            "autoinstall_known_extensions": "false",
            "lock_configuration": "true",
            "enable_external_access": "false",
        }
        with pytest.raises(duckdb.Error):
            con.execute("INSTALL httpfs")
        with pytest.raises(duckdb.Error):
            con.execute("LOAD httpfs")
    finally:
        con.close()


# ---- route: query concorrenti limitate ----


async def test_concurrent_queries_are_capped_with_503(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PIPELINE_MAX_QUERIES", "1")
    app = build_app()
    svc = PipelineService(tmp_path / "p", clock=lambda: NOW)
    app.state.pipeline = svc
    entered, release = threading.Event(), threading.Event()

    def slow(name: str, params: Any) -> list[dict[str, Any]]:
        entered.set()
        release.wait(5)
        return []

    monkeypatch.setattr(svc.engine, "query", slow)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        first = asyncio.create_task(c.get("/api/pipeline/query/latest_samples"))
        assert await asyncio.to_thread(entered.wait, 5)
        second = await c.get("/api/pipeline/query/latest_samples")
        assert second.status_code == 503 and second.headers.get("retry-after")
        release.set()
        assert (await first).status_code == 200
        assert (await c.get("/api/pipeline/query/latest_samples")).status_code == 200
    await svc.aclose()


@pytest.mark.parametrize("value", ["0", "abc", "-3"])
def test_invalid_max_queries_fails_fast(value: str, monkeypatch: pytest.MonkeyPatch) -> None:
    # comportamento cambiato: prima ricadeva sul default, ora ferma l'avvio (envconf condiviso)
    monkeypatch.setenv("PIPELINE_MAX_QUERIES", value)
    with pytest.raises(SystemExit, match="PIPELINE_MAX_QUERIES"):
        build_app()


def test_empty_max_queries_uses_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PIPELINE_MAX_QUERIES", "")
    assert build_app().state.pipeline_max_queries == 4


def test_max_queries_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PIPELINE_MAX_QUERIES", "7")
    assert build_app().state.pipeline_max_queries == 7
