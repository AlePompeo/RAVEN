# SPDX-License-Identifier: Apache-2.0
"""Sun versus LOLA terrain: full horizon mask (`horizon.py`) for `/api/lunar/solar-terrain`,
and sampled radial profiles for `/api/lunar/horizon` (`circular_horizon`).

`solar_terrain` evaluates, at every timeline instant, the Sun's upper limb, centre and lower limb
and the visible fraction of the solar disc against the cached per-site horizon mask (20 m DEM to
10 km, 240 m DEM to 200 km, Moon curvature, explicit observer height). Until 2026-11-04 it sampled
a single 10 km profile along the Sun azimuth, which missed crater rims beyond 10 km (Haworth and de
Gerlache appeared sunlit; docs/domain/validation.md). Missing DEM data stays unknown and never
becomes an unobstructed horizon.
"""

import math
from collections.abc import Callable, Sequence
from typing import Any, Literal

import numpy as np

from backend.domain.grazing.dem import (
    FAR_DEM_ID,
    DemOutOfCoverage,
    DemUnavailable,
    LolaDem,
    load_lock,
)
from backend.domain.grazing.horizon import (
    DEFAULT_OBSERVER_HEIGHT_M,
    LIMITS,
    HorizonMask,
    default_store,
    disc_criteria,
)
from backend.domain.grazing.terrain import Horizon, horizon_from_profile, profile_from_dem
from backend.domain.lunar.model import SUN_SEMIDIAMETER_DEG

PROFILE_LENGTH_M = 10_000.0
HORIZON_AZIMUTH_STEP_DEG = 5
UNKNOWN_STATES = ("outside_coverage", "missing_dem", "invalid_geometry")
MaskFor = Callable[[dict[str, Any], float], HorizonMask]


def _sample_horizon(
    dem: LolaDem, site: dict[str, Any], az: float, observer_height_m: float = 0
) -> tuple[Horizon | None, Literal["ok", "outside_coverage", "missing_dem"]]:
    try:
        profile = profile_from_dem(dem, site["lat_deg"], site["lon_deg_east"], az, PROFILE_LENGTH_M)
        return (
            horizon_from_profile(
                profile,
                observer_height_m=observer_height_m,
                moon_radius_m=dem.spec.radius_km * 1000,
            ),
            "ok",
        )
    except DemOutOfCoverage:
        return None, "outside_coverage"
    except DemUnavailable:
        return None, "missing_dem"


def circular_horizon(
    site: dict[str, Any], dem: LolaDem, observer_height_m: float
) -> dict[str, Any]:
    """Finite radial profiles at 5-degree intervals; unsampled directions remain unknown."""
    samples = []
    for azimuth in range(0, 360, HORIZON_AZIMUTH_STEP_DEG):
        horizon, state = _sample_horizon(dem, site, float(azimuth), observer_height_m)
        samples.append(
            {
                "azimuth_deg": azimuth,
                "elevation_deg": horizon.elevation_deg if horizon else None,
                "distance_m": horizon.distance_m if horizon else None,
                "state": state,
            }
        )
    return {
        "site": site,
        "samples": samples,
        "dem_product": dem.spec.id,
        "dem_sha256": dem.spec.sha256,
        "dem_label_sha256": dem.spec.label_sha256,
        "lunar_frame": "MOON_ME_DE440_ME421",
        "profile_length_m": PROFILE_LENGTH_M,
        "profile_spacing_m": dem.spec.scale_m,
        "azimuth_step_deg": HORIZON_AZIMUTH_STEP_DEG,
        "observer_height_m": observer_height_m,
        "limits": (
            "Experimental sampled horizon; terrain between azimuths, between samples or "
            "beyond the profile is unknown. No interpolation or visibility guarantee."
        ),
        "dem_policy": "cached tiles only; no downloads",
    }


def _store_mask(site: dict[str, Any], observer_height_m: float) -> HorizonMask:
    return default_store().get(site["lat_deg"], site["lon_deg_east"], observer_height_m)


def _unknown_row(site_id: str, n: int, state: str) -> dict[str, Any]:
    none: list[Any] = [None] * n
    return {
        "site_id": site_id,
        "horizon_deg": none,
        "state": [state] * n,
        "centre_above_profile": none,
        "lower_above_profile": none,
        "upper_limb_visible": none,
        "centre_visible": none,
        "lower_limb_visible": none,
        "disc_fraction": none,
        "mask": None,
        "mask_state": state,
    }


def site_solar_terrain(
    site: dict[str, Any],
    sun_az: Sequence[float | None],
    sun_el: Sequence[float | None],
    semidiameter_deg: Sequence[float] | float,
    observer_height_m: float,
    mask_for: MaskFor | None = None,
) -> dict[str, Any]:
    """One site: criteria per instant against the cached mask; unknown never becomes sunlit."""
    n = len(sun_az)
    try:
        mask = (mask_for or _store_mask)(site, observer_height_m)
    except DemOutOfCoverage:
        return _unknown_row(site["id"], n, "outside_coverage")
    except DemUnavailable:
        return _unknown_row(site["id"], n, "missing_dem")
    az = np.array([np.nan if v is None else v for v in sun_az], dtype=np.float64)
    el = np.array([np.nan if v is None else v for v in sun_el], dtype=np.float64)
    c = disc_criteria(mask, az, el, np.asarray(semidiameter_deg, dtype=np.float64))
    states: list[str] = []
    for k in range(n):
        if not (math.isfinite(az[k]) and math.isfinite(el[k])):
            states.append("invalid_geometry")
        elif c["upper"][k] is None:
            states.append("missing_dem")
        else:
            states.append("upper_above_profile" if c["upper"][k] else "upper_below_profile")
    return {
        "site_id": site["id"],
        "horizon_deg": c["horizon_deg"],
        "state": states,
        # pre-2026-11-04 names, kept for compatibility: same values as the *_visible fields
        "centre_above_profile": c["centre"],
        "lower_above_profile": c["lower"],
        "upper_limb_visible": c["upper"],
        "centre_visible": c["centre"],
        "lower_limb_visible": c["lower"],
        "disc_fraction": c["disc_fraction"],
        "mask": mask.metadata(),
        "mask_state": "ok",
    }


def solar_terrain(
    timeline: dict[str, Any],
    *,
    observer_height_m: float = DEFAULT_OBSERVER_HEIGHT_M,
    semidiameter_deg: Sequence[float] | float = SUN_SEMIDIAMETER_DEG,
    mask_for: MaskFor | None = None,
) -> dict[str, Any]:
    """Compare the solar disc with each site's horizon mask at the timeline instants."""
    sites = [
        site_solar_terrain(
            row["site"],
            row["series"]["sun_az_deg"],
            row["series"]["sun_el_deg"],
            semidiameter_deg,
            observer_height_m,
            mask_for,
        )
        for row in timeline["sites"]
    ]
    semi = np.asarray(semidiameter_deg, dtype=np.float64)
    near, far = load_lock(), load_lock(dataset_id=FAR_DEM_ID)
    return {
        "window": timeline["window"],
        "series_time_unix": timeline["series_time_unix"],
        "sites": sites,
        "sun_semidiameter_mean_deg": float(semi.mean()) if semi.size else SUN_SEMIDIAMETER_DEG,
        "assumptions": {
            # near product (compatible string fields) and both products of the mask
            "dem_product": near.id,
            "dem_sha256": near.sha256,
            "dem_label_sha256": near.label_sha256,
            "dem_products": [
                {
                    "id": s.id,
                    "sha256": s.sha256,
                    "label_sha256": s.label_sha256,
                    "scale_m": s.scale_m,
                }
                for s in (near, far)
            ],
            "lunar_frame": timeline["assumptions"]["lunar_frame"],
            "ephemeris": timeline["assumptions"]["ephemeris"],
            "method": "horizon_mask",
            "profile_length_m": 200_000.0,  # compatibility: now the outer radius of the mask
            "profile_spacing_m": 10.0,  # compatibility: near-field sampling step
            "observer_height_m": observer_height_m,
            "observer_height_status": "I",
            "observer": (
                "eye at observer_height_m above the bilinearly interpolated DEM surface (tag I, "
                "default 2 m); the result is sensitive to it: Malapert 2027 visible disc 31.0% at "
                "0 m, 33.0% at 2 m, 45.9% at 10 m (docs/domain/validation.md)"
            ),
            # window-independent (assumptions are compared across scenarios): nominal value;
            # the per-instant values and their window mean are reported outside `assumptions`
            "sun_semidiameter_deg": SUN_SEMIDIAMETER_DEG,
            "sun_semidiameter_source": (
                "per instant asin(695700 km / Sun-Moon distance); this field is the nominal "
                "0.27 deg, the window mean is sun_semidiameter_mean_deg"
                if semi.ndim
                else "fixed 0.27 deg"
            ),
            "limb_criteria": (
                "state = upper limb (centre elevation + semidiameter) vs the horizon mask at the "
                "Sun azimuth; centre_visible and lower_limb_visible apply the same mask to the "
                "centre and the lower limb; disc_fraction = visible fraction of the solar disc "
                "integrated over 48 vertical strips against the mask (no limb darkening); null "
                "when the answer depends on missing DEM data"
            ),
            "azimuth": "solar centre; north through east; mask linearly interpolated in azimuth",
            "sampling": "10 m to 10 km (20 m DEM), 120 m to 200 km (240 m DEM), bilinear",
            "coverage_limits": {
                "outer_radius_m": 200_000.0,
                "beyond": "terrain beyond 200 km is not modelled",
                "dem_uncertainty": "not modelled",
                "missing_dem": "unknown state, never sunlit",
            },
            "limits": LIMITS,
            "dem_policy": "cached tiles only; no downloads",
        },
    }
