# SPDX-License-Identifier: Apache-2.0
"""Assemblaggio della pipeline in-process: coda, processor, store, query, scheduler, metriche.

Richiede l'extra `[data]` (pyarrow, duckdb): importare questo modulo senza gli extra solleva
ImportError, gestito da `build_service_from_env` (l'app parte comunque, senza pipeline).
"""

import asyncio
import functools
import logging
import os
import threading
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.core.ports import IngestSource, Queue
from backend.envconf import env_positive_float, env_positive_int
from backend.pipeline.metrics import PipelineMetrics
from backend.pipeline.pipeline import Pipeline, ingest_once
from backend.pipeline.processors import TelemetryProcessor
from backend.pipeline.query import DuckDbQueryEngine
from backend.pipeline.queues import DurableQueue, MemoryQueue
from backend.pipeline.scheduler import AsyncScheduler
from backend.pipeline.store import ParquetStore

log = logging.getLogger(__name__)
DEFAULT_RETENTION_DAYS = {"raw": 365, "clean": 365, "curated": 365}


def _utc_now() -> datetime:
    return datetime.now(UTC)


class PipelineService:
    """Nota sui thread: ingestione/compattazione/retention/curated e la parte bloccante del batch
    girano nell'executor del servizio, mai sul loop. Un thread NON si puo' uccidere: allo scadere del
    timeout (o allo shutdown) il job attende e viene cancellato lato asyncio, mentre al thread arriva
    un flag cooperativo (`should_stop`) che i corpi dei job controllano fra una partizione e l'altra.
    """

    def __init__(
        self,
        root: Path,
        *,
        clock: Callable[[], datetime] = _utc_now,
        queue: Queue | None = None,
        stale_after_s: float = 300.0,
        retention_days: Mapping[str, int] | None = None,
        scheduler: AsyncScheduler | None = None,
        max_workers: int = 4,
        allow_lineage_loss: bool = False,
        max_infra_retries: int = 20,
        poison_breaker: int = 50,
        shutdown_wait_s: float = 30.0,
    ) -> None:
        retention_cfg = dict(retention_days or DEFAULT_RETENTION_DAYS)
        if not allow_lineage_loss and retention_cfg.get("raw", 0) < retention_cfg.get("curated", 0):
            raise ValueError(
                "retention raw < curated: il lineage dei curated non sarebbe risolvibile "
                "(allow_lineage_loss=True per accettarlo)"
            )
        self.clock = clock
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="pipeline")
        self._closing = threading.Event()
        self._closed = False
        self.store = ParquetStore(root, clock=clock)
        self.metrics = PipelineMetrics(clock, stale_after_s)
        self.queue: Queue = queue or MemoryQueue(capacity=10_000, policy="drop_with_counter")
        self.pipeline = Pipeline(
            queue=self.queue,
            processor=TelemetryProcessor(now=clock),
            store=self.store,
            metrics=self.metrics,
            clock=clock,
            executor=self.executor,
            max_infra_retries=max_infra_retries,
            poison_breaker=poison_breaker,
            shutdown_wait_s=shutdown_wait_s,
        )
        self.engine = DuckDbQueryEngine(self.store, clock=clock)
        self.scheduler = scheduler or AsyncScheduler()
        self._retention = retention_cfg

        async def drain() -> None:
            await self.pipeline.drain_until_idle(should_stop=self._closing.is_set)

        async def curate() -> None:
            await self._blocking(self.pipeline.curate_sync)

        def compact_body(stop: Callable[[], bool]) -> None:
            for layer in ("raw", "clean"):
                self.store.compact(layer, should_stop=stop)
            self.store.cleanup_tmp()

        async def compact() -> None:
            await self._blocking(compact_body)

        async def retention() -> None:
            await self._blocking(
                lambda stop: self.store.apply_retention(self._retention, should_stop=stop)
            )

        self.scheduler.add_job("drain", drain, interval_s=2, timeout_s=60)
        self.scheduler.add_job("curate", curate, interval_s=30, timeout_s=120)
        self.scheduler.add_job("compaction", compact, interval_s=300, timeout_s=300)
        self.scheduler.add_job("retention", retention, interval_s=3600, timeout_s=300)

    async def _blocking(self, fn: Callable[[Callable[[], bool]], Any]) -> Any:
        """Esegue `fn(should_stop)` nell'executor. Se l'attesa viene cancellata (timeout del job) il
        flag viene alzato: il thread termina alla prossima verifica cooperativa."""
        cancel = threading.Event()

        def should_stop() -> bool:
            return cancel.is_set() or self._closing.is_set()

        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(self.executor, functools.partial(fn, should_stop))
        except asyncio.CancelledError:
            cancel.set()
            raise

    async def aclose(self) -> None:
        """Ferma scheduler e job, attende i thread, chiude coda ed executor. Idempotente."""
        if self._closed:
            return
        self._closed = True
        self._closing.set()
        await self.scheduler.stop()
        await asyncio.to_thread(self.executor.shutdown, True)
        self.queue.close()

    def add_source(
        self,
        source: IngestSource,
        *,
        interval_s: float = 60.0,
        timeout_s: float = 30.0,
        stale_after_s: float | None = None,
    ) -> None:
        self.metrics.register_source(source.source_id, stale_after_s)

        async def ingest() -> None:
            await ingest_once(source, self.queue, self.metrics, self.clock)

        self.scheduler.add_job(
            f"ingest:{source.source_id}", ingest, interval_s=interval_s, timeout_s=timeout_s
        )

    def snapshot(self) -> dict[str, Any]:
        snap = self.metrics.snapshot()
        snap["enabled"] = True
        snap["queue"] = dict(self.queue.stats())
        snap["dead_letters_recent"] = [
            {"reason": d["reason"], "attempts": d["attempts"]}
            for d in list(self.queue.dead_letters())[-20:]
        ]
        snap["drain"] = self.pipeline.status()
        snap["jobs"] = {k: dict(v) for k, v in self.scheduler.status().items()}
        return snap


def build_service_from_env(env: Mapping[str, str] | None = None) -> PipelineService | None:
    """PIPELINE_DIR abilita la pipeline; PIPELINE_QUEUE = memory (default) | durable (SQLite in
    `<PIPELINE_DIR>/queue/`, confinata alla directory della pipeline); PIPELINE_STALE_AFTER_S."""
    env = os.environ if env is None else env
    root = env.get("PIPELINE_DIR")
    if not root:
        return None
    kind = env.get("PIPELINE_QUEUE", "memory")
    if kind not in ("memory", "durable"):
        raise ValueError("PIPELINE_QUEUE deve essere 'memory' o 'durable'")
    max_infra = env_positive_int("PIPELINE_MAX_INFRA_RETRIES", 20, env)
    breaker = env_positive_int("PIPELINE_POISON_BREAKER", 50, env)
    shutdown_wait = env_positive_float("PIPELINE_SHUTDOWN_WAIT_S", 30.0, env)
    base = Path(root)
    queue: Queue | None = None
    if kind == "durable":
        qdir = base / "queue"
        qdir.mkdir(parents=True, exist_ok=True)
        queue = DurableQueue(qdir / "pipeline-queue.db", base_dir=base, require_base_dir=True)
    try:
        stale = env_positive_float("PIPELINE_STALE_AFTER_S", 300.0, env)
        return PipelineService(
            base,
            stale_after_s=stale,
            queue=queue,
            max_infra_retries=max_infra,
            poison_breaker=breaker,
            shutdown_wait_s=shutdown_wait,
        )
    except ValueError as e:
        if queue is not None:
            queue.close()
        raise ValueError(f"configurazione pipeline non valida: {e}") from None
