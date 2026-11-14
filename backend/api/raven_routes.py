# SPDX-License-Identifier: Apache-2.0
"""RAVEN core API (migration step M7): one evaluation for the whole site.

* `POST /api/raven/evaluate`: one site, one window, stages S0-S7 (`backend.domain.raven.pipeline`).
* `POST /api/raven/compare`: several sites, same window and parameters; per-site summaries. No
  ranking yet (the single ranking is step M11): the summaries expose every component.
* `GET /api/raven/parameters`: the parameter registry (value, unit, range, V/D/I tag, source).
* `GET /api/raven/model`: the stages, which are implemented and the declared limits.

Caps (decision D9): 1500 steps per site and 6000 in total, no decimation (422 over the cap). Errors as
in the legacy lunar API: generic 422 without echoing the input, 503 without ephemerides or over the
concurrency cap, 500 for unexpected failures. Results are cached (LRU) by request.
"""

import asyncio
import dataclasses
import hashlib
import json
import logging
import math
import threading
from collections import OrderedDict
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Literal

from fastapi import APIRouter, FastAPI, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr

from backend.api.raven_custom import (
    CustomSiteIn,
    EstimateRequest,
    TerrainService,
    records,
)
from backend.api.raven_experiments import warm_imports
from backend.api.raven_report import build_report_router
from backend.domain.lunar.model import ORIENTATIONS, EnergyParams, ParamError
from backend.domain.raven import params as reg
from backend.domain.raven import s0_context as s0
from backend.domain.raven.known import Reason
from backend.domain.raven.meta import MODEL_VERSION, STAGE_ORDER, registry_sha256
from backend.domain.raven.ranking import RankingError, components_of, rank
from backend.domain.raven.reliability import MODEL as RELIABILITY_MODEL
from backend.domain.raven.validation import validation_report
from backend.envconf import env_positive_int
from backend.ephemeris import kernels
from backend.ephemeris.timeutil import TimeError, parse_utc

if (
    TYPE_CHECKING
):  # numpy-free import: the app must start without the data extras (like the lunar routes)
    from backend.domain.raven.pipeline import Evaluation, Scenario

log = logging.getLogger(__name__)

DEFAULT_MAX_CONCURRENT = 2
DEFAULT_CACHE_SIZE = 32
DEFAULT_COMPUTE_TIMEOUT_S = 120
_GENERIC_422 = "parametri non validi"
Num = StrictInt | StrictFloat
Override = StrictInt | StrictFloat | StrictStr

DECLARED_LIMITS = (
    "Potential under stated assumptions, not a mission forecast.",
    "Terrain beyond 200 km, multiple diffraction, solar limb darkening, dust and thermal effects are not modelled.",
    "Radio, power and battery parameters are illustrative (tag I).",
    "DSN is geometric visibility only, no scheduling.",
    "Far terrain beyond the RF profile: a single-obstacle estimate (decision D4).",
)


class _Common(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_utc: Annotated[str, Field(min_length=20, max_length=32)]
    days: Annotated[Num, Field(gt=0, le=366, allow_inf_nan=False)] = 7
    step_min: Annotated[Num, Field(ge=1, le=1440, allow_inf_nan=False)] = 60
    panel_height_m: Annotated[Num, Field(ge=0.1, le=100, allow_inf_nan=False)] = 2.0
    antenna_height_m: Annotated[Num, Field(ge=0.1, le=100, allow_inf_nan=False)] = 2.0
    rate_bps: Annotated[Num, Field(ge=1e4, le=3e6, allow_inf_nan=False)] = 1e5
    station: Literal["dsn34", "dsn18"] = "dsn34"
    required_margin_db: Annotated[Num, Field(ge=0, le=20, allow_inf_nan=False)] = 3.0
    rf_overrides: Annotated[
        dict[Annotated[str, Field(max_length=48)], Num | StrictBool | StrictStr],
        Field(max_length=24),
    ] = {}
    energy_overrides: Annotated[
        dict[Annotated[str, Field(max_length=48)], Override], Field(max_length=32)
    ] = {}


class EvaluateRequest(_Common):
    site_id: Annotated[str, Field(min_length=1, max_length=40)]
    custom_site: CustomSiteIn | None = None
    allow_download: StrictBool = False  # fetch the terrain tiles of a custom site if missing
    include_steps: StrictBool = True
    include_windows: StrictBool = (
        False  # edges refined by bisection to 1 s (a few engine calls per edge)
    )


class CompareRequest(_Common):
    site_ids: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=40)]], Field(min_length=1, max_length=16)
    ]
    custom_sites: Annotated[list[CustomSiteIn], Field(max_length=s0.MAX_CUSTOM_SITES)] = []
    allow_download: StrictBool = False
    # lexicographic order of the ranking (D5): components in priority order; default if omitted
    order: Annotated[list[Annotated[str, Field(max_length=32)]], Field(max_length=5)] | None = None


class SnapshotQuery(BaseModel):
    """One UTC instant, bit rate and station for the all-sites snapshot."""

    model_config = ConfigDict(extra="forbid")
    t: Annotated[str, Field(min_length=20, max_length=32)]
    rate_bps: Annotated[float, Field(ge=1e4, le=3e6, allow_inf_nan=False)] = 1e5
    station: Literal["dsn34", "dsn18"] = "dsn34"
    gain_dbi: Annotated[float, Field(ge=-10, le=45, allow_inf_nan=False)] | None = (
        None  # Tx antenna gain (rf.tx_gain_dbi)
    )
    # custom sites, compact: "id|name|lat|lon" items separated by ";" (at most 8); tiles from the
    # cache only (a site that needs a download is reported as such, nothing is fetched here)
    custom: Annotated[str, Field(max_length=1200)] | None = None


class SceneQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    site: Annotated[str, Field(min_length=1, max_length=40)]
    t: Annotated[str, Field(min_length=20, max_length=32)]
    rate_bps: Annotated[float, Field(ge=1e4, le=3e6, allow_inf_nan=False)] = 1e5
    station: Literal["dsn34", "dsn18"] = "dsn34"
    antenna_height_m: Annotated[float, Field(ge=0.1, le=100, allow_inf_nan=False)] = 2.0
    gain_dbi: Annotated[float, Field(ge=-10, le=45, allow_inf_nan=False)] | None = (
        None  # Tx antenna gain (rf.tx_gain_dbi)
    )
    # a user site: both coordinates together (the id is then only a label)
    lat_deg: Annotated[float, Field(ge=-90, le=90, allow_inf_nan=False)] | None = None
    lon_deg_east: Annotated[float, Field(ge=-180, le=360, allow_inf_nan=False)] | None = None
    name: Annotated[str, Field(max_length=40)] | None = None
    allow_download: bool = False  # a query string: "true"/"false", so not StrictBool


class HorizonQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    site: Annotated[str, Field(min_length=1, max_length=40)]
    height_m: Annotated[float, Field(ge=0.1, le=100, allow_inf_nan=False)] = 2.0
    # a user site: both coordinates together (the id is then only a label)
    lat_deg: Annotated[float, Field(ge=-90, le=90, allow_inf_nan=False)] | None = None
    lon_deg_east: Annotated[float, Field(ge=-180, le=360, allow_inf_nan=False)] | None = None
    name: Annotated[str, Field(max_length=40)] | None = None
    allow_download: bool = False  # a query string: "true"/"false", so not StrictBool


class BriefParseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: Annotated[str, Field(max_length=2000)]
    use_model: bool = False  # let a language model fill what the rules left empty (local, or the configured online one with allow_external)
    allow_external: bool = False  # the user agrees that the text leaves this computer for the configured online service


class OverlayQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    layer: Literal["elevation", "slope", "coverage", "sun", "earth", "both", "sun_gap", "earth_gap"]
    size: Annotated[int, Field(ge=64, le=512)] = 384
    limit_lat_deg: Annotated[float, Field(ge=-89, le=-60, allow_inf_nan=False)] = -75.0
    scope: Literal["polar", "global"] = "polar"


class RavenBusy(Exception):
    pass


class RavenService:
    def __init__(self, *, max_concurrent: int, cache_size: int) -> None:
        self.sem = asyncio.Semaphore(max_concurrent)
        self.cache_size = cache_size
        self._cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._lock = threading.Lock()
        self._dem: Any = None
        self._profiles: Any = None
        self.terrain = TerrainService()
        self.compute_timeout_s = env_positive_int(
            "RAVEN_MAX_COMPUTE_SECONDS", DEFAULT_COMPUTE_TIMEOUT_S
        )

    async def compute(self, work: Callable[[], Any]) -> Any:
        if self.sem.locked():
            raise RavenBusy
        await self.sem.acquire()
        try:
            future = asyncio.get_running_loop().run_in_executor(None, work)
        except BaseException:
            self.sem.release()
            raise

        def finished(done: asyncio.Future[Any]) -> None:
            self.sem.release()
            if not done.cancelled() and (error := done.exception()) is not None:
                log.error(
                    "worker RAVEN failed",
                    exc_info=(type(error), error, error.__traceback__),
                )

        # Cancelling the HTTP request must not free a lease while its thread still runs.
        future.add_done_callback(finished)
        async with asyncio.timeout(self.compute_timeout_s):
            return await asyncio.shield(future)

    def dem(self) -> Any:
        from backend.domain.grazing.dem import LolaDem

        with self._lock:
            if self._dem is None:
                self._dem = LolaDem(allow_download=False)  # cached tiles only, never a download
            return self._dem

    def profiles(self) -> Any:
        from backend.domain.grazing.analysis import ProfileCache

        with self._lock:
            if self._profiles is None:
                self._profiles = ProfileCache()
            return self._profiles

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


def _pipeline() -> Any:
    warm_imports()
    from backend.domain.raven import pipeline

    return pipeline


def _errors() -> tuple[type[BaseException], ...]:
    warm_imports()
    from backend.domain.grazing.analysis import GrazingParamError

    return (s0.S0Error, ParamError, GrazingParamError, TimeError, RankingError, ValueError)


def _defaults() -> dict[str, Any]:
    """Standard scenario for every page: a window inside the D9 cap and the unified parameter set."""
    lim = s0.default_limits()
    days, step = 7.0, 10.0
    n = s0.n_steps(days, step)
    assert n <= lim.max_steps_per_site
    try:
        from backend.domain.grazing.bitrate import DEFAULT_RATES_BPS

        rates: list[float] | None = [float(r) for r in DEFAULT_RATES_BPS]
    except ImportError:  # data extras not installed
        rates = None
    return {
        "window": {
            "days": days,
            "step_min": step,
            "n_steps": n,
            "max_steps_per_site": lim.max_steps_per_site,
            "max_steps_total": lim.max_steps_total,
            "max_days": lim.max_days,
            "step_min_bounds": [lim.min_step_min, lim.max_step_min],
            "note": "7 days at 10 min = 1008 steps; the legacy default of 29.53 d at 10 min is over the cap",
        },
        "scenario": {
            "panel_height_m": reg.value("rf.panel_height_m"),
            "antenna_height_m": reg.value("rf.antenna_height_m"),
            "rate_bps": 1e5,
            "station": "dsn34",
            "required_margin_db": reg.value("rf.required_margin_db"),
            "dsn_min_elevation_deg": reg.value("lunar.ground_station_min_elevation_deg"),
        },
        "rf": {k.removeprefix("rf."): reg.value(k) for k in reg.REGISTRY if k.startswith("rf.")},
        "rates_bps": rates,
        "energy_orientations": list(ORIENTATIONS),
        "sites": list(s0.load_catalog()),
        "sources": "every row of `parameters` carries tag, source, unit and range",
    }


def _error(status: int, detail: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"detail": detail}, status_code=status, headers=headers)


def _f(v: Any) -> float | None:
    return None if v is None or not math.isfinite(float(v)) else float(v)


def _reasons(rs: list[Reason]) -> list[str]:
    return [r.value for r in rs]


def _counts(rs: list[Reason]) -> dict[str, int]:
    return {r.value: sum(1 for x in rs if x is r) for r in Reason if any(x is r for x in rs)}


def summary(ev: "Evaluation") -> dict[str, Any]:
    """Everything except the per-step columns."""
    from backend.domain.raven.custom_terrain import terrain_block

    assert ev.geometry and ev.terrain and ev.illumination and ev.rf and ev.dsn and ev.mission
    t = ev.terrain
    return {
        "model_version": ev.model_version,
        "registry_sha256": ev.registry_sha256,
        "label": "potential under stated assumptions",
        "site": ev.site.to_dict(),
        "window": {
            "start_utc": ev.grid.start_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "step_min": ev.grid.step_min,
            "n_steps": ev.grid.n_steps,
        },
        "implemented_stages": list(ev.implemented_stages),
        "metrics": ev.mission.metrics,
        "first_unknown_index": ev.mission.first_unknown_index,
        "inputs_state": {
            "terrain_mask": t.mask_state.value,
            "terrain_reason_counts": _counts(t.terrain_reason),
            "illumination_reason_counts": _counts(ev.illumination.reason),
            "rf_reason_counts": _counts(ev.rf.reason),
            "dsn_reason_counts": _counts(ev.dsn.reason),
        },
        "mask": t.mask_meta,
        "terrain": terrain_block(ev.site, t.mask_meta, t.mask_state.value),
        "heights": {
            "panel_height_m": t.params.panel_height_m,
            "antenna_height_m": t.params.antenna_height_m,
            "profile_length_m": t.params.profile_length_m,
        },
        "rules": {
            "link_usable": "RF closes (margin >= required, or a KNOWN far-terrain block = no) AND DSN visible",
            "useful": "state == operational AND link_usable; unknown steps are counted apart",
            "lit": "disc_fraction > 0",
            "far_terrain": (
                "terrain beyond the RF profile above the Earth: knife-edge loss >= "
                f"{reg.value('common.far_terrain_blocked_loss_db')} dB = blocked_far_terrain (known no), "
                "else outside_model (unknown)"
            ),
        },
        "declared_limits": list(DECLARED_LIMITS),
    }


def _free_space_db(ev: "Evaluation", wavelength_m: float) -> list[float | None]:
    """Free-space loss per step from the true Earth range (S1): valid whether or not the terrain is
    known, so a site without terrain still has it (it is not a link margin)."""
    assert ev.geometry
    return [
        _f(20.0 * math.log10(4.0 * math.pi * float(r) * 1000.0 / wavelength_m))
        for r in ev.geometry.earth_range_km
    ]


def _diffraction_terms(ev: "Evaluation") -> dict[str, list[float | None]]:
    """The terms of the diffraction loss of S5 per step: Fresnel-Kirchhoff parameter nu (S2, dominant
    ridge), knife-edge loss J(nu), rounded-ridge correction T (ITU-R P.526-9) and their sum. A step whose
    RF link is unknown (or a known far-terrain block, outside the single-obstacle model) has no
    term: None, never zero."""
    assert ev.terrain and ev.rf
    r = ev.rf
    nu: list[float | None] = []
    for i, obstacle in enumerate(ev.terrain.rf_obstacle):
        nu.append(
            _f(obstacle.nu) if obstacle is not None and r.knife_edge_db[i] is not None else None
        )
    total: list[float | None] = []
    for j, t in zip(r.knife_edge_db, r.ridge_correction_db, strict=True):
        total.append(None if j is None or t is None else _f(j + t))
    return {
        "diffraction_nu": nu,
        "knife_edge_loss_db": [_f(x) for x in r.knife_edge_db],
        "ridge_correction_db": [_f(x) for x in r.ridge_correction_db],
        "diffraction_loss_db": total,
        "multipath_gain_db": [_f(x) for x in r.multipath_gain_db],
    }


def _stamp() -> dict[str, str]:
    """Model identity carried by every view, so a page can state which model its numbers come from."""
    return {"model_version": MODEL_VERSION, "registry_sha256": registry_sha256()}


def parameters_used(sc: "Scenario") -> dict[str, Any]:
    """The values the evaluation actually used (defaults plus overrides), so a page can show them
    without keeping its own copy."""
    from dataclasses import asdict

    return {
        "rf": asdict(sc.rf),
        "energy": sc.energy.to_dict(),
        "scenario": {
            "panel_height_m": sc.panel_height_m,
            "required_margin_db": sc.required_margin_db,
            "dsn_min_elevation_deg": sc.dsn_min_elevation_deg,
        },
    }


def steps(ev: "Evaluation", wavelength_m: float | None = None) -> dict[str, Any]:
    assert ev.geometry and ev.terrain and ev.illumination and ev.rf and ev.dsn and ev.mission
    assert ev.power
    g, t, i, r, d, m, p = (
        ev.geometry, ev.terrain, ev.illumination, ev.rf, ev.dsn, ev.mission, ev.power
    )  # fmt: skip
    fs = {} if wavelength_m is None else {"free_space_loss_db": _free_space_db(ev, wavelength_m)}
    return (
        fs
        | _diffraction_terms(ev)
        | {
            "time_unix": [int(x) for x in ev.grid.t_unix],
            "sun_az_deg": [_f(x) for x in g.sun_az_deg],
            "sun_el_deg": [_f(x) for x in g.sun_el_deg],
            "earth_az_deg": [_f(x) for x in g.earth_az_deg],
            "earth_el_deg": [_f(x) for x in g.earth_el_deg],
            "earth_range_km": [_f(x) for x in g.earth_range_km],
            "sun_horizon_deg": [_f(x) for x in t.sun_horizon_deg],
            "earth_horizon_deg": [_f(x) for x in t.earth_horizon_deg],
            "terrain_reason": _reasons(t.terrain_reason),
            "far_terrain_loss_db": [_f(x) for x in t.far_terrain_loss_db],
            "disc_fraction": [_f(x) for x in i.disc_fraction],
            "lit": list(i.lit),
            "margin_db": [_f(x) for x in r.margin_db],
            "chosen_rate_bps": list(r.chosen_rate_bps),
            "rf_state": list(r.rf_state),
            "rf_closes": list(r.closes),
            "rf_reason": _reasons(r.reason),
            "dsn_visible": list(d.any_visible),
            "gen_w": [_f(x) for x in p.gen_w],
            "soc": [_f(x) for x in p.soc],
            "state": list(m.state),
            "link_usable": list(m.link_usable),
            "useful": list(m.useful),
            "limiting": list(m.limiting),
        }
    )


def _scenario(req: _Common, site: s0.SiteRecord) -> "Scenario":
    from backend.domain.raven.s5_rf import unified_link_inputs

    pl = _pipeline()
    if {"antenna_height_m"} & set(req.rf_overrides):
        raise ParamError("rf")  # D8: the antenna height is a top-level parameter
    antenna_h = float(site.antenna_height_m or req.antenna_height_m)
    panel_h = float(site.panel_height_m or req.panel_height_m)
    rf = unified_link_inputs(
        {
            **req.rf_overrides,
            "rate_bps": float(req.rate_bps),
            "station": req.station,
            "antenna_height_m": antenna_h,
        }
    )
    energy = EnergyParams.from_overrides(req.energy_overrides)
    if set(req.energy_overrides) - set(energy.to_dict()):
        raise ParamError("energy")
    if {"rate_bps", "station"} & set(req.rf_overrides):
        raise ParamError("rf")
    window = s0.TimeWindow(parse_utc(req.start_utc), float(req.days), float(req.step_min))
    s0.build_grid(window)  # validates the window and the per-site cap early
    sc: Scenario = pl.Scenario(
        site,
        window,
        energy,
        rf,
        panel_h,
        reg.value("lunar.ground_station_min_elevation_deg"),
        float(req.required_margin_db),
    )
    return sc


def _site(site_id: str, custom: dict[str, s0.SiteRecord]) -> s0.SiteRecord:
    c = custom.get(site_id)
    return c if c is not None else s0.resolve_site(site_id)


def _terrain_site(site_id: str, custom: dict[str, s0.SiteRecord]) -> s0.SiteRecord:
    """The site as the evaluation needs it. A catalogue site outside the 20 m polar product gets its terrain like a user site:
    the global 237 m product through the terrain service (a download needs the same explicit consent, 409 first). Only /evaluate does this: the ranking of /compare keeps
    comparing sites on the same terrain product. Its identity,
    name and source stay the catalogue's; only the terrain path changes."""
    site = _site(site_id, custom)
    if site.custom or site.dem_coverage is True:
        return site
    try:
        from backend.domain.grazing.dem_select import plan_site

        covered: bool | None = plan_site(site.lat_deg, site.lon_deg_east).status == "ok"
    except (OSError, KeyError, ValueError):
        covered = None
    return dataclasses.replace(site, custom=True, dem_coverage=covered)


def _parse_custom(raw: str | None) -> list[CustomSiteIn]:
    """The compact `custom` query of the snapshot: "id|name|lat|lon[|panel_h|antenna_h]" items."""
    if not raw:
        return []
    out: list[CustomSiteIn] = []
    for item in raw.split(";"):
        f = item.split("|")
        if len(f) not in (4, 6):
            raise ParamError("custom")
        nums = [float(x) for x in f[2:]]
        out.append(
            CustomSiteIn(
                id=f[0],
                name=f[1],
                lat_deg=nums[0],
                lon_deg_east=nums[1],
                panel_height_m=nums[2] if len(nums) > 2 else None,
                antenna_height_m=nums[3] if len(nums) > 3 else None,
            )
        )
    return out


def _key(kind: str, req: BaseModel) -> str:
    from backend.domain.grazing.dem import dem_dir

    canon = json.dumps(
        [kind, str(dem_dir()), req.model_dump(exclude={"allow_download"})],
        sort_keys=True,
        allow_nan=False,
    )
    return "raven:" + hashlib.sha256(canon.encode()).hexdigest()


def _lock_products() -> list[dict[str, Any]]:
    raw = json.loads(
        (Path(__file__).resolve().parents[1] / "domain" / "grazing" / "dem.lock.json").read_text(
            encoding="utf-8"
        )
    )
    return [dict(d) for d in raw["datasets"]]


def _plan_near_id(site: s0.SiteRecord) -> str:
    from backend.domain.grazing.dem_select import plan_site

    plan = plan_site(site.lat_deg, site.lon_deg_east)
    if plan.near_id is None:
        raise ParamError("terrain")
    return plan.near_id


def _warm_terrain_plans() -> None:
    """Plan the terrain of the catalogue sites outside the 20 m product in the background (memoised, about 0.4 s each), so the
    first snapshot of the 3D viewer does not wait for it. Errors are ignored: the plan is made again on demand."""

    def run() -> None:
        try:
            from backend.domain.grazing.dem_select import plan_site

            for x in s0.load_catalog().values():
                if x.dem_coverage is not True:
                    plan_site(x.lat_deg, x.lon_deg_east)
        except (OSError, KeyError, ValueError):
            return

    threading.Thread(target=run, name="terrain-plans", daemon=True).start()


def build_raven_router() -> APIRouter:
    router = APIRouter()

    def svc(request: Request) -> RavenService:
        s: RavenService = request.app.state.raven
        return s

    async def run(
        request: Request,
        key: str,
        compute: Callable[[Any], dict[str, Any]],
        window: s0.TimeWindow | None = None,
    ) -> JSONResponse:
        s = svc(request)
        hit = s.get(key)
        if hit is not None:
            return JSONResponse(hit)

        def work() -> dict[str, Any]:
            warm_imports()
            engine = request.app.state.sky.engine()
            if window is not None:
                lo, hi = engine.supported_range()
                if window.start_utc < lo or window.start_utc + timedelta(days=window.days) > hi:
                    raise TimeError("mission window outside supported ephemeris range")
            return compute(engine)

        try:
            result = await s.compute(work)
        except RavenBusy:
            return _error(503, "troppe analisi in corso", {"Retry-After": "2"})
        except TimeoutError:
            log.warning("RAVEN computation response timed out")
            return _error(504, "analisi scaduta", {"Retry-After": "2"})
        except kernels.EphemerisUnavailable:
            return _error(503, "efemeridi non disponibili", {"Retry-After": "30"})
        except _errors():
            return _error(422, _GENERIC_422)
        except Exception:
            log.exception("errore di calcolo RAVEN")
            return _error(500, "errore interno")
        s.put(key, result)
        return JSONResponse(result)

    @router.post("/api/raven/evaluate")
    async def evaluate_route(request: Request, req: EvaluateRequest) -> JSONResponse:
        try:
            custom = records([req.custom_site] if req.custom_site else [])
            if custom and req.site_id not in custom:
                raise ParamError("site_id")
            site = _terrain_site(req.site_id, custom)
            sc = _scenario(req, site)
        except _errors():
            return _error(422, _GENERIC_422)
        tsv = svc(request).terrain
        early = await tsv.prepare([site] if site.custom else [], req.allow_download)
        if early is not None:
            return early
        kw = tsv.kwargs(site, sc.rf.profile_length_m)

        def compute(engine: Any) -> dict[str, Any]:
            ev = _pipeline().evaluate(sc, engine, **kw)
            out = summary(ev)
            out["parameters_used"] = parameters_used(sc)
            if req.include_steps:
                out["steps"] = steps(ev, sc.rf.wavelength_m)
                out["rf_series"] = {
                    str(rate): [_f(x) for x in values]
                    for rate, values in ev.rf.margin_db_by_rate.items()
                }
            if req.include_windows:
                out["windows"] = _pipeline().refined_windows(ev, sc, engine, **kw)
                out["windows_rule"] = (
                    "edges bisected to 1 s on the criterion at the exact instant (lit, link_usable); "
                    "useful keeps the step resolution (the battery has memory); one change per step assumed; "
                    f"at most {_pipeline().MAX_INSTANT_CALLS} instants are evaluated per request, edges beyond that "
                    "stay at the step boundary and are flagged unresolved"
                )
            return out

        return await run(request, _key("evaluate", req), compute, sc.window)

    @router.post("/api/raven/compare")
    async def compare_route(request: Request, req: CompareRequest) -> JSONResponse:
        try:
            custom = records(req.custom_sites)
            ids = list(dict.fromkeys(req.site_ids))
            if any(c not in ids for c in custom):
                raise ParamError("site_ids")
            scs = [_scenario(req, _site(i, custom)) for i in ids]
            s0.check_total_steps(len(scs), s0.build_grid(scs[0].window).n_steps)
            rank([], req.order)  # validates the order before any computation
        except _errors():
            return _error(422, _GENERIC_422)
        tsv = svc(request).terrain
        early = await tsv.prepare([sc.site for sc in scs if sc.site.custom], req.allow_download)
        if early is not None:
            return early
        kws = [tsv.kwargs(sc.site, sc.rf.profile_length_m) for sc in scs]

        def compute(engine: Any) -> dict[str, Any]:
            evs = [_pipeline().evaluate(sc, engine, **kw) for sc, kw in zip(scs, kws, strict=True)]
            ranking = rank([(e.site.id, components_of(e)) for e in evs], req.order)
            return {
                "model_version": MODEL_VERSION,
                "registry_sha256": registry_sha256(),
                "ranking": ranking,
                "sites": [
                    summary(e) | {"parameters_used": parameters_used(sc)}
                    for e, sc in zip(evs, scs, strict=True)
                ],
            }

        return await run(request, _key("compare", req), compute, scs[0].window)

    @router.get("/api/raven/snapshot")
    async def snapshot_route(
        request: Request, req: Annotated[SnapshotQuery, Query()]
    ) -> JSONResponse:
        try:
            t = parse_utc(req.t)
            from backend.domain.raven.s5_rf import unified_link_inputs

            rf = unified_link_inputs(
                {"rate_bps": req.rate_bps, "station": req.station}
                | ({} if req.gain_dbi is None else {"tx_gain_dbi": req.gain_dbi})
            )
            extra = list(records(_parse_custom(req.custom)).values())
        except _errors():
            return _error(422, _GENERIC_422)
        tsv = svc(request).terrain
        plen = rf.profile_length_m

        def compute(engine: Any) -> dict[str, Any]:
            from backend.domain.raven import views

            cached = tsv.store.cached_checker()

            return (
                views.snapshot(
                    t,
                    rf,
                    engine,
                    extra_sites=extra,
                    terrain_kw_for=lambda site: tsv.kwargs(
                        site, plen, compute=site.id.startswith(s0.CUSTOM_PREFIX)
                    ),
                    cached=cached,
                )
                | _stamp()
            )

        return await run(request, _key("snapshot", req), compute)

    @router.get("/api/raven/scene")
    async def scene_route(request: Request, req: Annotated[SceneQuery, Query()]) -> JSONResponse:
        try:
            t = parse_utc(req.t)
            if (req.lat_deg is None) != (req.lon_deg_east is None):
                raise ParamError("site")
            site = (
                _terrain_site(req.site, {})
                if req.lat_deg is None or req.lon_deg_east is None
                else s0.custom_site(
                    req.site,
                    req.lat_deg,
                    req.lon_deg_east,
                    name=req.name,
                    antenna_height_m=req.antenna_height_m,
                    strict=True,
                )
            )
            if site.dem_coverage is not True:
                return _error(422, "sito fuori copertura DEM")  # the scene needs LOLA terrain
            from backend.domain.raven.s5_rf import unified_link_inputs

            rf = unified_link_inputs(
                {
                    "rate_bps": req.rate_bps,
                    "station": req.station,
                    "antenna_height_m": req.antenna_height_m,
                }
                | ({} if req.gain_dbi is None else {"tx_gain_dbi": req.gain_dbi})
            )
        except _errors():
            return _error(422, _GENERIC_422)
        s = svc(request)
        early = await s.terrain.prepare([site] if site.custom else [], req.allow_download)
        if early is not None:
            return early
        kw = s.terrain.kwargs(site, rf.profile_length_m) if site.custom else None
        if site.custom:
            plan_dem = s.terrain.store.dem(_plan_near_id(site))
        else:
            plan_dem = None

        def compute(engine: Any) -> dict[str, Any]:
            from backend.domain.raven import views

            dem = plan_dem if plan_dem is not None else s.dem()
            prof = s.terrain.store.profiles if site.custom else s.profiles()
            return views.scene(t, site, rf, engine, dem, prof, terrain_kw=kw) | _stamp()

        return await run(request, _key("scene", req), compute)

    @router.post("/api/raven/brief/parse")
    async def brief_parse_route(request: Request, req: BriefParseRequest) -> dict[str, Any]:
        """The brief cascade: the rules first (no network, no tokens); then, only if asked and only for what is still missing, a language model
        (a local one, or the configured online one with the user's consent). What the model proposes must be written in the text."""
        from backend.api import raven_llm
        from backend.api.raven_brief import parse_rules

        rules = parse_rules(req.text)
        out: dict[str, Any] = {
            "level": "rules",
            "model": None,
            "filled_by_model": [],
            "model_error": None,
            "model_available": None,
        }
        if req.use_model and (rules.unresolved or not rules.found):
            try:
                answer = await raven_llm.ask(
                    request, req.text, rules.brief.model_dump(exclude_none=True), req.allow_external
                )
            except (TimeoutError, ValueError, Exception) as exc:  # noqa: BLE001 - a model that fails leaves the rules result, with a generic code
                out["model_error"] = type(exc).__name__
                answer = None
            if answer is None:
                out["model_available"] = out["model_error"] is not None
            else:
                obj, name = answer
                merged, filled, _rej = raven_llm.merge(rules, obj, req.text)
                rules = merged
                out.update(
                    {
                        "level": "rules+model" if filled else "rules",
                        "model": name,
                        "filled_by_model": filled,
                        "model_available": True,
                    }
                )
        return rules.model_dump() | out

    @router.get("/api/raven/overlay")
    async def overlay_route(
        request: Request, req: Annotated[OverlayQuery, Query()]
    ) -> JSONResponse:
        """A remote-sensing style raster of the south-polar disc (height, regional slope, data coverage); no data stays no data."""
        key = _key("overlay", req)
        hit = svc(request).get(key)
        if hit is not None:
            return JSONResponse(hit)
        if (
            req.scope == "global"
        ):  # the whole Moon (equirectangular), shipped; computed offline (scripts/build_overlays_global.py)
            from backend.domain.raven import overlays_global

            whole = overlays_global.load_precomputed(req.layer)
            if whole is None:
                return _error(503, "sovramappa non disponibile")
            svc(request).put(key, whole | _stamp())
            return JSONResponse(whole | _stamp())
        from backend.domain.grazing.dem import FAR_DEM_ID, DemUnavailable, LolaDem, load_lock
        from backend.domain.raven.overlays import compute_overlay, load_precomputed

        shipped = load_precomputed(req.layer, req.size, req.limit_lat_deg)
        if shipped is not None:
            svc(request).put(key, shipped | _stamp())
            return JSONResponse(shipped | _stamp())
        if req.layer in (
            "sun",
            "earth",
            "both",
            "sun_gap",
            "earth_gap",
        ):  # computed offline only (scripts/build_overlays.py)
            return _error(503, "sovramappa non disponibile")

        def work() -> dict[str, Any]:
            def sampler(lat: Any, lon: Any) -> Any:
                dem = LolaDem(spec=load_lock(dataset_id=FAR_DEM_ID), allow_download=False)
                rows, cols = dem.pixel_arrays(lat, lon)
                return dem.heights_m_at_pixels(rows, cols)

            return (
                compute_overlay(
                    req.layer,
                    size=req.size,
                    limit_lat_deg=req.limit_lat_deg,
                    sampler=None if req.layer == "coverage" else sampler,
                )
                | _stamp()
            )

        try:
            out = await svc(request).compute(work)
        except RavenBusy:
            return _error(503, "troppe analisi in corso", {"Retry-After": "2"})
        except TimeoutError:
            return _error(504, "analisi scaduta", {"Retry-After": "2"})
        except DemUnavailable:
            return _error(503, "dati DEM non disponibili", {"Retry-After": "30"})
        except Exception:
            log.exception("errore di calcolo della sovramappa")
            return _error(500, "errore interno")
        svc(request).put(key, out)
        return JSONResponse(out)

    @router.get("/api/raven/horizon")
    async def horizon_route(
        request: Request, req: Annotated[HorizonQuery, Query()]
    ) -> JSONResponse:
        try:
            if (req.lat_deg is None) != (req.lon_deg_east is None):
                raise ParamError("site")
            site = (
                _terrain_site(req.site, {})
                if req.lat_deg is None or req.lon_deg_east is None
                else s0.custom_site(
                    req.site,
                    req.lat_deg,
                    req.lon_deg_east,
                    name=req.name,
                    antenna_height_m=req.height_m,
                    strict=True,
                )
            )
        except _errors():
            return _error(422, _GENERIC_422)
        key = _key("horizon", req)
        hit = svc(request).get(key)
        if hit is not None:
            return JSONResponse(hit)
        from backend.domain.raven import views

        tsv = svc(request).terrain
        early = await tsv.prepare([site] if site.custom else [], req.allow_download)
        if early is not None:
            return early
        hkw = tsv.kwargs(site, reg.value("grazing.profile_length_m")) if site.custom else None

        try:
            out = (
                await svc(request).compute(
                    lambda: views.horizon(site, float(req.height_m), terrain_kw=hkw)
                )
                | _stamp()
            )
        except RavenBusy:
            return _error(503, "troppe analisi in corso", {"Retry-After": "2"})
        except TimeoutError:
            log.warning("RAVEN horizon response timed out")
            return _error(504, "analisi scaduta", {"Retry-After": "2"})
        except Exception:
            log.exception("errore di calcolo dell'orizzonte RAVEN")
            return _error(500, "errore interno")
        svc(request).put(key, out)
        return JSONResponse(out)

    @router.post("/api/raven/terrain-estimate")
    async def terrain_estimate(request: Request, req: EstimateRequest) -> JSONResponse:
        """Dry run for custom sites: product, resolution, range, tiles and MB (total, cached, to
        download), the caps and the disk cache. Never downloads."""
        try:
            recs = list(records(req.sites).values())
        except _errors():
            return _error(422, _GENERIC_422)
        try:
            est = await asyncio.to_thread(svc(request).terrain.store.estimate, recs)
        except Exception:
            log.exception("stima del terreno")
            return _error(500, "errore interno")
        return JSONResponse({"model_version": MODEL_VERSION, **est})

    @router.get("/api/raven/parameters")
    async def parameters() -> JSONResponse:
        return JSONResponse(
            {
                "model_version": MODEL_VERSION,
                "registry_sha256": registry_sha256(),
                "tags": {"V": "primary source", "D": "derived", "I": "illustrative"},
                "parameters": reg.registry_rows(),
                "defaults": _defaults(),
                "duplicated_concepts": {k: list(v) for k, v in reg.DUPLICATED_CONCEPTS.items()},
            }
        )

    @router.get("/api/raven/sites")
    async def sites_route(request: Request) -> JSONResponse:
        """Catalogue with provenance, DEM availability and ephemeris availability (replaces the
        legacy /api/lunar/sites and /api/grazing/status for the pages)."""

        def work() -> dict[str, Any]:
            from backend.domain.grazing.dem import dem_dir, load_lock

            spec = load_lock()
            d = dem_dir()
            tiles = len(list(d.glob("*.f32"))) if d.is_dir() else 0
            try:
                lo, hi = request.app.state.sky.engine().supported_range()
                eph = True
                supported_range = {
                    "start_utc": lo.isoformat().replace("+00:00", "Z"),
                    "end_utc": hi.isoformat().replace("+00:00", "Z"),
                }
            except kernels.EphemerisUnavailable:
                eph = False
                supported_range = None
            return {
                "model_version": MODEL_VERSION,
                "sites": [
                    {**s.to_dict(), "dem_covered": s.lat_deg <= -spec.max_lat_deg}
                    for s in s0.load_catalog().values()
                ],
                "dem": {
                    "available": tiles > 0,
                    "cached_tiles": tiles,
                    "product": {
                        "id": spec.id,
                        "coverage": f"latitude <= -{spec.max_lat_deg:g} degrees",
                        "coverage_north_limit_deg": -spec.max_lat_deg,
                        "credit": spec.credit,
                        "url": spec.url,
                    },
                },
                "ephemeris": {"available": eph, "supported_range": supported_range},
                "custom_sites": {
                    "max": s0.MAX_CUSTOM_SITES,
                    "id_prefix": s0.CUSTOM_PREFIX,
                    "products": [
                        {"id": e["id"], "resolution_m": e["scale_m"]} for e in _lock_products()
                    ],
                    "caps_mb": {"site": 10, "request": 40},
                },
                "disclaimer": DECLARED_LIMITS[0],
            }

        return JSONResponse(await asyncio.to_thread(work))

    @router.get("/api/raven/compensation")
    async def compensation_route() -> JSONResponse:
        """The versioned ridge-correction table (S5 band for the browser mirror), same payload as before."""
        from backend.api.raven_experiments import compensation_report

        return JSONResponse({**await asyncio.to_thread(compensation_report), **_stamp()})

    @router.get("/api/raven/validation")
    async def validation() -> JSONResponse:
        return JSONResponse({"model_version": MODEL_VERSION, **validation_report()})

    @router.get("/api/raven/model")
    async def model() -> JSONResponse:
        lim = s0.default_limits()
        return JSONResponse(
            {
                "model_version": MODEL_VERSION,
                "registry_sha256": registry_sha256(),
                "stages": [{"stage": s, "reads": list(r)} for s, r in STAGE_ORDER],
                "limits": {
                    "max_steps_per_site": lim.max_steps_per_site,
                    "max_steps_total": lim.max_steps_total,
                    "max_days": lim.max_days,
                },
                "declared_limits": list(DECLARED_LIMITS),
                "validation": validation_report(),
                "reliability_study": {
                    "model": RELIABILITY_MODEL,
                    "endpoint": "/api/raven/report/reliability",
                    "qualification": "not_validated",
                    "scope": "Optional conditional RAM/degradation and declared thermal/TID envelope checks, not a flight simulation.",
                },
            }
        )

    _warm_terrain_plans()
    return router


def include_raven_routes(app: FastAPI) -> None:
    app.state.raven = RavenService(
        max_concurrent=env_positive_int("RAVEN_MAX_CONCURRENT", DEFAULT_MAX_CONCURRENT),
        cache_size=env_positive_int("RAVEN_CACHE_SIZE", DEFAULT_CACHE_SIZE),
    )
    app.include_router(build_raven_router())
    app.include_router(build_report_router())
    from backend.api.raven_discover import include_discover_routes

    include_discover_routes(app)
