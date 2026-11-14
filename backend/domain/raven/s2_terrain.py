# SPDX-License-Identifier: Apache-2.0
"""S2 terrain (docs/domain/raven-model.md, 2.5).

Terrain comes only from LOLA (or a profile of the user, or a synthetic profile in tests, always
marked by the caller). A missing tile or a site outside the coverage is UNKNOWN, never an
unobstructed horizon.

Per grid step this stage gives:

* the horizon of the mask (20 m LOLA to 10 km, 240 m to 200 km, curvature, explicit eye height) at
  the Sun azimuth AND at the Earth azimuth (the mask was only read towards the Sun before);
* the RF profile along the Earth azimuth (`profile_length_m`, azimuth quantised to 0.1 deg) with its
  dominant obstacle (largest Fresnel-Kirchhoff parameter) and the highest terrain angle inside it;
* `far_terrain_hides_earth`: the highest terrain at the Earth azimuth lies BEYOND the RF profile
  and above the Earth centre. The single-obstacle RF model cannot represent it: `terrain_reason`
  is decided by D4 (ruling 2026-11-05): the knife-edge loss of that far obstacle (single obstacle,
  declared approximate, `diffraction.knife_edge_loss_db` with d1, d2 and the angle above the upper
  limb of the Earth) is `far_terrain_loss_db`; at or above `common.far_terrain_blocked_loss_db`
  (30 dB, tag I) the state is the KNOWN `blocked_far_terrain` (the link does not close, never
  "ok", never unknown); below it, `outside_model` (unknown: more obstacles / diffraction not modelled).

Heights are explicit: `panel_height_m` for the Sun mask, `antenna_height_m` for the Earth mask and
the RF profile (decision D8: two distinct parameters).

This stage wraps `horizon.compute_mask`/`MaskStore`, `terrain.profile_from_dem`, `dominant_ridge`
and `horizon_from_profile`; only the Earth-azimuth reading and the coherence check are new.

Limitation of `far_terrain_hides_earth`: the mask keeps only the highest sample per azimuth. If a
nearer, higher sample sets the horizon, farther terrain that also exceeds the Earth elevation is
not seen: the count is a lower bound of the far-terrain cases.
"""

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from backend.domain.grazing.analysis import AZIMUTH_QUANTUM_DEG, ProfileCache
from backend.domain.grazing.dem import DemOutOfCoverage, DemUnavailable
from backend.domain.grazing.diffraction import knife_edge_loss_db, nu_from_angle
from backend.domain.grazing.horizon import (
    HorizonMask,
    default_store,
    horizon_at,
    horizon_distance_m,
)
from backend.domain.grazing.terrain import (
    DominantRidge,
    TerrainProfile,
    dominant_ridge,
    horizon_from_profile,
)
from backend.domain.raven import params as reg
from backend.domain.raven.known import Known, Reason
from backend.domain.raven.s0_context import SiteRecord
from backend.domain.raven.s1_geometry import Geometry

__all__ = [
    "DominantRidge",
    "HorizonMask",
    "Terrain",
    "TerrainParams",
    "TerrainProfile",
    "terrain",
]

MaskFor = Callable[[float, float, float], HorizonMask]
ProfileFor = Callable[[float], TerrainProfile]


@dataclass(frozen=True)
class TerrainParams:
    """Heights and lengths of S2, explicit. Defaults come from the registry."""

    panel_height_m: float
    antenna_height_m: float
    profile_length_m: float
    wavelength_m: float
    moon_radius_m: float

    @classmethod
    def from_registry(cls, **over: float) -> "TerrainParams":
        base = {
            "panel_height_m": reg.value("common.observer_height_default_m"),
            "antenna_height_m": reg.value("grazing.antenna_height_m"),
            "profile_length_m": reg.value("grazing.profile_length_m"),
            "wavelength_m": reg.value("grazing.wavelength_m"),
            "moon_radius_m": reg.value("grazing.moon_radius_km") * 1000.0,
        }
        base.update(over)
        return cls(**base)


@dataclass(frozen=True)
class Terrain:
    """Horizon mask for the Sun and the Earth direction plus the RF profile and its dominant obstacle."""

    mask: HorizonMask | None  # panel-height mask (Sun); None when the tiles are unknown
    mask_state: Reason  # ok | missing_dem | outside_coverage
    mask_meta: dict[str, Any] | None
    params: TerrainParams
    sun_horizon_deg: list[Known[float]]  # mask at the Sun azimuth; None = azimuth incomplete
    earth_horizon_deg: list[Known[float]]  # mask at the Earth azimuth, antenna height
    earth_horizon_distance_m: list[Known[float]]  # ground distance of that horizon
    rf_obstacle: list[DominantRidge | None]
    rf_profile_horizon_deg: list[Known[float]]  # highest terrain angle inside the RF profile
    far_terrain_hides_earth: list[Known[bool]]  # mask beyond the profile above the Earth centre
    far_terrain_loss_db: list[Known[float]]  # single knife-edge loss of that far obstacle
    terrain_reason: list[Reason]  # for S5: ok | missing_dem | outside_coverage | outside_model


def _quantise(az_deg: float) -> float:
    return float((round(az_deg / AZIMUTH_QUANTUM_DEG) * AZIMUTH_QUANTUM_DEG) % 360.0)


def _state(exc: Exception) -> Reason:
    return Reason.OUTSIDE_COVERAGE if isinstance(exc, DemOutOfCoverage) else Reason.MISSING_DEM


def _read_horizon(
    mask: HorizonMask | None, az: np.ndarray
) -> tuple[list[Known[float]], list[Known[float]], np.ndarray, np.ndarray, np.ndarray]:
    """(horizon deg, distance m, complete, raw horizon, raw distance) at the azimuths.

    The first two are None where the azimuth is not fully known; the raw arrays keep the lower
    bound of an incomplete azimuth (a known terrain sample can only hide MORE, never less).
    """
    n = az.size
    if mask is None:
        nan = np.full(n, np.nan)
        return [None] * n, [None] * n, np.zeros(n, dtype=bool), nan, nan
    h, comp = horizon_at(mask, az)
    d = horizon_distance_m(mask, az)
    fin = np.isfinite(az)
    ok = comp & np.isfinite(h) & fin
    hv = [float(h[k]) if ok[k] else None for k in range(n)]
    dv = [float(d[k]) if ok[k] and math.isfinite(d[k]) else None for k in range(n)]
    raw_h = np.where(fin & np.isfinite(h), h, np.nan)
    return hv, dv, np.asarray(comp & fin), raw_h, d


def _far_loss_db(geo: Geometry, i: int, horizon_deg: float, dist_m: float, lam: float) -> float:
    """Knife-edge loss (dB) of the far obstacle seen at `horizon_deg`, `dist_m` away, against the
    UPPER limb of the Earth. Single obstacle, small angles: declared approximate (D4)."""
    upper = float(geo.earth_el_deg[i] + geo.earth_semidiameter_deg[i])
    d1 = max(dist_m, 1.0)
    d2 = max(float(geo.earth_range_km[i]) * 1000.0 - d1, 1.0)
    nu = nu_from_angle(math.radians(horizon_deg - upper), d1, d2, lam)
    return float(knife_edge_loss_db(nu))


def _get_mask(
    mask_for: MaskFor, site: SiteRecord, height_m: float
) -> tuple[HorizonMask | None, Reason]:
    try:
        return mask_for(site.lat_deg, site.lon_deg_east, height_m), Reason.OK
    except (DemOutOfCoverage, DemUnavailable) as e:
        return None, _state(e)


def _default_profile_for(site: SiteRecord, length_m: float, cache: ProfileCache) -> ProfileFor:
    from backend.domain.grazing.dem import LolaDem
    from backend.domain.grazing.terrain import profile_from_dem

    dem = LolaDem(allow_download=False)

    def make(azq: float) -> TerrainProfile:
        key = (dem.spec.id, round(site.lat_deg, 5), round(site.lon_deg_east, 5), azq, length_m)
        return cache.get(
            key, lambda: profile_from_dem(dem, site.lat_deg, site.lon_deg_east, azq, length_m)
        )

    return make


def terrain(
    site: SiteRecord,
    geo: Geometry,
    params: TerrainParams | None = None,
    *,
    mask_for: MaskFor | None = None,
    profile_for: ProfileFor | None = None,
    cache: ProfileCache | None = None,
    injected: bool | None = None,
) -> Terrain:
    """S2 over the grid of `geo`. `mask_for(lat, lon, height_m)` and `profile_for(azimuth_deg)`
    are injectable (tests, user profiles, the per-site product of a custom site: then `injected=False`,
    the terrain is real LOLA and a hole is a missing input); the defaults read the cached LOLA tiles only."""
    p = params or TerrainParams.from_registry()
    get_mask: MaskFor = mask_for or (
        lambda lat, lon, h: default_store().get(lat, lon, h)  # cached tiles, never downloads
    )
    n = geo.sun_az_deg.size

    mask, mask_state = _get_mask(get_mask, site, p.panel_height_m)
    if p.antenna_height_m == p.panel_height_m:
        earth_mask, earth_state = mask, mask_state
    else:
        earth_mask, earth_state = _get_mask(get_mask, site, p.antenna_height_m)

    sun_h = _read_horizon(mask, geo.sun_az_deg)[0]
    earth_h, earth_d, earth_comp, raw_h, raw_d = _read_horizon(earth_mask, geo.earth_az_deg)

    covered = site.dem_coverage is not False
    pf = profile_for
    if injected is None:
        injected = profile_for is not None  # a user or synthetic profile stands for the terrain
    if pf is None and covered:
        pf = _default_profile_for(site, p.profile_length_m, cache or ProfileCache())

    rf_obstacle: list[DominantRidge | None] = []
    rf_horizon: list[Known[float]] = []
    far: list[Known[bool]] = []
    far_loss: list[Known[float]] = []
    blocked_db = reg.value("common.far_terrain_blocked_loss_db")
    reason: list[Reason] = []
    for i in range(n):
        r = Reason.OK
        obstacle: DominantRidge | None = None
        prof_h: Known[float] = None
        if pf is None:
            r = Reason.OUTSIDE_COVERAGE
        else:
            try:
                prof = pf(_quantise(float(geo.earth_az_deg[i])))
                obstacle = dominant_ridge(
                    prof,
                    float(geo.earth_el_deg[i]),
                    p.wavelength_m,
                    earth_range_m=float(geo.earth_range_km[i]) * 1000.0,
                    antenna_height_m=p.antenna_height_m,
                    moon_radius_m=p.moon_radius_m,
                )
                prof_h = horizon_from_profile(
                    prof, observer_height_m=p.antenna_height_m, moon_radius_m=p.moon_radius_m
                ).elevation_deg
            except (DemOutOfCoverage, DemUnavailable) as e:
                r = _state(e)
        # far terrain: the highest mask sample towards the Earth is beyond the RF profile and above
        # the Earth centre. A known "no" needs a complete azimuth (unknown samples may hide more).
        el = float(geo.earth_el_deg[i])
        hides: Known[bool]
        if earth_mask is None:
            hides = None
        elif math.isfinite(raw_h[i]) and raw_h[i] > el:
            # terrain already above the Earth centre: hidden; "far" if its distance is past the profile
            hides = bool(math.isfinite(raw_d[i]) and raw_d[i] > p.profile_length_m)
        elif earth_comp[i]:
            hides = False
        else:
            hides = None
        loss_i: Known[float] = (
            _far_loss_db(geo, i, raw_h[i], raw_d[i], p.wavelength_m) if hides is True else None
        )
        if r is Reason.OK and earth_state is not Reason.OK and not injected:
            r = earth_state
        if r is Reason.OK:
            if hides is True and loss_i is not None:
                r = Reason.BLOCKED_FAR_TERRAIN if loss_i >= blocked_db else Reason.OUTSIDE_MODEL
            elif hides is None and not injected:
                r = Reason.MISSING_DEM  # the far field towards the Earth is not fully known
        rf_obstacle.append(obstacle)
        rf_horizon.append(prof_h)
        far.append(hides)
        far_loss.append(loss_i)
        reason.append(r)

    return Terrain(
        mask=mask,
        mask_state=mask_state,
        mask_meta=mask.metadata() if mask is not None else None,
        params=p,
        sun_horizon_deg=sun_h,
        earth_horizon_deg=earth_h,
        earth_horizon_distance_m=earth_d,
        rf_obstacle=rf_obstacle,
        rf_profile_horizon_deg=rf_horizon,
        far_terrain_hides_earth=far,
        far_terrain_loss_db=far_loss,
        terrain_reason=reason,
    )
