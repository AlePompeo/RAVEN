# SPDX-License-Identifier: Apache-2.0
"""Fix round 4: liveness del breaker, raw/clean idempotenti a meta' riga, doppia cancellazione."""

import asyncio
import logging
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from backend.pipeline.pipeline import BatchInterrupted, Pipeline
from backend.pipeline.processors import TelemetryProcessor
from backend.pipeline.reserved import CANARY_SOURCE
from backend.pipeline.service import build_service_from_env
from backend.pipeline.store import ParquetStore

from .test_pipeline import Env, msg, put_all, rec
from .test_round3 import crow

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


def make_pipe(env: Env, **kw: Any) -> None:
    env.pipe = Pipeline(
        queue=env.queue,
        processor=TelemetryProcessor(now=lambda: NOW),
        store=env.store,
        metrics=env.metrics,
        clock=lambda: env.now,
        rng=lambda: 1.0,
        **kw,
    )


def t(i: int) -> str:
    return (datetime(2026, 10, 13, 10, 0, tzinfo=UTC) + timedelta(seconds=i)).isoformat()


# ---- (1) liveness del breaker ----


async def test_poison_at_queue_head_does_not_wedge_healthy_messages(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_pipe(env, poison_breaker=5, breaker_backoff_s=30.0, batch_size=10)
    await put_all(
        env,
        *[msg(rec(t(i), power=666.0)) for i in range(80)],  # 80 veleni veri in testa
        *[msg(rec(t(1000 + i), power=1.0)) for i in range(20)],  # poi 20 sani
    )
    real = env.store.write

    def picky(layer: str, source: str, rows: Any) -> Any:
        if layer == "clean" and any(r["power_w"] == 666.0 for r in rows):
            raise TypeError("riga strana")
        return real(layer, source, rows)

    monkeypatch.setattr(env.store, "write", picky)
    previous = 0
    for _ in range(60):
        await env.pipe.drain_once()
        now_dead = len(env.queue.dead_letters())
        assert now_dead - previous <= 5  # velocita' di dead-letter limitata dal breaker
        previous = now_dead
        env.tick(1000)
        if env.queue.stats()["depth"] == 0:
            break
    assert len(env.queue.dead_letters()) == 80
    assert env.store.read("clean").num_rows == 20
    assert env.queue.stats()["depth"] == 0


async def test_globally_broken_store_cannot_drain_the_queue(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_pipe(env, poison_breaker=3, breaker_backoff_s=30.0)
    await put_all(env, *[msg(rec(t(i))) for i in range(20)])

    def broken(layer: str, source: str, rows: Any) -> Any:
        raise TypeError("tutto rifiutato")  # anche il canarino

    monkeypatch.setattr(env.store, "write", broken)
    for _ in range(12):
        await env.pipe.drain_once()
        env.tick(2000)
    assert len(env.queue.dead_letters()) == 3  # al massimo N in tutto, mai lo stream intero
    assert env.queue.stats()["depth"] == 17
    assert env.pipe.status()["breaker_opened"] >= 2


async def test_canary_is_invisible_and_cleaned_up(env: Env) -> None:
    await put_all(env, msg(rec()))
    await env.pipe.drain_once()
    assert env.pipe._canary_ok()
    assert not list(env.store.root.rglob(f"source={CANARY_SOURCE}"))
    assert CANARY_SOURCE not in {Path(f).parts[-3] for f in env.store.visible_files("clean")}
    assert env.store.read("clean").num_rows == 1


async def test_reserved_canary_source_id_is_rejected_by_processor() -> None:
    from backend.pipeline.processors import RecordRejected

    with pytest.raises(RecordRejected) as e:
        TelemetryProcessor(now=lambda: NOW).process(
            {"source_id": CANARY_SOURCE, "record": rec(), "received_utc": t(0)}
        )
    assert e.value.reason == "invalid_source_id"


# ---- (2) scritture parziali riga per riga ----


def interrupt_after(env: Env, monkeypatch: pytest.MonkeyPatch, layer: str, k: int) -> None:
    real = env.store.write
    state = {"singles": 0}

    def write(lay: str, source: str, rows: Any) -> Any:
        if lay == layer and len(rows) > 1:
            raise ValueError("gruppo rifiutato: si va riga per riga")
        out = real(lay, source, rows)
        if lay == layer:
            state["singles"] += 1
            if state["singles"] == k:
                env.pipe._batch_stop.set()
        return out

    monkeypatch.setattr(env.store, "write", write)


@pytest.mark.parametrize("layer", ["raw", "clean"])
async def test_interrupt_mid_row_by_row_redelivery_writes_only_the_rest(
    env: Env, monkeypatch: pytest.MonkeyPatch, layer: str
) -> None:
    n, k = 5, 2
    await put_all(env, *[msg(rec(t(i))) for i in range(n)])
    interrupt_after(env, monkeypatch, layer, k)
    with pytest.raises(BatchInterrupted):
        await env.pipe.drain_once()
    assert env.store.read(layer).num_rows == k  # scritte e durevoli prima dell'interruzione
    monkeypatch.undo()
    assert env.queue.stats()["ready"] == n  # tutti rilasciati
    for _ in range(3):
        await env.pipe.drain_once()
    assert env.store.read("raw").num_rows == n  # nessuna riga raw duplicata
    assert env.store.read("clean").num_rows == n  # nessuna riga clean duplicata
    snap = env.metrics.snapshot()["layers"]
    assert (snap["raw"]["in"], snap["raw"]["out"]) == (n, n)
    assert (snap["clean"]["in"], snap["clean"]["out"]) == (n, n)


# ---- (3) doppia cancellazione ----


async def test_second_cancel_waits_for_the_thread_before_releasing(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    entered, gate = threading.Event(), threading.Event()
    events: list[str] = []

    class Slow:
        def process(self, message: Any) -> Any:
            entered.set()
            assert gate.wait(10)
            return TelemetryProcessor(now=lambda: NOW).process(message)

    make_pipe(env)
    env.pipe.processor = Slow()
    orig = env.pipe._process_batch_safe

    def tracked(items: Any, stop: Any) -> Any:
        try:
            return orig(items, stop)
        finally:
            events.append("thread_done")

    monkeypatch.setattr(env.pipe, "_process_batch_safe", tracked)
    real_nack = env.queue.nack

    async def nack(*a: Any, **k: Any) -> Any:
        events.append("released")
        return await real_nack(*a, **k)

    monkeypatch.setattr(env.queue, "nack", nack)
    real_write = env.store.write

    def write(*a: Any) -> Any:
        events.append("write")
        return real_write(*a)

    monkeypatch.setattr(env.store, "write", write)
    await put_all(env, msg(rec()))
    task = asyncio.create_task(env.pipe.drain_once())
    assert await asyncio.to_thread(entered.wait, 5)
    task.cancel()
    while not env.pipe._batch_stop.is_set():
        await asyncio.sleep(0)
    task.cancel()  # seconda cancellazione mentre si attende il thread
    for _ in range(20):
        await asyncio.sleep(0)
    assert events == []  # nessun rilascio finche' il thread gira
    assert env.queue.stats()["inflight"] == 1
    gate.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert events == ["thread_done", "released"]  # thread concluso PRIMA del rilascio
    assert "write" not in events  # e nessuna scrittura tardiva
    assert env.queue.stats()["ready"] == 1


async def test_bounded_shutdown_wait_alarms_and_releases(
    env: Env, caplog: pytest.LogCaptureFixture
) -> None:
    gate, entered = threading.Event(), threading.Event()

    class Stuck:
        def process(self, message: Any) -> Any:
            entered.set()
            assert gate.wait(10)
            return TelemetryProcessor(now=lambda: NOW).process(message)

    make_pipe(env, shutdown_wait_s=0.2)
    env.pipe.processor = Stuck()
    await put_all(env, msg(rec()))
    task = asyncio.create_task(env.pipe.drain_once())
    assert await asyncio.to_thread(entered.wait, 5)
    with caplog.at_level(logging.ERROR):
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert any("ALLARME" in r.message for r in caplog.records)
    assert env.queue.stats()["ready"] == 1
    gate.set()  # il thread tardivo termina senza scrivere (flag di stop gia' alzato)
    await asyncio.sleep(0.05)
    assert env.store.read("raw").num_rows == 0


def test_shutdown_wait_env(tmp_path: Path) -> None:
    svc = build_service_from_env({"PIPELINE_DIR": str(tmp_path / "a")})
    assert svc is not None and svc.pipeline._shutdown_wait_s == 30.0
    svc2 = build_service_from_env(
        {"PIPELINE_DIR": str(tmp_path / "b"), "PIPELINE_SHUTDOWN_WAIT_S": "2.5"}
    )
    assert svc2 is not None and svc2.pipeline._shutdown_wait_s == 2.5
    for bad in ("0", "-1", "abc", "nan"):
        with pytest.raises(ValueError, match="PIPELINE_SHUTDOWN_WAIT_S"):
            build_service_from_env(
                {"PIPELINE_DIR": str(tmp_path / "c"), "PIPELINE_SHUTDOWN_WAIT_S": bad}
            )


# ---- minor: CRITICAL positivo per l'ultima copia ----


def test_critical_is_logged_when_last_visible_copy_is_quarantined(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    s = ParquetStore(tmp_path / "s", clock=lambda: NOW)
    for i in range(3):
        s.write("clean", "a", [crow(i)])
    for name in s.visible_files("clean"):
        Path(name).write_bytes(b"PAR1 rotto")
    with caplog.at_level(logging.CRITICAL):
        assert s.read("clean").num_rows == 0
    assert any(r.levelno == logging.CRITICAL for r in caplog.records)
