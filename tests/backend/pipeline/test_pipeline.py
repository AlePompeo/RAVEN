# SPDX-License-Identifier: Apache-2.0
import json
import math
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from backend.pipeline.metrics import PipelineMetrics
from backend.pipeline.pipeline import Pipeline, ingest_once
from backend.pipeline.processors import Deduplicator, TelemetryProcessor
from backend.pipeline.queues import DurableQueue, MemoryQueue
from backend.pipeline.store import ParquetStore

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)


def rec(
    t: str = "2026-10-13T10:00:00Z", site: str = "s1", power: Any = 100.0, **kw: Any
) -> dict[str, Any]:
    return {"schema_version": "1.0.0", "t_utc": t, "site_id": site, "power_w": power, **kw}


def msg(record: dict[str, Any], source: str = "a") -> dict[str, Any]:
    return {"source_id": source, "received_utc": "2026-10-13T11:00:00Z", "record": record}


class Env:
    def __init__(self, tmp_path: Path, queue: Any | None = None) -> None:
        self.now = NOW
        self.qt = 1000.0
        self.store = ParquetStore(tmp_path / "store", clock=lambda: NOW)
        self.queue = queue or MemoryQueue(max_attempts=2, clock=lambda: self.qt)
        self.metrics = PipelineMetrics(lambda: NOW)
        self.pipe = self.make_pipeline()

    def tick(self, seconds: float) -> None:
        """Avanza insieme l'orologio della pipeline (backoff) e quello della coda (ritardi)."""
        self.now += timedelta(seconds=seconds)
        self.qt += seconds

    def make_pipeline(self) -> Pipeline:
        return Pipeline(
            queue=self.queue,
            processor=TelemetryProcessor(now=lambda: NOW),
            store=self.store,
            metrics=self.metrics,
            clock=lambda: self.now,
        )


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


async def put_all(env: Env, *messages: Mapping[str, Any]) -> None:
    for m in messages:
        assert await env.queue.put(m)


async def test_valid_records_flow_to_raw_and_clean_and_are_acked(env: Env) -> None:
    await put_all(env, msg(rec()), msg(rec("2026-10-13T10:00:01Z")), msg(rec(site="s2")))
    r = await env.pipe.drain_once()
    assert (r.processed, r.clean_rows, r.duplicates, r.rejected) == (3, 3, 0, 0)
    assert env.store.read("clean").num_rows == 3
    assert env.store.read("raw").num_rows == 3
    assert env.queue.stats()["depth"] == 0 and env.queue.stats()["acked"] == 3
    layers = env.metrics.snapshot()["layers"]
    assert layers["clean"] == {"in": 3, "out": 3, "dropped": 0, "dead_letter": 0}
    assert layers["raw"]["out"] == 3
    q = env.metrics.snapshot()["quality"]
    assert q["clean"]["finite_values"] == {"passed": 3, "failed": 0}


async def test_same_record_twice_gives_one_clean_row(env: Env) -> None:
    await put_all(env, msg(rec()), msg(rec()))  # nello stesso batch
    r = await env.pipe.drain_once()
    assert r.clean_rows == 1 and r.duplicates == 1
    await put_all(env, msg(rec()))  # in un batch successivo
    r2 = await env.pipe.drain_once()
    assert r2.clean_rows == 0 and r2.duplicates == 1
    assert env.store.read("clean").num_rows == 1
    assert (
        env.store.read("raw").num_rows == 3
    )  # raw e' il registro immutabile di cio' che e' arrivato
    c = env.metrics.snapshot()["layers"]["clean"]
    assert c["dropped"] == 2 and c["out"] == 1


async def test_dedup_survives_restart_via_store(env: Env) -> None:
    await put_all(env, msg(rec()))
    await env.pipe.drain_once()
    fresh = env.make_pipeline()  # nuovo processo: nessuno stato in memoria
    await put_all(env, msg(rec()), msg(rec("2026-10-13T10:00:09Z")))
    r = await fresh.drain_once()
    assert r.clean_rows == 1 and r.duplicates == 1
    assert env.store.read("clean").num_rows == 2


async def test_dedup_key_includes_source(env: Env) -> None:
    await put_all(env, msg(rec(), "a"), msg(rec(), "b"))
    await env.pipe.drain_once()
    assert env.store.read("clean").num_rows == 2


async def test_invalid_records_go_to_dead_letter_with_reason(env: Env) -> None:
    bad = [
        msg(rec(power="inf")),
        msg(rec(site="")),
        msg(rec(t="not-a-time")),
        msg(rec(extra=1)),
        {"source_id": "../x", "record": rec()},
    ]
    await put_all(env, *bad, msg(rec()))
    r = await env.pipe.drain_once()
    assert r.rejected == 5 and r.clean_rows == 1
    codes = sorted(d["reason"] for d in env.queue.dead_letters())
    assert codes == sorted(
        [
            "non_finite_value:power_w",
            "schema_violation:site_id",
            "invalid_timestamp:t_utc",
            "unknown_field:extra",
            "invalid_source_id",
        ]
    )
    assert env.store.read("clean").num_rows == 1
    assert env.metrics.snapshot()["layers"]["clean"]["dead_letter"] == 5
    assert env.queue.stats()["depth"] == 0  # i rifiutati non vengono ritentati


async def test_nan_and_inf_never_reach_clean(env: Env) -> None:
    for p in (math.nan, math.inf, -math.inf):
        # un produttore corretto non puo' mettere NaN in coda (JSON); arriva come stringa
        await env.queue.put(msg(rec(power=str(p))))
    r = await env.pipe.drain_once()
    assert r.rejected == 3 and r.clean_rows == 0
    assert {d["reason"] for d in env.queue.dead_letters()} == {"non_finite_value:power_w"}


async def test_out_of_order_arrival_accepted_sorted_and_partitioned_by_data_date(env: Env) -> None:
    await put_all(
        env,
        msg(rec("2026-10-13T10:00:10Z")),
        msg(rec("2026-10-13T10:00:05Z")),  # in ritardo, stessa partizione
        msg(rec("2026-10-12T23:59:59Z")),  # giorno precedente: altra partizione
    )
    r = await env.pipe.drain_once()
    assert r.clean_rows == 3
    snap = env.metrics.snapshot()
    assert snap["sources"]["a"]["counters"]["out_of_order"] == 1
    day = env.store.read("clean", date="2026-10-13")
    ts = day.column("t_utc").to_pylist()
    assert ts == sorted(ts) and len(ts) == 2
    assert env.store.read("clean", date="2026-10-12").num_rows == 1


async def test_store_failure_requeues_and_retry_is_not_a_false_duplicate(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    await put_all(env, msg(rec()))
    real_write = env.store.write

    def broken(*a: Any, **k: Any) -> Any:
        if a[0] == "clean":
            raise OSError("disco pieno")
        return real_write(*a, **k)

    monkeypatch.setattr(env.store, "write", broken)
    r = await env.pipe.drain_once()
    assert r.requeued == 1 and r.clean_rows == 0
    assert env.queue.stats()["depth"] == 1  # niente perdita: ancora in coda
    monkeypatch.setattr(env.store, "write", real_write)
    env.tick(120)  # backoff scaduto
    r2 = await env.pipe.drain_once()
    assert r2.clean_rows == 1 and r2.duplicates == 0
    assert env.store.read("clean").num_rows == 1
    assert env.queue.dead_letters() == []


async def test_persistent_infra_failure_never_dead_letters_healthy_messages(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    await put_all(env, msg(rec()))
    monkeypatch.setattr(env.store, "write", lambda *a, **k: (_ for _ in ()).throw(OSError("x")))
    for _ in range(4):
        await env.pipe.drain_once()
        env.tick(120)
    assert env.queue.dead_letters() == []  # un guasto di infrastruttura non e' colpa del messaggio
    assert env.queue.stats()["depth"] == 1
    assert env.metrics.snapshot()["sources"]["a"]["counters"]["store_errors"] >= 1


async def test_processor_bug_is_isolated_per_message(env: Env) -> None:
    class Flaky:
        def process(self, message: Mapping[str, Any]) -> Any:
            if message["record"]["site_id"] == "boom":
                raise RuntimeError("bug")
            return TelemetryProcessor(now=lambda: NOW).process(message)

    env.pipe = Pipeline(
        queue=env.queue, processor=Flaky(), store=env.store, metrics=env.metrics, clock=lambda: NOW
    )
    await put_all(env, msg(rec(site="boom")), msg(rec()))
    r = await env.pipe.drain_once()
    assert r.clean_rows == 1 and r.requeued == 1


async def test_curate_builds_hourly_aggregates_with_lineage(env: Env) -> None:
    await put_all(
        env,
        msg(rec("2026-10-13T10:00:00Z", power=10.0)),
        msg(rec("2026-10-13T10:30:00Z", power=30.0)),
    )
    await env.pipe.drain_once()
    assert await env.pipe.curate_once() == 1
    (row,) = env.store.read("curated").to_pylist()
    assert row["n"] == 2 and row["power_w_mean"] == 20.0
    raw_ids = {Path(f).stem for f in env.store.visible_files("raw")}
    assert row["raw_file_ids"] and set(row["raw_file_ids"]) <= raw_ids
    assert await env.pipe.curate_once() == 0  # niente di nuovo
    cur = env.metrics.snapshot()["layers"]["curated"]
    assert cur["out"] == 1 and cur["in"] == 2
    assert env.metrics.snapshot()["quality"]["curated"]["n_positive"]["failed"] == 0


async def test_last_seen_updated_so_silent_source_goes_stale(env: Env) -> None:
    clock = [NOW]
    env.metrics = PipelineMetrics(lambda: clock[0], stale_after_s=60)
    env.pipe = env.make_pipeline()
    await put_all(env, msg(rec()))
    await env.pipe.drain_once()
    assert env.metrics.snapshot()["sources"]["a"]["status"] == "ok"
    clock[0] = NOW + timedelta(seconds=61)
    assert env.metrics.snapshot()["sources"]["a"]["status"] == "stale"


async def test_batch_size_limits_one_drain(env: Env) -> None:
    env.pipe = Pipeline(
        queue=env.queue, processor=TelemetryProcessor(), store=env.store, metrics=env.metrics,
        clock=lambda: NOW, batch_size=2,
    )  # fmt: skip
    await put_all(env, *[msg(rec(f"2026-10-13T10:00:0{i}Z")) for i in range(5)])
    assert (await env.pipe.drain_once()).processed == 2
    assert env.queue.stats()["depth"] == 3


async def test_pipeline_over_durable_queue_survives_crash_between_get_and_ack(
    tmp_path: Path,
) -> None:
    q = DurableQueue(tmp_path / "q.db", visibility_timeout_s=10.0, clock=lambda: NOW.timestamp())
    env = Env(tmp_path, queue=q)
    await q.put(msg(rec()))
    taken = await q.get(timeout_s=0)  # il consumatore muore dopo aver scritto ma prima di ack
    assert taken is not None
    env.pipe = env.make_pipeline()
    r0 = await env.pipe.drain_once()
    assert r0.processed == 0  # lease ancora valido
    q.close()
    q2 = DurableQueue(
        tmp_path / "q.db", visibility_timeout_s=10.0, clock=lambda: NOW.timestamp() + 60
    )
    env2 = Env(tmp_path, queue=q2)
    r1 = await env2.pipe.drain_once()
    assert r1.clean_rows == 1
    # secondo "crash": il record viene riconsegnato e scritto di nuovo => un solo clean
    await q2.put(msg(rec()))
    r2 = await env2.pipe.drain_once()
    assert r2.duplicates == 1 and env2.store.read("clean").num_rows == 1
    q2.close()


# ---- ingest ----


class ListSource:
    source_id = "src"

    def __init__(self, records: list[Mapping[str, Any]]) -> None:
        self.records = records

    async def read(self) -> Any:
        for r in self.records:
            yield r


async def test_ingest_once_enqueues_envelopes_and_counts_backpressure(env: Env) -> None:
    q = MemoryQueue(capacity=2, policy="drop_with_counter")
    n = await ingest_once(
        ListSource([rec(), rec("2026-10-13T10:00:01Z"), rec("2026-10-13T10:00:02Z")]),
        q,
        env.metrics,
        lambda: NOW,
    )
    assert n == 2
    item = await q.get(timeout_s=0)
    assert item is not None
    assert item.payload["source_id"] == "src" and item.payload["received_utc"].startswith(
        "2026-10-13T12:00:00"
    )
    snap = env.metrics.snapshot()["sources"]["src"]
    assert snap["counters"]["ingest_dropped"] == 1 and snap["status"] == "ok"


async def test_ingest_sanitises_non_finite_floats_for_dead_letter(env: Env) -> None:
    await ingest_once(
        ListSource([rec(power=math.nan), rec("2026-10-13T10:00:01Z", power=math.inf)]),
        env.queue,
        env.metrics,
        lambda: NOW,
    )
    r = await env.pipe.drain_once()
    assert r.rejected == 2 and r.clean_rows == 0
    assert {d["reason"] for d in env.queue.dead_letters()} == {"non_finite_value:power_w"}
    json.dumps(env.queue.dead_letters(), allow_nan=False)


async def test_ingest_respects_max_records_and_survives_source_error(env: Env) -> None:
    class Broken:
        source_id = "bad"

        async def read(self) -> Any:
            yield rec()
            raise RuntimeError("sorgente guasta")

    q = MemoryQueue()
    with pytest.raises(RuntimeError):
        await ingest_once(Broken(), q, env.metrics, lambda: NOW)
    assert q.stats()["depth"] == 1  # quanto gia' letto e' in coda
    assert (
        await ingest_once(
            ListSource([rec(f"2026-10-13T10:00:0{i}Z") for i in range(5)]),
            MemoryQueue(),
            env.metrics,
            lambda: NOW,
            max_records=3,
        )
        == 3
    )


def test_deduplicator_default_has_no_loader() -> None:
    assert Deduplicator().admit({"source_id": "a", "site_id": "s", "t_utc": NOW}).is_new
