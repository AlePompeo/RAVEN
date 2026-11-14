# SPDX-License-Identifier: Apache-2.0
"""Earth seen from a lunar site over time: topocentric azimuth/elevation, distance, angular size.

Everything comes from the validated engine `backend.ephemeris` (Skyfield + NAIF DE440 + the DE440
lunar principal-axes PCK): real physical libration and TOPOCENTRIC parallax (the site is on the
surface, not at the Moon centre). The toy sinusoidal libration of `compensation_demo.py` is NOT used
(docs/domain/grazinglink-model.md, sec. 2.1). Apparent az/el, no refraction, smooth sphere, flat local
horizon: the terrain is handled in `terrain.py`.

Tags: Earth radius 6371 km is I (standard value); the angular diameter is D = 2 atan(R_E / d).
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

import numpy as np
from numpy.typing import NDArray

from backend.domain.lunar.link import fspl_db

__all__ = [
    "EARTH_RADIUS_KM",
    "EarthGeometry",
    "EphemerisLike",
    "earth_angular_diameter_deg",
    "earth_geometry",
    "free_space_loss_series_db",
    "great_circle_destination",
]

Arr = NDArray[np.float64]
EARTH_RADIUS_KM = 6371.0  # tag I (EARTHFACT via assumptions.md)
Instants = str | datetime | Sequence[str | datetime]


def great_circle_destination(
    lat_deg: float, lon_deg: float, az: Arr, delta: Arr
) -> tuple[Arr, Arr]:
    """Spherical destinations along north-clockwise bearings, stable at both poles."""
    la, lo = math.radians(lat_deg), math.radians(lon_deg)
    sl, cl, so, co = math.sin(la), math.cos(la), math.sin(lo), math.cos(lo)
    ca, sa, cd, sd = np.cos(az), np.sin(az), np.cos(delta), np.sin(delta)
    # Rotate the site vector along its local north/east tangent, avoiding polar 0/0.
    x = cl * co * cd + (-sl * co * ca - so * sa) * sd
    y = cl * so * cd + (-sl * so * ca + co * sa) * sd
    z = sl * cd + cl * ca * sd
    latitude = np.degrees(np.arctan2(z, np.hypot(x, y)))
    longitude = (np.degrees(np.arctan2(y, x)) + 180.0) % 360.0 - 180.0
    return latitude, longitude


class EphemerisLike(Protocol):
    """The subset of `backend.ephemeris.engine.Engine` used here (allows a stub in tests)."""

    def topocentric_azel(
        self,
        site_body: str,
        lat_deg: float,
        lon_deg_east: float,
        target: str,
        t: Instants,
        h_m: float = 0.0,
    ) -> Any: ...

    def sub_earth_point(self, body: str, t: Instants) -> Any: ...


@dataclass(frozen=True)
class EarthGeometry:
    """Earth as seen from the site, one value per instant."""

    az_deg: Arr  # 0 = local North, clockwise (the azimuth along which the terrain profile is cut)
    el_deg: Arr  # topocentric elevation of the Earth CENTRE over the local horizontal
    range_km: Arr  # site -> Earth centre (astrometric, light time)
    angular_diameter_deg: Arr  # D: 2 atan(R_E / range)
    el_geocentric_deg: Arr  # elevation of the Moon-centre -> Earth-centre direction (no parallax)
    parallax_deg: Arr  # el_geocentric - el_topocentric (>= 0 near the horizon, up to ~0.26 deg)


def earth_angular_diameter_deg(range_km: float | Arr) -> Arr:
    """Angular diameter of the Earth: 2 atan(R_E / d) (1.8991 deg at 384 400 km)."""
    d = np.asarray(range_km, dtype=np.float64)
    if np.any(d <= 0):
        raise ValueError("distance must be positive")
    return np.asarray(np.degrees(2.0 * np.arctan(EARTH_RADIUS_KM / d)), dtype=np.float64)


def _default_engine() -> EphemerisLike:
    from backend.ephemeris.engine import get_engine

    return get_engine()


def earth_geometry(
    lat_deg: float,
    lon_deg_east: float,
    times: Instants,
    *,
    height_m: float = 0.0,
    engine: EphemerisLike | None = None,
) -> EarthGeometry:
    """Azimuth, elevation, distance and angular size of the Earth from a lunar site.

    Raises `backend.ephemeris.kernels.EphemerisUnavailable` when the kernels are missing (the API maps
    it to 503). `height_m` is the antenna height above the reference sphere.
    """
    eng = engine if engine is not None else _default_engine()
    tt = [times] if isinstance(times, (str, datetime)) else list(times)
    azel = eng.topocentric_azel("moon", lat_deg, lon_deg_east, "earth", tt, height_m)
    sub = eng.sub_earth_point("moon", tt)
    la, lo = math.radians(lat_deg), math.radians(lon_deg_east)
    sl, so = np.radians(np.asarray(sub.lat_deg)), np.radians(np.asarray(sub.lon_deg_east))
    # unit vectors: site zenith n and Moon-centre -> Earth-centre direction e (body-fixed frame)
    sin_el_geo = math.sin(la) * np.sin(sl) + math.cos(la) * np.cos(sl) * np.cos(so - lo)
    el_geo = np.degrees(np.arcsin(np.clip(sin_el_geo, -1.0, 1.0)))
    el = np.asarray(azel.el_deg, dtype=np.float64)
    rng = np.asarray(azel.range_km, dtype=np.float64)
    return EarthGeometry(
        az_deg=np.asarray(azel.az_deg, dtype=np.float64),
        el_deg=el,
        range_km=rng,
        angular_diameter_deg=earth_angular_diameter_deg(rng),
        el_geocentric_deg=np.asarray(el_geo, dtype=np.float64),
        parallax_deg=np.asarray(el_geo - el, dtype=np.float64),
    )


def free_space_loss_series_db(range_km: Arr, frequency_ghz: float) -> Arr:
    """FSPL(t) with the true Earth distance (not a fixed 384 400 km): 222.14-223.09 dB at 8.4 GHz."""
    return np.asarray(fspl_db(np.asarray(range_km, dtype=np.float64), frequency_ghz))
