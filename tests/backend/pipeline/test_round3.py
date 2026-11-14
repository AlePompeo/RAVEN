# SPDX-License-Identifier: Apache-2.0
"""Fix round 3: quarantena confermata, breaker sui veleni, raw idempotente, cancellazione reale."""

import asyncio
import logging
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from backend.pipeline import pipeline as pipeline_mod
from backend.pipeline import store as store_mod
from backend.pipeline.pipeline import Pipeline
from backend.pipeline.processors import TelemetryProcessor
from backend.pipeline.service import PipelineService, build_service_from_env
from backend.pipeline.store import LockOrderError, ParquetStore, StoreError

from .test_pipeline import Env, msg, put_all, rec

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


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


# ---- (1) quarantena confermata ----


def test_column_mismatch_on_healthy_file_is_not_quarantined(store: ParquetStore) -> None:
    with pytest.raises(StoreError, match="colonn"):
        store.read("clean", columns=["colonna_inesistente"])
    assert not list(store.root.rglob("*.corrupt")) and not store.quarantined
    assert store.read("clean").num_rows == 3


def test_truly_corrupt_file_is_still_quarantined(store: ParquetStore) -> None:
    f = Path(store.visible_files("clean")[0])
    f.write_bytes(b"PAR1 rotto")
    assert store.read("clean").num_rows == 2
    assert f.with_name(f.name + ".corrupt").exists()


def test_hidden_compaction_sources_do_not_count_as_siblings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    s = ParquetStore(tmp_path / "s", clock=lambda: NOW)
    for i in range(3):
        s.write("clean", "a", [crow(i)])
    monkeypatch.setattr(store_mod.os, "unlink", lambda p: (_ for _ in ()).throw(OSError("crash")))
    with pytest.raises(OSError):
        s.compact("clean", min_files=2)
    monkeypatch.undo()
    (merged,) = s.visible_files("clean")  # i 3 sorgenti sono nascosti ma ancora su disco
    Path(merged).write_bytes(b"PAR1 rotto")
    with caplog.at_level(logging.CRITICAL):
        assert (
            s.read("clean").num_rows == 3
        )  # al quarantine i sorgenti tornano visibili: dati salvi
    assert not any(r.levelno == logging.CRITICAL for r in caplog.records)


def test_only_copy_is_reported_critical_under_lock(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    s = ParquetStore(tmp_path / "s", clock=lambda: NOW)
    s.write("clean", "a", [crow(0)])
    f = Path(s.visible_files("clean")[0])
    f.write_bytes(b"PAR1 rotto")
    with caplog.at_level(logging.CRITICAL):
        s.read("clean")
    assert any(r.levelno == logging.CRITICAL for r in caplog.records)
    with s._layer_lock("clean") as free:  # il lock e' stato rilasciato
        assert free


def test_quarantine_inside_held_layer_lock_does_not_deadlock(store: ParquetStore) -> None:
    Path(store.visible_files("clean")[0]).write_bytes(b"PAR1 rotto")
    assert store.compact("clean", min_files=2) == 0  # file corrotto -> quarantena dentro il lock
    assert len(store.quarantined) == 1


# ---- (2) classificazione larga + breaker ----


@pytest.mark.parametrize("exc", [MemoryError(), LockOrderError("ordine")])
async def test_resource_and_lock_errors_are_infra_not_poison(
    env: Env, monkeypatch: pytest.MonkeyPatch, exc: Exception
) -> None:
    await put_all(env, msg(rec()))
    real = env.store.write

    def boom(layer: str, *a: Any) -> Any:
        if layer == "clean":
            raise exc
        return real(layer, *a)

    monkeypatch.setattr(env.store, "write", boom)
    r = await env.pipe.drain_once()
    assert r.requeued == 1 and env.queue.dead_letters() == []
    assert env.pipe.backoff_remaining_s() > 0


def make_breaker_pipe(env: Env, n: int = 3) -> None:
    env.pipe = Pipeline(
        queue=env.queue,
        processor=TelemetryProcessor(now=lambda: NOW),
        store=env.store,
        metrics=env.metrics,
        clock=lambda: env.now,
        poison_breaker=n,
        breaker_backoff_s=30.0,
        rng=lambda: 1.0,
    )


async def test_store_regression_trips_breaker_instead_of_draining_to_dead_letter(
    env: Env, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    make_breaker_pipe(env)
    await put_all(env, *[msg(rec(f"2026-10-13T10:00:0{i}Z")) for i in range(8)])
    real = env.store.write

    def regression(layer: str, *a: Any) -> Any:
        if layer == "clean":
            raise TypeError("regressione dello store")
        return real(layer, *a)

    monkeypatch.setattr(env.store, "write", regression)
    with caplog.at_level(logging.ERROR):
        r = await env.pipe.drain_once()
    assert r.rejected == 3  # solo N veleni, poi il breaker apre
    assert len(env.queue.dead_letters()) == 3
    assert env.queue.stats()["depth"] == 5  # gli altri sono rilasciati, non persi
    st = env.pipe.status()
    assert st["state"] == "breaker_open" and st["breaker_opened"] == 1
    assert any("ALLARME" in r.message and "breaker" in r.message.lower() for r in caplog.records)
    assert (await env.pipe.drain_once()).processed == 0  # in pausa
    # mezza apertura con store ancora rotto: nessun nuovo dead-letter, riapre piu' a lungo
    env.tick(31)
    assert env.pipe.status()["state"] == "half_open"
    await env.pipe.drain_once()
    assert len(env.queue.dead_letters()) == 3
    assert env.pipe.status()["state"] == "breaker_open" and env.pipe.status()["breaker_opened"] == 2
    # store riparato: sonda, poi flusso normale
    monkeypatch.undo()
    env.tick(1000)
    await env.pipe.drain_once()
    assert env.pipe.status()["state"] == "ok"
    for _ in range(3):
        env.tick(100)
        await env.pipe.drain_once()
    assert env.store.read("clean").num_rows == 5
    assert len(env.queue.dead_letters()) == 3


async def test_healthy_neighbours_prove_the_poison_is_real(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_breaker_pipe(env, n=2)
    await put_all(
        env,
        *[msg(rec(f"2026-10-13T10:00:0{i}Z", power=666.0 if i % 2 else 1.0)) for i in range(8)],
    )
    real = env.store.write

    def picky(layer: str, source: str, rows: Any) -> Any:
        if layer == "clean" and any(r["power_w"] == 666.0 for r in rows):
            raise TypeError("riga strana")
        return real(layer, source, rows)

    monkeypatch.setattr(env.store, "write", picky)
    await env.pipe.drain_once()
    assert env.pipe.status()["state"] == "ok"  # i sani passano: il breaker non scatta
    assert len(env.queue.dead_letters()) == 4 and env.store.read("clean").num_rows == 4


def test_poison_breaker_env(tmp_path: Path) -> None:
    svc = build_service_from_env({"PIPELINE_DIR": str(tmp_path / "a")})
    assert svc is not None and svc.pipeline.status()["poison_breaker"] == 50
    svc2 = build_service_from_env(
        {"PIPELINE_DIR": str(tmp_path / "b"), "PIPELINE_POISON_BREAKER": "7"}
    )
    assert svc2 is not None and svc2.pipeline.status()["poison_breaker"] == 7
    with pytest.raises(ValueError, match="PIPELINE_POISON_BREAKER"):
        build_service_from_env(
            {"PIPELINE_DIR": str(tmp_path / "c"), "PIPELINE_POISON_BREAKER": "x"}
        )


async def test_service_snapshot_exposes_drain_status(tmp_path: Path) -> None:
    svc = PipelineService(tmp_path / "p", clock=lambda: NOW)
    assert svc.snapshot()["drain"]["state"] == "ok"
    await svc.aclose()


# ---- (3) raw idempotente e metriche esatte nella bisezione ----


async def test_bisection_does_not_duplicate_raw_or_double_count_metrics(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    await put_all(
        env,
        *[msg(rec(f"2026-10-13T10:00:0{i}Z", site="bug" if i == 2 else "ok")) for i in range(5)],
    )
    real = pipeline_mod.check_clean_rows

    def buggy(rows: Any, now: Any) -> Any:
        if any(r["site_id"] == "bug" for r in rows):
            raise ValueError("bug dopo la scrittura")
        return real(rows, now)

    monkeypatch.setattr(pipeline_mod, "check_clean_rows", buggy)
    for _ in range(3):
        await env.pipe.drain_once()
        env.tick(1000)
    assert env.store.read("raw").num_rows == 5
    assert env.store.read("clean").num_rows == 5
    layers = env.metrics.snapshot()["layers"]
    assert (layers["raw"]["in"], layers["raw"]["out"]) == (5, 5)
    assert (layers["clean"]["in"], layers["clean"]["out"], layers["clean"]["dropped"]) == (5, 5, 0)
    assert env.queue.stats()["depth"] == 0 and env.queue.dead_letters() == []


# ---- (4) cancellazione reale ----


async def test_real_cancellation_stops_the_thread_and_redelivers_exactly_once(env: Env) -> None:
    entered, gate = threading.Event(), threading.Event()

    class Slow:
        def process(self, message: Any) -> Any:
            entered.set()
            assert gate.wait(10)
            return TelemetryProcessor(now=lambda: NOW).process(message)

    env.pipe = Pipeline(
        queue=env.queue,
        processor=Slow(),
        store=env.store,
        metrics=env.metrics,
        clock=lambda: env.now,
    )
    await put_all(env, msg(rec()))
    task = asyncio.create_task(env.pipe.drain_once())
    assert await asyncio.to_thread(entered.wait, 5)
    task.cancel()
    for _ in range(1000):  # il flag cooperativo viene alzato dal gestore della cancellazione
        if env.pipe._batch_stop.is_set():
            break
        await asyncio.sleep(0)
    assert env.pipe._batch_stop.is_set()
    gate.set()  # il thread riparte DOPO la cancellazione
    with pytest.raises(asyncio.CancelledError):
        await task
    assert env.store.read("raw").num_rows == 0  # nessuna scrittura dopo la cancellazione
    assert env.store.read("clean").num_rows == 0
    assert env.queue.stats()["ready"] == 1  # rilasciato esattamente una volta
    item = await env.queue.get(timeout_s=0)
    assert item is not None and item.attempt == 1  # tentativo non consumato
    await env.queue.nack(item, "test", count_attempt=False)
    env.pipe = Pipeline(
        queue=env.queue,
        processor=TelemetryProcessor(now=lambda: NOW),
        store=env.store,
        metrics=env.metrics,
        clock=lambda: env.now,
    )
    r = await env.pipe.drain_once()
    assert r.clean_rows == 1
    assert env.store.read("raw").num_rows == 1 and env.store.read("clean").num_rows == 1
    assert env.queue.stats()["depth"] == 0
