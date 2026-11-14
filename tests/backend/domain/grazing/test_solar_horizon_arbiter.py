# SPDX-License-Identifier: Apache-2.0
"""Synthetic terrain with analytic answers for the independent Sun-horizon arbiter."""

import math

import numpy as np
import pytest

from scripts import solar_horizon_arbiter as arb

R = arb.MOON_R_M
LAT0, LON0 = -89.0, 30.0


def _flat(lat: np.ndarray, _lon: np.ndarray) -> np.ndarray:
    return np.zeros_like(np.asarray(lat, dtype=np.float64))


def _ground_distance(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    u0 = arb.unit_vector(LAT0, LON0)
    p = arb.unit_vector(lat, lon)
    return R * np.arccos(np.clip(p @ u0, -1.0, 1.0))


def test_flat_sphere_curvature_exact() -> None:
    d = np.arange(10.0, 5000.0, 10.0)
    az = np.arange(0.0, 360.0, 30.0)
    m = arb.horizon_mask([(_flat, d)], LAT0, LON0, 0.0, az)
    # chord to a point at ground distance d on the same sphere dips by d / (2 R)
    assert np.allclose(m["elevation_deg"], -math.degrees(10.0 / (2 * R)), atol=1e-9)
    # observer 100 m up: geometric dip acos(R / (R + h)), tangent point at sqrt(2 R h)
    d = np.arange(10.0, 40_000.0, 10.0)
    m = arb.horizon_mask([(_flat, d)], LAT0, LON0, 100.0, az)
    dip = math.degrees(math.acos(R / (R + 100.0)))
    assert np.allclose(m["elevation_deg"], -dip, atol=1e-6)
    assert np.allclose(m["distance_m"], math.sqrt(2 * R * 100.0), atol=20.0)


def test_bowl_rim_constant_mask() -> None:
    rim_d, rim_h = 3000.0, 400.0

    def bowl(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
        return np.where(_ground_distance(lat, lon) >= rim_d - 1e-6, rim_h, -200.0)

    d = np.arange(10.0, 6000.0, 10.0)
    m = arb.horizon_mask([(bowl, d)], LAT0, LON0, 0.0, np.arange(0.0, 360.0, 5.0))
    phi = rim_d / R
    z0 = -200.0
    want = math.degrees(
        math.atan2((R + rim_h) * math.cos(phi) - (R + z0), (R + rim_h) * math.sin(phi))
    )
    assert np.allclose(m["elevation_deg"], want, atol=1e-7)
    assert np.allclose(m["distance_m"], rim_d)


def test_knife_edge_ridge_analytic_by_azimuth() -> None:
    """Straight (great-circle) ridge at perpendicular distance D, normal towards azimuth 90."""
    big_d, height, width = 2000.0, 300.0, 15.0
    _up, n, _north = arb.local_basis(LAT0, LON0)  # signed distance along East: asin(p . n) R

    def ridge(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
        s = np.arcsin(np.clip(arb.unit_vector(lat, lon) @ n, -1, 1)) * R  # signed distance
        return np.where((s >= big_d) & (s <= big_d + width), height, 0.0)

    d = np.arange(0.1, 8000.0, 0.1)
    az = np.array([90.0, 60.0, 120.0, 45.0, 270.0])
    m = arb.horizon_mask([(ridge, d)], LAT0, LON0, 0.0, az)
    for a, got in zip(az[:4], m["elevation_deg"][:4], strict=True):
        alpha = math.radians(a - 90.0)
        s = R * math.asin(math.sin(big_d / R) / math.cos(alpha))  # spherical right triangle
        phi = s / R
        want = math.degrees(
            math.atan2((R + height) * math.cos(phi) - R, (R + height) * math.sin(phi))
        )
        # sampling at 0.1 m: error below H / s^2 * 0.1 m, i.e. < 1e-3 deg here
        assert got == pytest.approx(want, abs=1e-3)
    # no ridge behind the observer; 0.1 m chords lose digits against R, hence 1e-7 deg
    assert m["elevation_deg"][4] == pytest.approx(-math.degrees(0.1 / (2 * R)), abs=1e-7)


def test_disc_fraction_matches_circular_segment() -> None:
    mask_az = np.arange(3600) * 0.1
    r = 0.27
    for h in (-0.4, -0.2, 0.0, 0.1, 0.25, 0.4):
        mask_el = np.full(3600, h)
        el = np.array([0.0])
        got = arb.disc_fraction(el, np.array([10.0]), r, mask_az, mask_el, cols=4000)[0]
        want = arb.segment_fraction(el, r, np.array([h]))[0]
        assert got == pytest.approx(want, abs=2e-5)
    # analytic half disc and empty/full limits
    assert arb.segment_fraction(np.array([0.0]), r, np.array([0.0]))[0] == pytest.approx(0.5)
    assert arb.segment_fraction(np.array([1.0]), r, np.array([0.0]))[0] == 1.0
    assert arb.segment_fraction(np.array([-1.0]), r, np.array([0.0]))[0] == 0.0


def test_disc_fraction_vertical_step_mask() -> None:
    """Mask +5 deg up to azimuth 99.99, -5 deg from 100 (linear in between): disc at 99.995."""
    mask_az = np.arange(36000) * 0.01
    mask_el = np.where(mask_az < 99.995, 5.0, -5.0)
    f = arb.disc_fraction(np.array([0.0]), np.array([99.995]), 0.27, mask_az, mask_el, cols=2000)
    assert f[0] == pytest.approx(0.5, abs=2e-3)


def test_time_fractions_of_sinusoidal_sun() -> None:
    """Sun elevation A sin(wt) against a constant mask H: P(el >= H) = 1/2 - asin(H/A)/pi."""
    amp, h, r = 1.5, 0.3, 0.27
    t = (np.arange(200_000) + 0.5) / 200_000 * 2 * math.pi
    el = amp * np.sin(t)
    az = np.degrees(t) % 360.0
    mask_az = np.arange(720) * 0.5
    c = arb.sun_criteria(el, az, r, mask_az, np.full(720, h))

    def p(x: float) -> float:
        return 0.5 - math.asin(x / amp) / math.pi

    assert np.mean(c["centre"]) == pytest.approx(p(h), abs=1e-4)
    assert np.mean(c["upper"]) == pytest.approx(p(h - r), abs=1e-4)
    assert np.mean(c["lower"]) == pytest.approx(p(h + r), abs=1e-4)
    assert np.mean(c["any_part"]) == pytest.approx(p(h - r), abs=1e-4)
    assert np.mean(c["full_disc"]) == pytest.approx(p(h + r), abs=1e-4)


def test_unknown_terrain_is_reported_not_free() -> None:
    def holey(lat: np.ndarray, _lon: np.ndarray) -> np.ndarray:
        z = np.zeros_like(np.asarray(lat, dtype=np.float64))
        z[1::2] = np.nan
        return z

    m = arb.horizon_mask(
        [(holey, np.arange(10.0, 1000.0, 10.0))],
        LAT0,
        LON0,
        0.0,
        np.array([0.0]),
        site_sampler=_flat,
    )
    assert float(m["unknown_fraction"]) > 0.4


def test_window_sampler_bilinear_and_unknown_outside() -> None:
    h = np.arange(16.0).reshape(4, 4)
    w = arb.Window(h, row0=100, col0=200, scale_m=20.0, center_px=150.0, radius_m=R)
    # invert the projection for pixel (row 101.5, col 201.25) of the global grid
    x, y = (201.25 - 150.0) * 20.0, (150.0 - 101.5) * 20.0
    rho, lon = math.hypot(x, y), math.degrees(math.atan2(x, y))
    lat = -90.0 + 2 * math.degrees(math.atan(rho / (2 * R)))
    got = w.sample(np.array([lat]), np.array([lon]))[0]
    assert got == pytest.approx(1.5 * 4 + 1.25, abs=1e-6)
    assert np.isnan(w.sample(np.array([-80.0]), np.array([0.0]))[0])
