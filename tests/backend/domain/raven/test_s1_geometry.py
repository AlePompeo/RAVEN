# SPDX-License-Identifier: Apache-2.0
"""S1 geometry (RAVEN M4): analytic cases with a stub engine, and equality with the legacy code."""

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import numpy as np
import pytest

from backend.domain.grazing.geometry import earth_geometry
from backend.domain.lunar.model import load_sites
from backend.domain.lunar.visibility import DSN_STATIONS, site_visibility
from backend.domain.raven import params as reg
from backend.domain.raven import s0_context as s0
from backend.domain.raven import s1_geometry as s1
from backend.ephemeris import kernels

T0 = datetime(2027, 4, 7, tzinfo=UTC)


@dataclass
class Azel:
    az_deg: Any
    el_deg: Any
    range_km: Any


@dataclass
class LatLon:
    lat_deg: Any
    lon_deg_east: Any


class StubEngine:
    """Deterministic engine: Sun at 1 AU, Earth at 384 400 km, fixed directions."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def topocentric_azel(
        self, site_body: str, lat: float, lon: float, target: str, t: Any, h_m: float = 0.0
    ) -> Azel:
        self.calls.append((site_body, target))
        n = len(t)
        base = {"sun": (90.0, 10.0), "earth": (180.0, 3.0), "moon": (0.0, 20.0)}[target]
        k = np.arange(n, dtype=float)
        return Azel(base[0] + 0.0 * k, base[1] + k, np.full(n, 384_400.0))

    def sun_distance_au(self, body: str, t: Any) -> Any:
        return np.full(len(t), 1.0)

    def sub_earth_point(self, body: str, t: Any) -> LatLon:
        n = len(t)
        return LatLon(np.zeros(n), np.zeros(n))


@pytest.fixture
def grid() -> s0.TimeGrid:
    return s0.build_grid(s0.TimeWindow(T0, 0.1, 60.0))


@pytest.fixture
def site() -> s0.SiteRecord:
    return s0.custom_site("stub", 0.0, 0.0)


def test_stub_analytic_values(site: s0.SiteRecord, grid: s0.TimeGrid) -> None:
    g = s1.geometry(StubEngine(), site, grid)
    n = grid.n_steps
    assert n == 2 and g.sun_az_deg.shape == (n,) and g.dsn_moon_el_deg.shape == (3, n)
    # Sun at exactly 1 AU: asin(695700 / 149597870.7) = 0.26645 deg
    expected_sun = math.degrees(math.asin(695_700.0 / 149_597_870.7))
    assert g.sun_semidiameter_deg[0] == pytest.approx(expected_sun, abs=1e-12)
    assert g.sun_range_km[0] == pytest.approx(149_597_870.7)
    # Earth at 384 400 km: atan(6371 / 384400) = 0.9496 deg (half of 1.8991)
    assert g.earth_semidiameter_deg[0] == pytest.approx(
        math.degrees(math.atan(6371.0 / 384_400.0)), abs=1e-12
    )
    assert 2 * g.earth_semidiameter_deg[0] == pytest.approx(1.8991, abs=1e-4)
    assert g.earth_az_deg[0] == 180.0 and g.earth_el_deg[1] - g.earth_el_deg[0] == 1.0
    assert g.dsn_complexes == tuple(s.complex for s in DSN_STATIONS)
    assert g.earth_range_km[0] == 384_400.0  # true distance from the engine, not a constant


def test_one_vectorised_call_per_body_and_deterministic(
    site: s0.SiteRecord, grid: s0.TimeGrid
) -> None:
    e = StubEngine()
    a = s1.geometry(e, site, grid)
    sun_calls = [c for c in e.calls if c[1] == "sun"]
    assert len(sun_calls) == 1
    b = s1.geometry(StubEngine(), site, grid)
    for f in a.__dataclass_fields__:
        va, vb = getattr(a, f), getattr(b, f)
        assert np.array_equal(va, vb) if isinstance(va, np.ndarray) else va == vb


def test_dsn_threshold_is_not_in_the_geometry(site: s0.SiteRecord, grid: s0.TimeGrid) -> None:
    """S1 gives elevations only; the 6 deg threshold lives in the registry (used by S6)."""
    g = s1.geometry(StubEngine(), site, grid)
    assert np.all(g.dsn_moon_el_deg[:, 0] == 20.0)
    assert reg.value("lunar.ground_station_min_elevation_deg") == 6.0


def test_ephemeris_failure_is_not_swallowed(site: s0.SiteRecord, grid: s0.TimeGrid) -> None:
    class Broken(StubEngine):
        def sun_distance_au(self, body: str, t: Any) -> Any:
            raise kernels.EphemerisUnavailable("no kernels")

    with pytest.raises(kernels.EphemerisUnavailable):
        s1.geometry(Broken(), site, grid)


def _have_kernels() -> bool:
    try:
        kernels.require_kernels()
    except kernels.EphemerisUnavailable:
        return False
    return True


@pytest.mark.skipif(not _have_kernels(), reason="kernels missing (make ephemeris)")
def test_real_engine_equals_legacy_code_and_is_bounded() -> None:
    from backend.ephemeris.engine import get_engine

    eng = get_engine()
    grid = s0.build_grid(s0.TimeWindow(T0, 3.0, 60.0))
    for sid in ("shackleton", "apollo11"):
        rec = s0.resolve_site(sid)
        g = s1.geometry(eng, rec, grid)
        legacy = site_visibility(
            eng,
            next(s for s in load_sites() if s.id == sid),
            list(grid.instants),
            sun_mask_deg=0.0,
            earth_mask_deg=0.0,
        )
        np.testing.assert_array_equal(g.sun_el_deg, legacy.sun_el_deg)
        np.testing.assert_array_equal(g.earth_az_deg, legacy.earth_az_deg)
        np.testing.assert_array_equal(g.earth_range_km, legacy.earth_range_km)
        eg = earth_geometry(rec.lat_deg, rec.lon_deg_east, list(grid.instants), engine=eng)
        np.testing.assert_array_equal(g.parallax_deg, eg.parallax_deg)
        # bounds
        assert np.all((g.sun_az_deg >= 0) & (g.sun_az_deg < 360))
        assert np.all((g.sun_semidiameter_deg > 0.26) & (g.sun_semidiameter_deg < 0.28))
        assert np.all((g.earth_semidiameter_deg > 0.85) & (g.earth_semidiameter_deg < 1.05))
        assert np.all((g.earth_range_km > 356_000) & (g.earth_range_km < 407_000))
        assert np.all(np.abs(g.parallax_deg) < 1.0)
        assert np.all(np.isfinite(g.dsn_moon_el_deg))


def test_snapshot_dsn_threshold_comes_from_the_registry() -> None:
    from pathlib import Path

    from backend.domain.grazing import snapshot

    key = "lunar.ground_station_min_elevation_deg"
    assert snapshot.DSN_MIN_ELEVATION_DEG == reg.value(key)
    assert "= 6.0" not in Path(snapshot.__file__).read_text(encoding="utf-8")
