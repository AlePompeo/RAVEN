# SPDX-License-Identifier: Apache-2.0
"""Fix round 1, tema A: nessuna perdita silenziosa fra dedup e scrittura."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from backend.pipeline.processors import Deduplicator
from backend.pipeline.store import StoreError

from .test_pipeline import Env, msg, put_all, rec

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


def clean_times(env: Env) -> list[str]:
    t = env.store.read("clean").column("t_utc").to_pylist()
    return sorted(x.isoformat() for x in t)


async def test_numeric_received_utc_does_not_crash_or_lose_the_record(env: Env) -> None:
    m = {"source_id": "a", "received_utc": 1_792_058_400, "record": rec()}
    await env.queue.put(m)
    r = await env.pipe.drain_once()
    assert r.clean_rows == 1 and r.requeued == 0
    assert env.store.read("clean").num_rows == 1
    assert env.queue.stats()["depth"] == 0
    # raw e clean concordano sul giorno di ricezione (stessa funzione di parsing)
    assert env.store.read("raw").num_rows == 1
    assert env.store.read("clean").column("raw_file_id")[0].as_py() in {
        f.rsplit("/", 1)[1].removesuffix(".parquet") for f in env.store.visible_files("raw")
    }


async def test_failure_after_partial_admit_loses_nothing(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    await put_all(env, msg(rec("2026-10-13T10:00:00Z")), msg(rec("2026-10-13T10:00:01Z")))
    real = Deduplicator.admit
    calls = {"n": 0}

    def flaky(self: Deduplicator, row: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("guasto dopo ammissione parziale")
        return real(self, row)

    monkeypatch.setattr(Deduplicator, "admit", flaky)
    await env.pipe.drain_once()
    monkeypatch.undo()
    for _ in range(3):
        env.tick(120)
        await env.pipe.drain_once()
    assert clean_times(env) == [
        "2026-10-13T10:00:00+00:00",
        "2026-10-13T10:00:01+00:00",
    ]
    assert env.queue.dead_letters() == [] and env.queue.stats()["depth"] == 0


async def test_unexpected_error_in_batch_rolls_back_all_admitted_keys(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Qualunque eccezione nella scrittura: nessuna chiave resta ammessa senza dati su disco."""
    await put_all(env, msg(rec("2026-10-13T10:00:00Z")))
    real_write = env.store.write

    def boom(layer: str, *a: Any, **k: Any) -> Any:
        if layer == "clean":
            raise KeyboardInterrupt  # BaseException: non e' un Exception
        return real_write(layer, *a, **k)

    monkeypatch.setattr(env.store, "write", boom)
    with pytest.raises(KeyboardInterrupt):
        await env.pipe.drain_once()
    monkeypatch.undo()
    assert not env.pipe.dedup.has_pending()
    await env.pipe.drain_once()
    env.tick(120)
    await env.pipe.drain_once()
    assert env.store.read("clean").num_rows == 1


async def test_failure_on_second_day_then_retry_is_exactly_once(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    await put_all(
        env,
        msg(rec("2026-10-12T23:00:00Z")),
        msg(rec("2026-10-12T23:00:01Z", site="s2")),
        msg(rec("2026-10-13T01:00:00Z")),
    )
    real_write = env.store.write
    state = {"fail": True}

    def fail_day2(layer: str, source: str, rows: Any) -> Any:
        day2 = layer == "clean" and any(r["t_utc"].date().isoformat() == "2026-10-13" for r in rows)
        if state["fail"] and day2:
            raise OSError("disco pieno al secondo giorno")
        return real_write(layer, source, rows)

    monkeypatch.setattr(env.store, "write", fail_day2)
    r1 = await env.pipe.drain_once()
    assert r1.clean_rows == 2 and r1.requeued == 1  # giorno 1 scritto e confermato
    state["fail"] = False
    for _ in range(3):
        env.tick(120)
        await env.pipe.drain_once()
    assert clean_times(env) == [
        "2026-10-12T23:00:00+00:00",
        "2026-10-12T23:00:01+00:00",
        "2026-10-13T01:00:00+00:00",
    ]
    assert env.queue.dead_letters() == []


async def test_poison_message_among_good_ones_does_not_nack_neighbours(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    await put_all(
        env,
        msg(rec("2026-10-13T10:00:00Z", power=1.0)),
        msg(rec("2026-10-13T10:00:01Z", power=666.0)),  # veleno
        msg(rec("2026-10-13T10:00:02Z", power=3.0)),
    )
    real_write = env.store.write

    def picky(layer: str, source: str, rows: Any) -> Any:
        if layer == "clean" and any(r["power_w"] == 666.0 for r in rows):
            raise StoreError("riga non conforme")
        return real_write(layer, source, rows)

    monkeypatch.setattr(env.store, "write", picky)
    r = await env.pipe.drain_once()
    assert r.clean_rows == 2  # i vicini passano subito, nello stesso giro
    assert env.queue.stats()["acked"] == 2
    for _ in range(3):
        await env.pipe.drain_once()
    (dl,) = env.queue.dead_letters()
    assert dl["payload"]["record"]["power_w"] == 666.0
    assert dl["reason"] == "store_rejected:StoreError"  # veleno su riga singola: subito
    assert env.store.read("clean").num_rows == 2


def test_deduplicator_two_phase_commit_and_rollback() -> None:
    d = Deduplicator()
    row = {"source_id": "a", "site_id": "s", "t_utc": NOW}
    assert d.admit(row).is_new and d.has_pending()
    dup = d.admit(row)
    assert not dup.is_new and dup.pending  # duplicato di una chiave non ancora durevole
    assert not d.is_committed(row)
    d.rollback_pending()
    assert d.admit(row).is_new  # rilasciata: il retry non e' un falso duplicato
    d.commit(row)
    assert d.is_committed(row) and not d.has_pending()
    dup2 = d.admit(row)
    assert not dup2.is_new and not dup2.pending


def test_pending_partitions_are_pinned_against_eviction() -> None:
    loads: list[str] = []

    def loader(source: str, day: str) -> set[Any]:
        loads.append(source)
        return set()

    d = Deduplicator(loader=loader, max_partitions=1)
    a = {"source_id": "a", "site_id": "s", "t_utc": NOW}
    b = {"source_id": "b", "site_id": "s", "t_utc": NOW}
    d.admit(a)  # in attesa di scrittura: partizione bloccata
    d.admit(b)
    assert not d.admit(a).is_new  # la chiave pendente non e' stata persa dall'LRU
    d.commit(a)
    d.commit(b)
    d.admit({"source_id": "c", "site_id": "s", "t_utc": NOW})
    assert loads.count("a") == 1


def test_memory_is_bounded_by_number_of_keys() -> None:
    d = Deduplicator(max_keys=10, max_partitions=1000)
    for src in "abcdef":
        for i in range(4):
            row = {
                "source_id": src,
                "site_id": f"s{i}",
                "t_utc": datetime(2026, 10, 13, 0, 0, i, tzinfo=UTC),
            }
            d.admit(row)
            d.commit(row)
    assert d.total_keys() <= 10 + 4  # al piu' una partizione (non bloccata) oltre il tetto
