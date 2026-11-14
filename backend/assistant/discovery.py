# SPDX-License-Identifier: Apache-2.0
"""Scoperta dei modelli candidati, a prova di SSRF.

Si contattano SOLO gli endpoint dichiarati nell'ambiente (ASSISTANT_OLLAMA_URL, default
http://127.0.0.1:11434, e ASSISTANT_LLM_BASE_URL): mai scansioni di rete, mai redirect seguiti
(un 3xx e' un errore), timeout breve, risposta con tetto di dimensione, nomi dei modelli validati.
Un endpoint NON locale richiede chiave E modello espliciti e non viene sondato (nessuna chiave ->
mai contattato). Chiavi e URL non compaiono mai in log, errori o risposte: solo etichette e codici.
"""

import asyncio
import ipaddress
import json
import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import httpx

from backend.assistant.cloud import GROQ_ID, MODEL_RE, groq_config
from backend.assistant.config import EXTRACTIVE_ID, Settings

log = logging.getLogger(__name__)
OLLAMA_ID = "ollama"
OPENAI_ID = "assistant-openai-compat"
MAX_RESPONSE_BYTES = 256 * 1024
MAX_MODELS = 32
NON_CHAT = ("embed", "rerank", "whisper", "tts", "moderation")
OFF_VALUES = ("", "off", "0", "none", "false")


@dataclass(frozen=True)
class Candidate:
    provider: str
    model: str | None
    local: bool
    base_url: str = field(default="", repr=False, compare=False)  # base /v1 per le chiamate chat
    api_key: str = field(default="", repr=False, compare=False)

    @property
    def id(self) -> str:
        return f"{self.provider}:{self.model}" if self.model else self.provider

    @property
    def key(self) -> tuple[str, str | None]:
        return (self.provider, self.model)


EXTRACTIVE = Candidate(EXTRACTIVE_ID, None, True)


@dataclass(frozen=True)
class Endpoint:
    provider: str
    base_url: str  # per Ollama: origine; per OpenAI-compat: base (di solito .../v1)
    local: bool
    model: str | None = None  # modello esplicito: nessuna sonda
    api_key: str = field(default="", repr=False)

    @property
    def probe_url(self) -> str:
        if self.provider == OLLAMA_ID:
            return self.base_url + "/api/tags"
        return self.base_url + "/models"

    @property
    def chat_base(self) -> str:
        return self.base_url + "/v1" if self.provider == OLLAMA_ID else self.base_url


def is_local_host(host: str, extra: tuple[str, ...] = ()) -> bool:
    h = host.lower()
    if h == "localhost" or h.endswith(".localhost") or h in extra:
        return True
    try:
        ip = ipaddress.ip_address(h)
    except ValueError:
        return False  # nessuna risoluzione DNS: un nome sconosciuto e' trattato come esterno
    return ip.is_loopback or ip.is_private or ip.is_link_local


def _parse(url: str) -> tuple[str, str] | None:
    """(schema+host+percorso senza slash finale, host) oppure None se l'URL non e' accettabile."""
    try:
        parts = urlsplit(url.strip())
        host = parts.hostname
        _ = parts.port  # solleva ValueError se la porta non e' valida
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not host or parts.username or parts.password:
        return None
    if parts.query or parts.fragment:
        return None
    return f"{parts.scheme}://{parts.netloc}{parts.path}".rstrip("/"), host


def build_endpoints(s: Settings, env: Mapping[str, str]) -> tuple[list[Endpoint], dict[str, str]]:
    """Endpoint da sondare/usare a partire dall'ambiente + codici dei motivi di esclusione."""
    out: list[Endpoint] = []
    skipped: dict[str, str] = {}
    cloud = groq_config(env)
    if cloud:
        base, cloud_model, key = cloud
        if MODEL_RE.fullmatch(cloud_model):
            out.append(Endpoint(GROQ_ID, base, False, cloud_model, key))
        else:
            skipped[GROQ_ID] = "invalid_config"
    elif env.get("RAVEN_SI_CLOUD_ENABLED") == "1":
        skipped[GROQ_ID] = "missing_key_or_model"
    if s.ollama_url.strip().lower() not in OFF_VALUES:
        parsed = _parse(s.ollama_url)
        if parsed is None:
            skipped[OLLAMA_ID] = "invalid_url"
        else:
            url, host = parsed
            out.append(Endpoint(OLLAMA_ID, url, is_local_host(host, s.local_hosts)))
    raw = (env.get("ASSISTANT_LLM_BASE_URL") or "").strip()
    if raw:
        parsed = _parse(raw)
        model = (env.get("ASSISTANT_LLM_MODEL") or "").strip() or None
        key = env.get("ASSISTANT_LLM_API_KEY") or ""
        if parsed is None or (model is not None and not MODEL_RE.match(model)):
            skipped[OPENAI_ID] = "invalid_config"
        else:
            url, host = parsed
            local = is_local_host(host, s.local_hosts)
            same = any(
                e.provider == OLLAMA_ID and urlsplit(e.base_url).netloc == urlsplit(url).netloc
                for e in out
            )
            if not local and (not key or model is None):
                skipped[OPENAI_ID] = "hosted_needs_key_and_model"
            elif not same:
                out.append(Endpoint(OPENAI_ID, url, local, model, key))
    return out, skipped


class ProbeError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def parse_models(provider: str, payload: object) -> list[str]:
    items: object = None
    if isinstance(payload, dict):
        items = payload.get("models" if provider == OLLAMA_ID else "data")
    if not isinstance(items, list):
        raise ProbeError("bad_shape")
    names: list[object] = []
    for m in items:
        if isinstance(m, dict):
            names.append(m.get("name") or m.get("model") if provider == OLLAMA_ID else m.get("id"))
    ok = {
        n
        for n in names
        if isinstance(n, str) and MODEL_RE.match(n) and not any(w in n.lower() for w in NON_CHAT)
    }
    return sorted(ok)[:MAX_MODELS]


async def _fetch(client: httpx.AsyncClient, url: str) -> bytes:
    try:
        async with client.stream("GET", url, headers={"Accept": "application/json"}) as resp:
            if 300 <= resp.status_code < 400:
                raise ProbeError("redirect_refused")
            if resp.status_code != 200:
                raise ProbeError(f"http_{resp.status_code}")
            declared = resp.headers.get("content-length", "")
            if declared.isdigit() and int(declared) > MAX_RESPONSE_BYTES:
                raise ProbeError("too_large")
            buf = bytearray()
            async for chunk in resp.aiter_bytes():
                buf += chunk
                if len(buf) > MAX_RESPONSE_BYTES:
                    raise ProbeError("too_large")
            return bytes(buf)
    except httpx.TimeoutException:
        raise ProbeError("timeout") from None
    except httpx.HTTPError:
        raise ProbeError("unreachable") from None


async def probe(
    ep: Endpoint, *, timeout_s: float, transport: httpx.AsyncBaseTransport | None
) -> list[str]:
    timeout = httpx.Timeout(timeout_s, connect=min(timeout_s, 2.0))
    async with httpx.AsyncClient(timeout=timeout, transport=transport, follow_redirects=False) as c:
        body = await asyncio.wait_for(_fetch(c, ep.probe_url), timeout=timeout_s * 2)
    try:
        payload = json.loads(body)
    except ValueError:
        raise ProbeError("bad_json") from None
    return parse_models(ep.provider, payload)


@dataclass
class _Entry:
    expiry: float
    probed_at: float
    models: list[str]
    error: str | None


class Discovery:
    """Cache con TTL dei modelli per endpoint; ri-sonda dopo un guasto (al massimo ogni `reprobe_min_s`)."""

    def __init__(
        self,
        endpoints: list[Endpoint],
        *,
        ttl_s: float = 60.0,
        timeout_s: float = 2.0,
        clock: Callable[[], float] = time.monotonic,
        transport: httpx.AsyncBaseTransport | None = None,
        reprobe_min_s: float = 5.0,
        failure_ttl_s: float = 10.0,
        skipped: Mapping[str, str] | None = None,
    ) -> None:
        self.endpoints = endpoints
        self.skipped = dict(skipped or {})
        self._ttl, self._timeout, self._clock = ttl_s, timeout_s, clock
        self._transport = transport
        self._reprobe_min = reprobe_min_s
        self._fail_ttl = min(failure_ttl_s, ttl_s)
        self._cache: dict[str, _Entry] = {}
        self._lock = asyncio.Lock()

    async def candidates(self) -> list[Candidate]:
        async with self._lock:
            out: list[Candidate] = []
            for ep in self.endpoints:
                models = [ep.model] if ep.model else await self._models(ep)
                out += [
                    Candidate(ep.provider, m, ep.local, ep.chat_base, ep.api_key) for m in models
                ]
            return out

    async def _models(self, ep: Endpoint) -> list[str]:
        now = self._clock()
        entry = self._cache.get(ep.provider)
        if entry is not None and now < entry.expiry:
            return entry.models
        try:
            models = await probe(ep, timeout_s=self._timeout, transport=self._transport)
            entry = _Entry(now + self._ttl, now, models, None)
        except ProbeError as e:
            entry = _Entry(now + self._fail_ttl, now, [], e.code)
        except (TimeoutError, ValueError, OSError):
            entry = _Entry(now + self._fail_ttl, now, [], "unreachable")
        if entry.error:
            log.info("assistente: sonda %s fallita (%s)", ep.provider, entry.error)
        self._cache[ep.provider] = entry
        return entry.models

    def errors(self) -> dict[str, str]:
        out = dict(self.skipped)
        out.update({p: e.error for p, e in self._cache.items() if e.error})
        return out

    def mark_failed(self, provider: str) -> None:
        """Un errore a runtime invalida la cache dell'endpoint (con limite anti-tempesta)."""
        entry = self._cache.get(provider)
        if entry is not None and self._clock() - entry.probed_at >= self._reprobe_min:
            entry.expiry = 0.0
