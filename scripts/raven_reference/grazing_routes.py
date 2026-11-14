# SPDX-License-Identifier: Apache-2.0
"""Endpoint RAVEN (docs/domain/grazinglink-plan.md, modello in grazinglink-model.md).

GET  /api/grazing/status        DEM (prodotto LOLA, tile in cache), tabella di compensazione, efemeridi
GET  /api/grazing/defaults      parametri con etichetta V/D/I, limiti dichiarati, tetti
POST /api/grazing/analyze       finestra geometrica vs reale, diffrazione, multipath, compensatore
POST /api/grazing/compare       confronto siti: stessa analisi per piu' siti, riassunto e classifica (compare.py)
POST /api/grazing/antenna       guadagno, HPBW, diametro, perdita di puntamento, gimbal (X band)
GET  /api/grazing/snapshot      un istante: Terra (az/el/distanza), stato del link e complessi DSN per tutti i siti
GET/POST /api/grazing/scene     scena lander: un istante, campo di quote LOLA, profilo, crinale, zona di Fresnel, margine
GET/POST /api/grazing/wave     onda 3D: split-step di Fresnel oltre una cresta (lama o raggio R), sezione e lama esatta
GET  /api/grazing/compensation  tabella R(nu, raggio) per i grafici, con provenienza e incoerenza aperta
POST /api/grazing/compensator   compromesso interruzioni/dati su una serie di margini fornita

Come `lunar_routes`: calcolo in un thread con tetto globale di richieste concorrenti (503 oltre il tetto),
cache LRU per hash della richiesta, 422 generico senza eco dell'input, 503 senza DEM o senza kernel. Il
terreno e' LOLA (mai inventato), un profilo fornito dall'utente (<= 1500 punti) o, per la geometria,
uno spazzolamento dell'elevazione della Terra scelto dall'utente. Il modulo non importa numpy all'avvio.
"""

import asyncio
import hashlib
import json
import logging
import os
import threading
from collections import OrderedDict
from collections.abc import Callable
from typing import Annotated, Any, Literal

from fastapi import APIRouter, FastAPI, Query, Request
from fastapi.responses import JSONResponse
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    model_validator,
)

from backend.api.custom_sites import CustomSite, resolve_sites
from backend.envconf import env_positive_int
from backend.ephemeris import kernels
from backend.ephemeris.timeutil import TimeError, parse_utc

log = logging.getLogger(__name__)

DEFAULT_MAX_CONCURRENT = 2
DEFAULT_CACHE_SIZE = 16
MAX_PROFILE_POINTS = 1500  # keeps a profile well inside the 64 KiB body limit
MAX_MARGIN_POINTS = 2000
_GENERIC_422 = "parametri non validi"
_DEM_503 = "dati DEM non disponibili"
DISCLAIMER = (
    "Risultati: potenziale nelle ipotesi dichiarate, non una previsione di missione. Ostacolo singolo "
    "dominante; nessuna misura radio reale al polo Sud; parametri del regolite da letteratura; correzione "
    "della cresta arrotondata da ITU-R P.526-9 par. 4.2 (formula verificata sul testo, non misurata), "
    "con lo scarto dallo split-step simulato come incertezza. "
    "I parametri con tag I sono illustrativi, senza fonte."
)

Num = Annotated[float, Field(allow_inf_nan=False)]
Override = StrictInt | StrictFloat | StrictStr | StrictBool


class ProfileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    distance_m: Annotated[
        list[Annotated[float, Field(ge=0, le=100_000, allow_inf_nan=False)]],
        Field(min_length=2, max_length=MAX_PROFILE_POINTS),
    ]
    height_m: Annotated[
        list[Annotated[float, Field(ge=-20_000, le=20_000, allow_inf_nan=False)]],
        Field(min_length=2, max_length=MAX_PROFILE_POINTS),
    ]


class SweepIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    el_start_deg: Annotated[float, Field(ge=-30, le=60, allow_inf_nan=False)]
    el_end_deg: Annotated[float, Field(ge=-30, le=60, allow_inf_nan=False)]
    range_km: Annotated[float, Field(ge=300_000, le=450_000, allow_inf_nan=False)] = 384_400.0
    az_deg: Annotated[float, Field(ge=0, lt=360, allow_inf_nan=False)] = 0.0


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    site_id: Annotated[str, Field(min_length=1, max_length=40)] | None = None
    start_utc: Annotated[str, Field(min_length=20, max_length=32)]
    days: Annotated[float, Field(gt=0, le=90, allow_inf_nan=False)] = 30.0
    step_min: Annotated[float, Field(ge=1, le=1440, allow_inf_nan=False)] = 15.0
    overrides: Annotated[
        dict[Annotated[str, Field(max_length=48)], Override], Field(max_length=32)
    ] = {}
    profile: ProfileIn | None = None
    earth_sweep: SweepIn | None = None


class CompareRequest(BaseModel):
    """Confronto siti: stessa finestra, passo, stazione, antenna, bit-rate e k (negli `overrides`) per tutti i siti."""

    model_config = ConfigDict(extra="forbid")
    site_ids: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=40)]], Field(min_length=1, max_length=8)
    ]
    custom_sites: Annotated[list[CustomSite], Field(max_length=2)] = []
    start_utc: Annotated[str, Field(min_length=20, max_length=32)]
    days: Annotated[float, Field(gt=0, le=90, allow_inf_nan=False)] = 5.0
    step_min: Annotated[float, Field(ge=1, le=1440, allow_inf_nan=False)] = 30.0
    timeline: StrictBool = False
    overrides: Annotated[
        dict[Annotated[str, Field(max_length=48)], Override], Field(max_length=32)
    ] = {}

    @model_validator(mode="after")
    def _unique(self) -> "CompareRequest":
        self.site_ids = list(dict.fromkeys(self.site_ids))
        return self


class AntennaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    station: Literal["dsn34", "dsn18"] = "dsn34"
    frequency_ghz: Annotated[float, Field(ge=0.1, le=40, allow_inf_nan=False)] = 8.4
    eta: Annotated[float, Field(gt=0.2, le=1, allow_inf_nan=False)] = 0.55
    rates_bps: Annotated[
        list[Annotated[float, Field(ge=1e2, le=1e10, allow_inf_nan=False)]],
        Field(min_length=1, max_length=12),
    ] = [1e3, 1e4, 1e5, 1e6, 1e7, 1e8]
    diameters_m: Annotated[
        list[Annotated[float, Field(ge=0.01, le=100, allow_inf_nan=False)]],
        Field(min_length=1, max_length=12),
    ] = [0.1, 0.2, 0.3, 0.5, 1.0]
    tx_power_dbw: Annotated[float, Field(ge=-20, le=40, allow_inf_nan=False)] = 10.0
    tsys_k: Annotated[float, Field(ge=10, le=300, allow_inf_nan=False)] = 30.0
    ebn0_db: Annotated[float, Field(ge=0, le=15, allow_inf_nan=False)] = 2.5
    losses_db: Annotated[float, Field(ge=0, le=20, allow_inf_nan=False)] = 3.0
    margin_db: Annotated[float, Field(ge=0, le=20, allow_inf_nan=False)] = 3.0
    distance_km: Annotated[float, Field(ge=300_000, le=450_000, allow_inf_nan=False)] = 384_400.0
    excursion_deg: Annotated[float, Field(ge=0, le=90, allow_inf_nan=False)] = 10.36
    gimbal_budget_db: Annotated[float, Field(ge=0.1, le=10, allow_inf_nan=False)] = 1.0


class CompensatorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    margin_db: Annotated[
        list[Annotated[float, Field(ge=-500, le=500, allow_inf_nan=False)]],
        Field(min_length=1, max_length=MAX_MARGIN_POINTS),
    ]
    reference_rate_bps: Annotated[float, Field(ge=1, le=1e10, allow_inf_nan=False)] = 1e4
    rates_bps: Annotated[
        list[Annotated[float, Field(ge=1, le=1e10, allow_inf_nan=False)]],
        Field(min_length=1, max_length=12),
    ] = [1e4, 3e4, 1e5, 3e5, 1e6, 3e6]
    k_values: Annotated[
        list[Annotated[float, Field(ge=0, le=6, allow_inf_nan=False)]],
        Field(min_length=1, max_length=8),
    ] = [0.0, 1.0, 2.33, 3.0]
    sigma_db: Annotated[float, Field(ge=0, le=10, allow_inf_nan=False)] = 1.5
    truth_offset_db: Annotated[float, Field(ge=-20, le=20, allow_inf_nan=False)] = 0.0
    step_s: Annotated[float, Field(ge=1, le=86400, allow_inf_nan=False)] = 900.0
    seed: Annotated[int, Field(ge=0, le=2**31 - 1)] = 3


class WaveRequest(BaseModel):
    """Onda 3D. Lunghezza d'onda o frequenza (non entrambe; default 0.0357 m, come la bozza). Gli ingressi sono
    quantizzati (chiave di cache): lambda 1e-5 m, frequenza 1e-3 GHz, raggio/y/step 0.1 m, distanza 1 m, dy 0.01 m."""

    model_config = ConfigDict(extra="forbid")
    wavelength_m: Annotated[float, Field(ge=0.005, le=1.0, allow_inf_nan=False)] | None = None
    frequency_ghz: Annotated[float, Field(ge=0.3, le=60.0, allow_inf_nan=False)] | None = None
    radius_m: Annotated[float, Field(ge=0, le=400, allow_inf_nan=False)] = 0.0
    distance_m: Annotated[float, Field(ge=100, le=5000, allow_inf_nan=False)] = 2000.0
    step_m: Annotated[float, Field(ge=0.5, le=1000, allow_inf_nan=False)] = 20.0
    y_min_m: Annotated[float, Field(ge=-200, le=-1, allow_inf_nan=False)] = -40.0
    y_max_m: Annotated[float, Field(ge=1, le=200, allow_inf_nan=False)] = 40.0
    dy_m: Annotated[float, Field(ge=0.05, le=0.4, allow_inf_nan=False)] = 0.1
    nx: Annotated[int, Field(ge=2, le=120)] = 100
    ny: Annotated[int, Field(ge=2, le=160)] = 160
    n_section: Annotated[int, Field(ge=2, le=800)] = 400

    @model_validator(mode="after")
    def _quantise(self) -> "WaveRequest":
        if self.wavelength_m is not None and self.frequency_ghz is not None:
            raise ValueError("wavelength_m or frequency_ghz, not both")
        if self.frequency_ghz is not None:
            self.frequency_ghz = round(self.frequency_ghz, 3)
        elif self.wavelength_m is not None:
            self.wavelength_m = round(self.wavelength_m, 5)
        else:
            self.wavelength_m = 0.0357
        self.radius_m = round(self.radius_m, 1)
        self.distance_m = float(round(self.distance_m))
        self.step_m = round(self.step_m, 1)
        self.y_min_m = round(self.y_min_m, 1)
        self.y_max_m = round(self.y_max_m, 1)
        self.dy_m = round(self.dy_m, 2)
        return self


class SnapshotRequest(BaseModel):
    """Un solo istante UTC, bit-rate, stazione e guadagno del rover opzionale."""

    model_config = ConfigDict(extra="forbid")
    t: Annotated[str, Field(min_length=20, max_length=32)]
    rate_bps: Annotated[float, Field(ge=1e2, le=1e10, allow_inf_nan=False)] = 1e4
    station: Literal["dsn34", "dsn18"] = "dsn34"
    gain: Annotated[float | None, Field(ge=-10, le=45, allow_inf_nan=False)] = None

    @model_validator(mode="after")
    def _canonical(self) -> "SnapshotRequest":
        try:
            self.t = parse_utc(self.t).strftime("%Y-%m-%dT%H:%M:%SZ")
        except (TimeError, ValueError):
            pass  # rejected (generic 422) when the work runs
        return self


class SceneRequest(BaseModel):
    """Scena lander: un istante UTC (quantizzato al secondo), sito, stazione, guadagno dell'antenna del rover (dBi),
    bit-rate e altezza del palo (m). Il profilo utente e' solo nel POST (il sito serve per la geometria)."""

    model_config = ConfigDict(extra="forbid")
    site: Annotated[str, Field(min_length=1, max_length=40)]
    t: Annotated[str, Field(min_length=20, max_length=32)]
    station: Literal["dsn34", "dsn18"] = "dsn34"
    gain: Annotated[float, Field(ge=-10, le=45, allow_inf_nan=False)] = 15.0
    rate: Annotated[float, Field(ge=1e4, le=3e6, allow_inf_nan=False)] = 1e5
    mast: Annotated[float, Field(ge=0.1, le=100, allow_inf_nan=False)] = 2.0

    @model_validator(mode="after")
    def _canonical(self) -> "SceneRequest":
        try:
            self.t = parse_utc(self.t).strftime("%Y-%m-%dT%H:%M:%SZ")
        except (TimeError, ValueError):
            pass  # rejected (generic 422) when the work runs
        self.gain = round(self.gain, 2)
        self.mast = round(self.mast, 2)
        return self


class ScenePostRequest(SceneRequest):
    profile: ProfileIn | None = None
    custom_site: CustomSite | None = None


class GrazingService:
    def __init__(self, *, max_concurrent: int, cache_size: int, allow_download: bool) -> None:
        self.max_concurrent = max_concurrent
        self.cache_size = cache_size
        self.allow_download = allow_download
        self.sem = asyncio.Semaphore(max_concurrent)
        self._cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._lock = threading.Lock()
        self._dem: Any = None
        self._profiles: Any = None
        self.computed = 0

    def limits(self) -> dict[str, Any]:
        return {
            "max_concurrent": self.max_concurrent,
            "cache_size": self.cache_size,
            "max_samples": 5000,
            "compare_max_sites": 8,
            "compare_max_steps_per_site": 1500,
            "compare_max_total_samples": 6000,
            "days_max": 90,
            "step_min_min": 1,
            "max_profile_points": MAX_PROFILE_POINTS,
            "max_margin_points": MAX_MARGIN_POINTS,
            "azimuth_quantum_deg": 0.1,
            "dem_download_on_demand": self.allow_download,
        }

    @staticmethod
    def cache_key(kind: str, req: BaseModel) -> str:
        canon = json.dumps(
            [kind, req.model_dump()], sort_keys=True, separators=(",", ":"), allow_nan=False
        )
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

    def dem(self) -> Any:
        from backend.domain.grazing.dem import LolaDem

        with self._lock:
            if self._dem is None:
                self._dem = LolaDem(allow_download=self.allow_download)
            return self._dem

    def profiles(self) -> Any:
        from backend.domain.grazing.analysis import ProfileCache

        with self._lock:
            if self._profiles is None:
                self._profiles = ProfileCache()
            return self._profiles

    def cached_tiles(self) -> int:
        from backend.domain.grazing.dem import dem_dir

        d = dem_dir()
        return len(list(d.glob("*.f32"))) if d.is_dir() else 0

    # -- synchronous workers (run in a thread) ---------------------------------------------------
    def analyze(self, engine_getter: Callable[[], Any], req: AnalyzeRequest) -> dict[str, Any]:
        from backend.domain.grazing.analysis import (
            OUT_OF_COVERAGE_MESSAGE,
            AnalysisWindow,
            EarthSweep,
            GrazingParamError,
            LinkInputs,
            analyze,
        )
        from backend.domain.grazing.dem import DemOutOfCoverage
        from backend.domain.grazing.terrain import profile_from_user
        from backend.domain.lunar.model import load_sites

        site: tuple[float, float] | None = None
        if req.site_id is not None:
            found = {s.id: s for s in load_sites()}.get(req.site_id)
            if found is None:
                raise GrazingParamError("site_id")
            site = (found.lat_deg, found.lon_deg_east)
        sweep = None
        if req.earth_sweep is not None:
            e = req.earth_sweep
            sweep = EarthSweep(e.el_start_deg, e.el_end_deg, e.range_km, e.az_deg)
        if site is None and sweep is None:
            raise GrazingParamError("site_id")
        window = AnalysisWindow.build(req.start_utc, req.days, req.step_min)
        inputs = LinkInputs.from_overrides(req.overrides)
        profile = None
        if req.profile is not None:
            if len(req.profile.distance_m) != len(req.profile.height_m):
                raise GrazingParamError("profile")
            profile = profile_from_user(req.profile.distance_m, req.profile.height_m)
        dem = self.dem() if profile is None else None
        if dem is not None and site is not None and site[0] > -dem.spec.max_lat_deg:
            raise DemOutOfCoverage(OUT_OF_COVERAGE_MESSAGE)  # before touching kernels or tiles
        engine = engine_getter() if sweep is None else None
        out = analyze(
            window=window,
            inputs=inputs,
            site=site,
            site_id=req.site_id,
            dem=dem,
            profile=profile,
            sweep=sweep,
            engine=engine,
            cache=self.profiles(),
        )
        self.computed += 1
        return out


def compare_report(
    service: GrazingService, engine_getter: Callable[[], Any], req: CompareRequest
) -> dict[str, Any]:
    """Un'analisi RAVEN per ogni sito coperto dal DEM; gli altri restano senza numeri."""
    from backend.domain.grazing import compare as cmp
    from backend.domain.grazing.analysis import (
        AnalysisWindow,
        GrazingParamError,
        LinkInputs,
        analyze,
    )

    registry = resolve_sites(req.site_ids, req.custom_sites)
    window = AnalysisWindow.build(req.start_utc, req.days, req.step_min)
    if window.n_steps > cmp.MAX_STEPS_PER_SITE:
        raise GrazingParamError("too_many_samples")
    inputs = LinkInputs.from_overrides(req.overrides)
    dem = service.dem()
    covered = [i for i in req.site_ids if registry[i].lat_deg <= -dem.spec.max_lat_deg]
    if len(covered) * window.n_steps > cmp.MAX_TOTAL_SAMPLES:
        raise GrazingParamError("too_many_samples")
    engine = engine_getter() if covered else None
    rows: list[dict[str, Any]] = []
    parameters: list[dict[str, Any]] = inputs.used_parameters()
    for sid in req.site_ids:
        x = registry[sid]
        meta = {"id": x.id, "name": x.name, "lat_deg": x.lat_deg, "lon_deg_east": x.lon_deg_east}
        if sid not in covered:
            rows.append(cmp.uncovered_row(meta))
            continue
        res = analyze(
            window=window,
            inputs=inputs,
            site=(x.lat_deg, x.lon_deg_east),
            site_id=x.id,
            dem=dem,
            engine=engine,
            cache=service.profiles(),
            include_window_samples=req.timeline,
        )
        rows.append(cmp.summarise(meta, res))
    order = cmp.rank_rows(rows)
    service.computed += 1
    return {
        "label": "potential under stated assumptions",
        "window": {
            "start_utc": window.start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "days": window.days,
            "step_min": window.step_min,
            "n_steps": window.n_steps,
        },
        "sites": rows,
        "ranking": order,
        "ranking_rule": cmp.RANKING_RULE,
        "ranking_columns": ["real_hours", "margin_median_db"],
        "uncovered_state": cmp.UNCOVERED_STATE,
        "rate_bps": inputs.rate_bps,
        "station": inputs.station,
        "k": inputs.compensator_k,
        "parameters": parameters,
        "disclaimer": DISCLAIMER,
    }


def snapshot_report(
    service: GrazingService, engine_getter: Callable[[], Any], req: SnapshotRequest
) -> dict[str, Any]:
    from backend.domain.grazing.analysis import LinkInputs
    from backend.domain.grazing.snapshot import snapshot

    overrides: dict[str, Any] = {"rate_bps": req.rate_bps, "station": req.station}
    if req.gain is not None:
        overrides["tx_gain_dbi"] = req.gain
    inputs = LinkInputs.from_overrides(overrides)
    out = snapshot(parse_utc(req.t), inputs, engine_getter(), service.dem, service.profiles())
    service.computed += 1
    return out


def scene_report(
    service: GrazingService, engine_getter: Callable[[], Any], req: SceneRequest
) -> dict[str, Any]:
    from backend.domain.grazing.analysis import GrazingParamError, LinkInputs
    from backend.domain.grazing.dem import DemOutOfCoverage
    from backend.domain.grazing.scene import scene
    from backend.domain.grazing.terrain import profile_from_user

    user_site = getattr(req, "custom_site", None)
    found = resolve_sites([req.site], [user_site] if user_site is not None else [])[req.site]
    profile = None
    user = getattr(req, "profile", None)
    if user is not None:
        if len(user.distance_m) != len(user.height_m):
            raise GrazingParamError("profile")
        profile = profile_from_user(user.distance_m, user.height_m)
    dem = service.dem() if profile is None else None
    if dem is not None and found.lat_deg > -dem.spec.max_lat_deg:
        from backend.domain.grazing.analysis import OUT_OF_COVERAGE_MESSAGE

        raise DemOutOfCoverage(OUT_OF_COVERAGE_MESSAGE)  # before touching kernels or tiles
    inputs = LinkInputs.from_overrides(
        {
            "rate_bps": req.rate,
            "station": req.station,
            "tx_gain_dbi": req.gain,
            "antenna_height_m": req.mast,
        }
    )
    out = scene(
        t=parse_utc(req.t),
        site=(found.lat_deg, found.lon_deg_east),
        site_id=found.id,
        inputs=inputs,
        engine=engine_getter(),
        dem=dem,
        cache=service.profiles(),
        profile=profile,
    )
    out["disclaimer"] = DISCLAIMER
    service.computed += 1
    return out


def antenna_report(req: AntennaRequest) -> dict[str, Any]:
    import math

    from backend.domain.grazing import antenna as ant

    f = req.frequency_ghz * 1e9
    st = ant.STATIONS[req.station]
    link = {
        "distance_m": req.distance_km * 1000.0,
        "tx_power_dbw": req.tx_power_dbw,
        "tsys_k": req.tsys_k,
        "ebn0_db": req.ebn0_db,
        "losses_db": req.losses_db,
        "margin_db": req.margin_db,
    }
    table = ant.antenna_table(st, tuple(req.rates_bps), frequency_hz=f, eta=req.eta, **link)
    dishes = []
    for d in req.diameters_m:
        hs = float(ant.hpbw_deg(d, f, "script_70"))
        hu = float(ant.hpbw_deg(d, f, "uniform"))
        dishes.append(
            {
                "diameter_m": d,
                "gain_dbi": round(float(ant.gain_dbi(d, f, req.eta)), 2),
                "hpbw_script_70_deg": round(hs, 3),
                "hpbw_uniform_deg": round(hu, 3),
                "hpbw_ratio": round(hs / hu, 4),
                "pointing": [
                    ant.pointing_loss_compare(x * hs, d, f) for x in (0.25, 0.5, 0.75, 1.0)
                ],
                "gimbal": ant.gimbal_assessment(
                    hs, req.excursion_deg, max_loss_db=req.gimbal_budget_db
                ),
            }
        )
    return {
        "frequency_ghz": req.frequency_ghz,
        "eta": req.eta,
        "eta_tag": "I",
        "station": st.to_dict(f),
        "stations": [s.to_dict(f) for s in ant.STATIONS.values()],
        "required_gain": table,
        "dishes": dishes,
        "uniform_hpbw_factor": ant.hpbw_factor_uniform(),
        "script_hpbw_factor": ant.HPBW_FACTOR_SCRIPT,
        "pointing_constants": {"script": 12.0, "gaussian_exact": ant.GAUSSIAN_DB_PER_X2},
        "earth_angular_diameter_deg": round(
            math.degrees(2.0 * math.atan(6371.0 / req.distance_km)), 4
        ),
        "excursion_deg": req.excursion_deg,
        "excursion_tag": "I (script: hypot(6.7, 7.9)); la finestra RAVEN la calcola dalle efemeridi (D)",
        "note": "formule dello script e varianti corrette affiancate; i guadagni delle stazioni sono tag I",
        "disclaimer": DISCLAIMER,
    }


def compensation_report() -> dict[str, Any]:
    from backend.domain.grazing.compensation import consistency_diagnostic, load_table

    tb = load_table()
    return {
        "nu": tb.nu.tolist(),
        "radius_m": tb.radius_m.tolist(),
        "correction_db": tb.correction_db.tolist(),
        "simulated_db": tb.simulated_db.tolist(),
        "oscillation_envelope_db": tb.envelope_db.tolist(),
        "anomaly": tb.anomaly.astype(int).tolist(),
        "axes": "[radius][nu]; interpolazione bilineare in (nu, log10(raggio + 1))",
        "info": tb.info(),
        "inconsistency": consistency_diagnostic(tb),
        "disclaimer": DISCLAIMER,
    }


def compensator_report(req: CompensatorRequest) -> dict[str, Any]:
    import numpy as np

    from backend.domain.grazing import bitrate as br

    pred = br.margin_matrix(req.margin_db, req.reference_rate_bps, req.rates_bps)
    rows = br.tradeoff(
        pred,
        pred + req.truth_offset_db,
        req.rates_bps,
        tuple(dict.fromkeys(req.k_values)),
        req.sigma_db,
        req.step_s,
        req.seed,
    )
    return {
        "n_steps": len(req.margin_db),
        "rates_bps": req.rates_bps,
        "sigma_db": req.sigma_db,
        "seed": req.seed,
        "rows": [r.to_dict(include_series=True) for r in rows],
        "rule": "R_b* = max{R_b : margine previsto - k sigma >= 0}; interruzione se margine vero + N(0, sigma) < 0",
        "note": "feedforward + margine statistico, non apprendimento per rinforzo; parametri tag I",
        "predicted_margin_min_db": float(np.min(pred)),
        "disclaimer": DISCLAIMER,
    }


def wave_report(req: WaveRequest) -> dict[str, Any]:
    from backend.domain.grazing.wave import C_LIGHT, WaveParams, simulate_wave

    lam = (
        req.wavelength_m
        if req.wavelength_m is not None
        else C_LIGHT / (req.frequency_ghz or 1.0) / 1e9
    )
    out = simulate_wave(
        WaveParams(
            wavelength_m=lam,
            radius_m=req.radius_m,
            distance_m=req.distance_m,
            step_m=req.step_m,
            y_min_m=req.y_min_m,
            y_max_m=req.y_max_m,
            dy_m=req.dy_m,
            nx=req.nx,
            ny=req.ny,
            n_section=req.n_section,
        )
    )
    out["disclaimer"] = (
        "Modello scalare 2D parassiale (split-step di Fresnel), onda piana, cresta assorbente; finestra FFT "
        "periodica; nessuna curvatura lunare ne suolo. La cresta arrotondata e' simulata e non validata "
        "(15-45 % sotto ITU-R P.526-9 eq. (30)-(32) a passo fine). Lama esatta: JPL 42-226 eq. (38)."
    )
    return out


_warm_lock = threading.Lock()
_warmed = False


def _warm_imports() -> None:
    """Import the heavy modules once, serialised: two threads importing different scipy submodules at the
    same time can deadlock on scipy.linalg (observed under concurrent first requests)."""
    global _warmed
    if _warmed:
        return
    with _warm_lock:
        if _warmed:
            return
        import backend.domain.grazing.analysis
        import backend.domain.grazing.antenna
        import backend.domain.grazing.bitrate
        import backend.domain.grazing.compare
        import backend.domain.grazing.compensation
        import backend.domain.grazing.scene
        import backend.domain.grazing.snapshot
        import backend.domain.grazing.wave  # noqa: F401

        _warmed = True


def _error(status: int, detail: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"detail": detail}, status_code=status, headers=headers)


def build_grazing_router() -> APIRouter:
    router = APIRouter()

    def svc(request: Request) -> GrazingService:
        s: GrazingService = request.app.state.grazing
        return s

    async def run(
        request: Request, kind: str, req: BaseModel, work: Callable[[], dict[str, Any]]
    ) -> JSONResponse:
        from backend.domain.grazing.analysis import OUT_OF_COVERAGE_MESSAGE
        from backend.domain.grazing.dem import DemOutOfCoverage, DemUnavailable
        from backend.domain.grazing.gimbal import GimbalUnavailable

        s = svc(request)
        try:
            key = s.cache_key(kind, req)
        except ValueError:
            return _error(422, _GENERIC_422)
        hit = s.get(key)
        if hit is not None:
            return JSONResponse(hit)
        if s.sem.locked():
            return _error(503, "troppe analisi in corso", {"Retry-After": "2"})
        await asyncio.to_thread(_warm_imports)
        try:
            async with s.sem:
                result = await asyncio.to_thread(work)
        except DemUnavailable:
            return _error(503, _DEM_503, {"Retry-After": "30"})
        except kernels.EphemerisUnavailable:
            return _error(503, "efemeridi non disponibili", {"Retry-After": "30"})
        except GimbalUnavailable:
            log.exception("simulatore gimbal C non disponibile")
            return _error(503, "simulatore gimbal C non disponibile")
        except DemOutOfCoverage:
            return _error(422, OUT_OF_COVERAGE_MESSAGE)
        except (TimeError, ValueError):  # GrazingParamError, TerrainError: never the input
            return _error(422, _GENERIC_422)
        except Exception:
            log.exception("errore di calcolo RAVEN")
            return _error(500, "errore interno")
        s.put(key, result)
        return JSONResponse(result)

    @router.get("/api/grazing/status")
    async def status(request: Request) -> JSONResponse:
        s = svc(request)

        def work() -> dict[str, Any]:
            _warm_imports()
            from backend.domain.grazing.compensation import load_table
            from backend.domain.grazing.dem import load_lock
            from backend.domain.lunar.model import load_sites

            spec = load_lock()
            tiles = s.cached_tiles()
            try:
                request.app.state.sky.engine()
                eph = True
            except kernels.EphemerisUnavailable:
                eph = False
            return {
                "dem": {
                    "available": tiles > 0 or s.allow_download,
                    "cached_tiles": tiles,
                    "mode": "download-on-demand" if s.allow_download else "cache-only",
                    "product": {
                        "id": spec.id,
                        "size": spec.size,
                        "sha256": spec.sha256,
                        "etag": spec.etag,
                        "scale_m": spec.scale_m,
                        "coverage": f"latitudine <= -{spec.max_lat_deg:g} gradi",
                        "coverage_north_limit_deg": -spec.max_lat_deg,
                        "retrieved": spec.retrieved,
                        "credit": spec.credit,
                        "url": spec.url,
                    },
                    "hint": "make grazing-dem scarica i tile dei siti predefiniti in build/lola",
                },
                "ephemeris": {"available": eph},
                "compensation_table": load_table().info(),
                "sites": [
                    {
                        "id": x.id,
                        "name": x.name,
                        "lat_deg": x.lat_deg,
                        "lon_deg_east": x.lon_deg_east,
                        "dem_covered": x.lat_deg <= -spec.max_lat_deg,
                    }
                    for x in load_sites()
                ],
                "limits": s.limits(),
                "disclaimer": DISCLAIMER,
            }

        return JSONResponse(await asyncio.to_thread(work))

    @router.get("/api/grazing/defaults")
    async def defaults(request: Request) -> JSONResponse:
        from backend.domain.grazing import antenna as ant
        from backend.domain.grazing import bitrate as br
        from backend.domain.grazing.analysis import DECLARED_LIMITS
        from backend.domain.grazing.model import PARAMS

        rows = [
            {
                "key": p.key,
                "value": p.default,
                "unit": p.unit,
                "min": p.lo,
                "max": p.hi,
                "status": p.status,
                "source": p.source,
                "note": p.note,
            }
            for p in PARAMS.values()
        ]
        return JSONResponse(
            {
                "parameters": rows,
                "stations": [x.to_dict(8.4e9) for x in ant.STATIONS.values()],
                "rates_bps": list(br.DEFAULT_RATES_BPS),
                "k_values": list(br.DEFAULT_K_VALUES),
                "status_legend": {
                    "V": "valore letto in una fonte primaria (con pagina)",
                    "D": "derivato con formula ripetibile",
                    "I": "illustrativo, nessuna fonte",
                },
                "declared_limits": list(DECLARED_LIMITS),
                "limits": svc(request).limits(),
                "disclaimer": DISCLAIMER,
            }
        )

    @router.post("/api/grazing/analyze")
    async def analyze(request: Request, req: AnalyzeRequest) -> JSONResponse:
        s = svc(request)
        sky = request.app.state.sky
        return await run(request, "analyze", req, lambda: s.analyze(sky.engine, req))

    @router.post("/api/grazing/compare")
    async def compare(request: Request, req: CompareRequest) -> JSONResponse:
        s = svc(request)
        sky = request.app.state.sky
        return await run(request, "compare", req, lambda: compare_report(s, sky.engine, req))

    @router.post("/api/grazing/antenna")
    async def antenna(request: Request, req: AntennaRequest) -> JSONResponse:
        return await run(request, "antenna", req, lambda: antenna_report(req))

    @router.get("/api/grazing/snapshot")
    async def snapshot_get(
        request: Request, req: Annotated[SnapshotRequest, Query()]
    ) -> JSONResponse:
        s = svc(request)
        sky = request.app.state.sky
        return await run(request, "snapshot", req, lambda: snapshot_report(s, sky.engine, req))

    @router.get("/api/grazing/scene")
    async def scene_get(request: Request, req: Annotated[SceneRequest, Query()]) -> JSONResponse:
        s = svc(request)
        sky = request.app.state.sky
        return await run(request, "scene", req, lambda: scene_report(s, sky.engine, req))

    @router.post("/api/grazing/scene")
    async def scene_post(request: Request, req: ScenePostRequest) -> JSONResponse:
        s = svc(request)
        sky = request.app.state.sky
        return await run(request, "scene", req, lambda: scene_report(s, sky.engine, req))

    @router.get("/api/grazing/compensation")
    async def compensation() -> JSONResponse:
        await asyncio.to_thread(_warm_imports)
        return JSONResponse(await asyncio.to_thread(compensation_report))

    @router.post("/api/grazing/compensator")
    async def compensator(request: Request, req: CompensatorRequest) -> JSONResponse:
        return await run(request, "compensator", req, lambda: compensator_report(req))

    @router.get("/api/grazing/wave")
    async def wave_get(request: Request, req: Annotated[WaveRequest, Query()]) -> JSONResponse:
        return await run(request, "wave", req, lambda: wave_report(req))

    @router.post("/api/grazing/wave")
    async def wave_post(request: Request, req: WaveRequest) -> JSONResponse:
        return await run(request, "wave", req, lambda: wave_report(req))

    return router


def include_grazing_routes(app: FastAPI) -> None:
    app.state.grazing = GrazingService(
        max_concurrent=env_positive_int("GRAZING_MAX_CONCURRENT", DEFAULT_MAX_CONCURRENT),
        cache_size=env_positive_int("GRAZING_CACHE_SIZE", DEFAULT_CACHE_SIZE),
        allow_download=os.environ.get("GRAZING_DEM_ALLOW_DOWNLOAD", "1") != "0",
    )
    app.include_router(build_grazing_router())
