# SPDX-License-Identifier: Apache-2.0
import os
import uuid
from collections.abc import AsyncIterator

import pytest

from backend.adapters.cache_memory import cached_fetch

VALKEY_URL = os.environ.get("VALKEY_URL")


@pytest.fixture
async def cache() -> AsyncIterator[object]:
    if not VALKEY_URL:
        pytest.skip("VALKEY_URL non impostato")
    pytest.importorskip("redis")
    from backend.adapters.cache_valkey import ValkeyCache

    c = ValkeyCache(VALKEY_URL, prefix=f"test:{uuid.uuid4().hex}:")
    try:
        await c.get("ping")
    except Exception:  # noqa: BLE001
        pytest.skip("Valkey non raggiungibile")
    yield c
    await c.close()


async def test_roundtrip_and_stale(cache: object) -> None:
    from backend.adapters.cache_valkey import ValkeyCache

    assert isinstance(cache, ValkeyCache)
    await cache.set("k", b"v", ttl_s=0.05)
    assert await cache.get("k") == b"v"
    import asyncio

    await asyncio.sleep(0.1)
    assert await cache.get("k") is None
    assert await cache.get("k", allow_stale=True) == b"v"


async def test_cached_fetch_stale_on_error(cache: object) -> None:
    from backend.adapters.cache_valkey import ValkeyCache

    assert isinstance(cache, ValkeyCache)

    async def ok() -> bytes:
        return b"fresh"

    async def down() -> bytes:
        raise ConnectionError("giù")

    assert (await cached_fetch(cache, "k", 0.05, ok)).value == b"fresh"
    import asyncio

    await asyncio.sleep(0.1)
    assert (await cached_fetch(cache, "k", 0.05, down)).value == b"fresh"
