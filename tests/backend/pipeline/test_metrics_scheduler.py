# SPDX-License-Identifier: Apache-2.0
import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from backend.core.ports import Scheduler
from backend.pipeline.metrics import (
    PipelineMetrics,
    check_clean_rows,
    check_curated_rows,
    check_raw_rows,
)
from backend.pipeline.scheduler import AsyncScheduler, SchedulerConfigError

T0 = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> datetime:
        return self.now

    def advance(self, s: float) -> None:
        self.now += timedelta(seconds=s)


# ---------------- metriche e stato stale ----------------


def test_layer_counters_per_source_and_total() -> None:
    c = FakeClock()
    m = PipelineMetrics(c)
    m.add("clean", "a", in_=5, out=3, dropped=1, dead_letter=1)
    m.add("clean", "b", in_=2, out=2)
    snap = m.snapshot()
    assert snap["layers"]["clean"] == {"in": 7, "out": 5, "dropped": 1, "dead_letter": 1}
    assert snap["sources"]["a"]["layers"]["clean"]["dead_letter"] == 1
    assert snap["layers"]["raw"] == {"in": 0, "out": 0, "dropped": 0, "dead_letter": 0}


def test_unknown_layer_rejected() -> None:
    with pytest.raises(ValueError):
        PipelineMetrics(FakeClock()).add("gold", "a", in_=1)


def test_source_becomes_stale_after_threshold_and_recovers() -> None:
    c = FakeClock()
    m = PipelineMetrics(c, stale_after_s=60)
    m.seen("a")
    c.advance(59)
    assert m.snapshot()["sources"]["a"]["status"] == "ok"
    c.advance(2)
    s = m.snapshot()["sources"]["a"]
    assert s["status"] == "stale" and s["lag_s"] == pytest.approx(61)
    m.seen("a")
    assert m.snapshot()["sources"]["a"]["status"] == "ok"


def test_registered_but_silent_source_is_no_data_then_stale() -> None:
    c = FakeClock()
    m = PipelineMetrics(c, stale_after_s=60)
    m.register_source("quiet")
    assert m.snapshot()["sources"]["quiet"]["status"] == "no_data"
    assert m.snapshot()["sources"]["quiet"]["last_seen_utc"] is None
    c.advance(61)
    assert m.snapshot()["sources"]["quiet"]["status"] == "stale"


def test_per_source_threshold_and_stale_list() -> None:
    c = FakeClock()
    m = PipelineMetrics(c, stale_after_s=600)
    m.register_source("fast", stale_after_s=5)
    m.seen("fast")
    m.seen("slow")
    c.advance(10)
    snap = m.snapshot()
    assert snap["sources"]["fast"]["status"] == "stale"
    assert snap["sources"]["slow"]["status"] == "ok"
    assert snap["stale_sources"] == ["fast"]


def test_data_lag_uses_latest_data_time() -> None:
    c = FakeClock()
    m = PipelineMetrics(c)
    m.seen("a", data_t=T0 - timedelta(seconds=30))
    m.seen("a", data_t=T0 - timedelta(seconds=90))  # dato vecchio: non fa arretrare
    c.advance(10)
    assert m.snapshot()["sources"]["a"]["data_lag_s"] == pytest.approx(40)


def test_invalid_threshold_rejected() -> None:
    for bad in (0, -1, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            PipelineMetrics(FakeClock(), stale_after_s=bad)


def test_snapshot_is_json_serialisable_and_finite() -> None:
    import json

    c = FakeClock()
    m = PipelineMetrics(c)
    m.seen("a", data_t=T0)
    m.register_source("b")
    m.quality("clean", "finite_values", 3, 1)
    json.dumps(m.snapshot(), allow_nan=False)


def test_quality_checks_per_layer() -> None:
    good = {
        "source_id": "a", "site_id": "s", "t_utc": T0, "power_w": 1.0, "received_utc": T0,
        "link_margin_db": None,
    }  # fmt: skip
    future = {**good, "t_utc": T0 + timedelta(days=1)}
    res = check_clean_rows([good, future], T0)
    assert res["not_in_future"] == (1, 1) and res["finite_values"] == (2, 0)
    assert check_raw_rows([{"payload_json": "{}"}, {"payload_json": ""}]) == {
        "non_empty_payload": (1, 1)
    }
    cur = {"n": 2, "power_w_mean": 2.0, "power_w_min": 1.0, "power_w_max": 3.0}
    bad = {"n": 0, "power_w_mean": 5.0, "power_w_min": 1.0, "power_w_max": 3.0}
    res2 = check_curated_rows([cur, bad])
    assert res2["n_positive"] == (1, 1) and res2["min_le_mean_le_max"] == (1, 1)


# ---------------- scheduler ----------------


class Clk:
    def __init__(self) -> None:
        self.t = 100.0

    def __call__(self) -> float:
        return self.t


def test_scheduler_conforms_to_port() -> None:
    assert isinstance(AsyncScheduler(clock=Clk()), Scheduler)


def test_add_job_validation() -> None:
    s = AsyncScheduler(clock=Clk())

    async def job() -> None: ...

    for kw in ({"interval_s": 0, "timeout_s": 1}, {"interval_s": 1, "timeout_s": 0},
               {"interval_s": float("nan"), "timeout_s": 1}):  # fmt: skip
        with pytest.raises(SchedulerConfigError):
            s.add_job("j", job, **kw)
    with pytest.raises(SchedulerConfigError):
        s.add_job("Bad Name", job, interval_s=1, timeout_s=1)
    s.add_job("j", job, interval_s=1, timeout_s=1)
    with pytest.raises(SchedulerConfigError):
        s.add_job("j", job, interval_s=1, timeout_s=1)
    with pytest.raises(KeyError):
        asyncio.run(s.run_now("missing"))


async def test_run_now_ok_and_status_metrics() -> None:
    clk = Clk()
    s = AsyncScheduler(clock=clk)
    calls: list[int] = []

    async def job() -> None:
        calls.append(1)
        clk.t += 2.5

    s.add_job("ingest", job, interval_s=10, timeout_s=5)
    assert await s.run_now("ingest") == "ok"
    st = s.status()["ingest"]
    assert (st["runs"], st["ok"], st["failed"]) == (1, 1, 0)
    assert st["last_status"] == "ok" and st["last_duration_s"] == pytest.approx(2.5)
    assert st["running"] is False and calls == [1]


async def test_failure_is_isolated_and_recorded() -> None:
    s = AsyncScheduler(clock=Clk())
    ran: list[str] = []

    async def bad() -> None:
        raise RuntimeError("secret detail /etc/x")

    async def good() -> None:
        ran.append("good")

    s.add_job("bad", bad, interval_s=1, timeout_s=1)
    s.add_job("good", good, interval_s=1, timeout_s=1)
    tasks = s.run_due()
    assert sorted(await asyncio.gather(*tasks)) == ["failed", "ok"]
    assert ran == ["good"]
    st = s.status()["bad"]
    assert st["failed"] == 1 and st["last_error"] == "RuntimeError"
    assert "secret" not in str(s.status())
    assert await s.run_now("bad") == "failed"  # il job resta schedulabile


async def test_timeout_cancels_job() -> None:
    s = AsyncScheduler(clock=Clk())
    cancelled = asyncio.Event()

    async def hang() -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    s.add_job("hang", hang, interval_s=1, timeout_s=0.02)
    assert await s.run_now("hang") == "timeout"
    assert cancelled.is_set()
    st = s.status()["hang"]
    assert st["timeouts"] == 1 and st["running"] is False
    assert await s.run_now("hang") == "timeout"  # non resta bloccato


async def test_no_overlap_second_run_skipped() -> None:
    s = AsyncScheduler(clock=Clk())
    gate, started = asyncio.Event(), asyncio.Event()

    async def slow() -> None:
        started.set()
        await gate.wait()

    s.add_job("slow", slow, interval_s=1, timeout_s=30)
    first = asyncio.create_task(s.run_now("slow"))
    await started.wait()
    assert s.status()["slow"]["running"] is True
    assert await s.run_now("slow") == "skipped"
    assert s.run_due() == []  # anche lo scheduler periodico salta
    assert s.status()["slow"]["skipped"] == 2
    gate.set()
    assert await first == "ok"
    assert await s.run_now("slow") == "ok"


async def test_run_due_follows_injected_clock() -> None:
    clk = Clk()
    s = AsyncScheduler(clock=clk)
    n: list[int] = []

    async def job() -> None:
        n.append(1)

    s.add_job("j", job, interval_s=60, timeout_s=5)
    await asyncio.gather(*s.run_due())  # primo giro subito
    assert len(n) == 1
    assert s.run_due() == []  # non ancora scaduto
    clk.t += 59
    assert s.run_due() == []
    clk.t += 2
    await asyncio.gather(*s.run_due())
    assert len(n) == 2


async def test_start_stop_loop_runs_jobs_and_cancels_cleanly() -> None:
    s = AsyncScheduler(clock=Clk(), tick_s=0.005)
    ran = asyncio.Event()
    cancelled = asyncio.Event()

    async def job() -> None:
        ran.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    s.add_job("j", job, interval_s=1, timeout_s=30)
    await s.start()
    await s.start()  # idempotente
    await asyncio.wait_for(ran.wait(), 2)
    await s.stop()
    assert cancelled.is_set()
    await s.stop()


def test_status_values_are_plain_json_types() -> None:
    import json

    s = AsyncScheduler(clock=Clk())

    async def job() -> None: ...

    s.add_job("j", job, interval_s=1, timeout_s=1)
    st: Any = s.status()
    json.dumps(st, allow_nan=False)
