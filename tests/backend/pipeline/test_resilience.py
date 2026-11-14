# SPDX-License-Identifier: Apache-2.0
"""Fix round 1, tema B: lavoro bloccante fuori dal loop, backoff, infra vs veleno, shutdown."""

import asyncio
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from backend.pipeline.metrics import PipelineMetrics
from backend.pipeline.pipeline import Pipeline
from backend.pipeline.processors import TelemetryProcessor
from backend.pipeline.queues import DurableQueue, MemoryQueue
from backend.pipeline.scheduler import AsyncScheduler
from backend.pipeline.service import PipelineService
from backend.pipeline.store import ParquetStore

from .test_pipeline import msg, rec

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture(params=["memory", "durable"])
def make_queue(request: pytest.FixtureRequest, tmp_path: Path) -> Callable[..., Any]:
    def factory(**kw: Any) -> Any:
        if request.param == "memory":
            return MemoryQueue(**kw)
        return DurableQueue(tmp_path / "q.db", **kw)

    return factory


# ---- coda: rilascio senza consumare tentativi, con ritardo ----


async def test_nack_without_attempt_and_with_delay(make_queue: Callable[..., Any]) -> None:
    clock = Clock()
    q = make_queue(max_attempts=2, clock=clock)
    await q.put({"k": 1})
    first = await q.get(timeout_s=0)
    assert first is not None and first.attempt == 1
    assert await q.nack(first, "infra", count_attempt=False, delay_s=30.0)
    assert await q.get(timeout_s=0) is None  # ritardo non scaduto
    assert not await q.ack(first)  # lease vecchio
    clock.t += 31
    second = await q.get(timeout_s=0)
    assert second is not None and second.attempt == 1  # il tentativo non e' stato consumato
    assert second.lease != first.lease


async def test_many_infra_nacks_never_dead_letter(make_queue: Callable[..., Any]) -> None:
    clock = Clock()
    q = make_queue(max_attempts=2, clock=clock)
    await q.put({"k": 1})
    for _ in range(6):
        item = await q.get(timeout_s=0)
        assert item is not None
        assert await q.nack(item, "infra", count_attempt=False)
    assert q.dead_letters() == []
    item = await q.get(timeout_s=0)
    assert item is not None and item.attempt == 1


# ---- pipeline: infra vs veleno, backoff, niente spin ----


def make_pipe(
    tmp_path: Path, *, clock: Callable[[], datetime], rng: Callable[[], float] = lambda: 1.0
) -> tuple[Pipeline, ParquetStore, MemoryQueue, Clock]:
    qclock = Clock()
    store = ParquetStore(tmp_path / "s", clock=clock)
    queue = MemoryQueue(max_attempts=2, clock=qclock)
    pipe = Pipeline(
        queue=queue,
        processor=TelemetryProcessor(now=clock),
        store=store,
        metrics=PipelineMetrics(clock),
        clock=clock,
        backoff_base_s=2.0,
        backoff_cap_s=10.0,
        rng=rng,
    )
    return pipe, store, queue, qclock


async def test_infra_failure_does_not_burn_attempts_and_backs_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = [NOW]
    pipe, store, queue, qclock = make_pipe(tmp_path, clock=lambda: now[0])
    await queue.put(msg(rec()))
    real = store.write
    monkeypatch.setattr(store, "write", lambda *a, **k: (_ for _ in ()).throw(OSError("disco")))
    delays: list[float] = []
    for _ in range(5):  # molto piu' di max_attempts=2
        r = await pipe.drain_once()
        assert r.requeued == 1
        delays.append(pipe.backoff_remaining_s())
        now[0] += timedelta(seconds=pipe.backoff_remaining_s() + 0.1)
        qclock.t += 1000
    assert queue.dead_letters() == []  # i messaggi sani non muoiono per un disco guasto
    assert delays == [2.0, 4.0, 8.0, 10.0, 10.0]  # esponenziale con tetto (rng=1 -> senza sconto)
    monkeypatch.setattr(store, "write", real)
    r = await pipe.drain_once()
    assert r.clean_rows == 1 and pipe.backoff_remaining_s() == 0.0  # successo: backoff azzerato


async def test_backoff_gate_means_no_spin_and_no_queue_access(tmp_path: Path) -> None:
    now = [NOW]
    pipe, store, queue, _ = make_pipe(tmp_path, clock=lambda: now[0])
    await queue.put(msg(rec()))
    store.write = lambda *a, **k: (_ for _ in ()).throw(OSError("x"))  # type: ignore[method-assign]
    await pipe.drain_once()
    gets = {"n": 0}
    real_get = queue.get

    async def counting_get(*a: Any, **k: Any) -> Any:
        gets["n"] += 1
        return await real_get(*a, **k)

    queue.get = counting_get  # type: ignore[method-assign]
    r = await pipe.drain_once()  # ancora in backoff
    assert r.processed == 0 and gets["n"] == 0


async def test_jitter_scales_the_delay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    now = [NOW]
    pipe, store, queue, _ = make_pipe(tmp_path, clock=lambda: now[0], rng=lambda: 0.0)
    await queue.put(msg(rec()))
    monkeypatch.setattr(store, "write", lambda *a, **k: (_ for _ in ()).throw(OSError("x")))
    await pipe.drain_once()
    assert pipe.backoff_remaining_s() == pytest.approx(1.0)  # 2.0 * (0.5 + 0.5 * 0.0)


async def test_drain_until_idle_terminates_without_progress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = [NOW]
    pipe, store, queue, qclock = make_pipe(tmp_path, clock=lambda: now[0])
    for i in range(3):
        await queue.put(msg(rec(f"2026-10-13T10:00:0{i}Z")))
    monkeypatch.setattr(store, "write", lambda *a, **k: (_ for _ in ()).throw(OSError("x")))
    total = await asyncio.wait_for(pipe.drain_until_idle(), 5)
    assert total.clean_rows == 0
    monkeypatch.undo()
    now[0] += timedelta(minutes=5)
    qclock.t += 1000
    total = await asyncio.wait_for(pipe.drain_until_idle(), 5)
    assert total.clean_rows == 3


# ---- lavoro bloccante fuori dal loop ----


async def test_batch_runs_in_worker_thread_and_loop_stays_responsive(tmp_path: Path) -> None:
    """Deterministico: il thread del processor resta bloccato finche' il LOOP non ha fatto 5 tick.
    Se il batch girasse sul loop, i tick non avanzerebbero mai e il thread scadrebbe (timeout 10 s)."""
    seen: list[int] = []
    loop_alive = threading.Event()

    class BlockingProcessor:
        def process(self, message: Any) -> Any:
            seen.append(threading.get_ident())
            assert loop_alive.wait(10), "il loop e' bloccato dal lavoro del batch"
            return TelemetryProcessor(now=lambda: NOW).process(message)

    store = ParquetStore(tmp_path / "s", clock=lambda: NOW)
    pipe = Pipeline(
        queue=MemoryQueue(),
        processor=BlockingProcessor(),
        store=store,
        metrics=PipelineMetrics(lambda: NOW),
        clock=lambda: NOW,
    )
    await pipe.queue.put(msg(rec()))

    async def ticker() -> None:
        for _ in range(5):
            await asyncio.sleep(0)
        loop_alive.set()

    t = asyncio.create_task(ticker())
    r = await pipe.drain_once()
    await t
    assert seen and seen[0] != threading.get_ident()
    assert loop_alive.is_set() and r.clean_rows == 1


async def test_durable_queue_sqlite_work_is_off_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    q = DurableQueue(tmp_path / "q.db")
    idents: list[int] = []
    for name in ("_try_put", "_try_get"):
        real = getattr(q, name)

        def spy(*a: Any, _real: Any = real, **k: Any) -> Any:
            idents.append(threading.get_ident())
            return _real(*a, **k)

        monkeypatch.setattr(q, name, spy)
    await q.put({"a": 1})
    item = await q.get(timeout_s=0)
    assert item is not None and await q.ack(item)
    assert idents and all(i != threading.get_ident() for i in idents)
    q.close()


async def test_service_jobs_run_in_worker_threads(tmp_path: Path) -> None:
    svc = PipelineService(tmp_path / "p", clock=lambda: NOW)
    idents: dict[str, int] = {}
    for layer_fn in ("compact", "apply_retention", "build_curated"):
        real = getattr(svc.store, layer_fn)

        def spy(*a: Any, _n: str = layer_fn, _real: Any = real, **k: Any) -> Any:
            idents[_n] = threading.get_ident()
            return _real(*a, **k)

        setattr(svc.store, layer_fn, spy)
    svc.pipeline._dirty.add(("a", "2026-10-13"))
    for job in ("compaction", "retention", "curate"):
        assert await svc.scheduler.run_now(job) == "ok"
    assert set(idents) == {"compact", "apply_retention", "build_curated"}
    assert all(i != threading.get_ident() for i in idents.values())
    await svc.aclose()


async def test_timeout_sets_cooperative_cancel_flag(tmp_path: Path) -> None:
    svc = PipelineService(tmp_path / "p", clock=lambda: NOW, scheduler=AsyncScheduler())
    stopped = threading.Event()

    def stubborn(layer: str, *, should_stop: Callable[[], bool] = lambda: False, **k: Any) -> int:
        while not should_stop():
            time.sleep(0.005)
        stopped.set()
        return 0

    svc.store.compact = stubborn  # type: ignore[method-assign,assignment]
    svc.scheduler._jobs["compaction"].timeout_s = 0.05
    assert await svc.scheduler.run_now("compaction") == "timeout"
    assert await asyncio.to_thread(stopped.wait, 2)  # il thread vede il flag e termina
    await svc.aclose()


def test_store_maintenance_honours_should_stop(tmp_path: Path) -> None:
    store = ParquetStore(tmp_path / "s", clock=lambda: NOW)
    row = {
        "source_id": "a", "site_id": "s", "t_utc": NOW, "schema_version": "1.0.0",
        "power_w": 1.0, "link_margin_db": None, "sun_az_deg": None, "sun_el_deg": None,
        "earth_az_deg": None, "earth_el_deg": None, "received_utc": NOW, "raw_file_id": "x",
    }  # fmt: skip
    for i in range(4):
        store.write("clean", "a", [{**row, "t_utc": NOW + timedelta(seconds=i)}])
    assert store.compact("clean", min_files=2, should_stop=lambda: True) == 0
    assert len(store.visible_files("clean")) == 4
    assert store.compact("clean", min_files=2) == 1
    old = NOW - timedelta(days=400)
    store.write("clean", "a", [{**row, "t_utc": old}])
    assert store.apply_retention({"clean": 30}, should_stop=lambda: True) == 0
    assert store.apply_retention({"clean": 30}) == 1


async def test_aclose_closes_durable_queue_and_executor(tmp_path: Path) -> None:
    q = DurableQueue(tmp_path / "q.db")
    svc = PipelineService(tmp_path / "p", clock=lambda: NOW, queue=q)
    await svc.scheduler.start()
    await svc.aclose()
    with pytest.raises(RuntimeError):
        await q.put({"a": 1})  # connessione chiusa
    with pytest.raises(RuntimeError):
        svc.executor.submit(lambda: None)  # executor spento
    await svc.aclose()  # idempotente
