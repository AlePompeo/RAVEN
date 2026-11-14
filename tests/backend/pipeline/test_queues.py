# SPDX-License-Identifier: Apache-2.0
import asyncio
import sqlite3
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from backend.core.ports import Queue
from backend.pipeline.queues import DurableQueue, MemoryQueue, QueueConfigError


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


Factory = Callable[..., Any]


@pytest.fixture(params=["memory", "durable"])
def make(request: pytest.FixtureRequest, tmp_path: Path) -> Factory:
    n = 0

    def factory(**kw: Any) -> Any:
        nonlocal n
        n += 1
        if request.param == "memory":
            return MemoryQueue(**kw)
        return DurableQueue(tmp_path / f"q{n}.db", **kw)

    return factory


async def test_conforms_to_port(make: Factory) -> None:
    assert isinstance(make(), Queue)


async def test_fifo_put_get_ack(make: Factory) -> None:
    q = make()
    for i in range(3):
        assert await q.put({"n": i})
    got = []
    for _ in range(3):
        item = await q.get(timeout_s=0)
        assert item is not None
        got.append(item.payload["n"])
        assert await q.ack(item)
    assert got == [0, 1, 2]
    assert await q.get(timeout_s=0) is None
    assert q.stats()["acked"] == 3


async def test_get_timeout_returns_none(make: Factory) -> None:
    assert await make().get(timeout_s=0.02) is None


async def test_nack_redelivers_then_dead_letters_with_reason(make: Factory) -> None:
    q = make(max_attempts=3)
    await q.put({"k": 1})
    for attempt in (1, 2, 3):
        item = await q.get(timeout_s=0)
        assert item is not None and item.attempt == attempt
        assert await q.nack(item, "boom")
    assert await q.get(timeout_s=0) is None
    dl = q.dead_letters()
    assert len(dl) == 1
    assert dl[0]["payload"] == {"k": 1}
    assert "boom" in dl[0]["reason"] and dl[0]["attempts"] == 3
    assert q.stats()["dead_letter"] == 1


async def test_nack_without_requeue_dead_letters_immediately(make: Factory) -> None:
    q = make()
    await q.put({"k": 1})
    item = await q.get(timeout_s=0)
    assert item is not None
    assert await q.nack(item, "schema_violation:power_w", requeue=False)
    assert await q.get(timeout_s=0) is None
    assert q.dead_letters()[0]["reason"] == "schema_violation:power_w"


async def test_unacked_redelivered_after_visibility_timeout(make: Factory) -> None:
    clock = Clock()
    q = make(visibility_timeout_s=10.0, clock=clock)
    await q.put({"k": 1})
    first = await q.get(timeout_s=0)
    assert first is not None
    assert await q.get(timeout_s=0) is None  # lease ancora valido
    clock.t += 11
    second = await q.get(timeout_s=0)
    assert second is not None and second.id == first.id and second.attempt == 2
    assert not await q.ack(first)  # lease vecchio: nessun doppio ack
    assert await q.ack(second)
    assert not await q.ack(second)
    assert await q.get(timeout_s=0) is None


async def test_crash_loop_ends_in_dead_letter(make: Factory) -> None:
    clock = Clock()
    q = make(visibility_timeout_s=1.0, max_attempts=2, clock=clock)
    await q.put({"k": 1})
    for _ in range(2):
        assert await q.get(timeout_s=0) is not None
        clock.t += 2
    assert await q.get(timeout_s=0) is None
    assert q.dead_letters()[0]["reason"].startswith("visibility_timeout")


async def test_drop_policy_counts_drops(make: Factory) -> None:
    q = make(capacity=2, policy="drop_with_counter")
    assert await q.put({"n": 1}) and await q.put({"n": 2})
    assert not await q.put({"n": 3})
    assert q.stats()["dropped"] == 1 and q.stats()["depth"] == 2


async def test_block_policy_waits_for_space(make: Factory) -> None:
    q = make(capacity=1, policy="block")
    await q.put({"n": 1})
    task = asyncio.create_task(q.put({"n": 2}))
    for _ in range(5):
        await asyncio.sleep(0)
    assert not task.done()
    item = await q.get(timeout_s=0)
    assert item is not None
    await q.ack(item)
    assert await asyncio.wait_for(task, 2) is True
    assert q.stats()["dropped"] == 0


async def test_block_policy_put_timeout(make: Factory) -> None:
    q = make(capacity=1, policy="block", put_timeout_s=0.02)
    await q.put({"n": 1})
    assert not await q.put({"n": 2})
    assert q.stats()["put_timeouts"] == 1


async def test_invalid_config_and_payload(make: Factory) -> None:
    with pytest.raises(QueueConfigError):
        make(capacity=0)
    with pytest.raises(QueueConfigError):
        make(policy="whatever")
    with pytest.raises(QueueConfigError):
        make(max_attempts=0)
    q = make()
    with pytest.raises(ValueError):
        await q.put({"x": float("nan")})
    with pytest.raises(TypeError):
        await q.put("not a mapping")  # type: ignore[arg-type]


async def test_concurrent_producers_consumers_no_loss_no_duplicate_ack(make: Factory) -> None:
    q = make(capacity=16, policy="block")
    producers, per, consumers = 4, 50, 4
    total = producers * per
    acked: list[int] = []
    ack_results: list[bool] = []

    async def produce(p: int) -> None:
        for i in range(per):
            assert await q.put({"id": p * 1000 + i})

    async def consume() -> None:
        while len(acked) < total:
            item = await q.get(timeout_s=0.05)
            if item is None:
                continue
            ok = await q.ack(item)
            ack_results.append(ok)
            if ok:
                acked.append(item.payload["id"])

    await asyncio.wait_for(
        asyncio.gather(
            *[produce(p) for p in range(producers)], *[consume() for _ in range(consumers)]
        ),
        30,
    )
    expected = sorted(p * 1000 + i for p in range(producers) for i in range(per))
    assert sorted(acked) == expected
    assert all(ack_results)


# ---- DurableQueue specifici ----


async def test_durable_crash_unacked_item_redelivered_after_reopen(tmp_path: Path) -> None:
    clock = Clock()
    path = tmp_path / "q.db"
    q = DurableQueue(path, visibility_timeout_s=10.0, clock=clock)
    for i in range(3):
        await q.put({"n": i})
    done = await q.get(timeout_s=0)
    crashed = await q.get(timeout_s=0)
    assert done is not None and crashed is not None
    await q.ack(done)
    q.close()  # "crash": nessun ack per `crashed`, il terzo mai letto

    clock.t += 11
    q2 = DurableQueue(path, visibility_timeout_s=10.0, clock=clock)
    seen = []
    while (item := await q2.get(timeout_s=0)) is not None:
        seen.append((item.payload["n"], item.attempt))
        await q2.ack(item)
    assert seen == [(1, 2), (2, 1)]  # 0 era stato confermato; 1 riconsegnato
    q2.close()


async def test_durable_restart_keeps_ready_items_and_dead_letters(tmp_path: Path) -> None:
    path = tmp_path / "q.db"
    q = DurableQueue(path)
    await q.put({"n": 1})
    await q.put({"n": 2})
    item = await q.get(timeout_s=0)
    assert item is not None
    await q.nack(item, "bad", requeue=False)
    q.close()
    q2 = DurableQueue(path)
    assert [d["reason"] for d in q2.dead_letters()] == ["bad"]
    nxt = await q2.get(timeout_s=0)
    assert nxt is not None and nxt.payload == {"n": 2}
    q2.close()


async def test_durable_is_wal_and_sql_is_parameterised(tmp_path: Path) -> None:
    path = tmp_path / "q.db"
    q = DurableQueue(path)
    evil = {"a": "x'); DROP TABLE items;--", "b": ["\u0000", "é"]}
    await q.put(evil)
    item = await q.get(timeout_s=0)
    assert item is not None and item.payload == evil
    await q.nack(item, "r'); DROP TABLE items;--", requeue=False)
    assert q.dead_letters()[0]["reason"] == "r'); DROP TABLE items;--"
    q.close()
    con = sqlite3.connect(path)
    assert con.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert con.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 1
    con.close()


async def test_durable_two_instances_never_claim_same_item(tmp_path: Path) -> None:
    path = tmp_path / "q.db"
    a, b = DurableQueue(path), DurableQueue(path)
    for i in range(100):
        await a.put({"n": i})
    claimed: list[int] = []
    lock = threading.Lock()

    def worker(q: DurableQueue) -> None:
        loop = asyncio.new_event_loop()
        try:
            while True:
                item = loop.run_until_complete(q.get(timeout_s=0))
                if item is None:
                    return
                with lock:
                    claimed.append(item.payload["n"])
                assert loop.run_until_complete(q.ack(item))
        finally:
            loop.close()

    threads = [threading.Thread(target=worker, args=(q,)) for q in (a, b, a, b)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert sorted(claimed) == list(range(100))
    a.close()
    b.close()


@pytest.mark.parametrize(
    "name", ["../q.db", "q.txt", "q\x00.db", "sub/missing/q.db", "", "q.db/../../x.db"]
)
def test_durable_rejects_bad_paths(tmp_path: Path, name: str) -> None:
    with pytest.raises(QueueConfigError):
        DurableQueue(
            tmp_path / name if name and "\x00" not in name else name or "", base_dir=tmp_path
        )


def test_durable_rejects_special_and_escaping_paths(tmp_path: Path) -> None:
    for bad in (":memory:", "file:x.db?mode=memory", str(tmp_path)):
        with pytest.raises(QueueConfigError):
            DurableQueue(bad, base_dir=tmp_path)
    outside = tmp_path.parent / "outside.db"
    with pytest.raises(QueueConfigError):
        DurableQueue(outside, base_dir=tmp_path)
    link = tmp_path / "link"
    link.symlink_to(tmp_path.parent)
    with pytest.raises(QueueConfigError):
        DurableQueue(link / "x.db", base_dir=tmp_path)
    q = DurableQueue(tmp_path / "ok.db", base_dir=tmp_path)
    q.close()
