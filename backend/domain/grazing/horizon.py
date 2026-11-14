# SPDX-License-Identifier: Apache-2.0
"""Per-site horizon mask from LOLA (20 m to 10 km, 240 m to 200 km) and disc-aware Sun criteria.

Production implementation of the method checked by the independent arbiter
`scripts/solar_horizon_arbiter.py` (docs/domain/validation.md, 2026-11-04). The two share only the
tile reader `LolaDem`; the formulation here is different on purpose, so that the comparison test
(`tests/backend/domain/grazing/test_horizon.py`) is meaningful:

* ray points by the spherical "destination point" formula (the arbiter rotates 3D vectors);
* terrain elevation angle seen from the eye by plane trigonometry in the great-circle plane,
  `el = atan2((R + z) cos(delta) - (R + z0 + h), (R + z) sin(delta))`, delta = d / R (the arbiter
  uses Cartesian differences). Moon curvature is therefore included exactly on the 1737.4 km sphere;
* the DEM windows are projected with the orientation recorded in `dem.lock.json` (swap, sx, sy).

Mask: `n_azimuths` (360-1440, default 1440) directions from north through east; LDEM_85S_20M sampled
every 10 m from 10 m to 10 km, then LDEM_75S_240M every 120 m to 200 km (bilinear interpolation,
half the pixel spacing: at 20 m / 240 m steps the mask of a steep summit such as Malapert was up
to 1.2 deg lower, 0.14 deg on average, because the maximum was missed between samples).
Eye at `observer_height_m` above the interpolated DEM surface (default 2 m, tag I).

Unknowns: a DEM sample that is missing (tile not cached, outside the product) is NaN. It is
excluded from the maximum and the azimuth is flagged incomplete; the known maximum is then a LOWER
bound of the real mask. A Sun criterion is reported True only if every mask bin it touches is
complete; a False obtained against the lower bound stays False (more terrain can only hide more).
Everything else is `None` (unknown), never sunlit.

Not modelled (declared in `LIMITS`): terrain beyond 200 km, DEM vertical uncertainty and sub-pixel
relief, limb darkening, the solar corona, refraction (none on the Moon), the site's own lander.

Cache: one mask per (site, observer height, configuration, DEM hashes) in memory (LRU) and on disk
under `<GRAZING_DEM_DIR>/horizon/` (JSON with its own key, re-checked on load).
"""

import hashlib
import json
import logging
import math
import os
import threading
import time
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from backend.domain.grazing import dem_cache
from backend.domain.grazing.dem import (
    FAR_DEM_ID,
    TILE,
    DemSpec,
    DemUnavailable,
    LolaDem,
    dem_dir,
    load_lock,
)
from backend.domain.grazing.geometry import great_circle_destination
from backend.domain.raven import params as reg

log = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_OBSERVER_HEIGHT_M",
    "LIMITS",
    "HorizonMask",
    "MaskConfig",
    "MaskStore",
    "compute_mask",
    "default_store",
    "disc_criteria",
    "horizon_at",
    "horizon_distance_m",
    "mask_from_samplers",
    "sun_semidiameter_deg",
]

Arr = NDArray[np.float64]
BoolArr = NDArray[np.bool_]
ALGORITHM = "raven-horizon-v2"
# Values from the parameter registry (RAVEN M1): tag I eye height (sensitivity: validation.md),
# IAU 2015 nominal solar radius, number of strips of the disc integral.
DEFAULT_OBSERVER_HEIGHT_M = reg.value("common.observer_height_default_m")
SUN_RADIUS_KM = reg.value("common.sun_radius_km")
DISC_STRIPS = int(reg.value("common.disc_strips"))
LIMITS = (
    "Horizon mask from LOLA: LDEM_85S_20M to 10 km, LDEM_75S_240M to 200 km; terrain beyond 200 km "
    "is not modelled; DEM vertical uncertainty, sub-pixel relief, limb darkening and the lander "
    "itself are not modelled; missing DEM data makes the affected criteria unknown, never sunlit. "
    "Checked against an independent implementation (scripts/solar_horizon_arbiter.py) and, near "
    "the pole, against LROC WAC illumination (docs/domain/validation.md); not a mission forecast."
)


@dataclass(frozen=True)
class MaskConfig:
    near_m: float = 10_000.0
    far_m: float = 200_000.0
    near_step_m: float = 10.0
    far_step_m: float = 120.0
    n_azimuths: int = 1440

    def __post_init__(self) -> None:
        if not (360 <= self.n_azimuths <= 1440):
            raise ValueError("n_azimuths must be in [360, 1440]")
        if not (0 < self.near_step_m <= self.near_m <= self.far_m <= 200_000.0):
            raise ValueError("invalid distances")


@dataclass(frozen=True)
class HorizonMask:
    lat_deg: float
    lon_deg_east: float
    observer_height_m: float
    site_height_m: float
    elevation_deg: Arr  # max over KNOWN samples (lower bound where incomplete); -inf if none known
    distance_m: Arr  # ground distance of that maximum (NaN if none known)
    complete: BoolArr  # every sample of the azimuth known
    unknown_fraction: float  # unknown samples / all samples
    config: MaskConfig
    products: list[dict[str, Any]] = field(default_factory=list)
    compute_s: float = 0.0
    from_cache: str = "computed"

    @property
    def azimuth_deg(self) -> Arr:
        n = self.config.n_azimuths
        return np.arange(n, dtype=np.float64) * (360.0 / n)

    def metadata(self) -> dict[str, Any]:
        far = self.distance_m > self.config.near_m
        return {
            "algorithm": ALGORITHM,
            "n_azimuths": self.config.n_azimuths,
            "azimuth_step_deg": 360.0 / self.config.n_azimuths,
            "near_product": self.products[0]["id"] if self.products else None,
            "far_product": self.products[1]["id"] if len(self.products) > 1 else None,
            "products": self.products,
            "near_range_m": [self.config.near_step_m, self.config.near_m],
            "near_step_m": self.config.near_step_m,
            "far_range_m": [self.config.near_m + self.config.far_step_m, self.config.far_m],
            "far_step_m": self.config.far_step_m,
            "observer_height_m": self.observer_height_m,
            "site_height_m": self.site_height_m,
            "moon_radius_m": 1_737_400.0,
            "curvature": "included (spherical reference of the DEM)",
            "complete_azimuth_fraction": float(np.mean(self.complete)),
            "unknown_sample_fraction": self.unknown_fraction,
            "far_terrain_dominant_fraction": float(np.mean(far & np.isfinite(self.distance_m))),
            "max_elevation_deg": _finite_or_none(np.max(self.elevation_deg)),
            "compute_s": round(self.compute_s, 3),
            "cache": self.from_cache,
            "coverage_limit": f"terrain beyond {self.config.far_m / 1000.0:g} km not modelled",
        }

    def to_json(self, key: str) -> dict[str, Any]:
        return {
            "key": key,
            "lat_deg": self.lat_deg,
            "lon_deg_east": self.lon_deg_east,
            "observer_height_m": self.observer_height_m,
            "site_height_m": self.site_height_m,
            "elevation_deg": [_finite_or_none(v) for v in self.elevation_deg],
            "distance_m": [_finite_or_none(v) for v in self.distance_m],
            "complete": self.complete.tolist(),
            "unknown_fraction": self.unknown_fraction,
            "config": asdict(self.config),
            "products": self.products,
            "compute_s": self.compute_s,
        }

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> "HorizonMask":
        cfg = MaskConfig(**raw["config"])
        n = cfg.n_azimuths
        el = np.array([-np.inf if v is None else v for v in raw["elevation_deg"]], dtype=np.float64)
        dist = np.array([np.nan if v is None else v for v in raw["distance_m"]], dtype=np.float64)
        comp = np.array(raw["complete"], dtype=bool)
        if not (el.size == dist.size == comp.size == n):
            raise ValueError("cached mask has the wrong size")
        return cls(
            float(raw["lat_deg"]),
            float(raw["lon_deg_east"]),
            float(raw["observer_height_m"]),
            float(raw["site_height_m"]),
            el,
            dist,
            comp,
            float(raw["unknown_fraction"]),
            cfg,
            list(raw["products"]),
            float(raw["compute_s"]),
        )


def _finite_or_none(v: Any) -> float | None:
    f = float(v)
    return f if math.isfinite(f) else None


# --------------------------------------------------------------------------------------------
# DEM windows
# --------------------------------------------------------------------------------------------
class _Grid:
    """numpy window of a LOLA product, heights in m (NaN = unknown).

    Polar products: a window of whole tiles around the site. Cylindrical products: the same, with
    columns unwrapped around the site (the 0/360 seam). `needed` (a set of (ti, tj) tile indices,
    column index already wrapped) restricts the loading to the tiles the caller planned: others stay
    NaN and are not counted as missing (they are never sampled by construction).
    """

    def __init__(
        self,
        dem: LolaDem,
        lat_deg: float,
        lon_deg: float,
        half_m: float,
        needed: set[tuple[int, int]] | None = None,
    ) -> None:
        s = dem.spec
        self.spec = s
        self.dem = dem
        self.cyl = s.projection == "cylindrical"
        row, col = dem.pixel_arrays(np.array([lat_deg]), np.array([lon_deg]))
        self.col_site = float(col[0])
        half_px = half_m / s.scale_m + 2.0
        half_c = half_px
        ntj = -(-s.samples // TILE)
        if self.cyl:
            reach = min(abs(lat_deg) + math.degrees(half_m / (s.radius_km * 1000.0)), 89.99)
            half_c = half_px / max(math.cos(math.radians(reach)), 1e-3)
        r0 = max(0, int(row[0] - half_px)) // TILE
        r1 = min(s.lines - 1, int(row[0] + half_px)) // TILE
        if self.cyl and 2.0 * half_c + 1.0 >= s.samples:
            c0 = math.floor(
                (col[0] - s.samples / 2.0) / TILE
            )  # the whole ring, centred on the site
            c1 = c0 + ntj
        else:
            c0 = math.floor((col[0] - half_c) / TILE)
            c1 = math.floor((col[0] + half_c) / TILE)
            if not self.cyl:
                c0, c1 = (
                    max(0, int(col[0] - half_c)) // TILE,
                    min(s.samples - 1, int(col[0] + half_c)) // TILE,
                )
        self.row0, self.col0 = r0 * TILE, c0 * TILE
        h = np.full(((r1 - r0 + 1) * TILE, (c1 - c0 + 1) * TILE), np.nan, dtype=np.float64)
        self.tiles_missing = 0
        for ti in range(r0, r1 + 1):
            for tj in range(c0, c1 + 1):
                tjw = tj % ntj if self.cyl else tj
                if needed is not None and (ti, tjw) not in needed:
                    continue
                try:
                    t = dem.tile(ti, tjw)
                except DemUnavailable:
                    self.tiles_missing += 1
                    continue
                h[
                    (ti - r0) * TILE : (ti - r0 + 1) * TILE, (tj - c0) * TILE : (tj - c0 + 1) * TILE
                ] = t.astype(np.float64) * 1000.0
        rows = np.arange(h.shape[0]) + self.row0
        h[rows >= s.lines, :] = np.nan  # zero padding of edge tiles is not data
        if not self.cyl:
            cols = np.arange(h.shape[1]) + self.col0
            h[:, cols >= s.samples] = np.nan
        self.h = h

    def _pixel(self, lat_deg: Arr, lon_deg: Arr) -> tuple[Arr, Arr]:
        row, col = self.dem.pixel_arrays(lat_deg, lon_deg)
        if self.cyl:
            n = float(self.spec.samples)
            d = col - self.col_site
            col = self.col_site + d - n * np.round(d / n)
        return row, col

    def sample(self, lat_deg: Arr, lon_deg: Arr) -> Arr:
        row, col = self._pixel(lat_deg, lon_deg)
        r = row - self.row0
        c = col - self.col0
        nr, nc = self.h.shape
        inside = (r >= 0) & (c >= 0) & (r < nr - 1) & (c < nc - 1)
        r = np.where(inside, r, 0.0)
        c = np.where(inside, c, 0.0)
        i, j = r.astype(np.int64), c.astype(np.int64)
        fr, fc = r - i, c - j
        h = self.h
        top = h[i, j] + fc * (h[i, j + 1] - h[i, j])
        bot = h[i + 1, j] + fc * (h[i + 1, j + 1] - h[i + 1, j])
        out: Arr = np.where(inside, top + fr * (bot - top), np.nan)
        return out


def _product_info(spec: DemSpec, grid: _Grid) -> dict[str, Any]:
    return {
        "id": spec.id,
        "sha256": spec.sha256,
        "label_sha256": spec.label_sha256,
        "scale_m": spec.scale_m,
        "tiles_missing": grid.tiles_missing,
    }


# --------------------------------------------------------------------------------------------
# mask
# --------------------------------------------------------------------------------------------
def mask_from_samplers(
    segments: list[tuple[Any, Arr]],
    lat_deg: float,
    lon_deg: float,
    observer_height_m: float,
    n_azimuths: int,
    *,
    site_height_m: float,
    radius_m: float = 1_737_400.0,
    chunk: int = 96,
) -> tuple[Arr, Arr, BoolArr, float]:
    """(elevation_deg, distance_m, complete, unknown_fraction) for `segments` = [(sample, d_m)]."""
    az_all = np.radians(np.arange(n_azimuths, dtype=np.float64) * (360.0 / n_azimuths))
    r_eye = radius_m + site_height_m + observer_height_m
    best = np.full(n_azimuths, -np.inf)
    best_d = np.full(n_azimuths, np.nan)
    complete = np.ones(n_azimuths, dtype=bool)
    unknown = total = 0
    for k in range(0, n_azimuths, chunk):
        az = az_all[k : k + chunk, None]
        for sample, dist in segments:
            delta = (np.asarray(dist, dtype=np.float64) / radius_m)[None, :]
            lat, lon = great_circle_destination(lat_deg, lon_deg, az, delta)
            z = sample(lat.ravel(), lon.ravel()).reshape(lat.shape)
            rt = radius_m + z
            el = np.degrees(np.arctan2(rt * np.cos(delta) - r_eye, rt * np.sin(delta)))
            bad = ~np.isfinite(el)
            unknown += int(bad.sum())
            total += el.size
            complete[k : k + chunk] &= ~bad.any(axis=1)
            el = np.where(bad, -np.inf, el)
            i = np.argmax(el, axis=1)
            m = el[np.arange(el.shape[0]), i]
            up = m > best[k : k + chunk]
            best[k : k + chunk] = np.where(up, m, best[k : k + chunk])
            best_d[k : k + chunk] = np.where(up, np.asarray(dist)[i], best_d[k : k + chunk])
    return best, best_d, complete, unknown / max(total, 1)


def compute_mask(
    lat_deg: float,
    lon_deg_east: float,
    observer_height_m: float = DEFAULT_OBSERVER_HEIGHT_M,
    config: MaskConfig | None = None,
    *,
    near_dem: LolaDem | None = None,
    far_dem: LolaDem | None = None,
    needed: dict[str, set[tuple[int, int]]] | None = None,
) -> HorizonMask:
    """Compute the mask (no cache). Raises DemOutOfCoverage, or DemUnavailable without site height.

    `needed` maps a product id to the tiles to load (custom sites: the planned tiles); None loads
    every tile of the window (catalogue sites)."""
    cfg = config or MaskConfig()
    if not (0.0 <= observer_height_m <= 100.0):
        raise ValueError("observer height out of range")
    t0 = time.perf_counter()
    near_dem = near_dem or LolaDem(allow_download=False)
    near_dem.pixel(lat_deg, lon_deg_east)  # DemOutOfCoverage outside the 20 m product
    near = _Grid(
        near_dem,
        lat_deg,
        lon_deg_east,
        cfg.near_m + 200.0,
        None if needed is None else needed.get(near_dem.spec.id),
    )
    z0 = float(near.sample(np.array([lat_deg]), np.array([lon_deg_east]))[0])
    if not math.isfinite(z0):
        raise DemUnavailable("site height unknown (DEM tile missing)")
    segments: list[tuple[Any, Arr]] = [
        (near.sample, np.arange(cfg.near_step_m, cfg.near_m + 1e-6, cfg.near_step_m))
    ]
    products = [_product_info(near_dem.spec, near)]
    if cfg.far_m > cfg.near_m:
        far_dem = far_dem or LolaDem(spec=load_lock(dataset_id=FAR_DEM_ID), allow_download=False)
        far = _Grid(
            far_dem,
            lat_deg,
            lon_deg_east,
            cfg.far_m + 1000.0,
            None if needed is None else needed.get(far_dem.spec.id),
        )
        segments.append(
            (far.sample, np.arange(cfg.near_m + cfg.far_step_m, cfg.far_m + 1e-6, cfg.far_step_m))
        )
        products.append(_product_info(far_dem.spec, far))
    el, dist, comp, unk = mask_from_samplers(
        segments,
        lat_deg,
        lon_deg_east,
        observer_height_m,
        cfg.n_azimuths,
        site_height_m=z0,
        radius_m=near_dem.spec.radius_km * 1000.0,
    )
    return HorizonMask(
        lat_deg,
        lon_deg_east,
        observer_height_m,
        z0,
        el,
        dist,
        comp,
        unk,
        cfg,
        products,
        time.perf_counter() - t0,
    )


# --------------------------------------------------------------------------------------------
# Sun criteria
# --------------------------------------------------------------------------------------------
def sun_semidiameter_deg(sun_distance_km: Arr | float) -> Arr:
    """Apparent solar semidiameter asin(R_sun / d)."""
    d = np.asarray(sun_distance_km, dtype=np.float64)
    return np.asarray(np.degrees(np.arcsin(SUN_RADIUS_KM / d)), dtype=np.float64)


def _mask_lookup(mask: HorizonMask, az_deg: Arr) -> tuple[Arr, BoolArr]:
    """Linear interpolation between the two neighbouring azimuth bins and their completeness."""
    n = mask.config.n_azimuths
    x = np.mod(np.nan_to_num(az_deg, nan=0.0), 360.0) * (n / 360.0)  # NaN: masked by caller
    i = np.floor(x).astype(np.int64) % n
    j = (i + 1) % n
    f = x - np.floor(x)
    lo, hi = mask.elevation_deg[i], mask.elevation_deg[j]
    with np.errstate(invalid="ignore"):
        h = np.where(np.isfinite(lo) & np.isfinite(hi), lo + f * (hi - lo), -np.inf)
    return h, mask.complete[i] & mask.complete[j]


def horizon_at(mask: HorizonMask, az_deg: Arr) -> tuple[Arr, BoolArr]:
    """Horizon elevation (deg) at the azimuths and whether both neighbouring bins are complete.

    Public form of the mask lookup used by `disc_criteria` (same interpolation, no new rule). The
    elevation is a lower bound where the answer is incomplete; -inf where no sample is known.
    """
    return _mask_lookup(mask, np.asarray(az_deg, dtype=np.float64))


def horizon_distance_m(mask: HorizonMask, az_deg: Arr) -> Arr:
    """Ground distance (m) of the highest terrain sample at each azimuth; NaN if unknown.

    Of the two neighbouring bins, the distance of the higher one (the one that sets the horizon).
    """
    n = mask.config.n_azimuths
    x = np.mod(np.nan_to_num(np.asarray(az_deg, dtype=np.float64), nan=0.0), 360.0) * (n / 360.0)
    i = np.floor(x).astype(np.int64) % n
    j = (i + 1) % n
    use_j = mask.elevation_deg[j] > mask.elevation_deg[i]
    return np.asarray(np.where(use_j, mask.distance_m[j], mask.distance_m[i]), dtype=np.float64)


def _circle_primitive(v: Arr) -> Arr:
    return (v * np.sqrt(np.maximum(1.0 - v * v, 0.0)) + np.arcsin(v)) / 2.0


def _linear_disc_area(left: Arr, right: Arr, slope: Arr, cut: Arr) -> Arr:
    """Exact area above each linear horizon segment inside the unit circle."""
    norm = 1.0 + slope * slope
    root = np.sqrt(np.maximum(norm - cut * cut, 0.0))
    a = np.clip((-slope * cut - root) / norm, left, right)
    b = np.clip((-slope * cut + root) / norm, left, right)
    edges = np.stack((left, a, b, right))
    lo, hi = edges[:-1], edges[1:]
    mid = (lo + hi) / 2.0
    upper = np.sqrt(np.maximum(1.0 - mid * mid, 0.0))
    line = slope * mid + cut
    circular = _circle_primitive(hi) - _circle_primitive(lo)
    full = 2.0 * circular
    partial = circular - (hi - lo) * (slope * (hi + lo) / 2.0 + cut)
    area = np.where(line >= upper, 0.0, np.where(line <= -upper, full, partial))
    return np.clip(area, 0.0, full).sum(axis=0)


def disc_criteria(
    mask: HorizonMask, sun_az_deg: Arr, sun_el_deg: Arr, semidiameter_deg: Arr | float
) -> dict[str, list[Any]]:
    """Per instant: horizon at the centre azimuth, upper/centre/lower limb, visible disc fraction.

    The disc is cut into DISC_STRIPS vertical strips of equal width; each strip at sky offset x
    is split at every horizon-mask interpolation knot. Integrate the circular area against the
    actual linear horizon on each piece, not a constant midpoint horizon.
    Values are None when the
    answer depends on missing DEM data (see the module docstring); never 'visible' by default.
    """
    az = np.asarray(sun_az_deg, dtype=np.float64)
    el = np.asarray(sun_el_deg, dtype=np.float64)
    r = np.broadcast_to(np.asarray(semidiameter_deg, dtype=np.float64), el.shape)
    valid = (
        np.isfinite(az)
        & np.isfinite(el)
        & (np.abs(el) <= 90.0)
        & np.isfinite(r)
        & (r > 0.0)
        & (r < 90.0)
    )
    r = np.where(valid, r, 1.0)
    h0, ok0 = _mask_lookup(mask, az)
    frac = np.zeros(el.size)
    disc_ok = np.zeros(el.size, dtype=bool)
    all_known = bool(mask.complete.all() and np.isfinite(mask.elevation_deg).all())
    minimum, maximum = float(mask.elevation_deg.min()), float(mask.elevation_deg.max())
    base_edges = np.linspace(-1.0, 1.0, DISC_STRIPS + 1)
    step = 360.0 / mask.config.n_azimuths
    for index in np.flatnonzero(valid):
        k = int(index)
        if all_known and (el[k] - r[k] >= maximum or el[k] + r[k] <= minimum):
            frac[k] = float(el[k] - r[k] >= maximum)
            disc_ok[k] = True
            continue
        span = r[k] / max(math.cos(math.radians(float(el[k]))), 1e-6)
        if span >= 180.0:
            valid[k] = False
            continue
        centre = float(az[k] % 360.0)
        first, last = math.floor((centre - span) / step), math.ceil((centre + span) / step)
        knots = (np.arange(first + 1, last) * step - centre) / span
        edges = np.unique(np.concatenate((base_edges, knots[(knots > -1) & (knots < 1)])))
        left, right = edges[:-1], edges[1:]
        midpoint = centre + (left + right) / 2.0 * span
        position = np.mod(midpoint, 360.0) / step
        i = np.floor(position).astype(np.int64) % mask.config.n_azimuths
        j = (i + 1) % mask.config.n_azimuths
        lo, hi = mask.elevation_deg[i], mask.elevation_deg[j]
        finite = np.isfinite(lo) & np.isfinite(hi)
        slope = np.zeros(left.size)
        cut = np.zeros(left.size)
        slope[finite] = (hi[finite] - lo[finite]) / step * span / r[k]
        at_midpoint = lo[finite] + (position[finite] - np.floor(position[finite])) * (
            hi[finite] - lo[finite]
        )
        cut[finite] = (at_midpoint - el[k]) / r[k] - slope[finite] * (
            left[finite] + right[finite]
        ) / 2.0
        area = _linear_disc_area(left, right, slope, cut)
        area[~finite] = 2.0 * (_circle_primitive(right[~finite]) - _circle_primitive(left[~finite]))
        frac[k] = np.clip(float(area.sum()) / math.pi, 0.0, 1.0)
        disc_ok[k] = bool((mask.complete[i] & mask.complete[j] & finite).all() and ok0[k])
    out: dict[str, list[Any]] = {
        "horizon_deg": [],
        "upper": [],
        "centre": [],
        "lower": [],
        "disc_fraction": [],
        "complete": [],
    }
    for k in range(el.size):
        if not valid[k]:
            for values in out.values():
                values.append(None)
            continue
        comp = bool(disc_ok[k])
        hk = float(h0[k])
        out["horizon_deg"].append(hk if comp and math.isfinite(hk) else None)
        out["complete"].append(comp)
        for key, edge in (("upper", r[k]), ("centre", 0.0), ("lower", -r[k])):
            seen = bool(el[k] + edge >= hk)
            out[key].append(seen if comp or not seen else None)
        fk = float(frac[k])
        out["disc_fraction"].append(fk if comp or fk == 0.0 else None)
    return out


# --------------------------------------------------------------------------------------------
# cache
# --------------------------------------------------------------------------------------------
class MaskStore:
    """Masks cached per (site, observer height, config, DEM hashes): memory LRU + JSON on disk."""

    def __init__(
        self,
        directory: Path | None = None,
        capacity: int = 32,
        *,
        max_disk_bytes: int = 8_000_000,
        max_disk_entries: int = 128,
        quota_directory: Path | None = None,
    ) -> None:
        if max_disk_bytes <= 0 or max_disk_entries <= 0:
            raise ValueError("horizon cache limits must be positive")
        self.directory = directory
        self.capacity = capacity
        self.max_disk_bytes = max_disk_bytes
        self.max_disk_entries = max_disk_entries
        self.quota_directory = quota_directory
        self._mem: OrderedDict[str, HorizonMask] = OrderedDict()
        self._lock = threading.Lock()
        self._compute_lock = threading.Lock()
        self.computed = 0

    def _dir(self) -> Path:
        return self.directory if self.directory is not None else dem_dir() / "horizon"

    @staticmethod
    def key(
        lat: float,
        lon: float,
        h: float,
        cfg: MaskConfig,
        near: DemSpec | None = None,
        far: DemSpec | None = None,
    ) -> str:
        near = near or load_lock()
        far = far or load_lock(dataset_id=FAR_DEM_ID)
        canon = json.dumps(
            [
                ALGORITHM,
                round(lat, 7),
                round(lon, 7),
                round(h, 3),
                asdict(cfg),
                near.sha256
                or near.label_sha256,  # sha256 is "" where the whole file was not hashed
                far.sha256 or far.label_sha256,
            ],
            separators=(",", ":"),
        )
        return hashlib.sha256(canon.encode()).hexdigest()

    def get(
        self,
        lat_deg: float,
        lon_deg_east: float,
        observer_height_m: float = DEFAULT_OBSERVER_HEIGHT_M,
        config: MaskConfig | None = None,
        *,
        near_dem: LolaDem | None = None,
        far_dem: LolaDem | None = None,
        needed: dict[str, set[tuple[int, int]]] | None = None,
        compute: bool = True,
    ) -> HorizonMask:
        """The mask from memory, disk or (when `compute`) a new computation; without `compute` an uncached mask raises
        `DemUnavailable` (a quick look that never starts a long computation)."""
        cfg = config or MaskConfig()
        k = self.key(
            lat_deg,
            lon_deg_east,
            observer_height_m,
            cfg,
            None if near_dem is None else near_dem.spec,
            None if far_dem is None else far_dem.spec,
        )
        mk = f"{self._dir()}|{k}"  # the memory entry also depends on the cache directory
        with self._lock:
            hit = self._mem.get(mk)
            if hit is not None:
                self._mem.move_to_end(mk)
                return _with_source(hit, "memory")
        with self._compute_lock:  # one computation at a time; others wait and then hit the cache
            with self._lock:
                hit = self._mem.get(mk)
            if hit is not None:
                return _with_source(hit, "memory")
            mask = self._load(k)
            if mask is None and not compute:
                raise DemUnavailable("horizon mask not computed yet")
            if mask is None:
                mask = compute_mask(
                    lat_deg,
                    lon_deg_east,
                    observer_height_m,
                    cfg,
                    near_dem=near_dem,
                    far_dem=far_dem,
                    needed=needed,
                )
                self.computed += 1
                if any(p["tiles_missing"] for p in mask.products):
                    return mask  # never cache a mask built on missing tiles (they may arrive)
                self._save(k, mask)
            with self._lock:
                self._mem[mk] = mask
                while len(self._mem) > self.capacity:
                    self._mem.popitem(last=False)
            return mask

    def _load(self, k: str) -> HorizonMask | None:
        p = self._dir() / f"{k}.json"
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            if raw.get("key") != k:
                return None
            dem_cache.touch(p)
            return _with_source(HorizonMask.from_json(raw), "disk")
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def _save(self, k: str, mask: HorizonMask) -> None:
        d = self._dir()
        tmp = d / f"{k}.{os.getpid()}.part"
        try:
            d.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(mask.to_json(k), separators=(",", ":"))
            size = len(payload.encode("utf-8"))
            if size > self.max_disk_bytes:
                log.warning("horizon mask exceeds disk cache quota; not persisted")
                return
            dem_cache.enforce_limit(
                d, self.max_disk_bytes - size, max_files=self.max_disk_entries - 1
            )
            root = self.quota_directory if self.quota_directory is not None else d
            if root != d:
                dem_cache.enforce_limit(root, self.max_disk_bytes - size)
            if (
                dem_cache.usage_bytes(root) + size > self.max_disk_bytes
                or len(dem_cache.cache_files(d)) >= self.max_disk_entries
            ):
                log.warning("horizon cache quota unavailable; mask not persisted")
                return
            tmp.write_text(payload, encoding="utf-8")
            os.replace(tmp, d / f"{k}.json")
            dem_cache.enforce_limit(d, self.max_disk_bytes, max_files=self.max_disk_entries)
            if self.quota_directory is not None:
                dem_cache.enforce_limit(self.quota_directory, self.max_disk_bytes)
        except OSError:
            log.warning("horizon disk cache write failed", exc_info=True)
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                log.warning("horizon temporary cache cleanup failed", exc_info=True)


def _with_source(mask: HorizonMask, source: str) -> HorizonMask:
    from dataclasses import replace

    return replace(mask, from_cache=source)


_STORE: MaskStore | None = None
_STORE_LOCK = threading.Lock()


def default_store() -> MaskStore:
    global _STORE
    with _STORE_LOCK:
        if _STORE is None:
            _STORE = MaskStore()
        return _STORE
