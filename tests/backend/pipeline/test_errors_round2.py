# SPDX-License-Identifier: Apache-2.0
"""Fix round 2, N1/N2: classificazione esplicita degli errori e bug interni isolati per bisezione."""

import errno
from pathlib import Path
from typing import Any

import pyarrow as pa
import pytest

from backend.pipeline.pipeline import Pipeline
from backend.pipeline.processors import TelemetryProcessor
from backend.pipeline.service import build_service_from_env

from .test_pipeline import NOW, Env, msg, put_all, rec


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


def with_pipe(env: Env, **kw: Any) -> None:
    env.pipe = Pipeline(
        queue=env.queue,
        processor=env.pipe.processor,
        store=env.store,
        metrics=env.metrics,
        clock=lambda: env.now,
        **kw,
    )


def picky(env: Env, monkeypatch: pytest.MonkeyPatch, exc: Exception) -> None:
    real = env.store.write

    def write(layer: str, source: str, rows: Any) -> Any:
        if layer == "clean" and any(r["power_w"] == 666.0 for r in rows):
            raise exc
        return real(layer, source, rows)

    monkeypatch.setattr(env.store, "write", write)


@pytest.mark.parametrize(
    "exc",
    [
        TypeError("riga strana"),
        pa.ArrowNotImplementedError("tipo non supportato"),
        ValueError("da from_pylist"),
    ],
)
async def test_non_oserror_on_single_row_is_poison_dead_lettered_immediately(
    env: Env, monkeypatch: pytest.MonkeyPatch, exc: Exception
) -> None:
    await put_all(
        env,
        msg(rec("2026-10-13T10:00:00Z", power=1.0)),
        msg(rec("2026-10-13T10:00:01Z", power=666.0)),
        msg(rec("2026-10-13T10:00:02Z", power=3.0)),
    )
    picky(env, monkeypatch, exc)
    r = await env.pipe.drain_once()
    assert r.clean_rows == 2  # i vicini sani sono scritti nello stesso giro
    assert env.pipe.backoff_remaining_s() == 0.0  # un veleno non ferma tutti
    (dl,) = env.queue.dead_letters()
    assert dl["reason"] == f"store_rejected:{type(exc).__name__}"
    assert dl["payload"]["record"]["power_w"] == 666.0
    assert env.queue.stats()["depth"] == 0  # niente retry, niente consumo del budget altrui


async def test_oserror_is_infra_and_does_not_poison_neighbours_in_other_groups(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    await put_all(
        env,
        msg(rec("2026-10-13T10:00:00Z", power=666.0), source="a"),
        msg(rec("2026-10-13T10:00:01Z", power=2.0), source="b"),
    )
    picky(env, monkeypatch, OSError(errno.ENOSPC, "disco pieno"))
    r = await env.pipe.drain_once()
    assert r.clean_rows == 1 and r.requeued == 1  # b scritto, a ritentato
    assert env.queue.dead_letters() == []
    assert env.pipe.backoff_remaining_s() > 0


@pytest.mark.parametrize("code", [errno.ENOSPC, errno.EIO, errno.EMFILE])
async def test_persistent_infra_failure_is_capped_per_message(
    env: Env, monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    with_pipe(env, max_infra_retries=3)
    await put_all(env, msg(rec("2026-10-13T10:00:00Z", power=666.0)))
    picky(env, monkeypatch, OSError(code, "guasto"))
    for i in range(3):
        env.tick(10_000)
        await env.pipe.drain_once()
        assert len(env.queue.dead_letters()) == (1 if i == 2 else 0)
    (dl,) = env.queue.dead_letters()
    assert dl["reason"] == "infra_retry_exhausted"
    snap = env.metrics.snapshot()["sources"]["a"]["counters"]
    assert snap["infra_retry_exhausted"] == 1


def test_max_infra_retries_default_and_env(tmp_path: Path) -> None:
    svc = build_service_from_env({"PIPELINE_DIR": str(tmp_path / "a")})
    assert svc is not None and svc.pipeline._max_infra_retries == 20
    svc2 = build_service_from_env(
        {"PIPELINE_DIR": str(tmp_path / "b"), "PIPELINE_MAX_INFRA_RETRIES": "5"}
    )
    assert svc2 is not None and svc2.pipeline._max_infra_retries == 5
    with pytest.raises(ValueError, match="PIPELINE_MAX_INFRA_RETRIES"):
        build_service_from_env(
            {"PIPELINE_DIR": str(tmp_path / "c"), "PIPELINE_MAX_INFRA_RETRIES": "0"}
        )


# ---- N2: bug interno nel batch ----


async def test_internal_bug_is_bisected_counted_and_delayed(env: Env) -> None:
    class Buggy:
        """Restituisce received_utc come stringa per un messaggio: rompe il batch (non il processor)."""

        def process(self, message: Any) -> Any:
            rows = TelemetryProcessor(now=lambda: NOW).process(message)
            if message["record"]["site_id"] == "bug":
                return [{**rows[0], "received_utc": "non-un-datetime"}]
            return rows

    env.pipe = Pipeline(
        queue=env.queue,
        processor=Buggy(),
        store=env.store,
        metrics=env.metrics,
        clock=lambda: env.now,
    )
    await put_all(
        env,
        msg(rec("2026-10-13T10:00:00Z", site="ok1")),
        msg(rec("2026-10-13T10:00:01Z", site="bug")),
        msg(rec("2026-10-13T10:00:02Z", site="ok2")),
    )
    r = await env.pipe.drain_once()
    assert r.clean_rows == 2  # i sani passano: il batch e' stato bisecato
    assert r.requeued == 1
    # nessun hot loop: il messaggio colpevole ha un ritardo e un tentativo consumato
    assert await env.queue.get(timeout_s=0) is None
    env.tick(10_000)
    again = await env.queue.get(timeout_s=0)
    assert again is not None and again.attempt == 2
    await env.queue.nack(again, "x", requeue=False)
    assert env.store.read("clean").num_rows == 2


async def test_internal_bug_ends_in_dead_letter_with_type_only(env: Env) -> None:
    class Buggy:
        def process(self, message: Any) -> Any:
            rows = TelemetryProcessor(now=lambda: NOW).process(message)
            return [{**rows[0], "received_utc": "SEGRETO-nel-payload"}]

    env.pipe = Pipeline(
        queue=env.queue,
        processor=Buggy(),
        store=env.store,
        metrics=env.metrics,
        clock=lambda: env.now,
    )
    await put_all(env, msg(rec()))
    for _ in range(3):
        await env.pipe.drain_once()
        env.tick(10_000)
    (dl,) = env.queue.dead_letters()
    assert dl["reason"].startswith("max_attempts:internal_error:")
    assert "SEGRETO" not in dl["reason"]


async def test_cancellation_releases_items_without_burning_attempts(env: Env) -> None:
    """Cancellazione reale (task.cancel) durante il processor: percorso CancelledError esatto."""
    import asyncio
    import threading

    entered, gate = threading.Event(), threading.Event()

    class Blocking:
        def process(self, message: Any) -> Any:
            entered.set()
            assert gate.wait(10)
            return TelemetryProcessor(now=lambda: NOW).process(message)

    env.pipe = Pipeline(
        queue=env.queue,
        processor=Blocking(),
        store=env.store,
        metrics=env.metrics,
        clock=lambda: env.now,
    )
    await put_all(env, msg(rec()))
    task = asyncio.create_task(env.pipe.drain_once())
    assert await asyncio.to_thread(entered.wait, 5)
    task.cancel()
    while not env.pipe._batch_stop.is_set():
        await asyncio.sleep(0)
    gate.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert task.cancelled()
    item = await env.queue.get(timeout_s=0)
    assert item is not None and item.attempt == 1  # rilasciato senza consumare il tentativo
    assert env.queue.dead_letters() == []
