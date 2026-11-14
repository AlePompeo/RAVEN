# SPDX-License-Identifier: Apache-2.0
import time
from collections.abc import Awaitable, Callable
from typing import NamedTuple

from backend.core.ports import CachePort


class MemoryCache:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._data: dict[str, tuple[bytes, float]] = {}

    async def get(self, key: str, *, allow_stale: bool = False) -> bytes | None:
        item = self._data.get(key)
        if item is None:
            return None
        value, expires = item
        return value if allow_stale or self._clock() < expires else None

    async def set(self, key: str, value: bytes, ttl_s: float) -> None:
        self._data[key] = (value, self._clock() + ttl_s)


class Cached(NamedTuple):
    value: bytes
    stale: bool


async def cached_fetch(
    cache: CachePort,
    key: str,
    ttl_s: float,
    fetch: Callable[[], Awaitable[bytes]],
) -> Cached:
    """Restituisce il valore in cache; se l'upstream fallisce serve il valore scaduto (stale)."""
    hit = await cache.get(key)
    if hit is not None:
        return Cached(hit, False)
    try:
        value = await fetch()
    except Exception:
        stale = await cache.get(key, allow_stale=True)
        if stale is not None:
            return Cached(stale, True)
        raise
    await cache.set(key, value, ttl_s)
    return Cached(value, False)
