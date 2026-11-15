# SPDX-License-Identifier: Apache-2.0
"""Provider LLM generico per endpoint compatibili con l'API chat-completions di OpenAI.

Configurazione SOLO da ambiente (mai dal client): ASSISTANT_LLM_BASE_URL (default Ollama locale),
ASSISTANT_LLM_MODEL (obbligatorio), ASSISTANT_LLM_API_KEY (opzionale). La chiave non viene mai
registrata nei log ne' inclusa in messaggi di errore. Lo stream e' letto riga per riga con tetti
di dimensione; nessuna chiamata a strumenti (`tools` non e' mai inviato).
"""

import json
import os
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urlsplit

import httpx

from backend.core.errors import PluginError
from backend.core.manifest import Manifest

DEFAULT_BASE_URL = "http://localhost:11434/v1"
MAX_LINE_BYTES = 64 * 1024
MAX_TOTAL_CHARS = 24_000
MAX_EVENTS = 20_000
MAX_TOKENS = 1024


class LLMError(PluginError):
    """Errore del provider con un codice stabile (http_429, http_5xx, timeout, unreachable, ...)."""

    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.code = code


class OpenAICompatProvider:
    """Con `endpoint=(base_url, model, api_key)` (candidati scoperti dall'assistente) ignora l'ambiente."""

    def __init__(
        self,
        manifest: Manifest,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        endpoint: tuple[str, str, str] | None = None,
        trust_env: bool = True,
        max_tokens: int = MAX_TOKENS,
        json_mode: bool = False,
        reasoning_effort: str | None = None,
        timeout_s: float | None = None,
    ) -> None:
        self.manifest = manifest
        self._transport = transport
        self._endpoint = endpoint
        self._trust_env = trust_env
        self._max_tokens = max_tokens
        self._json_mode = json_mode
        self._reasoning_effort = reasoning_effort
        self._timeout_s = timeout_s if timeout_s is not None else manifest.timeout_s

    def _resolve(self) -> tuple[str, str, str]:
        return self._endpoint if self._endpoint is not None else self._config()

    @staticmethod
    def _config() -> tuple[str, str, str]:
        base = (os.environ.get("ASSISTANT_LLM_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        parts = urlsplit(base)
        if parts.scheme not in ("http", "https") or not parts.hostname or parts.username:
            raise PluginError("ASSISTANT_LLM_BASE_URL non valido")
        model = os.environ.get("ASSISTANT_LLM_MODEL") or ""
        if not model:
            raise PluginError("ASSISTANT_LLM_MODEL non impostato")
        return base, model, os.environ.get("ASSISTANT_LLM_API_KEY") or ""

    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        base, model, key = self._resolve()
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
        if key:
            headers["Authorization"] = f"Bearer {key}"
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,
            "temperature": 0.2,
            "max_tokens": self._max_tokens,
        }
        if self._json_mode:
            body["response_format"] = {"type": "json_object"}
        if self._reasoning_effort:
            body["reasoning_effort"] = self._reasoning_effort
        timeout = httpx.Timeout(self._timeout_s, connect=5.0)
        total = 0
        events = 0
        try:
            async with (
                httpx.AsyncClient(
                    timeout=timeout,
                    transport=self._transport,
                    follow_redirects=False,
                    trust_env=self._trust_env,
                ) as client,
                client.stream(
                    "POST", f"{base}/chat/completions", json=body, headers=headers
                ) as resp,
            ):
                if resp.status_code != 200:
                    raise LLMError(
                        f"endpoint LLM: HTTP {resp.status_code}",
                        "http_429" if resp.status_code == 429 else f"http_{resp.status_code}",
                    )
                async for line in resp.aiter_lines():
                    if len(line) > MAX_LINE_BYTES:
                        raise PluginError("riga di stream troppo lunga")
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        return
                    events += 1
                    if events > MAX_EVENTS:
                        raise PluginError("troppi eventi")
                    try:
                        delta = json.loads(data)["choices"][0].get("delta", {})
                        piece = delta.get("content")
                    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
                        raise PluginError("evento di stream non valido") from None
                    if not isinstance(piece, str) or not piece:
                        continue
                    total += len(piece)
                    if total > MAX_TOTAL_CHARS:
                        raise PluginError("risposta troppo lunga")
                    yield piece
        except httpx.HTTPError as e:
            # solo il tipo: il messaggio potrebbe contenere dettagli dell'endpoint
            code = "timeout" if isinstance(e, httpx.TimeoutException) else "unreachable"
            raise LLMError(f"endpoint LLM non raggiungibile ({type(e).__name__})", code) from None
