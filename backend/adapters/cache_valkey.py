# SPDX-License-Identifier: Apache-2.0
"""Cache su Valkey/Redis (extra opzionale `valkey`); `redis` è importato solo all'uso."""

import importlib
import struct
import time
from collections.abc import Callable
from typing import Any

_HEADER = struct.Struct(">d")


class ValkeyCache:
    """Implementa `CachePort`. Il valore è salvato con la scadenza logica in testa e resta
    fisicamente in Valkey per `stale_grace_s` oltre il TTL, per poter servire dati stale."""

    def __init__(
        self,
        url: str,
        *,
        prefix: str = "hb:",
        stale_grace_s: float = 86400.0,
        clock: Callable[[], float] = time.time,
    ) -> None:
        try:
            aioredis: Any = importlib.import_module("redis.asyncio")
        except ImportError as e:
            raise RuntimeError("pacchetto `redis` mancante: pip install '.[valkey]'") from e
        self._client: Any = aioredis.from_url(url)
        self._prefix, self._grace, self._clock = prefix, stale_grace_s, clock

    async def get(self, key: str, *, allow_stale: bool = False) -> bytes | None:
        raw: bytes | None = await self._client.get(self._prefix + key)
        if raw is None or len(raw) < _HEADER.size:
            return None
        (expires,) = _HEADER.unpack_from(raw)
        if not allow_stale and self._clock() >= expires:
            return None
        return raw[_HEADER.size :]

    async def set(self, key: str, value: bytes, ttl_s: float) -> None:
        payload = _HEADER.pack(self._clock() + ttl_s) + value
        await self._client.set(
            self._prefix + key, payload, px=max(1, int((ttl_s + self._grace) * 1000))
        )

    async def close(self) -> None:
        await self._client.aclose()
