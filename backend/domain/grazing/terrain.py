# SPDX-License-Identifier: Apache-2.0
"""Terrain profile along the Earth azimuth and the dominant obstacle (ridge).

Real data only: the profile comes from the LOLA DEM (`dem.py`) or from a user-provided list of
(distance, height). A synthetic profile exists ONLY for tests and carries `synthetic=True`, which the
API exposes (UI text: "profilo sintetico di prova"). No DEM value is ever invented.

Geometry (docs/domain/grazinglink-model.md, sec. 2.2): local frame at the antenna, e = along the
azimuth, u = up. A terrain sample at arc distance s and radius r = R + z (R = 1737.4 km) sits at
    e = r sin(s / R),   u = r cos(s / R) - (R + z_a)
and the Earth line of sight has direction (cos el, sin el). Then, exactly (curvature included):
    h  = u cos(el) - e sin(el)      height of the sample ABOVE the line of sight (h > 0 blocks it)
    d1 = e cos(el) + u sin(el)      distance along the line of sight (antenna -> foot of the sample)
    d2 = Earth range - d1           (the Earth is at ~384 000 km)
    nu = h sqrt(2 (d1 + d2) / (lambda d1 d2))      (diffraction.nu_from_geometry)
The dominant ridge is the sample with maximum nu (single dominant obstacle: a declared limit).
Its radius of curvature comes from a least-squares parabola z ~ z0 - x^2 / (2 Rc) around the peak,
over the samples within `RIDGE_FIT_DEPTH_M` (20 m, as the split-step truncation of the script) of the
top; it is NOT resolvable below about twice the sample spacing (flag `radius_resolved`).
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from backend.domain.grazing.dem import DemOutOfCoverage, DemUnavailable, LolaDem
from backend.domain.grazing.diffraction import nu_from_geometry
from backend.domain.grazing.geometry import great_circle_destination
from backend.domain.grazing.model import MOON_RADIUS_M

__all__ = [
    "MAX_PROFILE_LENGTH_M",
    "MAX_PROFILE_POINTS",
    "SYNTHETIC_LABEL",
    "DemOutOfCoverage",
    "DemUnavailable",
    "DominantRidge",
    "Horizon",
    "TerrainError",
    "TerrainProfile",
    "dominant_ridge",
    "horizon_from_profile",
    "profile_from_dem",
    "profile_from_user",
    "synthetic_ridge_profile",
]

Arr = NDArray[np.float64]
MAX_PROFILE_POINTS = 5000
MAX_PROFILE_LENGTH_M = 100_000.0
MAX_ABS_HEIGHT_M = 20_000.0
RIDGE_FIT_DEPTH_M = 20.0
SYNTHETIC_LABEL = "profilo sintetico di prova"
Source = Literal["lola", "user", "synthetic"]


class TerrainError(ValueError):
    """Invalid terrain input. `key` names the field; the message never contains the input values."""

    def __init__(self, key: str) -> None:
        super().__init__("invalid terrain profile")
        self.key = key


@dataclass(frozen=True)
class TerrainProfile:
    """Heights (m over the reference sphere) at arc distances from the antenna (sample 0)."""

    distance_m: Arr
    height_m: Arr
    source: Source
    synthetic: bool
    label: str
    spacing_m: float
    azimuth_deg: float | None = None


@dataclass(frozen=True)
class DominantRidge:
    """The obstacle with the largest Fresnel-Kirchhoff parameter along the profile."""

    index: int
    d1_m: float  # antenna -> foot of the ridge along the line of sight
    d2_m: float  # ridge -> Earth
    ridge_distance_m: float  # arc distance along the ground
    ridge_height_m: float  # terrain height of the tip over the reference sphere
    height_above_los_m: float  # h (> 0: the tip is above the line of sight)
    tip_elevation_deg: (
        float  # apparent elevation of the tip seen from the antenna (curvature incl.)
    )
    los_elevation_deg: float
    angle_above_los_deg: float  # tip elevation - Earth elevation (> 0: blocks)
    nu: float
    radius_of_curvature_m: float  # nan when the parabola is not concave
    radius_resolved: bool
    blocks_los: bool


@dataclass(frozen=True)
class Horizon:
    """Highest sampled terrain angle within the profile, not a complete planetary horizon."""

    elevation_deg: float
    distance_m: float
    profile_length_m: float


def _validate_arrays(d: Arr, z: Arr) -> None:
    if d.ndim != 1 or z.ndim != 1 or d.size != z.size:
        raise TerrainError("shape")
    if d.size < 2:
        raise TerrainError("too_few_points")
    if d.size > MAX_PROFILE_POINTS:
        raise TerrainError("too_many_points")
    if not (np.all(np.isfinite(d)) and np.all(np.isfinite(z))):
        raise TerrainError("not_finite")
    if d[0] != 0.0:
        raise TerrainError("first_distance_must_be_zero")
    if np.any(np.diff(d) <= 0.0):
        raise TerrainError("distance_not_increasing")
    if d[-1] > MAX_PROFILE_LENGTH_M:
        raise TerrainError("profile_too_long")
    if np.any(np.abs(z) > MAX_ABS_HEIGHT_M):
        raise TerrainError("height_out_of_range")


def profile_from_user(distance_m: Sequence[float], height_m: Sequence[float]) -> TerrainProfile:
    """Validated user profile: <= 5000 points, finite, d[0] = 0, strictly increasing, <= 100 km."""
    try:
        d = np.asarray(distance_m, dtype=np.float64)
        z = np.asarray(height_m, dtype=np.float64)
    except (TypeError, ValueError) as e:
        raise TerrainError("not_numeric") from e
    _validate_arrays(d, z)
    return TerrainProfile(
        d, z, "user", False, "profilo fornito dall'utente", float(np.median(np.diff(d)))
    )


def synthetic_ridge_profile(
    ridge_distance_m: float,
    ridge_height_m: float,
    *,
    ridge_radius_m: float = 100.0,
    length_m: float | None = None,
    step_m: float = 5.0,
    antenna_ground_m: float = 0.0,
) -> TerrainProfile:
    """FOR TESTS ONLY (`synthetic=True`): flat ground at `antenna_ground_m` with a parabolic ridge."""
    if length_m is None:
        length_m = 2.0 * ridge_distance_m
    d = np.arange(0.0, length_m + step_m / 2.0, step_m)
    z = np.full_like(d, antenna_ground_m)
    x = d - ridge_distance_m
    z = z + np.maximum(ridge_height_m - x * x / (2.0 * ridge_radius_m), 0.0)
    return TerrainProfile(d, z, "synthetic", True, SYNTHETIC_LABEL, step_m)


def profile_from_dem(
    dem: LolaDem,
    lat_deg: float,
    lon_deg_east: float,
    azimuth_deg: float,
    length_m: float = 10_000.0,
    step_m: float | None = None,
) -> TerrainProfile:
    """Profile along the great circle leaving the site at `azimuth_deg` (0 = North, clockwise).

    Raises `DemUnavailable` (no data) or `DemOutOfCoverage` (the path leaves the 85S-90S product).
    """
    step = step_m if step_m is not None else dem.spec.scale_m
    if not (math.isfinite(azimuth_deg) and 0 < length_m <= MAX_PROFILE_LENGTH_M and step > 0):
        raise TerrainError("profile_request")
    n = int(length_m / step) + 1
    if n > MAX_PROFILE_POINTS:
        raise TerrainError("too_many_points")
    s = np.arange(n, dtype=np.float64) * step
    R = dem.spec.radius_km * 1000.0
    ang = s / R
    lat2, lon2 = great_circle_destination(
        lat_deg, lon_deg_east, np.asarray(math.radians(azimuth_deg)), ang
    )
    rows = np.empty(n)
    cols = np.empty(n)
    for i in range(n):
        rows[i], cols[i] = dem.pixel(float(lat2[i]), float(lon2[i]))
    z = dem.heights_m_at_pixels(rows, cols)
    return TerrainProfile(s, z, "lola", False, dem.spec.id, step, azimuth_deg)


def horizon_from_profile(
    profile: TerrainProfile,
    observer_height_m: float = 0.0,
    moon_radius_m: float = MOON_RADIUS_M,
) -> Horizon:
    """Highest terrain elevation in this one sampled direction, including spherical curvature.

    Terrain beyond the profile and between its samples is unknown; a clear profile does not
    establish that a body is visible over the complete horizon.
    """
    d, z = profile.distance_m, profile.height_m
    _validate_arrays(d, z)
    if not (
        math.isfinite(observer_height_m)
        and observer_height_m >= 0
        and math.isfinite(moon_radius_m)
        and moon_radius_m > MAX_ABS_HEIGHT_M
        and d[-1] / moon_radius_m < math.pi / 2
    ):
        raise TerrainError("horizon_parameters")
    phi = d[1:] / moon_radius_m
    radius = moon_radius_m + z[1:]
    horizontal = radius * np.sin(phi)
    vertical = radius * np.cos(phi) - (moon_radius_m + z[0] + observer_height_m)
    angles = np.arctan2(vertical, horizontal)
    i = int(np.argmax(angles))
    return Horizon(math.degrees(float(angles[i])), float(d[i + 1]), float(d[-1]))


def _ridge_radius(d: Arr, z: Arr, k: int, spacing: float) -> tuple[float, bool]:
    """Radius of curvature of the crest near sample `k` (least-squares parabola)."""
    top = k
    lo = hi = top
    while lo > 0 and z[top] - z[lo - 1] <= RIDGE_FIT_DEPTH_M:
        lo -= 1
    while hi < z.size - 1 and z[top] - z[hi + 1] <= RIDGE_FIT_DEPTH_M:
        hi += 1
    if hi - lo + 1 < 5:
        return math.nan, False
    x = d[lo : hi + 1] - d[top]
    c2, c1, _ = map(float, np.polyfit(x, z[lo : hi + 1] - z[top], 2))
    if c2 >= 0.0:
        return math.nan, False
    apex = -c1 / (2.0 * c2)
    if not x[0] < apex < x[-1]:
        return math.nan, False
    rc = -1.0 / (2.0 * c2)
    return rc, rc >= 2.0 * spacing


def dominant_ridge(
    profile: TerrainProfile,
    earth_elevation_deg: float,
    wavelength_m: float,
    earth_range_m: float = 384_400_000.0,
    antenna_height_m: float = 2.0,
    moon_radius_m: float = MOON_RADIUS_M,
) -> DominantRidge:
    """Dominant obstacle along the profile for an Earth at `earth_elevation_deg` (topocentric)."""
    if not (math.isfinite(earth_elevation_deg) and -90.0 < earth_elevation_deg < 90.0):
        raise TerrainError("elevation")
    if wavelength_m <= 0 or earth_range_m <= 0 or antenna_height_m < 0:
        raise TerrainError("parameters")
    d, z = profile.distance_m, profile.height_m
    za = float(z[0]) + antenna_height_m
    ra = moon_radius_m + za
    r = moon_radius_m + z
    phi = d / moon_radius_m
    e = r * np.sin(phi)
    u = r * np.cos(phi) - ra
    el = math.radians(earth_elevation_deg)
    h = u * math.cos(el) - e * math.sin(el)
    d1 = e * math.cos(el) + u * math.sin(el)
    d2 = earth_range_m - d1
    cand = np.flatnonzero(d1 > 0.0)
    if cand.size == 0:
        raise TerrainError("no_samples_ahead")
    nu = np.full(d.shape, -np.inf)
    nu[cand] = nu_from_geometry(h[cand], d1[cand], d2[cand], wavelength_m)
    k = int(np.argmax(nu))
    tip_el = math.degrees(math.atan2(float(u[k]), float(e[k])))
    rc, resolved = _ridge_radius(d, z, k, profile.spacing_m)
    return DominantRidge(
        index=k,
        d1_m=float(d1[k]),
        d2_m=float(d2[k]),
        ridge_distance_m=float(d[k]),
        ridge_height_m=float(z[k]),
        height_above_los_m=float(h[k]),
        tip_elevation_deg=tip_el,
        los_elevation_deg=earth_elevation_deg,
        angle_above_los_deg=tip_el - earth_elevation_deg,
        nu=float(nu[k]),
        radius_of_curvature_m=rc,
        radius_resolved=resolved,
        blocks_los=bool(h[k] > 0.0),
    )
