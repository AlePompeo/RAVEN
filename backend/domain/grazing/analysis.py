# SPDX-License-Identifier: Apache-2.0
"""GrazingLink analysis for a site and a time window: geometric visibility vs the real link margin.

Per step: Earth az/el/range (geometry.py, ephemerides), dominant ridge on the terrain profile cut at
the Earth azimuth (terrain.py; profiles cached by azimuth quantised to 0.1 deg), exact knife-edge loss
plus the rounded-ridge table correction (compensation.py), two-ray multipath only where applicable
(multipath.py), free-space loss with the true distance, antenna gain and pointing loss (antenna.py) and
the margin for every candidate bit rate. The link sum (dB):

    M(R_b) = P_t + G_t + G_r - L_pt - FSPL - L_misc - J(nu) - R(nu, radius) + G2 - N0 - EbN0 - 10 log10 R_b

Every parameter used is returned with its V/D/I tag. No data is invented: the terrain is LOLA (product
id from dem.lock.json), a validated user profile, or an explicitly flagged synthetic test profile.
Sites outside the DEM coverage raise `DemOutOfCoverage` ('fuori copertura DEM').
"""

import math
import threading
from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields, replace
from datetime import datetime, timedelta
from typing import Any, Literal

import numpy as np
from numpy.typing import NDArray

from backend.domain.grazing import antenna as ant
from backend.domain.grazing import bitrate as br
from backend.domain.grazing.compensation import (
    consistency_diagnostic,
    load_table,
    ridge_correction,
)
from backend.domain.grazing.dem import DemOutOfCoverage, LolaDem
from backend.domain.grazing.diffraction import knife_edge_loss_db
from backend.domain.grazing.geometry import (
    EarthGeometry,
    EphemerisLike,
    earth_geometry,
    free_space_loss_series_db,
)
from backend.domain.grazing.model import PARAMS
from backend.domain.grazing.multipath import NOT_APPLICABLE, two_ray
from backend.domain.grazing.terrain import (
    DominantRidge,
    TerrainProfile,
    dominant_ridge,
    profile_from_dem,
)
from backend.ephemeris.timeutil import parse_utc

__all__ = [
    "AZIMUTH_QUANTUM_DEG",
    "MAX_SAMPLES",
    "OUT_OF_COVERAGE_MESSAGE",
    "AnalysisWindow",
    "EarthSweep",
    "GrazingParamError",
    "LinkInputs",
    "ProfileCache",
    "analyze",
]

Arr = NDArray[np.float64]
AZIMUTH_QUANTUM_DEG = 0.1
MAX_SAMPLES = 5000
MAX_OUTPUT_POINTS = 1500
MAX_INTERVALS = 100
OUT_OF_COVERAGE_MESSAGE = (
    "sito fuori copertura DEM (il prodotto LOLA copre latitudini <= -85 gradi)"
)
C_MS = 299_792_458.0
TABLE_REFERENCE_D1_M = 2000.0
RATES_BPS = br.DEFAULT_RATES_BPS
Mount = Literal["tracking", "fixed", "gimbal"]

DECLARED_LIMITS = (
    "Ostacolo singolo dominante (massimo nu sul profilo): nessuna diffrazione multipla; errore non stimato.",
    "Nessuna misura radio reale al polo Sud: il modello non e' validato (anche JPL 42-226 p. 40: validazione sperimentale in sospeso).",
    "Parametri del regolite (eps_r, rugosita') da letteratura (JPL 42-226 Tab. 1, ingressi di simulazione in banda S), non misurati al sito.",
    "Multipath a due raggi su suolo piano, solo parte coerente; il raggio riflesso usa la diffrazione del diretto.",
    "Profilo del terreno lungo il solo azimut del centro della Terra; il disco (0.9-1.0 deg di raggio) non e' aggiunto.",
    "Stazione di terra: guadagno costante, nessuna elevazione DSN, atmosfera, pioggia, scintillazione (CB79 sez. 2.1-2.5).",
    "Parametri radio illustrativi (tag I) negli script della ricerca; restano I finche' una fonte non li conferma.",
)


class GrazingParamError(ValueError):
    """Invalid analysis input; `key` names the field, the message never contains the value."""

    def __init__(self, key: str) -> None:
        super().__init__("invalid parameter")
        self.key = key


@dataclass(frozen=True)
class AnalysisWindow:
    start: datetime
    days: float
    step_min: float

    @classmethod
    def build(cls, start_utc: str | datetime, days: float, step_min: float) -> "AnalysisWindow":
        for key, v in (("days", days), ("step_min", step_min)):
            if not (isinstance(v, (int, float)) and math.isfinite(v) and v > 0):
                raise GrazingParamError(key)
        w = cls(parse_utc(start_utc), float(days), float(step_min))
        lo, hi = PARAMS["window_days"], PARAMS["window_step_min"]
        if not (lo.lo <= w.days <= lo.hi and hi.lo <= w.step_min <= hi.hi):
            raise GrazingParamError("window")
        if w.n_steps > MAX_SAMPLES:
            raise GrazingParamError("too_many_samples")
        return w

    @property
    def n_steps(self) -> int:
        return int(self.days * 1440.0 / self.step_min)

    def times(self) -> list[datetime]:
        return [self.start + timedelta(minutes=i * self.step_min) for i in range(self.n_steps)]


@dataclass(frozen=True)
class EarthSweep:
    """Site-independent geometry fallback: the Earth elevation sweeps linearly (NOT the ephemerides)."""

    el_start_deg: float
    el_end_deg: float
    range_km: float = 384_400.0
    az_deg: float = 0.0

    def __post_init__(self) -> None:
        ok = all(math.isfinite(v) for v in (self.el_start_deg, self.el_end_deg, self.range_km))
        if not (ok and -30 <= self.el_start_deg <= 60 and -30 <= self.el_end_deg <= 60):
            raise GrazingParamError("earth_sweep")
        if not (300_000 <= self.range_km <= 450_000 and 0 <= self.az_deg < 360):
            raise GrazingParamError("earth_sweep")


_KEYS = [
    "frequency_ghz",
    "tx_power_dbw",
    "tx_gain_dbi",
    "antenna_eta",
    "tsys_k",
    "ebn0_db",
    "misc_loss_db",
    "antenna_height_m",
    "regolith_eps_real",
    "regolith_eps_imag",
    "roughness_rms_m",
    "compensator_sigma_db",
    "compensator_k",
    "truth_height_offset_m",
    "profile_length_m",
    "tracking_error_deg",
    "gimbal_budget_db",
    "rate_bps",
]


@dataclass(frozen=True)
class LinkInputs:
    frequency_ghz: float = PARAMS["frequency_ghz"].default
    tx_power_dbw: float = PARAMS["tx_power_dbw"].default
    tx_gain_dbi: float = PARAMS["tx_gain_dbi"].default
    antenna_eta: float = PARAMS["antenna_eta"].default
    tsys_k: float = PARAMS["tsys_k"].default
    ebn0_db: float = PARAMS["ebn0_db"].default
    misc_loss_db: float = PARAMS["misc_loss_db"].default
    antenna_height_m: float = PARAMS["antenna_height_m"].default
    regolith_eps_real: float = PARAMS["regolith_eps_real"].default
    regolith_eps_imag: float = PARAMS["regolith_eps_imag"].default
    roughness_rms_m: float = PARAMS["roughness_rms_m"].default
    compensator_sigma_db: float = PARAMS["compensator_sigma_db"].default
    compensator_k: float = PARAMS["compensator_k"].default
    truth_height_offset_m: float = PARAMS["truth_height_offset_m"].default
    profile_length_m: float = PARAMS["profile_length_m"].default
    tracking_error_deg: float = PARAMS["tracking_error_deg"].default
    gimbal_budget_db: float = PARAMS["gimbal_budget_db"].default
    rate_bps: float = PARAMS["rate_bps"].default
    station: Literal["dsn34", "dsn18"] = "dsn34"
    station_gain_dbi: float | None = None  # None = the station table value (legacy)
    mount: Mount = "tracking"
    apply_correction: bool = True
    apply_multipath: bool = True
    seed: int = 3

    @classmethod
    def from_overrides(cls, overrides: Mapping[str, float | str | bool]) -> "LinkInputs":
        """Validated copy of the defaults: unknown key, non-finite or out-of-bound value -> error."""
        names = {f.name for f in fields(cls)}
        upd: dict[str, Any] = {}
        for key, val in overrides.items():
            if key not in names:
                raise GrazingParamError("overrides")
            if key in _KEYS:
                spec = PARAMS[key]
                if isinstance(val, bool) or not isinstance(val, (int, float)):
                    raise GrazingParamError(key)
                if not (math.isfinite(val) and spec.lo <= val <= spec.hi):
                    raise GrazingParamError(key)
                upd[key] = float(val)
            elif (
                key == "station_gain_dbi"
                and isinstance(val, int | float)
                and not isinstance(val, bool)
                and math.isfinite(val)
                and 40.0 <= val <= 80.0
            ):
                upd[key] = float(val)
            elif (
                key == "station"
                and val in ant.STATIONS
                or key == "mount"
                and val in ("tracking", "fixed", "gimbal")
                or key in ("apply_correction", "apply_multipath")
                and isinstance(val, bool)
                or key == "seed"
                and isinstance(val, int)
                and not isinstance(val, bool)
            ):
                upd[key] = val
            else:
                raise GrazingParamError(key)
        out = replace(cls(), **upd)
        if out.rate_bps not in RATES_BPS:
            raise GrazingParamError("rate_bps")
        return out

    @property
    def frequency_hz(self) -> float:
        return self.frequency_ghz * 1e9

    @property
    def wavelength_m(self) -> float:
        return C_MS / self.frequency_hz

    @property
    def eps_r(self) -> complex:
        return complex(self.regolith_eps_real, -self.regolith_eps_imag)

    def used_parameters(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for key in ("wavelength_m", *_KEYS, "boltzmann_dbw_per_k_hz", "earth_radius_km"):
            spec = PARAMS.get(key)
            if spec is None:
                continue
            value = self.wavelength_m if key == "wavelength_m" else getattr(self, key, spec.default)
            rows.append(
                {
                    "key": key,
                    "value": value,
                    "unit": spec.unit,
                    "status": spec.status,
                    "source": spec.source,
                    "min": spec.lo,
                    "max": spec.hi,
                }
            )
            if key == "tracking_error_deg" and self.mount == "gimbal":
                rows[-1]["note"] = "non applicato: il gimbal usa l'errore simulato"
        st = ant.STATIONS[self.station]
        own = self.station_gain_dbi is not None
        rows.append(
            {
                "key": "station_gain_dbi",
                "value": self.station_gain_dbi if own else st.gain_dbi,
                "unit": "dBi",
                "status": "D" if own else st.gain_tag,
                "source": (
                    "DSN 810-005 Module 104 Rev. Q Tab. 7 (RAVEN unified set)"
                    if own
                    else st.gain_source
                ),
                "note": st.note,
            }
        )
        rows.append(
            {
                "key": "hpbw_factor",
                "value": ant.HPBW_FACTOR_SCRIPT,
                "unit": "lambda/D deg",
                "status": "I",
                "source": "antenna_directivity.py; uniform aperture 58.96 (D) reported alongside",
            }
        )
        return rows


class ProfileCache:
    """LRU cache of terrain profiles keyed by (site, quantised azimuth, length)."""

    def __init__(self, max_items: int = 2048) -> None:
        self.max_items = max_items
        self._d: OrderedDict[tuple[Any, ...], TerrainProfile] = OrderedDict()
        self._lock = threading.Lock()
        self.extracted = 0

    def get(self, key: tuple[Any, ...], make: Callable[[], TerrainProfile]) -> TerrainProfile:
        with self._lock:
            hit = self._d.get(key)
            if hit is not None:
                self._d.move_to_end(key)
                return hit
        prof = make()
        with self._lock:
            self._d[key] = prof
            self.extracted += 1
            while len(self._d) > self.max_items:
                self._d.popitem(last=False)
        return prof


def _quantise_az(az_deg: float) -> float:
    return float((round(az_deg / AZIMUTH_QUANTUM_DEG) * AZIMUTH_QUANTUM_DEG) % 360.0)


def _clean(a: Any, nd: int = 3) -> list[float | None]:
    x = np.asarray(a, dtype=np.float64)
    return [None if not math.isfinite(v) else round(float(v), nd) for v in x]


def _decimate(a: Any, k: int, nd: int = 3) -> list[float | None]:
    x = np.asarray(a, dtype=np.float64)
    out: list[float | None] = []
    for b in range(-(-len(x) // k)):
        seg = x[b * k : (b + 1) * k]
        seg = seg[np.isfinite(seg)]
        out.append(round(float(seg.mean()), nd) if seg.size else None)
    return out


def _intervals(mask: Any, t_unix: Arr, step_s: float) -> list[list[int]]:
    out: list[list[int]] = []
    start: int | None = None
    n = len(mask)
    for i in range(n + 1):
        on = i < n and bool(mask[i])
        if on and start is None:
            start = i
        elif not on and start is not None:
            out.append([int(t_unix[start]), int(t_unix[i - 1] + step_s)])
            start = None
    return out[:MAX_INTERVALS]


def _earth_series(
    site: tuple[float, float] | None,
    sweep: EarthSweep | None,
    times: list[datetime],
    engine: EphemerisLike | None,
) -> tuple[EarthGeometry | None, Arr, Arr, Arr, str]:
    """(geometry|None, az, el, range_km, source)."""
    if sweep is not None:
        n = len(times)
        el = np.linspace(sweep.el_start_deg, sweep.el_end_deg, n)
        return None, np.full(n, sweep.az_deg), el, np.full(n, sweep.range_km), "user-sweep"
    if site is None:
        raise GrazingParamError("site")
    g = earth_geometry(site[0], site[1], times, engine=engine)
    return g, g.az_deg, g.el_deg, g.range_km, "ephemeris"


def _dem_profile(
    dem: LolaDem, site: tuple[float, float], azq: float, length_m: float, cache: ProfileCache
) -> TerrainProfile:
    key = (dem.spec.id, round(site[0], 5), round(site[1], 5), azq, length_m)
    return cache.get(key, lambda: profile_from_dem(dem, site[0], site[1], azq, length_m))


def _two_ray_gain(el: Arr, h: float, inp: LinkInputs, ridge_dist: Arr) -> tuple[Arr, Any, Arr]:
    """Gain (dB), applicable mask and specular distance; not applicable beyond the ridge."""
    tr = two_ray(
        el,
        h,
        inp.wavelength_m,
        polarization="circular_co",
        eps_r=inp.eps_r,
        sigma_m=inp.roughness_rms_m,
        ridge_distance_m=None,
    )
    beyond = tr.applicable & (tr.specular_distance_m > ridge_dist)
    ok = tr.applicable & ~beyond
    return np.where(ok, tr.gain_db, 0.0), ok, tr.specular_distance_m


@dataclass(frozen=True)
class LinkSeries:
    """Per-step link terms of one analysis (shared by `analyze` and the RAVEN S5 stage)."""

    nu: Any
    d1: Any
    ridge_dist: Any
    radius: Any
    resolved: Any
    blocks: Any
    tip_angle: Any
    j_db: Any
    have_radius: Any
    corr: Any
    unc: Any
    split: Any
    anomaly: Any
    clamped: Any
    table: Any
    geometry_extrap: Any
    g2_pred: Any
    g2_true: Any
    mp_ok: Any
    st: Any
    d_m: Any
    hp_script: Any
    hp_uniform: Any
    excursion: Any
    gimbal_limited: Any
    pt_gauss: Any
    pt_script: Any
    fspl: Any
    pred: Any
    truth: Any
    ridx: Any
    margin: Any


def link_series(
    inputs: LinkInputs,
    az: Arr,
    el: Arr,
    rng_km: Arr,
    ridges: Sequence[DominantRidge],
    step_s: float,
) -> LinkSeries:
    """Knife-edge + ITU rounded-ridge correction, multipath, antenna pointing and the margin per
    rate for given Earth az/el/range and dominant ridges. Moved verbatim out of `analyze` (RAVEN M5)."""
    n = len(el)
    lam = inputs.wavelength_m
    nu = np.array([r.nu for r in ridges])
    d1 = np.array([r.d1_m for r in ridges])
    ridge_dist = np.array([r.ridge_distance_m for r in ridges])
    radius = np.array([r.radius_of_curvature_m for r in ridges])
    resolved = np.array([r.radius_resolved for r in ridges])
    blocks = np.array([r.blocks_los for r in ridges])
    tip_angle = np.array([r.angle_above_los_deg for r in ridges])

    # --- diffraction: exact knife edge + ITU-R P.526-9 cylinder term (split-step as band) ---------
    j_db = knife_edge_loss_db(nu)
    have_radius = np.isfinite(radius)
    corr = np.zeros(n)
    unc = np.zeros(n)
    split = np.zeros(n)
    anomaly = np.zeros(n, dtype=bool)
    clamped = np.zeros(n, dtype=bool)
    if inputs.apply_correction and have_radius.any():
        hr = have_radius
        c, u, a, cl, s = ridge_correction(
            nu[hr], radius[hr], np.maximum(d1[hr], 1.0), lam, rng_km[hr] * 1000.0
        )
        corr[hr], unc[hr], split[hr] = c, u, s
        anomaly[hr], clamped[hr] = a, cl
        weak = have_radius & ~resolved  # radius below ~2 sample spacings: the correction is guessed
        unc[weak] = np.maximum(unc[weak], np.abs(corr[weak]))
    table = load_table()
    geometry_extrap = (d1 < 0.25 * TABLE_REFERENCE_D1_M) | (d1 > 4.0 * TABLE_REFERENCE_D1_M)

    # --- multipath ----------------------------------------------------------------------------------
    g2_pred, mp_ok, _spec_d = _two_ray_gain(el, inputs.antenna_height_m, inputs, ridge_dist)
    g2_true, _mp_ok2, _ = _two_ray_gain(
        el, inputs.antenna_height_m + inputs.truth_height_offset_m, inputs, ridge_dist
    )
    if not inputs.apply_multipath:
        g2_pred, g2_true = np.zeros(n), np.zeros(n)
        mp_ok = np.zeros(n, dtype=bool)

    # --- antenna ---------------------------------------------------------------------------------------
    st = ant.STATIONS[inputs.station]
    d_m = ant.diameter_for_gain_m(inputs.tx_gain_dbi, inputs.frequency_hz, inputs.antenna_eta)
    hp_script = float(ant.hpbw_deg(d_m, inputs.frequency_hz, "script_70"))
    hp_uniform = float(ant.hpbw_deg(d_m, inputs.frequency_hz, "uniform"))
    e_vec = np.stack(
        [
            np.cos(np.radians(el)) * np.sin(np.radians(az)),
            np.cos(np.radians(el)) * np.cos(np.radians(az)),
            np.sin(np.radians(el)),
        ],
        axis=1,
    )
    up = el > 0.0
    mean_dir = e_vec[up].mean(axis=0) if up.any() else e_vec.mean(axis=0)
    nrm = float(np.linalg.norm(mean_dir))
    axis = mean_dir / nrm if nrm > 0 else mean_dir
    dev = np.degrees(np.arccos(np.clip(e_vec @ axis, -1.0, 1.0)))
    excursion = float(dev[up].max()) if up.any() else float(dev.max())
    gimbal_limited = None
    if inputs.mount == "fixed":
        err = dev
    elif inputs.mount == "gimbal":
        from backend.domain.grazing.gimbal import track

        actual_az, actual_el, gimbal_limited = track(az, el, step_s)
        az_rad, el_rad = np.radians(actual_az), np.radians(actual_el)
        actual_vec = np.stack(
            [np.cos(el_rad) * np.sin(az_rad), np.cos(el_rad) * np.cos(az_rad), np.sin(el_rad)],
            axis=1,
        )
        err = np.degrees(np.arccos(np.clip(np.sum(e_vec * actual_vec, axis=1), -1.0, 1.0)))
    else:
        err = np.full(n, inputs.tracking_error_deg)
    pt_gauss = ant.pointing_loss_db(err, hp_script, "gaussian")
    pt_script = ant.pointing_loss_db(err, hp_script, "script")
    fspl = free_space_loss_series_db(rng_km, inputs.frequency_ghz)

    # --- link margin per rate -------------------------------------------------------------------------
    n0 = ant.BOLTZMANN_DBW + 10.0 * math.log10(inputs.tsys_k)
    fixed = (
        inputs.tx_power_dbw
        + inputs.tx_gain_dbi
        + (st.gain_dbi if inputs.station_gain_dbi is None else inputs.station_gain_dbi)
        - inputs.misc_loss_db
        - n0
        - inputs.ebn0_db
    )
    loss = j_db + corr
    base_pred = fixed - pt_gauss - fspl - loss + g2_pred
    base_true = fixed - pt_gauss - fspl - loss + g2_true
    pred = br.margin_matrix(base_pred, 1.0, RATES_BPS)
    truth = br.margin_matrix(base_true, 1.0, RATES_BPS)
    ridx = list(RATES_BPS).index(inputs.rate_bps)
    margin = pred[:, ridx]

    return LinkSeries(
        nu=nu,
        d1=d1,
        ridge_dist=ridge_dist,
        radius=radius,
        resolved=resolved,
        blocks=blocks,
        tip_angle=tip_angle,
        j_db=j_db,
        have_radius=have_radius,
        corr=corr,
        unc=unc,
        split=split,
        anomaly=anomaly,
        clamped=clamped,
        table=table,
        geometry_extrap=geometry_extrap,
        g2_pred=g2_pred,
        g2_true=g2_true,
        mp_ok=mp_ok,
        st=st,
        d_m=d_m,
        hp_script=hp_script,
        hp_uniform=hp_uniform,
        excursion=excursion,
        gimbal_limited=gimbal_limited,
        pt_gauss=pt_gauss,
        pt_script=pt_script,
        fspl=fspl,
        pred=pred,
        truth=truth,
        ridx=ridx,
        margin=margin,
    )


def analyze(
    *,
    window: AnalysisWindow,
    inputs: LinkInputs,
    site: tuple[float, float] | None = None,
    site_id: str | None = None,
    dem: LolaDem | None = None,
    profile: TerrainProfile | None = None,
    sweep: EarthSweep | None = None,
    engine: EphemerisLike | None = None,
    cache: ProfileCache | None = None,
    include_window_samples: bool = False,
) -> dict[str, Any]:
    """Run the analysis. Terrain: `profile` (user / synthetic test) else the LOLA `dem` at `site`.

    Raises `DemOutOfCoverage` (site outside the DEM), `DemUnavailable` (no data), `TerrainError`,
    `GrazingParamError`, `EphemerisUnavailable` (from the geometry).
    """
    if profile is None:
        if dem is None or site is None:
            raise GrazingParamError("terrain")
        if not dem.spec.covers(
            site[0]
        ):  # polar products: latitude <= -max_lat; the global one: every latitude
            raise DemOutOfCoverage(OUT_OF_COVERAGE_MESSAGE)
    cache = cache if cache is not None else ProfileCache()
    times = window.times()
    n = len(times)
    t_unix = np.array([t.timestamp() for t in times])
    step_s = window.step_min * 60.0
    _geo, az, el, rng_km, geo_source = _earth_series(site, sweep, times, engine)
    lam = inputs.wavelength_m

    # --- terrain and dominant ridge per step ---------------------------------------------------
    ridges: list[DominantRidge] = []
    source: Literal["lola", "user", "synthetic"]
    if profile is not None:
        source = profile.source
        label = profile.label
        product = None
    else:
        assert dem is not None and site is not None
        source, label, product = "lola", "LOLA " + dem.spec.id, dem.spec.id
    for i in range(n):
        if profile is not None:
            prof = profile
        else:
            assert dem is not None and site is not None
            prof = _dem_profile(
                dem, site, _quantise_az(float(az[i])), inputs.profile_length_m, cache
            )
        ridges.append(
            dominant_ridge(
                prof,
                float(el[i]),
                lam,
                earth_range_m=float(rng_km[i]) * 1000.0,
                antenna_height_m=inputs.antenna_height_m,
            )
        )
    ls = link_series(inputs, az, el, rng_km, ridges, step_s)
    nu = ls.nu
    radius = ls.radius
    resolved = ls.resolved
    blocks = ls.blocks
    tip_angle = ls.tip_angle
    j_db = ls.j_db
    have_radius = ls.have_radius
    corr = ls.corr
    unc = ls.unc
    split = ls.split
    anomaly = ls.anomaly
    clamped = ls.clamped
    table = ls.table
    geometry_extrap = ls.geometry_extrap
    g2_pred = ls.g2_pred
    mp_ok = ls.mp_ok
    st = ls.st
    d_m = ls.d_m
    hp_script = ls.hp_script
    hp_uniform = ls.hp_uniform
    excursion = ls.excursion
    gimbal_limited = ls.gimbal_limited
    pt_gauss = ls.pt_gauss
    pt_script = ls.pt_script
    fspl = ls.fspl
    pred = ls.pred
    truth = ls.truth
    margin = ls.margin

    # --- windows --------------------------------------------------------------------------------------------
    geom_vis = ~blocks
    real_ok = margin >= 0.0
    hours = step_s / 3600.0
    transition = ~geom_vis & real_ok
    windows = {
        "rate_bps": inputs.rate_bps,
        "geometric_hours": float(geom_vis.sum() * hours),
        "real_hours": float(real_ok.sum() * hours),
        "transition_hours": float(transition.sum() * hours),
        "geometric_not_closing_hours": float((geom_vis & ~real_ok).sum() * hours),
        "both_hours": float((geom_vis & real_ok).sum() * hours),
        "total_hours": float(n * hours),
        "geometric_intervals_unix": _intervals(geom_vis, t_unix, step_s),
        "real_intervals_unix": _intervals(real_ok, t_unix, step_s),
        "transition_intervals_unix": _intervals(transition, t_unix, step_s),
        "rule": "geometrica = centro della Terra sopra la linea del crinale dominante; reale = margine >= 0 al rate scelto",
    }

    # --- compensator -----------------------------------------------------------------------------------------
    ks = tuple(dict.fromkeys((*br.DEFAULT_K_VALUES, inputs.compensator_k)))
    rows = br.tradeoff(pred, truth, RATES_BPS, ks, inputs.compensator_sigma_db, step_s, inputs.seed)
    chosen = next(r for r in rows if r.k == inputs.compensator_k)
    chosen_rate = np.where(
        chosen.chosen_rate_index >= 0,
        np.asarray(RATES_BPS)[np.maximum(chosen.chosen_rate_index, 0)],
        0.0,
    )

    # --- output ------------------------------------------------------------------------------------------------
    k = max(1, -(-n // MAX_OUTPUT_POINTS))
    series: dict[str, Any] = {
        "earth_az_deg": _decimate(az, k),
        "earth_el_deg": _decimate(el, k),
        "range_km": _decimate(rng_km, k, 1),
        "ridge_angle_above_los_deg": _decimate(tip_angle, k),
        "nu": _decimate(nu, k),
        "knife_edge_loss_db": _decimate(j_db, k),
        "ridge_correction_db": _decimate(corr, k),
        "ridge_correction_uncertainty_db": _decimate(unc, k),
        "ridge_correction_splitstep_db": _decimate(split, k),
        "multipath_gain_db": _decimate(g2_pred, k),
        "multipath_applicable": _decimate(mp_ok.astype(float), k),
        "fspl_db": _decimate(fspl, k),
        "pointing_loss_db": _decimate(pt_gauss, k),
        "geometric_visible": _decimate(geom_vis.astype(float), k),
        "margin_chosen_rate_db": _decimate(margin, k),
        "margin_by_rate_db": [_decimate(pred[:, j], k) for j in range(len(RATES_BPS))],
        "chosen_rate_bps": _decimate(chosen_rate, k, 0),
    }
    n_corr = int(have_radius.sum()) if inputs.apply_correction else 0
    res_frac = float(resolved[have_radius].mean()) if have_radius.any() else 0.0
    if not inputs.apply_correction:
        corr_status = "off"
    elif n_corr == 0:
        corr_status = "not-available"
    else:
        corr_status = "itu"
    mp_frac = float(mp_ok.mean())
    flags = {
        "terrain": {
            "source": source,
            "synthetic": source == "synthetic",
            "label": label,
            "product_id": product,
            "azimuth_quantum_deg": AZIMUTH_QUANTUM_DEG,
            "profiles_extracted": cache.extracted,
            "profile_length_m": inputs.profile_length_m
            if profile is None
            else float(profile.distance_m[-1]),
            "spacing_m": profile.spacing_m
            if profile is not None
            else (dem.spec.scale_m if dem is not None else 0.0),
        },
        "geometry_source": geo_source,
        "radius_resolved": bool(have_radius.all() and resolved.all()),
        "radius_resolved_fraction": res_frac,
        "ridge_radius_median_m": float(np.nanmedian(radius)) if have_radius.any() else None,
        "multipath": {
            "applicable_fraction": mp_frac,
            "status": "applicato"
            if mp_frac == 1.0
            else ("non applicabile" if mp_frac == 0.0 else "parziale"),
            "enabled": inputs.apply_multipath,
            "reason_not_applicable": NOT_APPLICABLE
            + ": punto speculare oltre il crinale, oppure elevazione <= 0",
        },
        "correction": {
            "status": corr_status,
            "enabled": inputs.apply_correction,
            "steps_with_radius": n_corr,
            "anomaly_steps": int(anomaly.sum()),
            "clamped_steps": int(clamped.sum()),
            "geometry_extrapolated_steps": int(geometry_extrap.sum()),
            "max_uncertainty_db": float(unc.max()) if n else 0.0,
            "max_correction_db": float(corr.max()) if n else 0.0,
            "max_itu_minus_splitstep_db": float(np.max(np.abs(corr - split))) if n else 0.0,
            "model": "ITU-R P.526-9 par. 4.2 eq. (28)-(32); tabella split-step come confronto",
            "table": table.info(),
            "table_reference": {
                "d1_m": TABLE_REFERENCE_D1_M,
                "wavelength_m": 0.0357,
                "plane_wave": True,
            },
            "label": "correzione ITU-R P.526-9 (cilindro), banda split-step; non misurata",
        },
        "blocked_fraction": float(blocks.mean()),
        "earth_below_horizon_fraction": float((el <= 0).mean()),
    }
    ante = {
        "station": st.to_dict(inputs.frequency_hz),
        "rover_gain_dbi": inputs.tx_gain_dbi,
        "diameter_m": d_m,
        "hpbw_script_70_deg": hp_script,
        "hpbw_uniform_deg": hp_uniform,
        "mount": inputs.mount,
        "gimbal_mechanical_limit_fraction": (
            float(np.mean(gimbal_limited[1:]))
            if gimbal_limited is not None and len(gimbal_limited) > 1
            else None
        ),
        "gimbal": ant.gimbal_assessment(hp_script, excursion, max_loss_db=inputs.gimbal_budget_db),
        "libration_excursion_deg": excursion,
        "pointing_loss_max_db": float(pt_gauss.max()),
        "pointing_script_minus_gaussian_max_db": float(np.max(pt_script - pt_gauss)),
        "note": "perdita di puntamento: gaussiana esatta 12.04 (x/HPBW)^2; variante dello script 12 (x/HPBW)^2",
    }
    result: dict[str, Any] = {
        "label": "potential under stated assumptions",
        "window": {
            "start_utc": window.start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "days": window.days,
            "step_min": window.step_min,
            "n_steps": n,
        },
        "site": {
            "id": site_id,
            "lat_deg": None if site is None else site[0],
            "lon_deg_east": None if site is None else site[1],
        },
        "series_time_unix": [int(v) for v in t_unix[::k]],
        "series_step_min": window.step_min * k,
        "series": series,
        "rates_bps": list(RATES_BPS),
        "windows": windows,
        "compensator": {
            "k": inputs.compensator_k,
            "sigma_db": inputs.compensator_sigma_db,
            "seed": inputs.seed,
            "chosen": chosen.to_dict(),
            "tradeoff": [r.to_dict() for r in rows],
            "note": "feedforward + margine statistico, non apprendimento per rinforzo; rumore comune a tutti i k",
        },
        "antenna": ante,
        "flags": flags,
        "parameters": inputs.used_parameters(),
        "declared_limits": [
            *DECLARED_LIMITS,
            *(
                [
                    (
                        "Gimbal simulato C (tag I), non validato su hardware: inizialmente allineato, "
                        "PI e parametri servo illustrativi, corsa 180 gradi per asse; interpolazione "
                        "lineare tra campioni, nessun errore costante aggiunto."
                    )
                ]
                if inputs.mount == "gimbal"
                else []
            ),
        ],
        "correction_inconsistency": consistency_diagnostic(table),
    }
    if include_window_samples:
        result["window_samples"] = {
            "time_unix": t_unix.tolist(),
            "geometric_visible": geom_vis.tolist(),
            "link_ok": real_ok.tolist(),
            "margin_db": [float(x) if math.isfinite(x) else None for x in margin],
            "chosen_rate_bps": chosen_rate.tolist(),
        }
    return result


def sites_from_registry(site_id: str, sites: Sequence[Any]) -> tuple[float, float]:
    for s in sites:
        if s.id == site_id:
            return float(s.lat_deg), float(s.lon_deg_east)
    raise GrazingParamError("site_id")
