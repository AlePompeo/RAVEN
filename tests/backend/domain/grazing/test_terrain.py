# SPDX-License-Identifier: Apache-2.0
import math

import numpy as np
import pytest

from backend.domain.grazing.dem import LolaDem
from backend.domain.grazing.diffraction import knife_edge_loss_db
from backend.domain.grazing.terrain import (
    MAX_PROFILE_POINTS,
    SYNTHETIC_LABEL,
    TerrainError,
    dominant_ridge,
    horizon_from_profile,
    profile_from_dem,
    profile_from_user,
    synthetic_ridge_profile,
)
from backend.domain.lunar.link import SPEED_OF_LIGHT_M_S

LAM = SPEED_OF_LIGHT_M_S / 8.4e9
R_MOON = 1_737_400.0


@pytest.mark.parametrize("azimuth", [45.0, 135.0, 225.0, 315.0])
def test_dem_profile_at_south_pole_follows_requested_bearing(
    azimuth: float, monkeypatch: pytest.MonkeyPatch
) -> None:
    dem = LolaDem(allow_download=False)
    positions: list[tuple[float, float]] = []

    def pixel(lat: float, lon: float) -> tuple[float, float]:
        positions.append((lat, lon))
        return 0.0, 0.0

    monkeypatch.setattr(dem, "pixel", pixel)
    monkeypatch.setattr(dem, "heights_m_at_pixels", lambda rows, cols: np.zeros_like(rows))
    profile_from_dem(dem, -90.0, 30.0, azimuth, length_m=200.0, step_m=100.0)
    expected_lon = (30.0 + azimuth + 180.0) % 360.0 - 180.0
    for i, (lat, lon) in enumerate(positions[1:], 1):
        assert lat == pytest.approx(-90.0 + math.degrees(i * 100.0 / R_MOON), abs=1e-10)
        assert lon == pytest.approx(expected_lon, abs=1e-8)


@pytest.mark.parametrize("elevation_deg", [-1.0, 0.0, 2.0])
def test_obstacle_geometry_against_cartesian_projection(elevation_deg: float) -> None:
    p = synthetic_ridge_profile(2000.0, 45.0, ridge_radius_m=400.0)
    up, east = np.array([0.0, 0.0, 1.0]), np.array([0.6, 0.8, 0.0])
    theta = p.distance_m / R_MOON
    points = (R_MOON + p.height_m)[:, None] * (
        np.cos(theta)[:, None] * up + np.sin(theta)[:, None] * east
    )
    offsets = points - (R_MOON + p.height_m[0] + 2.0) * up
    a = math.radians(elevation_deg)
    along = offsets @ (math.cos(a) * east + math.sin(a) * up)
    height = offsets @ (math.cos(a) * up - math.sin(a) * east)
    candidates = np.flatnonzero(along > 0.0)
    other = 384_400_000.0 - along[candidates]
    nu = height[candidates] * np.sqrt(2.0 * 384_400_000.0 / (LAM * along[candidates] * other))
    k = int(candidates[np.argmax(nu)])
    actual = dominant_ridge(p, elevation_deg, LAM)
    assert actual.index == k
    assert actual.d1_m == pytest.approx(along[k], abs=1e-8)
    assert actual.d2_m == pytest.approx(384_400_000.0 - along[k], abs=1e-8)
    assert actual.height_above_los_m == pytest.approx(height[k], abs=1e-8)
    assert actual.nu == pytest.approx(np.max(nu), rel=1e-9)


def test_synthetic_profile_is_flagged() -> None:
    p = synthetic_ridge_profile(2000.0, 30.0)
    assert p.synthetic is True and p.source == "synthetic" and p.label == SYNTHETIC_LABEL
    assert profile_from_user([0, 10, 20], [0, 1, 0]).synthetic is False


def test_ridge_known_answer() -> None:
    p = synthetic_ridge_profile(2000.0, 33.4, ridge_radius_m=100.0)
    r = dominant_ridge(p, 0.0, LAM, antenna_height_m=2.0)
    assert r.ridge_distance_m == pytest.approx(2000.0, abs=5.0)
    assert r.d1_m == pytest.approx(2000.0, abs=10.0)
    assert r.d2_m == pytest.approx(384_400_000.0, rel=1e-4)
    assert r.ridge_height_m == pytest.approx(33.4, abs=0.1)
    # flat-horizon expectation: (33.4 - 2) / 2000 rad, minus the lunar curvature drop s / (2 R)
    expected = math.degrees((33.4 - 2.0) / 2000.0 - 2000.0 / (2 * R_MOON))
    assert r.tip_elevation_deg == pytest.approx(expected, abs=0.01)
    assert r.angle_above_los_deg == pytest.approx(expected, abs=0.01)
    assert r.height_above_los_m == pytest.approx(math.radians(expected) * 2000.0, rel=0.02)
    assert r.blocks_los and r.nu > 0
    assert r.radius_of_curvature_m == pytest.approx(100.0, rel=0.05)
    assert r.radius_resolved


@pytest.mark.parametrize("height", [-15000.0, -1000.0, 1000.0, 15000.0])
def test_constant_relief_does_not_fabricate_a_resolved_ridge_radius(height: float) -> None:
    d = np.arange(0.0, 4001.0, 20.0)
    p = profile_from_user(d.tolist(), np.full(d.size, height).tolist())
    ridge = dominant_ridge(p, 0.0, LAM)
    assert math.isnan(ridge.radius_of_curvature_m)
    assert not ridge.radius_resolved


@pytest.mark.parametrize("offset", [-15000.0, 0.0, 15000.0])
def test_parabolic_radius_is_invariant_to_vertical_datum(offset: float) -> None:
    p = synthetic_ridge_profile(2000.0, 45.0, ridge_radius_m=400.0, step_m=20.0)
    translated = profile_from_user(p.distance_m.tolist(), (p.height_m + offset).tolist())
    ridge = dominant_ridge(translated, 0.0, LAM)
    assert ridge.radius_of_curvature_m == pytest.approx(400.0, rel=1e-9)
    assert ridge.radius_resolved


@pytest.mark.parametrize("slope", [-0.1, 0.1, 0.5])
def test_linear_relief_without_a_crest_has_no_resolved_crest_radius(slope: float) -> None:
    d = np.arange(0.0, 4001.0, 20.0)
    p = profile_from_user(d.tolist(), (slope * d - 1000.0).tolist())
    ridge = dominant_ridge(p, 0.0, LAM)
    assert math.isnan(ridge.radius_of_curvature_m)
    assert not ridge.radius_resolved


def test_nu_sign_and_loss_follow_earth_elevation() -> None:
    p = synthetic_ridge_profile(2000.0, 33.4, ridge_radius_m=100.0)
    below = dominant_ridge(p, 0.0, LAM)  # ridge above the line of sight
    above = dominant_ridge(p, 2.0, LAM)  # Earth well above the ridge
    assert below.nu > 0 > above.nu
    assert not above.blocks_los
    assert float(knife_edge_loss_db(below.nu)) > 10.0 > float(knife_edge_loss_db(above.nu))
    # model doc T3: Earth 0.5 deg below the tip (flat horizon): nu = 2.922, J = 22.29 dB
    el = math.degrees((33.4 - 2.0) / 2000.0 - 2000.0 / (2 * R_MOON)) - 0.5
    r = dominant_ridge(p, el, LAM)
    assert r.nu == pytest.approx(2.922, abs=0.03)
    assert float(knife_edge_loss_db(r.nu)) == pytest.approx(22.29, abs=0.15)


def test_unresolved_radius_is_flagged() -> None:
    p = synthetic_ridge_profile(2000.0, 33.4, ridge_radius_m=2.0, step_m=20.0)
    r = dominant_ridge(p, 0.0, LAM)
    assert not r.radius_resolved


def test_dominant_picks_the_larger_nu() -> None:
    d = np.arange(0.0, 6000.0, 10.0)
    z = np.zeros_like(d)
    z[(d > 900) & (d < 1100)] = 10.0  # near, small
    z[(d > 4900) & (d < 5100)] = 20.0  # far: nu ~ h / sqrt(d1) = 0.28 < 0.32 of the near one
    r = dominant_ridge(profile_from_user(d.tolist(), z.tolist()), 0.0, LAM, antenna_height_m=0.0)
    assert r.ridge_distance_m == pytest.approx(1000.0, abs=100.0)


def test_curvature_hides_far_flat_ground_not_near() -> None:
    d = np.arange(0.0, 20_000.0, 50.0)
    p = profile_from_user(d.tolist(), np.zeros_like(d).tolist())
    r = dominant_ridge(p, 0.0, LAM, antenna_height_m=2.0)
    assert not r.blocks_los or r.height_above_los_m < 2.0


def test_horizon_from_profile_includes_curvature_and_observer_height() -> None:
    flat = profile_from_user([0.0, 1000.0, 2000.0], [0.0, 0.0, 0.0])
    horizon = horizon_from_profile(flat)
    assert horizon.distance_m == 1000.0
    assert horizon.profile_length_m == 2000.0
    assert horizon.elevation_deg == pytest.approx(math.degrees(-1000 / (2 * R_MOON)), abs=1e-8)

    ridge = profile_from_user([0.0, 1000.0, 2000.0], [0.0, 0.0, 100.0])
    ground = horizon_from_profile(ridge)
    raised = horizon_from_profile(ridge, observer_height_m=2)
    angle = math.atan2(
        (R_MOON + 100) * math.cos(2000 / R_MOON) - R_MOON,
        (R_MOON + 100) * math.sin(2000 / R_MOON),
    )
    assert ground.distance_m == 2000.0
    assert ground.elevation_deg == pytest.approx(math.degrees(angle))
    assert raised.elevation_deg < ground.elevation_deg


@pytest.mark.parametrize("azimuth_deg", [0.0, 90.0, 225.0])
def test_horizon_matches_cartesian_line_of_sight(azimuth_deg: float) -> None:
    distances = np.array([0.0, 1000.0, 5000.0, 10000.0])
    heights = np.array([500.0, 520.0, 640.0, 400.0])
    profile = profile_from_user(distances.tolist(), heights.tolist())
    lat, lon, az = np.radians([-86.0, 35.0, azimuth_deg])
    up = np.array([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)])
    east = np.array([-np.sin(lon), np.cos(lon), 0.0])
    north = np.cross(up, east)
    tangent = north * np.cos(az) + east * np.sin(az)
    angles = []
    for distance, height in zip(distances[1:], heights[1:], strict=True):
        direction = up * np.cos(distance / R_MOON) + tangent * np.sin(distance / R_MOON)
        line = (R_MOON + height) * direction - (R_MOON + heights[0] + 2.0) * up
        angles.append(math.degrees(math.asin(float(np.dot(line, up) / np.linalg.norm(line)))))
    actual = horizon_from_profile(profile, observer_height_m=2.0)
    assert actual.elevation_deg == pytest.approx(max(angles), abs=1e-10)
    assert actual.distance_m == distances[1:][int(np.argmax(angles))]


@pytest.mark.parametrize("height,radius", [(-1.0, R_MOON), (float("nan"), R_MOON), (0.0, 1.0)])
def test_horizon_rejects_invalid_observer_or_radius(height: float, radius: float) -> None:
    p = profile_from_user([0.0, 1000.0], [0.0, 0.0])
    with pytest.raises(TerrainError):
        horizon_from_profile(p, observer_height_m=height, moon_radius_m=radius)


def test_user_profile_validation() -> None:
    ok_d, ok_z = [0.0, 10.0, 20.0], [0.0, 1.0, 2.0]
    for d, z, key in [
        ([0.0, 10.0], [0.0], "shape"),
        ([0.0], [0.0], "too_few_points"),
        ([0.0, float("nan"), 2.0], ok_z, "not_finite"),
        (ok_d, [0.0, float("inf"), 0.0], "not_finite"),
        ([0.0, 10.0, 10.0], ok_z, "distance_not_increasing"),
        ([0.0, 20.0, 10.0], ok_z, "distance_not_increasing"),
        ([5.0, 10.0, 20.0], ok_z, "first_distance_must_be_zero"),
        ([0.0, 10.0, 200_000.0], ok_z, "profile_too_long"),
        (ok_d, [0.0, 99_999.0, 0.0], "height_out_of_range"),
        (list(range(MAX_PROFILE_POINTS + 1)), [0.0] * (MAX_PROFILE_POINTS + 1), "too_many_points"),
        (["a", "b"], [0.0, 1.0], "not_numeric"),
    ]:
        with pytest.raises(TerrainError) as e:
            profile_from_user(d, z)  # type: ignore[arg-type]
        assert e.value.key == key
        assert "nan" not in str(e.value) and "99999" not in str(e.value)  # no echo of the input
    assert profile_from_user(list(range(MAX_PROFILE_POINTS)), [0.0] * MAX_PROFILE_POINTS)


def test_dominant_ridge_rejects_bad_arguments() -> None:
    p = profile_from_user([0.0, 10.0, 20.0], [0.0, 0.0, 0.0])
    with pytest.raises(TerrainError):
        dominant_ridge(p, 95.0, LAM)
    with pytest.raises(TerrainError):
        dominant_ridge(p, float("nan"), LAM)
    with pytest.raises(TerrainError):
        dominant_ridge(p, 0.0, 0.0)
