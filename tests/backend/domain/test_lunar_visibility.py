# SPDX-License-Identifier: Apache-2.0
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from backend.domain.lunar.model import SUN_SEMIDIAMETER_DEG, load_sites
from backend.domain.lunar.visibility import (
    DSN_STATIONS,
    dsn_stations_info,
    dsn_visibility,
    site_visibility,
)
from backend.ephemeris import kernels

try:
    from backend.ephemeris.engine import get_engine

    ENGINE: Any = get_engine()
except kernels.EphemerisUnavailable:  # pragma: no cover
    ENGINE = None

needs_kernels = pytest.mark.skipif(ENGINE is None, reason="kernels missing (make ephemeris)")
T0 = datetime(2027, 4, 7, tzinfo=UTC)
TS = [T0 + timedelta(minutes=30 * i) for i in range(48 * 30)]


def test_dsn_coordinates_match_cited_table() -> None:
    by = {s.name: s for s in DSN_STATIONS}
    # DSN 810-005/301 Rev. P Table 5: DSS 24 35 20 23.61416, 243 07 30.74007; DSS 34 -35 23 54.52383,
    # 148 58 55.07191; DSS 54 40 25 32.23805, 355 44 45.25141
    assert by["DSS-24"].lat_deg == pytest.approx(35.339892, abs=1e-6)
    assert by["DSS-24"].lon_deg_east == pytest.approx(243.125206, abs=1e-6)
    assert by["DSS-34"].lat_deg == pytest.approx(-35.398478, abs=1e-6)
    assert by["DSS-34"].lon_deg_east == pytest.approx(148.981964, abs=1e-6)
    assert by["DSS-54"].lat_deg == pytest.approx(40.425622, abs=1e-6)
    assert by["DSS-54"].lon_deg_east == pytest.approx(355.745903, abs=1e-6)
    assert all(i["verified"] and "301P.pdf" in i["source"]["url"] for i in dsn_stations_info())


def _stub(az: float, el: np.ndarray) -> Any:
    n = len(el)

    def f(body: str, lat: float, lon: float, target: str, t: Any, h_m: float = 0.0) -> Any:
        return SimpleNamespace(
            az_deg=np.full(n, az), el_deg=el.copy(), range_km=np.full(n, 384400.0)
        )

    return SimpleNamespace(topocentric_azel=f)


def test_sun_disk_and_masks_with_stub() -> None:
    site = load_sites()[0]
    el = np.array([-0.30, -0.27, -0.2, 0.0, 5.0, 4.9])
    v = site_visibility(_stub(10.0, el), site, [T0] * 6, sun_mask_deg=0.0, earth_mask_deg=5.0)
    # upper limb: el + 0.27 >= 0  -> el >= -0.27
    assert list(v.sun_up) == [False, True, True, True, True, True]
    assert list(v.earth_visible) == [False, False, False, False, True, False]
    v2 = site_visibility(_stub(10.0, el), site, [T0] * 6, sun_mask_deg=5.0, earth_mask_deg=0.0)
    assert list(v2.sun_up) == [False, False, False, False, True, True]
    assert SUN_SEMIDIAMETER_DEG == 0.27


@needs_kernels
def test_dsn_moon_elevation_matches_independent_skyfield() -> None:
    from skyfield.api import load, wgs84

    ts = load.timescale()
    de = ENGINE._spk
    sample = TS[::20]
    vis = dsn_visibility(ENGINE, sample, 6.0)
    t = ts.from_datetimes(sample)
    for k, s in enumerate(DSN_STATIONS):
        obs = de["earth"] + wgs84.latlon(s.lat_deg, s.lon_deg_east, s.height_m)
        alt = obs.at(t).observe(de["moon"]).apparent().altaz()[0].degrees
        assert np.max(np.abs(alt - vis.moon_el_deg[k])) < 0.01
    assert vis.visible.dtype == bool


@needs_kernels
def test_moon_visible_from_some_complex_almost_always() -> None:
    vis = dsn_visibility(ENGINE, TS, 6.0)
    assert vis.visible.mean() > 0.9
    vis_hi = dsn_visibility(ENGINE, TS, 40.0)
    assert vis_hi.visible.mean() < vis.visible.mean()


@needs_kernels
def test_site_visibility_real_engine_shapes() -> None:
    site = load_sites()[0]
    v = site_visibility(ENGINE, site, TS, sun_mask_deg=0.0, earth_mask_deg=0.0)
    assert v.sun_el_deg.shape == (len(TS),) and v.sun_up.dtype == bool
    assert 355_000 < v.earth_range_km.min() < v.earth_range_km.max() < 407_000
