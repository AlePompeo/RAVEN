# SPDX-License-Identifier: Apache-2.0
"""Physical sanity of the whole chain with the real engine.

Expected values are derived from geometry (not fitted to the output):

* Earth elevation at a lunar site of colatitude/offset theta from the sub-Earth point:
  tan(el) = (d cos(theta) - R) / (d sin(theta)), d = Earth-Moon centre distance, R = 1737.4 km
  (smooth sphere; the d >> R limit is el = 90 deg - theta). The sub-Earth point (libration) moves
  within about +/-7.6 deg in longitude and +/-6.8 deg in latitude (Phase A scan, MOONFACT
  libration up to ~7 deg), so the Earth elevation at Apollo 11 (0.67 N, 23.47 E) stays in
  90 - (23.5 + 8) - 0.3 (parallax) .. 90 - (23.5 - 8) = 57.5 .. 75 deg.
* At a polar site at colatitude c the elevation is el ~ c*cos(dlon) - beta(t), beta = sub-Earth
  latitude oscillating +/-6.8 deg with the 27.2 d draconic period, so the Earth is above a flat
  horizon for the fraction of the cycle where beta < c cos(dlon): ~50 % for c << 6.8 deg
  (Shackleton, c = 0.33 deg), up to ~70 % for c = 4 deg (Malapert) and never 0 or 100 %.
* Sun at a near-equatorial site is up about half of a synodic month (29.53 d).
"""

import math
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
import pytest

from backend.domain.lunar.model import load_sites
from backend.domain.lunar.visibility import site_visibility
from backend.ephemeris import kernels

try:
    from backend.ephemeris.engine import get_engine

    ENGINE: Any = get_engine()
except kernels.EphemerisUnavailable:  # pragma: no cover
    ENGINE = None

pytestmark = pytest.mark.skipif(ENGINE is None, reason="kernels missing (make ephemeris)")
SITES = {s.id: s for s in load_sites()}
# the six polar sites of the original catalogue; the Apollo, Chang'e 4 and Chandrayaan-3 sites are not polar
POLAR_SITES = (
    "malapert-massif",
    "haworth",
    "mons-mouton",
    "nobile-rim",
    "de-gerlache",
    "shackleton",
)
R = 1737.4


def grid(start: datetime, days: float, step_min: float) -> list[datetime]:
    n = int(days * 1440 / step_min)
    return [start + timedelta(minutes=step_min * i) for i in range(n)]


YEAR = grid(datetime(2027, 1, 1, tzinfo=UTC), 365.25, 60)


def vis(site: str, ts: list[datetime], sun_mask: float = 0.0, earth_mask: float = 0.0) -> Any:
    return site_visibility(
        ENGINE, SITES[site], ts, sun_mask_deg=sun_mask, earth_mask_deg=earth_mask
    )


def geometric_earth_el(site: str, ts: list[datetime]) -> Any:
    """Earth elevation from the sub-Earth point only (independent of topocentric_azel)."""
    s = SITES[site]
    p = ENGINE.sub_earth_point("moon", ts)
    la, lo = np.radians(s.lat_deg), np.radians(s.lon_deg_east)
    pb, pl = np.radians(p.lat_deg), np.radians(p.lon_deg_east)
    cos_t = np.sin(la) * np.sin(pb) + np.cos(la) * np.cos(pb) * np.cos(lo - pl)
    theta = np.arccos(np.clip(cos_t, -1, 1))
    d = ENGINE.distance_km("earth", "moon", ts)
    return np.degrees(np.arctan2(d * np.cos(theta) - R, d * np.sin(theta)))


def test_apollo11_earth_high_and_always_visible() -> None:
    v = vis("apollo11", YEAR)
    assert v.earth_visible.mean() == 1.0
    assert 57.5 <= v.earth_el_deg.min() and v.earth_el_deg.max() <= 76.0
    # sanity of the derivation itself: the pure-geometry elevation agrees with the engine
    g = geometric_earth_el("apollo11", YEAR[::6])
    assert np.max(np.abs(g - v.earth_el_deg[::6])) < 0.15


@pytest.mark.parametrize("site", ["malapert-massif", "haworth", "mons-mouton", "shackleton"])
def test_polar_earth_elevation_matches_geometry(site: str) -> None:
    v = vis(site, YEAR)
    g = geometric_earth_el(site, YEAR[::6])
    assert np.max(np.abs(g - v.earth_el_deg[::6])) < 0.2
    # at polar sites the Earth stays within the libration band around the horizon
    assert -12.0 < v.earth_el_deg.min() and v.earth_el_deg.max() < 12.0


def test_polar_earth_visible_only_part_of_the_time() -> None:
    fracs = {s: float(vis(s, YEAR).earth_visible.mean()) for s in SITES if s in POLAR_SITES}
    for s, f in fracs.items():
        assert 0.40 < f < 0.80, (s, f)
    # c << 6.8 deg: close to one half (symmetric libration); here c = 0.33 deg
    assert fracs["shackleton"] == pytest.approx(0.5, abs=0.05)
    # c = 4 deg: sin x <= 4/6.8 -> 1 - (pi - 2 asin(0.59))/(2 pi) ~ 0.70
    expected = 1 - (math.pi - 2 * math.asin(4.0 / 6.8)) / (2 * math.pi)
    assert fracs["malapert-massif"] == pytest.approx(expected, abs=0.06)
    # with a 5 deg horizon mask the visible fraction can only shrink
    assert (
        float(vis("malapert-massif", YEAR, earth_mask=5.0).earth_visible.mean())
        < fracs["malapert-massif"]
    )


def test_sun_fraction_equatorial_site_about_half_of_a_synodic_month() -> None:
    # One 29.53 d window at 12 start dates across a year. A window of the MEAN synodic length
    # differs from the true lunation (29.27-29.83 d) by at most 0.3 d, so the daylight fraction
    # can deviate by ~0.3/2/29.53 = 0.005; the 0.27 deg disk and 0.67 deg latitude add < 0.002.
    sun_days = []
    for k in range(12):
        ts = grid(datetime(2027, 1, 1, tzinfo=UTC) + timedelta(days=30.4 * k), 29.53, 10)
        v = vis("apollo11", ts)
        sun_days.append(float(v.sun_up.mean()) * 29.53)
    assert all(abs(d - 14.77) < 0.35 for d in sun_days), sun_days
    assert abs(float(np.mean(sun_days)) - 14.77) < 0.15
    # Apollo 17 (20 N) is also close to one half
    v17 = vis("apollo17", grid(datetime(2027, 1, 1, tzinfo=UTC), 29.53, 10))
    assert abs(float(v17.sun_up.mean()) - 0.5) < 0.03


def test_sun_never_sets_difference_with_mask() -> None:
    ts = grid(datetime(2027, 1, 1, tzinfo=UTC), 29.53, 10)
    f0 = float(vis("apollo11", ts).sun_up.mean())
    f5 = float(vis("apollo11", ts, sun_mask=5.0).sun_up.mean())
    assert f5 < f0
    # a 5 deg mask removes 2*5/360 of the cycle (the Sun's hour angle advances 360 deg per month)
    assert f0 - f5 == pytest.approx(10.0 / 360.0, abs=0.002)
