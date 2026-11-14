# SPDX-License-Identifier: Apache-2.0
"""Hardening HTTP: header di sicurezza, rate limit in memoria. Nessun cookie viene mai impostato."""

import json
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

CSP = "default-src 'self'"
HSTS = "max-age=31536000; includeSubDomains"
MAX_TRACKED = 10_000


def client_key(scope: Scope, *, trusted_proxy: bool = False) -> str:
    if trusted_proxy:
        for k, v in scope["headers"]:
            if k.lower() == b"x-forwarded-for":
                first: str = v.decode("latin-1").split(",")[0].strip()
                if first:
                    return first[:64]
    client: Any = scope.get("client")
    return str(client[0]) if client else "unknown"


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, *, hsts: bool = False) -> None:
        self.app = app
        self._hsts = hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers: list[tuple[bytes, bytes]] = [
                    (k, v) for k, v in message["headers"] if k.lower() != b"set-cookie"
                ]
                headers += [
                    (b"content-security-policy", CSP.encode()),
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"),
                ]
                if self._hsts:
                    headers.append((b"strict-transport-security", HSTS.encode()))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_wrapper)


class RateLimitMiddleware:
    """Finestra fissa per client, con tabella LRU limitata (evizione del più vecchio).

    Per default il client è l'IP del peer. Dietro un reverse proxy tutti i client condividono
    quell'IP, quindi il limite diventa globale: con `trusted_proxy=True` (env TRUSTED_PROXY=1) si
    usa il primo hop di X-Forwarded-For. Abilitarlo solo se il proxy riscrive l'header, altrimenti
    è falsificabile. I preflight OPTIONS non vengono contati.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        limit: int,
        window_s: float = 60.0,
        exempt: tuple[str, ...] = ("/health",),
        clock: Callable[[], float] = time.monotonic,
        max_tracked: int = MAX_TRACKED,
        trusted_proxy: bool = False,
    ) -> None:
        self.app = app
        self._limit = limit
        self._window = window_s
        self._exempt = exempt
        self._clock = clock
        self._max = max_tracked
        self._trusted = trusted_proxy
        self._hits: OrderedDict[str, tuple[float, int]] = OrderedDict()

    def _allow(self, key: str) -> tuple[bool, int]:
        now = self._clock()
        start, count = self._hits.get(key, (now, 0))
        if now - start >= self._window:
            start, count = now, 0
        if count >= self._limit:
            self._hits.move_to_end(key)
            return False, max(1, int(self._window - (now - start)) + 1)
        self._hits[key] = (start, count + 1)
        self._hits.move_to_end(key)
        while len(self._hits) > self._max:
            self._hits.popitem(last=False)
        return True, 0

    def _key(self, scope: Scope) -> str:
        return client_key(scope, trusted_proxy=self._trusted)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] == "OPTIONS" or scope["path"] in self._exempt:
            await self.app(scope, receive, send)
            return
        ok, retry = self._allow(self._key(scope))
        if ok:
            await self.app(scope, receive, send)
            return
        await _plain(send, 429, "troppe richieste", [(b"retry-after", str(retry).encode())])


async def _plain(
    send: Send, status: int, detail: str, extra: list[tuple[bytes, bytes]] | None = None
) -> None:
    body = json.dumps({"detail": detail}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                *(extra or []),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class _TooLarge(Exception):
    pass


class BodySizeLimitMiddleware:
    """413 se il body supera `max_bytes` (Content-Length e conteggio in streaming)."""

    def __init__(
        self, app: ASGIApp, *, max_bytes: int, path_limits: dict[str, int] | None = None
    ) -> None:
        self.app = app
        self._max = max_bytes
        self._path_limits = (
            path_limits or {}
        )  # tetto specifico per percorso esatto (PDF del report)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = self._path_limits.get(scope["path"], self._max)
        for k, v in scope["headers"]:
            if k == b"content-length":
                try:
                    too_big = int(v) > limit
                except ValueError:
                    too_big = True
                if too_big:
                    await _plain(send, 413, "body troppo grande")
                    return
        total = 0
        exceeded = False
        replied = False

        async def counting_receive() -> Message:
            nonlocal total, exceeded
            msg = await receive()
            if msg["type"] == "http.request":
                total += len(msg.get("body", b""))
                if total > limit:
                    exceeded = True
                    raise _TooLarge
            return msg

        async def guarded_send(message: Message) -> None:
            # se il limite è superato l'app (che può aver intercettato l'eccezione e risposto 400)
            # viene sostituita da un 413
            nonlocal replied
            if exceeded:
                if not replied:
                    replied = True
                    await _plain(send, 413, "body troppo grande")
                return
            await send(message)

        try:
            await self.app(scope, counting_receive, guarded_send)
        except _TooLarge:
            pass
        if exceeded and not replied:
            await _plain(send, 413, "body troppo grande")
