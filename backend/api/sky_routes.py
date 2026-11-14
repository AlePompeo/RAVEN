# SPDX-License-Identifier: Apache-2.0
"""Endpoint delle efemeridi (docs/ephemeris.md): illuminazione reale dei corpi a un istante UTC.

GET /api/raven/sky/status                       disponibilita' dei kernel, intervallo UTC, versioni
GET /api/raven/sky/subsolar?body=&t=            punto subsolare, distanza dal Sole, direzione del Sole nel frame del viewer
GET /api/raven/sky/series?body=&t0=&t1=&step_s= serie temporale con tetti (punti, passo minimo, durata)

Il calcolo gira in un thread (`asyncio.to_thread`) con un tetto globale di richieste concorrenti
(503 oltre il tetto) e una piccola cache LRU. Errori generici e nessun eco dell'input; senza
kernel o senza l'extra `sky` le rotte di calcolo rispondono 503 e l'app resta viva.
Questo modulo NON importa numpy/skyfield: il motore si carica pigramente da `backend.ephemeris`.
"""

import asyncio
import logging
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, FastAPI, Query, Request
from fastapi.responses import JSONResponse

from backend.domain.raven.meta import MODEL_VERSION, registry_sha256
from backend.envconf import env_positive_float, env_positive_int
from backend.ephemeris import kernels
from backend.ephemeris.timeutil import TimeError, parse_utc, utc_grid

log = logging.getLogger(__name__)

DEFAULT_MAX_CONCURRENT = 4
DEFAULT_MAX_POINTS = 2000
DEFAULT_MIN_STEP_S = 60.0
DEFAULT_MAX_SPAN_DAYS = 366
DEFAULT_CACHE_SIZE = 512
DEFAULT_CACHE_ROUND_S = 1.0
RETRY_LOAD_S = (
    30.0  # dopo un caricamento fallito, non ritentare (hash di 45 MB) piu' spesso di cosi'
)

BodyName = Literal["moon", "earth", "mars"]
TimeParam = Annotated[str, Query(min_length=20, max_length=32)]
SECONDS = 1.0

_GENERIC_422 = "parametri non validi"


class SkyService:
    """Motore pigro + cache LRU + tetto di concorrenza. Una istanza per app."""

    def __init__(
        self,
        *,
        max_concurrent: int,
        max_points: int,
        min_step_s: float,
        max_span_days: int,
        cache_size: int,
        cache_round_s: float,
        engine_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.max_concurrent = max_concurrent
        self.max_points = max_points
        self.min_step_s = min_step_s
        self.max_span = timedelta(days=max_span_days)
        self.cache_size = cache_size
        self.cache_round_s = cache_round_s
        self.sem = asyncio.Semaphore(max_concurrent)
        self._factory = engine_factory
        self._engine: Any = None
        self._failed_at: float | None = None
        self._load_lock = threading.Lock()
        self._cache: OrderedDict[tuple[str, int], dict[str, Any]] = OrderedDict()
        self._cache_lock = threading.Lock()

    # -- motore ---------------------------------------------------------------------------
    def engine(self) -> Any:
        """Motore caricato, o `EphemerisUnavailable` (kernel/extra mancanti)."""
        with self._load_lock:
            if self._engine is not None:
                return self._engine
            if self._failed_at is not None and time.monotonic() - self._failed_at < RETRY_LOAD_S:
                raise kernels.EphemerisUnavailable("efemeridi non disponibili")
            try:
                if self._factory is not None:
                    self._engine = self._factory()
                else:
                    from backend.ephemeris.engine import get_engine  # import pigro: serve numpy

                    self._engine = get_engine()
            except kernels.EphemerisUnavailable:
                self._failed_at = time.monotonic()
                raise
            except Exception as e:
                log.error("motore di efemeridi non inizializzato: %s", type(e).__name__)
                self._failed_at = time.monotonic()
                raise kernels.EphemerisUnavailable("efemeridi non disponibili") from e
            return self._engine

    def status(self) -> dict[str, Any]:
        lock = [
            {"name": s.name, "size": s.size, "sha256": s.sha256, "retrieved": s.retrieved}
            for s in kernels.load_lock()
        ]
        try:
            eng = self.engine()
        except kernels.EphemerisUnavailable:
            return {
                "available": False,
                "reason": "kernel NAIF assenti o extra `sky` non installato (make ephemeris)",
                "supported_range": None,
                "engine": None,
                "kernels": lock,
                "limits": self.limits(),
            }
        lo, hi = eng.supported_range()
        return {
            "available": True,
            "supported_range": {"start_utc": _iso(lo), "end_utc": _iso(hi)},
            "engine": eng.info()["versions"],
            "kernels": lock,
            "bodies": ["moon", "earth", "mars"],
            "convention": {
                "longitude": "east-positive, degrees in [-180, 180)",
                "latitude": "planetocentric",
                "sun_direction_body_fixed": "viewer axes (cos(lat) sin(lon), sin(lat), cos(lat) cos(lon))",
                "sun": "apparent (light time, aberration, deflection), body time at t",
            },
            "limits": self.limits(),
        }

    def limits(self) -> dict[str, Any]:
        return {
            "max_points": self.max_points,
            "min_step_s": self.min_step_s,
            "max_span_days": self.max_span.days,
            "max_concurrent": self.max_concurrent,
        }

    # -- calcolo (sincrono, eseguito in un thread) -----------------------------------------
    def _compute(self, eng: Any, body: str, ts: list[datetime]) -> dict[str, Any]:
        p = eng.subsolar_point(body, ts)
        d = eng.sun_distance_au(body, ts)
        v = eng.solar_direction_body_fixed(body, ts)
        out: dict[str, Any] = {
            "lat_deg": _r(p.lat_deg),
            "lon_deg_east": _r(p.lon_deg_east),
            "sun_distance_au": _r(d, 9),
            "sun_direction_body_fixed": _r(v),
        }
        if body == "moon":
            q = eng.sub_earth_point("moon", ts)
            out["sub_earth_lat_deg"] = _r(q.lat_deg)
            out["sub_earth_lon_deg_east"] = _r(q.lon_deg_east)
        return out

    def subsolar(self, body: str, t: datetime) -> dict[str, Any]:
        step = self.cache_round_s
        key_s = round(t.timestamp() / step)
        key = (body, key_s)
        with self._cache_lock:
            hit = self._cache.get(key)
            if hit is not None:
                self._cache.move_to_end(key)
                return hit
        rounded = datetime.fromtimestamp(key_s * step, UTC)
        res = self._compute(self.engine(), body, [rounded])
        row = {k: (v[0] if isinstance(v, list) else v) for k, v in res.items()}
        item: dict[str, Any] = {
            "body": body,
            "t_utc": _iso(rounded),
            "subsolar": {"lat_deg": row["lat_deg"], "lon_deg_east": row["lon_deg_east"]},
            "sun_distance_au": row["sun_distance_au"],
            "sun_direction_body_fixed": row["sun_direction_body_fixed"],
            "frame": "viewer",
        }
        if body == "moon":
            item["sub_earth"] = {
                "lat_deg": row["sub_earth_lat_deg"],
                "lon_deg_east": row["sub_earth_lon_deg_east"],
            }
        with self._cache_lock:
            self._cache[key] = item
            while len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)
        return item

    def series(self, body: str, ts: list[datetime]) -> dict[str, Any]:
        res = self._compute(self.engine(), body, ts)
        res.update({"body": body, "t_utc": [_iso(t) for t in ts], "frame": "viewer"})
        return res


def _iso(t: datetime) -> str:
    return (
        t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S")
        + (f".{t.microsecond:06d}".rstrip("0") if t.microsecond else "")
        + "Z"
    )


def _r(a: Any, nd: int = 7) -> Any:
    return a.round(nd).tolist()


def _error(status: int, detail: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"detail": detail}, status_code=status, headers=headers)


def build_sky_router() -> APIRouter:
    router = APIRouter()

    def svc(request: Request) -> SkyService:
        s: SkyService = request.app.state.sky
        return s

    async def guarded(request: Request, fn: Callable[[], dict[str, Any]]) -> JSONResponse:
        s = svc(request)
        if s.sem.locked():
            return _error(503, "troppe richieste di efemeridi in corso", {"Retry-After": "1"})
        try:
            async with s.sem:
                return JSONResponse(
                    {
                        **await asyncio.to_thread(fn),
                        "model_version": MODEL_VERSION,
                        "registry_sha256": registry_sha256(),
                    }
                )
        except kernels.EphemerisUnavailable:
            return _error(503, "efemeridi non disponibili", {"Retry-After": "30"})
        except (TimeError, ValueError):  # include OutOfRange; mai l'input nel messaggio
            return _error(422, _GENERIC_422)
        except Exception:
            log.exception("errore di calcolo efemeridi")
            return _error(500, "errore interno")

    @router.get("/api/raven/sky/status")
    async def status(request: Request) -> JSONResponse:
        return JSONResponse(
            {
                **await asyncio.to_thread(svc(request).status),
                "model_version": MODEL_VERSION,
                "registry_sha256": registry_sha256(),
            }
        )

    @router.get("/api/raven/sky/subsolar")
    async def subsolar(request: Request, body: BodyName, t: TimeParam) -> JSONResponse:
        try:
            when = parse_utc(t)
        except TimeError:
            return _error(422, "t deve essere UTC ISO-8601 con Z")
        s = svc(request)

        return await guarded(request, lambda: s.subsolar(body, when))

    @router.get("/api/raven/sky/series")
    async def series(
        request: Request,
        body: BodyName,
        t0: TimeParam,
        t1: TimeParam,
        step_s: Annotated[float, Query(allow_inf_nan=False, gt=0, le=1e9)],
    ) -> JSONResponse:
        s = svc(request)
        try:
            a, b = parse_utc(t0), parse_utc(t1)
        except TimeError:
            return _error(422, "t0 e t1 devono essere UTC ISO-8601 con Z")
        if step_s < s.min_step_s or b < a or b - a > s.max_span:
            return _error(422, "intervallo o passo fuori dai limiti (vedi /api/raven/sky/status)")
        if int((b - a).total_seconds() // step_s) + 1 > s.max_points:
            return _error(422, "troppi punti richiesti (vedi /api/raven/sky/status)")
        ts = utc_grid(a, b, step_s)

        return await guarded(request, lambda: s.series(body, ts))

    return router


def include_sky_routes(app: FastAPI) -> None:
    app.state.sky = SkyService(
        max_concurrent=env_positive_int("SKY_MAX_CONCURRENT", DEFAULT_MAX_CONCURRENT),
        max_points=env_positive_int("SKY_MAX_POINTS", DEFAULT_MAX_POINTS),
        min_step_s=env_positive_float("SKY_MIN_STEP_S", DEFAULT_MIN_STEP_S),
        max_span_days=env_positive_int("SKY_MAX_SPAN_DAYS", DEFAULT_MAX_SPAN_DAYS),
        cache_size=env_positive_int("SKY_CACHE_SIZE", DEFAULT_CACHE_SIZE),
        cache_round_s=env_positive_float("SKY_CACHE_ROUND_S", DEFAULT_CACHE_ROUND_S),
    )
    app.include_router(build_sky_router())
