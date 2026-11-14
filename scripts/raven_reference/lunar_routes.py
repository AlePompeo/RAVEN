# SPDX-License-Identifier: Apache-2.0
"""Endpoint dell'analisi lunare (docs/domain/method.md): siti, date, link, energia, ore utili.

GET  /api/lunar/sites      registro dei siti (coordinate, fonte, verified) e stazioni DSN
GET  /api/lunar/defaults   TUTTI i parametri: valore, unita', limiti, fonte oppure 'illustrative'
POST /api/lunar/analyze    metriche per sito, serie decimate per i grafici, classifica, ipotesi
POST /api/lunar/timeline   campioni non aggregati per la timeline del mission planner
POST /api/lunar/solar-terrain  Sole contro la maschera d'orizzonte LOLA del sito (200 km, cache)
POST /api/lunar/horizon    profili LOLA lungo azimut campionati, non una visibilita' garantita
POST /api/lunar/mission    un sito: Sole-terreno, batteria, margine RF GrazingLink, DSN, stato per passo

I risultati sono "potenziale nelle ipotesi dichiarate": orizzonte locale piatto con maschera di
elevazione (nessun terreno), nessuna atmosfera, link budget semplificato.

Il calcolo gira in un thread (`asyncio.to_thread`) con tetto globale di richieste concorrenti
(503 oltre il tetto), cache LRU per hash della richiesta, errori 422 generici senza eco
dell'input, 503 se i kernel mancano. Il modulo NON importa numpy/skyfield all'avvio: il dominio
di calcolo si carica pigramente (numpy e' un extra opzionale).
"""

import asyncio
import hashlib
import json
import logging
import threading
from collections import OrderedDict
from itertools import pairwise
from typing import Annotated, Any, Literal

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr

from backend.api.custom_sites import CustomSite, resolve_sites
from backend.domain.lunar import model as lm
from backend.domain.raven.params import value as reg_value
from backend.envconf import env_positive_int
from backend.ephemeris import kernels
from backend.ephemeris.timeutil import TimeError

log = logging.getLogger(__name__)

DEFAULT_MAX_CONCURRENT = 2
DEFAULT_CACHE_SIZE = 32
DEFAULT_MAX_TOTAL_POINTS = 20000
TERRAIN_SOLAR_MAX_STEPS = 240
TERRAIN_SOLAR_MAX_SITES = 2
MISSION_MAX_STEPS = 1500
AU_KM = reg_value("common.au_km")  # IAU 2012 Resolution B2 (registry)
SERIES_NAMES = ("sun_el_deg", "earth_el_deg", "margin_db", "soc", "gen_w", "useful")
TIMELINE_SERIES_NAMES = (
    "sun_az_deg",
    "sun_el_deg",
    "earth_az_deg",
    "earth_el_deg",
    "sun_up",
    "earth_visible",
    "dsn_visible",
    "link_ok",
    "margin_db",
    "useful",
    "gen_w",
    "soc",
)
_GENERIC_422 = "parametri non validi"

DISCLAIMER = (
    "Risultati: potenziale nelle ipotesi dichiarate, non una previsione di missione. "
    "Limiti: orizzonte locale piatto con maschera di elevazione (nessun terreno: l'illuminazione "
    "polare reale dipende dalla topografia), nessuna atmosfera ne' rifrazione, link budget "
    "semplificato (spazio libero, G/T costante, nessun guadagno di codifica verificato). "
    "I parametri 'illustrative' non hanno fonte."
)
RANKING_RULE = (
    "score = somma_k w_k * c_k / max_siti(c_k) / somma_k w_k, con c_1 = frazione di ore utili e "
    "c_2 = SOC minimo della batteria; pesi di default 1 e 1. Le componenti sono sempre riportate."
)

Override = StrictInt | StrictFloat | StrictStr


class TimelineTooLarge(ValueError):
    """The requested unaggregated timeline exceeds the response limit."""


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    site_ids: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=40)]], Field(min_length=1, max_length=16)
    ]
    custom_sites: Annotated[list[CustomSite], Field(max_length=2)] = []
    start_utc: Annotated[str, Field(min_length=20, max_length=32)]
    days: StrictInt | StrictFloat = lm.PARAMS["days"].default
    step_min: StrictInt | StrictFloat = lm.PARAMS["step_min"].default
    overrides: Annotated[
        dict[Annotated[str, Field(max_length=48)], Override], Field(max_length=64)
    ] = {}
    weights: Annotated[
        dict[Annotated[str, Field(max_length=32)], StrictInt | StrictFloat], Field(max_length=4)
    ] = {}


class SolarTerrainRequest(AnalyzeRequest):
    """AnalyzeRequest + observer eye height above the DEM (tag I, default 2 m)."""

    observer_height_m: Annotated[
        StrictInt | StrictFloat, Field(ge=0, le=100, allow_inf_nan=False)
    ] = 2.0

    def base(self) -> AnalyzeRequest:
        return AnalyzeRequest(**self.model_dump(exclude={"observer_height_m"}))


class MissionRequest(BaseModel):
    """One site, one window: coupled Sun-terrain, battery, GrazingLink RF and DSN evaluation."""

    model_config = ConfigDict(extra="forbid")
    site_id: Annotated[str, Field(min_length=1, max_length=40)]
    custom_site: CustomSite | None = None
    start_utc: Annotated[str, Field(min_length=20, max_length=32)]
    days: Annotated[StrictInt | StrictFloat, Field(gt=0, le=90, allow_inf_nan=False)] = 7
    step_min: Annotated[StrictInt | StrictFloat, Field(ge=10, le=1440, allow_inf_nan=False)] = 60
    observer_height_m: Annotated[
        StrictInt | StrictFloat, Field(ge=0, le=100, allow_inf_nan=False)
    ] = 2.0
    rate_bps: Annotated[StrictInt | StrictFloat, Field(ge=1e4, le=3e6, allow_inf_nan=False)] = 1e5
    station: Literal["dsn34", "dsn18"] = "dsn34"
    rf_overrides: Annotated[
        dict[
            Annotated[str, Field(max_length=48)], StrictInt | StrictFloat | StrictBool | StrictStr
        ],
        Field(max_length=24),
    ] = {}
    energy_overrides: Annotated[
        dict[Annotated[str, Field(max_length=48)], Override], Field(max_length=32)
    ] = {}


class HorizonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    site_id: Annotated[str, Field(min_length=1, max_length=40)]
    custom_site: CustomSite | None = None
    observer_height_m: Annotated[
        StrictInt | StrictFloat, Field(ge=0, le=100, allow_inf_nan=False)
    ] = 0


class CoupledSample(BaseModel):
    model_config = ConfigDict(extra="forbid")
    time_unix: Annotated[StrictInt | StrictFloat, Field(allow_inf_nan=False)]
    gen_w: Annotated[StrictInt | StrictFloat, Field(ge=0, le=1e9, allow_inf_nan=False)]
    sun_up: StrictBool
    earth_visible: StrictBool
    dsn_visible: StrictBool
    rf_ok: StrictBool
    solar_state: Literal[
        "upper_above_profile",
        "upper_below_profile",
        "outside_coverage",
        "missing_dem",
        "invalid_geometry",
    ]


class CoupledRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    samples: Annotated[list[CoupledSample], Field(min_length=1, max_length=TERRAIN_SOLAR_MAX_STEPS)]
    step_min: Annotated[StrictInt | StrictFloat, Field(ge=10, le=1440, allow_inf_nan=False)]
    tx_power_dbw: Annotated[StrictInt | StrictFloat, Field(ge=-20, le=40, allow_inf_nan=False)]
    station: Literal["dsn34"]
    energy: Annotated[dict[Annotated[str, Field(max_length=48)], Override], Field(max_length=32)]


class LunarService:
    def __init__(self, *, max_concurrent: int, cache_size: int, max_total_points: int) -> None:
        self.max_concurrent = max_concurrent
        self.cache_size = cache_size
        self.max_total_points = max_total_points
        self.sem = asyncio.Semaphore(max_concurrent)
        self._cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._lock = threading.Lock()
        self.computed = 0  # number of real computations (cache misses), for tests

    def limits(self) -> dict[str, Any]:
        return {
            "max_concurrent": self.max_concurrent,
            "cache_size": self.cache_size,
            "max_total_points": self.max_total_points,
            "days_max": lm.PARAMS["days"].hi,
            "step_min_min": lm.PARAMS["step_min"].lo,
            "timeline_series_per_site": len(TIMELINE_SERIES_NAMES),
            "terrain_solar_max_steps_per_site": TERRAIN_SOLAR_MAX_STEPS,
            "terrain_solar_max_sites": TERRAIN_SOLAR_MAX_SITES,
            "mission_max_steps": MISSION_MAX_STEPS,
        }

    @staticmethod
    def cache_key(req: AnalyzeRequest) -> str:
        canon = json.dumps(req.model_dump(), sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(canon.encode()).hexdigest()

    def get(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            hit = self._cache.get(key)
            if hit is not None:
                self._cache.move_to_end(key)
            return hit

    def put(self, key: str, value: dict[str, Any]) -> None:
        with self._lock:
            self._cache[key] = value
            while len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)

    def analyze(
        self, engine: Any, req: AnalyzeRequest, *, timeline: bool = False
    ) -> dict[str, Any]:
        """Synchronous (runs in a thread). Raises ParamError / ValueError / TimeError on bad input."""
        from backend.domain.lunar.mission import analyze

        catalog = resolve_sites(req.site_ids, req.custom_sites)
        window = lm.AnalysisWindow.build(req.start_utc, req.days, req.step_min)
        timeline_points = window.n_steps * len(req.site_ids) * len(TIMELINE_SERIES_NAMES)
        if timeline and timeline_points > self.max_total_points:
            raise TimelineTooLarge
        link = lm.LinkParams.from_overrides(req.overrides)
        energy = lm.EnergyParams.from_overrides(req.overrides)
        # every override key must belong to link or energy (checked by from_overrides: an unknown
        # key raises; keys of the other group are accepted by it, so check the union explicitly)
        known = set(link.to_dict()) | set(energy.to_dict())
        if any(k not in known for k in req.overrides):
            raise lm.ParamError("overrides")
        weights = {k: float(v) for k, v in req.weights.items()}
        res = analyze(engine, [catalog[i] for i in req.site_ids], window, link, energy, weights)
        out = (
            _render_timeline(res, link, energy, self.max_total_points)
            if timeline
            else _render(res, link, energy, self.max_total_points)
        )
        if timeline:
            out["assumptions"]["ephemeris"] = engine.info()
            out["assumptions"]["lunar_frame"] = "MOON_ME_DE440_ME421"
        self.computed += 1
        return out


def _decimate(a: Any, k: int) -> list[float | None]:
    """Bin mean (for flags: fraction of true steps); NaN -> null. k = steps per bin."""
    import numpy as np

    x = np.asarray(a, dtype=np.float64)
    n = len(x)
    nb = -(-n // k)
    out: list[float | None] = []
    for b in range(nb):
        seg = x[b * k : (b + 1) * k]
        seg = seg[np.isfinite(seg)]
        out.append(round(float(seg.mean()), 4) if seg.size else None)
    return out


def _render(
    res: Any, link: lm.LinkParams, energy: lm.EnergyParams, max_total: int
) -> dict[str, Any]:
    import numpy as np

    n = res.window.n_steps
    per_series = max(2, max_total // (len(res.sites) * len(SERIES_NAMES)))
    k = max(1, -(-n // per_series))
    t = [int(v) for v in res.instants_unix[::k]]
    sites_out = []
    for sa in res.sites:
        margin = np.where(sa.vis.earth_visible, sa.margin_db, np.nan)
        series = {
            "sun_el_deg": _decimate(sa.vis.sun_el_deg, k),
            "earth_el_deg": _decimate(sa.vis.earth_el_deg, k),
            "margin_db": _decimate(margin, k),
            "soc": _decimate(sa.energy.soc, k),
            "gen_w": _decimate(sa.energy.gen_w, k),
            "useful": _decimate(sa.useful.astype(np.float64), k),
        }
        sites_out.append({"site": sa.site.to_dict(), "metrics": sa.metrics, "series": series})
    return {
        "label": "potential under stated assumptions",
        "disclaimer": DISCLAIMER,
        "window": res.window.to_dict(),
        "series_time_unix": t,
        "series_step_min": res.window.step_min * k,
        "series_names": list(SERIES_NAMES),
        "sites": sites_out,
        "ranking": res.ranking,
        "ranking_rule": RANKING_RULE,
        "assumptions": {
            "link": link.to_dict(),
            "energy": energy.to_dict(),
            "parameters": lm.defaults_table(),
            "dsn_stations": _dsn_info(),
            "sun_semidiameter_deg": lm.SUN_SEMIDIAMETER_DEG,
            "sun_up_rule": "upper solar limb: elevation of the centre + 0.27 deg >= mask",
            "earth_visible_rule": "Earth centre elevation >= mask (disk not added)",
            "useful_rule": "power_available AND earth_visible AND dsn_visible AND margin >= required",
        },
    }


def _dsn_info() -> list[dict[str, Any]]:
    from backend.domain.lunar.visibility import dsn_stations_info

    return dsn_stations_info()


def _render_timeline(
    res: Any, link: lm.LinkParams, energy: lm.EnergyParams, max_total: int
) -> dict[str, Any]:
    """Keep actual step-start samples: averages cannot represent visibility transitions."""
    import numpy as np

    out = _render(res, link, energy, max_total)

    def floats(values: Any) -> list[float | None]:
        return [float(v) if np.isfinite(v) else None for v in values]

    out["series_time_unix"] = res.instants_unix.tolist()
    out["series_step_min"] = res.window.step_min
    out["series_names"] = list(TIMELINE_SERIES_NAMES)
    out["sampling"] = (
        "Each sample is evaluated at the start of its step and represents [t, t + step); "
        "transitions are known only to the sampling resolution. Generation is evaluated at the "
        "step start; battery state of charge is at the end of the step. The model uses a flat horizon."
    )
    for row, sa in zip(out["sites"], res.sites, strict=True):
        row["series"] = {
            "sun_az_deg": floats(sa.vis.sun_az_deg),
            "sun_el_deg": floats(sa.vis.sun_el_deg),
            "earth_az_deg": floats(sa.vis.earth_az_deg),
            "earth_el_deg": floats(sa.vis.earth_el_deg),
            "sun_up": sa.vis.sun_up.tolist(),
            "earth_visible": sa.vis.earth_visible.tolist(),
            "dsn_visible": res.dsn.visible.tolist(),
            "link_ok": sa.link_ok.tolist(),
            "margin_db": floats(np.where(sa.vis.earth_visible, sa.margin_db, np.nan)),
            "useful": sa.useful.tolist(),
            "gen_w": floats(sa.energy.gen_w),
            "soc": floats(sa.energy.soc),
        }
    return out


def _error(status: int, detail: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"detail": detail}, status_code=status, headers=headers)


def build_lunar_router() -> APIRouter:
    router = APIRouter()

    def svc(request: Request) -> LunarService:
        s: LunarService = request.app.state.lunar
        return s

    @router.get("/api/lunar/sites")
    async def sites(request: Request) -> JSONResponse:
        return JSONResponse(
            {
                "sites": [s.to_dict() for s in lm.load_sites()],
                "dsn_stations": await asyncio.to_thread(_dsn_info),
                "disclaimer": DISCLAIMER,
            }
        )

    @router.get("/api/lunar/defaults")
    async def defaults(request: Request) -> JSONResponse:
        return JSONResponse(
            {
                "parameters": lm.defaults_table(),
                "ranking": {
                    "components": ["useful_fraction", "energy_margin"],
                    "default_weights": {"useful_fraction": 1.0, "energy_margin": 1.0},
                    "rule": RANKING_RULE,
                },
                "status_legend": {
                    "V": "valore letto in una fonte primaria",
                    "D": "derivato con formula ripetibile da valori V",
                    "I": "illustrativo, nessuna fonte",
                },
                "limits": svc(request).limits(),
                "disclaimer": DISCLAIMER,
            }
        )

    async def run_analysis(
        request: Request, req: AnalyzeRequest, *, timeline: bool
    ) -> JSONResponse:
        s = svc(request)
        try:
            key = ("timeline:" if timeline else "analyze:") + s.cache_key(req)
        except ValueError:  # NaN/inf in the overrides: not canonicalisable
            return _error(422, _GENERIC_422)
        hit = s.get(key)
        if hit is not None:
            return JSONResponse(hit)
        if s.sem.locked():
            return _error(503, "troppe analisi in corso", {"Retry-After": "2"})
        try:
            async with s.sem:
                engine = await asyncio.to_thread(request.app.state.sky.engine)
                result = await asyncio.to_thread(s.analyze, engine, req, timeline=timeline)
        except kernels.EphemerisUnavailable:
            return _error(503, "efemeridi non disponibili", {"Retry-After": "30"})
        except TimelineTooLarge:
            return _error(
                422, "timeline troppo grande: ridurre durata o siti, oppure aumentare il passo"
            )
        except (lm.ParamError, TimeError, ValueError):  # include OutOfRange; mai l'input
            return _error(422, _GENERIC_422)
        except Exception:
            log.exception("errore di calcolo dell'analisi lunare")
            return _error(500, "errore interno")
        s.put(key, result)
        return JSONResponse(result)

    @router.post("/api/lunar/analyze")
    async def analyze(request: Request, req: AnalyzeRequest) -> JSONResponse:
        return await run_analysis(request, req, timeline=False)

    @router.post("/api/lunar/timeline")
    async def timeline(request: Request, req: AnalyzeRequest) -> JSONResponse:
        return await run_analysis(request, req, timeline=True)

    @router.post("/api/lunar/solar-terrain")
    async def solar_terrain(request: Request, full: SolarTerrainRequest) -> JSONResponse:
        from backend.domain.grazing.horizon import sun_semidiameter_deg
        from backend.domain.grazing.solar_terrain import solar_terrain as compare_terrain
        from backend.domain.lunar.terrain_energy import terrain_energy_sensitivity

        s = svc(request)
        req = full.base()
        height = float(full.observer_height_m)
        try:
            window = lm.AnalysisWindow.build(req.start_utc, req.days, req.step_min)
            if (
                window.n_steps > TERRAIN_SOLAR_MAX_STEPS
                or len(req.site_ids) > TERRAIN_SOLAR_MAX_SITES
            ):
                return _error(422, "troppi campioni per l'analisi del terreno solare")
        except (lm.ParamError, TimeError, ValueError):
            return _error(422, _GENERIC_422)
        if s.sem.locked():
            return _error(503, "troppe analisi in corso", {"Retry-After": "2"})

        def compute(engine: Any) -> dict[str, Any]:
            import numpy as np

            timeline_data = s.analyze(engine, req, timeline=True)
            sun_au = np.asarray(engine.sun_distance_au("moon", window.instants()), dtype=float)
            semi = sun_semidiameter_deg(sun_au * AU_KM)
            result = compare_terrain(
                timeline_data, observer_height_m=height, semidiameter_deg=semi.tolist()
            )
            terrain_energy_sensitivity(timeline_data, result, req.overrides, sun_au)
            return result

        try:
            async with s.sem:
                engine = await asyncio.to_thread(request.app.state.sky.engine)
                result = await asyncio.to_thread(compute, engine)
        except kernels.EphemerisUnavailable:
            return _error(503, "efemeridi non disponibili", {"Retry-After": "30"})
        except (TimelineTooLarge, lm.ParamError, TimeError, ValueError):
            return _error(422, _GENERIC_422)
        except Exception:
            log.exception("errore di calcolo dell'orizzonte solare")
            return _error(500, "errore interno")
        return JSONResponse(result)

    @router.post("/api/lunar/horizon")
    async def horizon(request: Request, req: HorizonRequest) -> JSONResponse:
        from backend.domain.grazing.dem import LolaDem
        from backend.domain.grazing.solar_terrain import circular_horizon

        try:
            site = resolve_sites(
                [req.site_id], [req.custom_site] if req.custom_site is not None else []
            )[req.site_id]
        except lm.ParamError:
            return _error(422, _GENERIC_422)
        s = svc(request)
        if s.sem.locked():
            return _error(503, "troppe analisi in corso", {"Retry-After": "2"})
        try:
            async with s.sem:
                result = await asyncio.to_thread(
                    circular_horizon,
                    site.to_dict(),
                    LolaDem(allow_download=False),
                    float(req.observer_height_m),
                )
        except Exception:
            log.exception("errore di calcolo dell'orizzonte")
            return _error(500, "errore interno")
        return JSONResponse(result)

    @router.post("/api/lunar/coupled-sensitivity")
    async def coupled_sensitivity(req: CoupledRequest) -> JSONResponse:
        from backend.domain.lunar.coupled import coupled_sensitivity as compute

        try:
            energy = lm.EnergyParams.from_overrides(req.energy)
            if set(req.energy) - set(energy.to_dict()):
                raise lm.ParamError("energy")
            times = [float(s.time_unix) for s in req.samples]
            if any(abs((b - a) - float(req.step_min) * 60) > 1e-6 for a, b in pairwise(times)):
                raise ValueError("unsynchronised samples")
            result = compute(
                [s.model_dump() for s in req.samples],
                float(req.step_min),
                energy,
                float(req.tx_power_dbw),
            )
        except (lm.ParamError, ValueError):
            return _error(422, _GENERIC_422)
        return JSONResponse(result)

    @router.post("/api/lunar/mission")
    async def mission(request: Request, req: MissionRequest) -> JSONResponse:
        from backend.domain.grazing.analysis import LinkInputs
        from backend.domain.grazing.dem import dem_dir
        from backend.domain.lunar.coupled import evaluate_mission

        s = svc(request)
        try:
            site = resolve_sites(
                [req.site_id], [req.custom_site] if req.custom_site is not None else []
            )[req.site_id]
            window = lm.AnalysisWindow.build(req.start_utc, req.days, req.step_min)
            if window.n_steps > MISSION_MAX_STEPS or window.n_steps < 1:
                return _error(422, "troppi campioni per la missione: ridurre durata o passo")
            energy = lm.EnergyParams.from_overrides(req.energy_overrides)
            if set(req.energy_overrides) - set(energy.to_dict()):
                raise lm.ParamError("energy")
            if {"rate_bps", "station"} & set(req.rf_overrides):
                raise lm.ParamError("rf")
            rf = LinkInputs.from_overrides(
                {**req.rf_overrides, "rate_bps": float(req.rate_bps), "station": req.station}
            )
            dsn_min = lm.LinkParams.from_overrides({}).ground_station_min_elevation_deg
            key = (
                "mission:"
                + hashlib.sha256(
                    json.dumps(
                        [str(dem_dir()), req.model_dump()], sort_keys=True, allow_nan=False
                    ).encode()
                ).hexdigest()
            )
        except (lm.ParamError, TimeError, ValueError):
            return _error(422, _GENERIC_422)
        hit = s.get(key)
        if hit is not None:
            return JSONResponse(hit)
        if s.sem.locked():
            return _error(503, "troppe analisi in corso", {"Retry-After": "2"})
        try:
            async with s.sem:
                engine = await asyncio.to_thread(request.app.state.sky.engine)
                result = await asyncio.to_thread(
                    evaluate_mission,
                    engine,
                    site,
                    window,
                    energy,
                    rf,
                    float(req.observer_height_m),
                    dsn_min_elevation_deg=dsn_min,
                )
        except kernels.EphemerisUnavailable:
            return _error(503, "efemeridi non disponibili", {"Retry-After": "30"})
        except (lm.ParamError, TimeError, ValueError):
            return _error(422, _GENERIC_422)
        except Exception:
            log.exception("errore di calcolo della missione")
            return _error(500, "errore interno")
        s.put(key, result)
        return JSONResponse(result)

    return router


def include_lunar_routes(app: FastAPI) -> None:
    app.state.lunar = LunarService(
        max_concurrent=env_positive_int("LUNAR_MAX_CONCURRENT", DEFAULT_MAX_CONCURRENT),
        cache_size=env_positive_int("LUNAR_CACHE_SIZE", DEFAULT_CACHE_SIZE),
        max_total_points=env_positive_int("LUNAR_MAX_TOTAL_POINTS", DEFAULT_MAX_TOTAL_POINTS),
    )
    app.include_router(build_lunar_router())
