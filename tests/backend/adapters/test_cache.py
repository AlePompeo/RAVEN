# SPDX-License-Identifier: Apache-2.0
import pytest

from backend.adapters.cache_memory import MemoryCache, cached_fetch


class Clock:
    t = 0.0

    def __call__(self) -> float:
        return self.t


async def test_ttl_and_stale() -> None:
    clock = Clock()
    c = MemoryCache(clock=clock)
    await c.set("k", b"v", ttl_s=10)
    assert await c.get("k") == b"v"
    clock.t = 11
    assert await c.get("k") is None
    assert await c.get("k", allow_stale=True) == b"v"


async def test_cached_fetch_serves_stale_when_upstream_down() -> None:
    clock = Clock()
    c = MemoryCache(clock=clock)

    async def ok() -> bytes:
        return b"fresh"

    async def down() -> bytes:
        raise ConnectionError("giù")

    first = await cached_fetch(c, "k", 10, ok)
    assert (first.value, first.stale) == (b"fresh", False)
    clock.t = 99
    second = await cached_fetch(c, "k", 10, down)
    assert (second.value, second.stale) == (b"fresh", True)


async def test_cached_fetch_raises_without_stale() -> None:
    async def down() -> bytes:
        raise ConnectionError("giù")

    with pytest.raises(ConnectionError):
        await cached_fetch(MemoryCache(), "x", 10, down)


async def test_cached_fetch_fresh_hit_skips_upstream() -> None:
    c = MemoryCache()
    await c.set("k", b"cached", ttl_s=10)

    async def boom() -> bytes:
        raise AssertionError("non va chiamato")

    hit = await cached_fetch(c, "k", 10, boom)
    assert (hit.value, hit.stale) == (b"cached", False)
