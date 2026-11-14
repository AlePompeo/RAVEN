# SPDX-License-Identifier: Apache-2.0
import asyncio
import csv
import hashlib
import hmac
import json
import logging
import math
import os
import re
import secrets
import threading
from collections import OrderedDict
from collections.abc import AsyncIterator, Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, StringConstraints, ValidationError
from starlette.types import Receive, Scope, Send

from backend.adapters.cache_memory import cached_fetch
from backend.api.security import client_key
from backend.contracts_models import Telemetry
from backend.core.errors import (
    InvalidMeasurement,
    InvalidOutput,
    PluginError,
    PluginNotFound,
    SimulationTimeout,
)
from backend.core.registry import Registry
from backend.envconf import env_positive_int

SCHEMA_VERSION = "1.0.0"
QUEUE_MAX = 100
KEEPALIVE_S = 15.0
MIN_PASS_S = 0.05
DEFAULT_CHAT_MAX_STREAM_S = 120.0
DEFAULT_SIM_MAX_CONCURRENT = 8
MAX_CHAT_MESSAGES = 50
MAX_CHAT_CHARS = 4000
DATA_TTL_S = 60.0
log = logging.getLogger(__name__)

Finite = Annotated[float, Field(allow_inf_nan=False)]
Key = Annotated[str, StringConstraints(min_length=1, max_length=64)]
MAX_SUBSCRIBERS = 100
MAX_SUBSCRIBERS_PER_CLIENT = 3
TELEMETRY_MAX_STREAM_S = 300
ESTIMATOR_OWNER_HEADER = "X-Estimator-Owner"


class TooManySubscribers(Exception):
    pass


class TooManyClientSubscribers(Exception):
    pass


class TelemetryHub:
    """Observer: ogni sottoscrittore ha una coda limitata; publish non blocca mai."""

    def __init__(
        self,
        max_subscribers: int = MAX_SUBSCRIBERS,
        max_per_client: int = MAX_SUBSCRIBERS_PER_CLIENT,
    ) -> None:
        self._max = max_subscribers
        self._max_per_client = max_per_client
        self.invalid_rows = 0
        self._subs: set[asyncio.Queue[dict[str, Any]]] = set()
        self._owners: dict[asyncio.Queue[dict[str, Any]], str] = {}

    @property
    def subscriber_count(self) -> int:
        return len(self._subs)

    @property
    def at_capacity(self) -> bool:
        return len(self._subs) >= self._max

    def subscribe(self, client: str | None = None) -> asyncio.Queue[dict[str, Any]]:
        if (
            client is not None
            and sum(c == client for c in self._owners.values()) >= self._max_per_client
        ):
            raise TooManyClientSubscribers
        if self.at_capacity:
            raise TooManySubscribers
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=QUEUE_MAX)
        self._subs.add(q)
        if client is not None:
            self._owners[q] = client
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        self._subs.discard(q)
        self._owners.pop(q, None)

    def publish(self, sample: dict[str, Any]) -> None:
        for q in tuple(self._subs):
            try:
                q.put_nowait(sample)
            except asyncio.QueueFull:
                pass  # sottoscrittore lento: il campione viene scartato


async def sse_events(
    hub: TelemetryHub, q: asyncio.Queue[dict[str, Any]], keepalive_s: float = KEEPALIVE_S
) -> AsyncIterator[str]:
    """Il chiamante ha già sottoscritto (atomico con il controllo del tetto); qui si rilascia."""
    try:
        while True:
            try:
                sample = await asyncio.wait_for(q.get(), timeout=keepalive_s)
            except TimeoutError:
                yield ": keepalive\n\n"
                continue
            yield f"data: {json.dumps(sample, allow_nan=False)}\n\n"
    finally:
        hub.unsubscribe(q)


_NESTED = ("sun", "earth")
_NUMERIC = ("power_w", "link_margin_db")
_STRINGS = ("t_utc", "site_id", "schema_version")


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _row_to_sample(
    row: Mapping[str, str | None], site_id: str, now: Callable[[], datetime]
) -> dict[str, Any]:
    """Mappa una riga CSV sul contratto Telemetry; solleva ValueError se non valida."""
    sample: dict[str, Any] = {}
    nested: dict[str, dict[str, float]] = {}
    for key, raw in row.items():
        if not key or raw is None or raw.strip() == "":
            raise ValueError(f"cella vuota: {key!r}")
        if key in _STRINGS:
            sample[key] = raw.strip()
        elif key in _NUMERIC:
            sample[key] = float(raw)
        elif key.split("_", 1)[0] in _NESTED and key.split("_", 1)[1] in ("az_deg", "el_deg"):
            obj, field = key.split("_", 1)
            nested.setdefault(obj, {})[field] = float(raw)
        else:
            raise ValueError(f"colonna fuori contratto: {key!r}")
    sample.update(nested)
    sample.setdefault("schema_version", SCHEMA_VERSION)
    sample.setdefault("site_id", site_id)
    sample.setdefault("t_utc", now().astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
    _check_finite(sample)
    t = sample["t_utc"]
    if "T" not in t or datetime.fromisoformat(t).tzinfo is None:
        raise ValueError("t_utc non è ISO-8601 con fuso orario")
    Telemetry.model_validate(sample)
    return sample


def _check_finite(obj: Any) -> None:
    if isinstance(obj, float) and not math.isfinite(obj):
        raise ValueError("valore non finito")
    if isinstance(obj, dict):
        for v in obj.values():
            _check_finite(v)


async def csv_replay(
    hub: TelemetryHub,
    path: Path,
    *,
    interval_s: float = 1.0,
    loop: bool = True,
    site_id: str | None = None,
    now: Callable[[], datetime] = _utc_now,
) -> None:
    """Rilancia un CSV come telemetria conforme a contracts/telemetry.schema.json (demo offline).

    Ogni campione è validato col modello generato dal contratto; le righe non valide vengono
    scartate (log + `hub.invalid_rows`), mai emesse."""
    site = site_id or os.environ.get("TELEMETRY_SITE_ID") or "demo"
    while True:
        with path.open(newline="", encoding="utf-8") as f:
            for lineno, row in enumerate(csv.DictReader(f), start=2):
                try:
                    sample = _row_to_sample(row, site, now)
                except (ValueError, TypeError, ValidationError) as e:
                    hub.invalid_rows += 1
                    log.warning("riga CSV %d scartata: %s", lineno, type(e).__name__)
                    continue
                hub.publish(sample)
                await asyncio.sleep(interval_s)
        if not loop:
            return
        await asyncio.sleep(max(interval_s, MIN_PASS_S))  # CSV vuoto: niente busy loop


class RunRequest(BaseModel):
    inputs: dict[Key, Finite] = Field(max_length=64)


SessionId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,64}$")]
DEFAULT_ESTIMATOR_SESSIONS = 64


class EstimatorReset(BaseModel):
    session: SessionId = "default"


class EstimatorUpdate(EstimatorReset):
    measurement: dict[Key, Finite] = Field(max_length=64)
    dt_s: Finite | None = None


class _EstimatorSession:
    def __init__(self, estimator: Any) -> None:
        self.estimator = estimator
        self.lock = threading.Lock()
        self.users = 0  # richieste in corso o in attesa; solo sotto sessions_guard


def _max_sessions() -> int:
    return env_positive_int("ESTIMATOR_MAX_SESSIONS", DEFAULT_ESTIMATOR_SESSIONS)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]  # "system" non accettato dal client (prompt injection)
    content: str = Field(min_length=1, max_length=MAX_CHAT_CHARS)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=MAX_CHAT_MESSAGES)
    provider: str = Field(default="echo-llm", min_length=1, max_length=64)


class UpstreamTimeout(Exception):
    pass


def _timeout_for(registry: Registry, kind: str, id: str) -> float:
    return next((m.timeout_s for m in registry.manifests() if m.kind == kind and m.id == id), 30.0)


async def chat_events(
    provider: Any,
    messages: list[dict[str, str]],
    timeout_s: float = 30.0,
    max_stream_s: float = DEFAULT_CHAT_MAX_STREAM_S,
) -> AsyncIterator[str]:
    """Budget `timeout_s` sul tempo di attesa del provider (somma delle attese dei token); ogni
    attesa è limitata a min(timeout_s, residuo). Il tempo in cui il client è lento a leggere
    (backpressure) non è contato dal budget, ma `max_stream_s` è un tetto assoluto di wall time
    controllato a ogni iterazione. Nessun contesto di timeout resta aperto attraverso uno yield."""
    it: Any = None
    loop = asyncio.get_running_loop()
    begun = loop.time()
    remaining = timeout_s
    try:
        it = provider.stream(messages).__aiter__()
        while True:
            if loop.time() - begun > max_stream_s:
                raise TimeoutError("tetto di durata dello stream")
            started = loop.time()
            try:
                token = await asyncio.wait_for(
                    it.__anext__(), timeout=min(timeout_s, max(remaining, 0.0))
                )
            except StopAsyncIteration:
                break
            remaining -= loop.time() - started
            yield f"data: {json.dumps({'token': token})}\n\n"
    except Exception:
        log.exception("provider LLM fallito")
        yield 'event: error\ndata: {"detail": "provider non disponibile"}\n\n'
        return
    finally:
        aclose = getattr(it, "aclose", None)
        if aclose is not None:
            await aclose()
    yield "data: [DONE]\n\n"


class _CappedStreamingResponse(StreamingResponse):
    """Tetto assoluto sulla risposta: se il client smette di leggere (backpressure) il generatore
    resta sospeso a uno yield; allo scadere si annulla l'invio e lo si chiude (aclose) così il
    provider rilascia le risorse upstream. Il contesto di timeout avvolge la risposta, non gli yield."""

    def __init__(self, gen: AsyncIterator[str], cap_s: float, **kwargs: Any) -> None:
        super().__init__(gen, **kwargs)
        self._gen = gen
        self._cap_s = cap_s

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            try:
                async with asyncio.timeout(self._cap_s):
                    await super().__call__(scope, receive, send)
            except TimeoutError:
                log.error("stream chat oltre il tetto di %s s: chiuso", self._cap_s)
        finally:
            aclose = getattr(self._gen, "aclose", None)
            if aclose is not None:
                await aclose()


class _LeasedStreamingResponse(StreamingResponse):
    """Rilascia la sottoscrizione comunque finisca la risposta (anche prima che il generatore
    parta, es. send() che fallisce): non dipende dal ciclo di vita del generatore."""

    def __init__(
        self, hub: TelemetryHub, q: asyncio.Queue[dict[str, Any]], *args: Any, **kwargs: Any
    ) -> None:
        super().__init__(*args, **kwargs)
        self._hub = hub
        self._q = q
        self._cap_s = env_positive_int("TELEMETRY_MAX_STREAM_SECONDS", TELEMETRY_MAX_STREAM_S)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            try:
                async with asyncio.timeout(self._cap_s):
                    await super().__call__(scope, receive, send)
            except TimeoutError:
                log.info("telemetry stream lease expired after %s s", self._cap_s)
        finally:
            self._hub.unsubscribe(self._q)
            close = getattr(self.body_iterator, "aclose", None)
            if close is not None:
                await close()


def _finite_outputs(outputs: Mapping[str, Any]) -> dict[str, float]:
    clean: dict[str, float] = {}
    for k, v in outputs.items():
        if isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v):
            raise InvalidOutput(f"output non valido: {k}")
        clean[str(k)] = float(v)
    return clean


def build_router() -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/api/plugins")
    async def plugins(request: Request) -> dict[str, Any]:
        registry: Registry = request.app.state.registry
        return {
            "plugins": [
                {"id": m.id, "kind": m.kind, "version": m.version, "license": m.license}
                for m in registry.manifests()
            ],
            "errors": request.app.state.plugin_errors,
        }

    @router.post("/api/simulations/{sim_id}/run")
    async def run_simulation(sim_id: str, body: RunRequest, request: Request) -> Any:
        registry: Registry = request.app.state.registry
        try:
            sim = registry.create("simulation", sim_id)
            timeout_s = next(
                (
                    m.timeout_s
                    for m in registry.manifests()
                    if m.kind == "simulation" and m.id == sim_id
                ),
                30.0,
            )
            sem: asyncio.Semaphore = request.app.state.sim_sem
            if sem.locked():  # tetto globale ai subprocess: rifiuto pulito, mai in coda
                return JSONResponse(
                    {"detail": "troppe simulazioni in corso"},
                    status_code=503,
                    headers={"Retry-After": "1"},
                )
            async with sem:  # rilasciato anche su timeout/cancellazione
                raw = await sim.run(body.inputs, timeout_s=timeout_s)
            outputs = _finite_outputs(raw)
        except PluginNotFound:
            raise HTTPException(404, "simulazione non trovata") from None
        except SimulationTimeout:
            raise HTTPException(504, "simulazione scaduta") from None
        except PluginError:
            raise HTTPException(502, "simulazione fallita") from None
        return {"schema_version": SCHEMA_VERSION, "outputs": outputs}

    # Stato in-process per (id estimatore, proprietario, sessione): lock per
    # sessione (handler sincroni nel threadpool, calcolo breve), tetto con eviction LRU.
    # Un 404 puo' anche significare "plugin non registrato" (extra opzionale mancante).
    # Eviction sicura: ogni richiesta prende un "lease" (users += 1 sotto il guard) PRIMA di
    # attendere il lock di sessione e lo rilascia in finally. Si evince solo il piu' vecchio
    # con users == 0; se al tetto sono tutte in uso, 503 invece di evincere: cosi' una richiesta
    # non opera mai su un'istanza orfana e le richieste concorrenti vedono la stessa istanza.
    sessions: OrderedDict[tuple[str, str, str], _EstimatorSession] = OrderedDict()
    sessions_guard = threading.Lock()  # protegge dict e contatori, mai chiamate al plugin
    max_sessions = _max_sessions()
    owner_secret = secrets.token_bytes(32)

    def estimator_owner(request: Request, response: Response) -> str:
        response.headers["Cache-Control"] = "no-store"
        supplied = request.headers.get(ESTIMATOR_OWNER_HEADER)
        if supplied is None:
            owner = secrets.token_urlsafe(32)
            signature = hmac.new(owner_secret, owner.encode(), hashlib.sha256).hexdigest()
            response.headers[ESTIMATOR_OWNER_HEADER] = f"{owner}.{signature}"
            return owner

        if re.fullmatch(r"[A-Za-z0-9_-]{43}\.[0-9a-f]{64}", supplied) is None:
            raise HTTPException(403, "identita' estimatore non valida")
        owner, _, signature = supplied.partition(".")
        expected = hmac.new(owner_secret, owner.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise HTTPException(403, "identita' estimatore non valida")
        return owner

    @router.get("/api/estimators/session")
    def new_estimator_owner(request: Request, response: Response) -> dict[str, str]:
        estimator_owner(request, response)
        return {"status": "ready"}

    def acquire(registry: Registry, est_id: str, session: str, owner: str) -> _EstimatorSession:
        key = (est_id, owner, session)
        with sessions_guard:
            found = sessions.get(key)
            if found is not None:
                sessions.move_to_end(key)
                found.users += 1
                return found
        try:
            est = registry.create("estimator", est_id)  # fuori da ogni lock
        except PluginNotFound:
            raise HTTPException(404, "estimatore non trovato") from None
        except Exception:
            log.exception("creazione estimatore %s fallita", est_id)
            raise HTTPException(502, "estimatore non disponibile") from None
        with sessions_guard:
            found = sessions.get(key)  # corsa: vince la prima istanza inserita
            if found is None:
                while len(sessions) >= max_sessions:
                    victim = next((k for k, v in sessions.items() if v.users == 0), None)
                    if victim is None:
                        raise HTTPException(503, "troppe sessioni attive")
                    del sessions[victim]
                found = sessions[key] = _EstimatorSession(est)
            sessions.move_to_end(key)
            found.users += 1
            return found

    def release(sess: _EstimatorSession) -> None:
        with sessions_guard:
            sess.users -= 1

    @router.post("/api/estimators/{est_id}/update")
    def update_estimator(
        est_id: str, body: EstimatorUpdate, request: Request, response: Response
    ) -> dict[str, Any]:
        sess = acquire(
            request.app.state.registry, est_id, body.session, estimator_owner(request, response)
        )
        try:
            with sess.lock:
                try:
                    state = _finite_outputs(sess.estimator.update(body.measurement, body.dt_s))
                except InvalidMeasurement as e:  # solo la validazione del plugin e' mostrata
                    raise HTTPException(422, str(e)) from None
                except Exception:
                    log.exception("estimatore %s: aggiornamento fallito", est_id)
                    raise HTTPException(502, "estimatore non disponibile") from None
        finally:
            release(sess)
        return {
            "schema_version": SCHEMA_VERSION,
            "t_utc": _utc_now().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "state": state,
        }

    @router.post("/api/estimators/{est_id}/reset")
    def reset_estimator(
        est_id: str, body: EstimatorReset, request: Request, response: Response
    ) -> dict[str, str]:
        sess = acquire(
            request.app.state.registry, est_id, body.session, estimator_owner(request, response)
        )
        try:
            with sess.lock:
                try:
                    sess.estimator.reset()
                except Exception:
                    log.exception("estimatore %s: reset fallito", est_id)
                    raise HTTPException(502, "estimatore non disponibile") from None
        finally:
            release(sess)
        return {"status": "reset"}

    @router.get("/api/telemetry/stream")
    async def telemetry_stream(request: Request) -> StreamingResponse:
        hub: TelemetryHub = request.app.state.hub
        try:
            q = hub.subscribe(
                client_key(request.scope, trusted_proxy=request.app.state.trusted_proxy)
            )
        except TooManyClientSubscribers:
            raise HTTPException(
                429, "troppe sottoscrizioni per client", headers={"Retry-After": "15"}
            ) from None
        except TooManySubscribers:
            raise HTTPException(503, "troppi sottoscrittori") from None
        try:
            return _LeasedStreamingResponse(
                hub,
                q,
                sse_events(hub, q),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        except BaseException:
            hub.unsubscribe(q)
            raise

    @router.post("/api/chat")
    async def chat(body: ChatRequest, request: Request) -> StreamingResponse:
        registry: Registry = request.app.state.registry
        try:
            provider = registry.create("llm", body.provider)
        except PluginNotFound:
            raise HTTPException(404, "provider non trovato") from None
        except Exception:
            log.exception("creazione provider %s fallita", body.provider)
            raise HTTPException(502, "provider non disponibile") from None
        messages = [m.model_dump() for m in body.messages]
        max_s: float = request.app.state.chat_max_stream_s
        return _CappedStreamingResponse(
            chat_events(provider, messages, _timeout_for(registry, "llm", body.provider), max_s),
            max_s + 1.0,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.get("/api/data/{source_id}")
    async def data(source_id: str, request: Request) -> JSONResponse:
        registry: Registry = request.app.state.registry
        try:
            source = registry.create("data_source", source_id)
        except PluginNotFound:
            raise HTTPException(404, "sorgente non trovata") from None
        except Exception:
            log.exception("creazione sorgente %s fallita", source_id)
            raise HTTPException(502, "sorgente non disponibile") from None
        timeout_s = _timeout_for(registry, "data_source", source_id)

        async def fetch() -> bytes:
            try:
                async with asyncio.timeout(timeout_s):
                    result = await source.fetch({})
                return json.dumps(result, allow_nan=False).encode()
            except TimeoutError:
                log.error("sorgente dati %s: timeout", source_id)
                raise UpstreamTimeout from None
            except Exception:
                log.exception("sorgente dati %s non raggiungibile", source_id)
                raise

        try:
            res = await cached_fetch(
                request.app.state.cache, f"data:{source_id}", DATA_TTL_S, fetch
            )
        except UpstreamTimeout:  # solo il fetch upstream, non le operazioni di cache
            return JSONResponse({"detail": "sorgente dati scaduta"}, status_code=504)
        except Exception:  # noqa: BLE001  503 senza dettagli interni
            return JSONResponse({"detail": "sorgente dati non disponibile"}, status_code=503)
        headers = {"X-Cache": "stale" if res.stale else "fresh"}
        return JSONResponse({"data": json.loads(res.value)}, headers=headers)

    return router


def include_routes(app: FastAPI) -> None:
    app.state.sim_max_concurrent = env_positive_int(
        "SIM_MAX_CONCURRENT", DEFAULT_SIM_MAX_CONCURRENT
    )
    app.state.sim_sem = asyncio.Semaphore(app.state.sim_max_concurrent)
    app.include_router(build_router())
