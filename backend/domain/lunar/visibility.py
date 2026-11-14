# SPDX-License-Identifier: Apache-2.0
"""Sun and Earth geometry seen from lunar sites, and Moon visibility from the DSN complexes.

All geometry comes from the validated engine `backend.ephemeris` (apparent az/el, no refraction,
smooth-sphere Moon, flat local horizon: NO terrain). One vectorised call per site and body.

Conventions:

* Each time step i stands for [t_i, t_i + dt); the geometry is sampled at the step START t_i.
* Sun: the visible disk counts. The Sun is "up" when its UPPER LIMB clears the elevation mask,
  i.e. el_centre + SUN_SEMIDIAMETER_DEG >= mask (semi-diameter 0.27 deg, explicit).
* Earth: the disk (semi-diameter ~0.95 deg from the Moon) is NOT added: Earth is visible when
  its CENTRE is at or above the mask. This is a documented simplification.
* Ground side: the Moon centre must be at or above the DSN minimum elevation at ANY of the three
  complexes (one 34 m BWG antenna per complex). Geodetic WGS 84 coordinates from DSN 810-005.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
from numpy.typing import NDArray

from backend.domain.lunar.model import SUN_SEMIDIAMETER_DEG, Site

__all__ = [
    "DSN_STATIONS",
    "DsnStation",
    "DsnVisibility",
    "SiteVisibility",
    "dsn_stations_info",
    "dsn_visibility",
    "site_visibility",
    "sun_distance_au",
]

Arr = NDArray[np.float64]
BoolArr = NDArray[np.bool_]
DSN_SOURCE = {
    "document": "DSN 810-005 Module 301 Rev. P (2026-05-22), Table 5 'Geodetic Coordinates for DSN "
    "Stations With Respect to the WGS 84 Ellipsoid'",
    "url": "https://deepspace.jpl.nasa.gov/dsndocs/810-005/301/301P.pdf",
    "accessed": "2026-10-20",
}


def _dms(deg: int, minutes: int, sec: float, south: bool = False) -> float:
    v = deg + minutes / 60.0 + sec / 3600.0
    return -v if south else v


@dataclass(frozen=True)
class DsnStation:
    complex: str
    name: str
    lat_deg: float  # geodetic WGS 84
    lon_deg_east: float  # in [0, 360) as published; the engine accepts any value
    height_m: float
    verified: bool  # True = copied from the cited document


# One 34 m BWG antenna per complex (the same class as the G/T default in DSN 810-005/104).
DSN_STATIONS: tuple[DsnStation, ...] = (
    DsnStation(
        "Goldstone",
        "DSS-24",
        _dms(35, 20, 23.61416),
        _dms(243, 7, 30.74007),
        951.499,
        True,
    ),
    DsnStation(
        "Canberra",
        "DSS-34",
        _dms(35, 23, 54.52383, south=True),
        _dms(148, 58, 55.07191),
        692.020,
        True,
    ),
    DsnStation(
        "Madrid",
        "DSS-54",
        _dms(40, 25, 32.23805),
        _dms(355, 44, 45.25141),
        837.051,
        True,
    ),
)


@dataclass(frozen=True)
class SiteVisibility:
    """Per-step Sun and Earth geometry for one site."""

    sun_az_deg: Arr
    sun_el_deg: Arr
    earth_az_deg: Arr
    earth_el_deg: Arr
    earth_range_km: Arr
    sun_up: BoolArr
    earth_visible: BoolArr


@dataclass(frozen=True)
class DsnVisibility:
    """Moon elevation at each complex and 'any complex above the minimum' flag."""

    moon_el_deg: Arr  # shape (n_stations, n)
    visible: BoolArr


def sun_distance_au(engine: Any, instants: list[datetime]) -> Arr:
    """Sun-Moon distance (centres, same instant) in AU, one vectorised call."""
    return np.asarray(engine.sun_distance_au("moon", instants), dtype=np.float64)


def site_visibility(
    engine: Any,
    site: Site,
    instants: list[datetime],
    *,
    sun_mask_deg: float,
    earth_mask_deg: float,
) -> SiteVisibility:
    sun = engine.topocentric_azel("moon", site.lat_deg, site.lon_deg_east, "sun", instants)
    earth = engine.topocentric_azel("moon", site.lat_deg, site.lon_deg_east, "earth", instants)
    return SiteVisibility(
        sun_az_deg=np.asarray(sun.az_deg, dtype=np.float64),
        sun_el_deg=np.asarray(sun.el_deg, dtype=np.float64),
        earth_az_deg=np.asarray(earth.az_deg, dtype=np.float64),
        earth_el_deg=np.asarray(earth.el_deg, dtype=np.float64),
        earth_range_km=np.asarray(earth.range_km, dtype=np.float64),
        sun_up=np.asarray(sun.el_deg + SUN_SEMIDIAMETER_DEG >= sun_mask_deg),
        earth_visible=np.asarray(earth.el_deg >= earth_mask_deg),
    )


def dsn_visibility(
    engine: Any, instants: list[datetime], min_elevation_deg: float
) -> DsnVisibility:
    """Moon elevation from Goldstone, Canberra and Madrid (engine Earth-observer topocentric)."""
    els = np.stack(
        [
            np.asarray(
                engine.topocentric_azel(
                    "earth", s.lat_deg, s.lon_deg_east, "moon", instants, h_m=s.height_m
                ).el_deg,
                dtype=np.float64,
            )
            for s in DSN_STATIONS
        ]
    )
    return DsnVisibility(els, np.asarray((els >= min_elevation_deg).any(axis=0)))


def dsn_stations_info() -> list[dict[str, Any]]:
    return [
        {
            "complex": s.complex,
            "antenna": s.name,
            "lat_deg": s.lat_deg,
            "lon_deg_east": s.lon_deg_east,
            "height_m": s.height_m,
            "verified": s.verified,
            "source": DSN_SOURCE,
        }
        for s in DSN_STATIONS
    ]
