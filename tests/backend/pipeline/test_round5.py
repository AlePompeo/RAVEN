# SPDX-License-Identifier: Apache-2.0
"""Fix round 5: backoff realistico del breaker, canarino invisibile davvero, pulizia e sonda pigra."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from backend.pipeline.reserved import CANARY_SOURCE
from backend.pipeline.store import ParquetStore

from .test_pipeline import Env, msg, put_all, rec
from .test_round4 import make_pipe, t

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
BASE = 30.0


@pytest.fixture
def env(tmp_path: Path) -> Env:
    return Env(tmp_path)


async def test_long_poison_head_waits_only_the_base_interval_per_cycle(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_pipe(env, poison_breaker=5, breaker_backoff_s=BASE, batch_size=10)
    await put_all(
        env,
        *[msg(rec(t(i), power=666.0)) for i in range(80)],
        *[msg(rec(t(1000 + i), power=1.0)) for i in range(20)],
    )
    real = env.store.write

    def picky(layer: str, source: str, rows: Any) -> Any:
        if layer == "clean" and any(r["power_w"] == 666.0 for r in rows):
            raise TypeError("riga strana")
        return real(layer, source, rows)

    monkeypatch.setattr(env.store, "write", picky)
    drains = 0
    while env.queue.stats()["depth"] and drains < 40:
        await env.pipe.drain_once()
        drains += 1
        assert env.pipe._breaker_level <= 1
        env.tick(BASE + 1)  # tempo REALISTICO: solo l'intervallo base
    assert env.queue.stats()["depth"] == 0
    assert len(env.queue.dead_letters()) == 80
    assert env.store.read("clean").num_rows == 20
    # 80 veleni a 5 per intervallo = 16 giri, piu' quelli per i sani: limite dichiarato
    assert drains <= 20


async def test_canary_is_invisible_while_its_files_still_exist(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    await put_all(env, msg(rec()))
    await env.pipe.drain_once()
    monkeypatch.setattr(env.store, "discard_canary", lambda: None)  # il file resta su disco
    assert env.pipe._canary_ok()
    on_disk = list(env.store.root.rglob(f"source={CANARY_SOURCE}"))
    assert on_disk and any(p.rglob("*.parquet") for p in on_disk)  # esiste davvero
    assert all(CANARY_SOURCE not in f for f in env.store.visible_files("clean"))
    assert env.store.read("clean").num_rows == 1  # solo il record vero
    assert {r["source_id"] for r in env.store.read("clean").to_pylist()} == {"a"}
    # ... ed e' interrogabile solo chiedendolo per nome esplicito (uso interno)
    assert env.store.visible_files("clean", CANARY_SOURCE)


def test_leftover_canary_is_swept_at_open(tmp_path: Path) -> None:
    root = tmp_path / "s"
    stale = root / "clean" / f"source={CANARY_SOURCE}" / "date=2026-10-13"
    stale.mkdir(parents=True)
    (stale / "part-1.parquet").write_bytes(b"x")
    ParquetStore(root, clock=lambda: NOW)
    assert not (root / "clean" / f"source={CANARY_SOURCE}").exists()


async def test_canary_not_run_when_queue_is_empty(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_pipe(env, poison_breaker=1, breaker_backoff_s=BASE)
    await put_all(env, msg(rec(power=666.0)), msg(rec(t(5), power=666.0)))
    real = env.store.write

    def picky(layer: str, source: str, rows: Any) -> Any:
        if layer == "clean" and any(r["power_w"] == 666.0 for r in rows):
            raise TypeError("x")
        return real(layer, source, rows)

    monkeypatch.setattr(env.store, "write", picky)
    await env.pipe.drain_once()  # un veleno in dead-letter, il breaker apre, l'altro rilasciato
    env.tick(BASE + 1)
    await env.pipe.drain_once()  # half-open: canarino, poi veleno 2 (budget 1)
    # svuota tutto
    for _ in range(4):
        env.tick(BASE + 1)
        await env.pipe.drain_once()
    assert env.queue.stats()["depth"] == 0
    calls = {"n": 0}
    real_canary = env.pipe._canary_ok

    def counting() -> bool:
        calls["n"] += 1
        return real_canary()

    monkeypatch.setattr(env.pipe, "_canary_ok", counting)
    env.pipe._breaker_until = env.now
    for _ in range(3):
        env.tick(1)
        await env.pipe.drain_once()
    assert calls["n"] == 0
