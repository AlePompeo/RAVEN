# SPDX-License-Identifier: Apache-2.0
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from backend.domain.grazing.geometry import (
    earth_angular_diameter_deg,
    earth_geometry,
    free_space_loss_series_db,
)
from backend.domain.lunar.model import load_sites
from backend.ephemeris import kernels

try:
    from backend.ephemeris.engine import get_engine

    ENGINE: Any = get_engine()
except kernels.EphemerisUnavailable:  # pragma: no cover
    ENGINE = None

needs_kernels = pytest.mark.skipif(ENGINE is None, reason="kernels missing (make ephemeris)")
T0 = datetime(2027, 4, 7, tzinfo=UTC)
TS = [T0 + timedelta(hours=3 * i) for i in range(8 * 28)]  # one lunar month, 3 h step
MALAPERT = next(s for s in load_sites() if s.id == "malapert-massif")


def test_angular_diameter_model_doc() -> None:
    assert float(earth_angular_diameter_deg(384_400.0)) == pytest.approx(1.8991, abs=1e-3)
    assert float(earth_angular_diameter_deg(363_300.0)) == pytest.approx(2.009, abs=2e-3)
    assert float(earth_angular_diameter_deg(405_500.0)) == pytest.approx(1.800, abs=2e-3)
    with pytest.raises(ValueError):
        earth_angular_diameter_deg(0.0)


def test_fspl_series_uses_true_distance() -> None:
    f = free_space_loss_series_db(np.array([363_300.0, 384_400.0, 405_500.0]), 8.4)
    np.testing.assert_allclose(f, [222.139, 222.629, 223.093], atol=1e-3)


def test_stub_engine_no_kernels_needed() -> None:
    """Geocentric elevation: site on the sub-Earth point -> 90 deg; parallax = geo - topo."""
    stub = SimpleNamespace(
        topocentric_azel=lambda *a, **k: SimpleNamespace(
            az_deg=np.array([10.0]), el_deg=np.array([89.9]), range_km=np.array([384_400.0])
        ),
        sub_earth_point=lambda *a, **k: SimpleNamespace(
            lat_deg=np.array([-86.0]), lon_deg_east=np.array([0.12])
        ),
    )
    g = earth_geometry(-86.0, 0.12, [T0], engine=stub)
    assert g.el_geocentric_deg[0] == pytest.approx(90.0, abs=1e-6)
    assert g.parallax_deg[0] == pytest.approx(0.1, abs=1e-6)
    assert g.angular_diameter_deg[0] == pytest.approx(1.8991, abs=1e-3)


@needs_kernels
def test_earth_elevation_at_south_pole_site_within_libration_range() -> None:
    g = earth_geometry(MALAPERT.lat_deg, MALAPERT.lon_deg_east, TS, engine=ENGINE)
    # Earth elevation at lat -86 deg is about 4 deg (90 - 86) +- the libration in latitude (~6.7 deg)
    assert g.el_deg.min() > -4.0 - 1.0
    assert (
        g.el_deg.max() < 12.0
    )  # JPL226 p. 35 (Fig. 9): "almost never rises above 12 deg" (Malapert)
    assert g.el_deg.max() - g.el_deg.min() > 8.0  # librations of a few degrees at least
    assert (g.el_deg < 0).any() and (g.el_deg > 0).any()  # Earth sets for part of the month
    # azimuth along which the terrain is cut: defined and in [0, 360)
    assert np.all((g.az_deg >= 0) & (g.az_deg < 360))


@needs_kernels
def test_distance_and_angular_diameter_in_real_range() -> None:
    g = earth_geometry(MALAPERT.lat_deg, MALAPERT.lon_deg_east, TS, engine=ENGINE)
    assert 355_000 < g.range_km.min() < g.range_km.max() < 407_000
    assert 1.79 < g.angular_diameter_deg.min() < g.angular_diameter_deg.max() < 2.02
    assert g.range_km.max() - g.range_km.min() > 10_000  # not a constant 384 400 km


@needs_kernels
def test_parallax_up_to_quarter_degree_near_horizon() -> None:
    g = earth_geometry(MALAPERT.lat_deg, MALAPERT.lon_deg_east, TS, engine=ENGINE)
    assert np.all(np.abs(g.parallax_deg) < 0.275)  # <= asin(R_moon / 363 300 km) = 0.274 deg (D)
    near = np.abs(g.el_deg) < 1.0
    assert near.any()
    assert np.abs(g.parallax_deg[near]).max() > 0.2  # close to the maximum near the horizon
    # flat-horizon direction from the Moon centre differs by the parallax: topocentric < geocentric
    assert np.all(g.parallax_deg[near] > 0)
