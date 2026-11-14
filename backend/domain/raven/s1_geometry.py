# SPDX-License-Identifier: Apache-2.0
"""S1 ephemeris geometry (docs/domain/raven-model.md, 2.4).

Sun and Earth are seen from the site (topocentric: parallax and physical libration included) at the
grid instants; distances are the true ones; semidiameters follow from them (Sun `asin(R_sun/d)`,
Earth `atan(R_E/d)`); the Moon is also seen from the three DSN complexes (DSN 810-005/301 Rev. P,
Table 5). Heights are 0: the site is on the reference sphere; observer and antenna heights enter in
S2. Apparent az/el, no refraction. There is no partial result without ephemerides: the caller maps
`EphemerisUnavailable` to 503.

This stage wraps `grazing.geometry.earth_geometry`, `lunar.visibility.dsn_visibility` and
`grazing.horizon.sun_semidiameter_deg`; it adds no new formula except the Earth semidiameter, which
is half of `earth_angular_diameter_deg`.
"""

from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from backend.domain.grazing.geometry import earth_angular_diameter_deg, earth_geometry
from backend.domain.grazing.horizon import sun_semidiameter_deg
from backend.domain.lunar.visibility import DSN_STATIONS, dsn_visibility
from backend.domain.raven import params as reg
from backend.domain.raven.s0_context import SiteRecord, TimeGrid

__all__ = ["Arr", "Geometry", "geometry"]

Arr = NDArray[np.float64]


@dataclass(frozen=True)
class Geometry:
    """Sun, Earth and DSN geometry, one value per grid step (site on the reference sphere, h = 0)."""

    sun_az_deg: Arr  # 0 = North, clockwise, apparent, no refraction
    sun_el_deg: Arr
    sun_range_km: Arr  # true distance, not 1 AU
    sun_semidiameter_deg: Arr  # asin(R_sun / range)
    earth_az_deg: Arr  # azimuth along which the RF profile is cut
    earth_el_deg: Arr  # topocentric (parallax and physical libration included)
    earth_range_km: Arr  # true distance, not 384 400 km
    earth_semidiameter_deg: Arr  # atan(R_E / range)
    earth_el_geocentric_deg: Arr  # Moon centre -> Earth centre, no parallax
    parallax_deg: Arr  # geocentric minus topocentric elevation
    sub_earth_lat_deg: Arr
    sub_earth_lon_deg_east: Arr
    dsn_complexes: tuple[str, ...]  # order of the rows of `dsn_moon_el_deg`
    dsn_moon_el_deg: Arr  # shape (n_complexes, n): elevation of the Moon centre


def geometry(engine: Any, site: SiteRecord, grid: TimeGrid) -> Geometry:
    """Geometry of `site` over `grid` with one vectorised engine call per body."""
    inst = list(grid.instants)
    sun = engine.topocentric_azel("moon", site.lat_deg, site.lon_deg_east, "sun", inst)
    sun_au = np.asarray(engine.sun_distance_au("moon", inst), dtype=np.float64)
    sun_range = sun_au * reg.value("common.au_km")
    eg = earth_geometry(site.lat_deg, site.lon_deg_east, inst, engine=engine)
    sub = engine.sub_earth_point("moon", inst)
    dsn = dsn_visibility(engine, inst, reg.value("lunar.ground_station_min_elevation_deg"))
    return Geometry(
        sun_az_deg=np.asarray(sun.az_deg, dtype=np.float64),
        sun_el_deg=np.asarray(sun.el_deg, dtype=np.float64),
        sun_range_km=sun_range,
        sun_semidiameter_deg=sun_semidiameter_deg(sun_range),
        earth_az_deg=eg.az_deg,
        earth_el_deg=eg.el_deg,
        earth_range_km=eg.range_km,
        earth_semidiameter_deg=earth_angular_diameter_deg(eg.range_km) / 2.0,
        earth_el_geocentric_deg=eg.el_geocentric_deg,
        parallax_deg=eg.parallax_deg,
        sub_earth_lat_deg=np.asarray(sub.lat_deg, dtype=np.float64),
        sub_earth_lon_deg_east=np.asarray(sub.lon_deg_east, dtype=np.float64),
        dsn_complexes=tuple(s.complex for s in DSN_STATIONS),
        dsn_moon_el_deg=dsn.moon_el_deg,
    )
