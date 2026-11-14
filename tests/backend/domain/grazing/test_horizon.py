# SPDX-License-Identifier: Apache-2.0
"""Production horizon mask (`horizon.py`): analytic cases, arbiter oracle, unknowns, cache."""

import dataclasses
import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from scipy.integrate import quad

from backend.domain.grazing import horizon as hz
from backend.domain.grazing.dem import FAR_DEM_ID, DemUnavailable, LolaDem, load_lock
from scripts import solar_horizon_arbiter as arb

R = 1_737_400.0
LAT0, LON0 = -89.0, 30.0
CFG = hz.MaskConfig(n_azimuths=360)


def _flat(lat: np.ndarray, _lon: np.ndarray) -> np.ndarray:
    return np.zeros_like(np.asarray(lat, dtype=np.float64))


def _dist(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    u0 = arb.unit_vector(LAT0, LON0)
    return R * np.arccos(np.clip(arb.unit_vector(lat, lon) @ u0, -1.0, 1.0))


def _mask(segments, h: float = 0.0, n: int = 360, z0: float = 0.0) -> hz.HorizonMask:  # type: ignore[no-untyped-def]
    el, d, comp, unk = hz.mask_from_samplers(segments, LAT0, LON0, h, n, site_height_m=z0)
    cfg = hz.MaskConfig(n_azimuths=n)
    return hz.HorizonMask(LAT0, LON0, h, z0, el, d, comp, unk, cfg)


def test_flat_sphere_dip_is_exact() -> None:
    m = _mask([(_flat, np.arange(20.0, 5000.0, 20.0))])
    assert np.allclose(m.elevation_deg, -math.degrees(20.0 / (2 * R)), atol=1e-9)
    m = _mask([(_flat, np.arange(10.0, 40_000.0, 10.0))], h=100.0)
    assert np.allclose(m.elevation_deg, -math.degrees(math.acos(R / (R + 100.0))), atol=1e-6)
    assert np.allclose(m.distance_m, math.sqrt(2 * R * 100.0), atol=20.0)
    assert m.complete.all() and m.unknown_fraction == 0.0


def test_crater_rim_analytic() -> None:
    rim_d, rim_h, z0 = 3000.0, 400.0, -200.0

    def bowl(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
        return np.where(_dist(lat, lon) >= rim_d - 1e-6, rim_h, z0)

    m = _mask([(bowl, np.arange(10.0, 6000.0, 10.0))], z0=z0)
    phi = rim_d / R
    want = math.degrees(
        math.atan2((R + rim_h) * math.cos(phi) - (R + z0), (R + rim_h) * math.sin(phi))
    )
    assert np.allclose(m.elevation_deg, want, atol=1e-7)


def _hills(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """Synthetic relief: two Gaussian hills and a ridge-like ripple, smooth and finite."""
    x = np.asarray(lat, dtype=np.float64)
    y = np.asarray(lon, dtype=np.float64)
    return (
        900.0 * np.exp(-(((x + 88.95) / 0.02) ** 2 + ((y - 32.0) / 1.5) ** 2))
        + 1500.0 * np.exp(-(((x + 89.3) / 0.05) ** 2 + ((y - 200.0) / 8.0) ** 2))
        + 50.0 * np.sin(y / 3.0)
    )


def test_matches_independent_arbiter_on_synthetic_relief() -> None:
    d = np.arange(20.0, 60_000.0, 20.0)
    m = _mask([(_hills, d)], h=2.0, n=720, z0=float(_hills(np.array([LAT0]), np.array([LON0]))[0]))
    a = arb.horizon_mask([(_hills, d)], LAT0, LON0, 2.0, np.arange(720) * 0.5, site_sampler=_hills)
    assert np.max(np.abs(m.elevation_deg - a["elevation_deg"])) < 1e-8
    assert np.array_equal(m.distance_m, a["distance_m"])


@pytest.mark.parametrize("latitude", [-90.0, -89.999999, 89.999999, 90.0])
def test_polar_horizon_preserves_bearings_against_cartesian_oracle(latitude: float) -> None:
    distances = np.arange(100.0, 2001.0, 100.0)

    def relief(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
        return 100.0 * np.sin(np.radians(lon)) + 30.0 * np.cos(3 * np.radians(lon))

    site_height = float(relief(np.array([latitude]), np.array([30.0]))[0])
    actual, _, complete, _ = hz.mask_from_samplers(
        [(relief, distances)], latitude, 30.0, 2.0, 360, site_height_m=site_height
    )
    expected = arb.horizon_mask(
        [(relief, distances)],
        latitude,
        30.0,
        2.0,
        np.arange(360),
        site_sampler=relief,
    )
    assert complete.all()
    np.testing.assert_allclose(actual, expected["elevation_deg"], atol=1e-8, rtol=0)


def test_disc_criteria_against_segment_and_limbs() -> None:
    m = _mask([(_flat, np.arange(20.0, 2000.0, 20.0))])
    flat = np.full(360, 0.1)
    m = dataclasses.replace(m, elevation_deg=flat)
    el = np.array([-0.4, -0.2, 0.0, 0.1, 0.3, 0.5])
    c = hz.disc_criteria(m, np.full(el.size, 77.0), el, 0.27)
    want = arb.segment_fraction(el, 0.27, np.full(el.size, 0.1))
    assert np.allclose(c["disc_fraction"], want, atol=2e-3)
    assert c["upper"] == [False, False, True, True, True, True]
    assert c["centre"] == [False, False, False, True, True, True]
    assert c["lower"] == [False, False, False, False, False, True]
    assert all(h == pytest.approx(0.1) for h in c["horizon_deg"])
    # invalid geometry stays unknown
    nan = hz.disc_criteria(m, np.array([np.nan]), np.array([1.0]), 0.27)
    assert nan["upper"] == [None] and nan["disc_fraction"] == [None]


@pytest.mark.parametrize("slope", [-2.0, -1.0, 0.5, 1.0, 2.0])
@pytest.mark.parametrize("clearance", [-1e-5, 0.0, 1e-5])
@pytest.mark.parametrize("centre", [0.0, 180.0, 359.95])
def test_tilted_horizon_disc_matches_rotated_circular_segment(
    slope: float, clearance: float, centre: float
) -> None:
    cfg = hz.MaskConfig()
    azimuths = np.arange(cfg.n_azimuths) * 360.0 / cfg.n_azimuths
    offset = (azimuths - centre + 180.0) % 360.0 - 180.0
    intercept = math.sqrt(1 + slope**2) + clearance
    elevations = np.clip(0.27 * intercept + slope * offset, -5.0, 5.0)
    mask = hz.HorizonMask(
        LAT0,
        LON0,
        0.0,
        0.0,
        elevations,
        np.full(cfg.n_azimuths, 2000.0),
        np.ones(cfg.n_azimuths, dtype=bool),
        0.0,
        cfg,
    )
    distance = intercept / math.sqrt(1 + slope**2)
    expected = float(arb.segment_fraction(np.array([0.0]), 1.0, np.array([distance]))[0])
    actual = hz.disc_criteria(mask, np.array([centre]), np.array([0.0]), 0.27)["disc_fraction"][0]
    assert actual == pytest.approx(expected, abs=2e-13)
    # At exact tangency the stored/interpolated line can differ by floating-point roundoff.
    if clearance > 0.0:
        assert actual == 0.0


def test_high_sun_disc_does_not_skip_an_incomplete_azimuth_bin() -> None:
    cfg = hz.MaskConfig()
    complete = np.ones(cfg.n_azimuths, dtype=bool)
    complete[round(182.0 * cfg.n_azimuths / 360.0)] = False
    mask = hz.HorizonMask(
        LAT0,
        LON0,
        0.0,
        0.0,
        np.zeros(cfg.n_azimuths),
        np.full(cfg.n_azimuths, 2000.0),
        complete,
        1 / cfg.n_azimuths,
        cfg,
    )
    actual = hz.disc_criteria(mask, np.array([180.0]), np.array([89.0]), 0.27)
    assert actual["complete"] == [False]
    assert actual["disc_fraction"] == [None]


def test_near_zenith_partial_disc_outside_projection_scope_is_unknown() -> None:
    m = _mask([(_flat, np.arange(20.0, 200.0, 20.0))])
    m = dataclasses.replace(m, elevation_deg=np.full(360, 89.98))
    actual = hz.disc_criteria(m, np.array([77.0]), np.array([89.99]), 0.27)
    assert actual["complete"] == [None]
    assert actual["disc_fraction"] == [None]


def test_disc_area_matches_circle_segment_over_full_transition() -> None:
    m = _mask([(_flat, np.arange(20.0, 200.0, 20.0))])
    m = dataclasses.replace(m, elevation_deg=np.zeros(360))
    u = np.linspace(-1.0, 1.0, 1001)
    expected = (np.arccos(-u) + u * np.sqrt(1.0 - u * u)) / math.pi
    got = hz.disc_criteria(m, np.full(u.size, 77.0), u * 0.27, 0.27)
    np.testing.assert_allclose(got["disc_fraction"], expected, atol=2e-15, rtol=0)


def test_thin_crescent_is_not_rounded_to_dark_or_known_hidden() -> None:
    m = _mask([(_flat, np.arange(20.0, 200.0, 20.0))])
    m = dataclasses.replace(m, elevation_deg=np.zeros(360))
    az, el = np.array([77.0]), np.array([-0.27 + 1e-5])
    c = hz.disc_criteria(m, az, el, 0.27)
    assert c["upper"] == [True]
    assert 0.0 < c["disc_fraction"][0] < 1e-6
    incomplete = dataclasses.replace(m, complete=np.zeros(360, dtype=bool))
    unknown = hz.disc_criteria(incomplete, az, el, 0.27)
    assert unknown["disc_fraction"] == [None]
    assert unknown["upper"] == [None]


@pytest.mark.parametrize("radius", [0.0, -0.27, np.nan, np.inf])
def test_invalid_solar_disc_geometry_stays_unknown(radius: float) -> None:
    m = _mask([(_flat, np.arange(20.0, 200.0, 20.0))])
    result = hz.disc_criteria(m, np.array([77.0]), np.array([1.0]), radius)
    assert all(values == [None] for values in result.values())


@pytest.mark.parametrize("el", [-0.2, 0.0, 0.2])
def test_variable_horizon_strip_area_against_independent_quadrature(el: float) -> None:
    m = _mask([(_flat, np.arange(20.0, 200.0, 20.0))])
    heights = 0.3 * np.sin(np.radians(np.arange(360) * 12.0))
    m = dataclasses.replace(m, elevation_deg=heights)
    az, radius = 77.17, 0.27

    def chord(theta: float) -> float:
        u = math.sin(theta)
        c = math.cos(theta)
        offset = u * radius / math.cos(math.radians(el))
        horizon = float(np.interp(az + offset, np.arange(360), heights))
        cut = (horizon - el) / radius
        return min(2.0 * c, max(0.0, c - cut)) * c

    span = radius / math.cos(math.radians(el))
    points = [math.asin((k - az) / span) for k in range(360) if -1 < (k - az) / span < 1]
    total, _ = quad(
        chord, -math.pi / 2, math.pi / 2, points=points, epsabs=1e-10, epsrel=1e-10, limit=200
    )
    actual = hz.disc_criteria(m, np.array([az]), np.array([el]), radius)
    assert actual["disc_fraction"][0] == pytest.approx(total / math.pi, abs=1e-9)


def test_sinusoidal_sun_time_fractions() -> None:
    m = _mask([(_flat, np.arange(20.0, 200.0, 20.0))], n=720)
    m = dataclasses.replace(m, elevation_deg=np.full(720, 0.3))
    t = (np.arange(40_000) + 0.5) / 40_000 * 2 * math.pi
    el = 1.5 * np.sin(t)
    c = hz.disc_criteria(m, np.degrees(t) % 360.0, el, 0.27)

    def p(x: float) -> float:
        return 0.5 - math.asin(x / 1.5) / math.pi

    assert np.mean(c["centre"]) == pytest.approx(p(0.3), abs=2e-4)
    assert np.mean(c["upper"]) == pytest.approx(p(0.3 - 0.27), abs=2e-4)
    assert np.mean(c["lower"]) == pytest.approx(p(0.3 + 0.27), abs=2e-4)


def test_missing_terrain_is_unknown_never_sunlit() -> None:
    def holey(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
        z = np.zeros(np.shape(lat))
        z[::7] = np.nan  # scattered missing samples
        return z

    m = _mask([(holey, np.arange(20.0, 2000.0, 20.0))])
    assert not m.complete.all() and m.unknown_fraction > 0
    comp = np.ones(360, dtype=bool)
    comp[:90] = False  # first quadrant incomplete, the rest complete
    m = dataclasses.replace(m, complete=comp, elevation_deg=np.zeros(360))
    bad, good = 45, 200
    az = np.array([bad + 0.5, bad + 0.5, good + 0.5])
    el = np.array([5.0, -5.0, 5.0])
    c = hz.disc_criteria(m, az, el, 0.27)
    assert c["upper"][0] is None and c["disc_fraction"][0] is None  # could be hidden: unknown
    assert c["upper"][1] is False and c["disc_fraction"][1] == 0.0  # below even the lower bound
    assert c["upper"][2] is True and c["disc_fraction"][2] == pytest.approx(1.0)


class _NoTiles(LolaDem):
    def tile(self, ti: int, tj: int):  # type: ignore[no-untyped-def]
        raise DemUnavailable("not cached")


def test_site_without_dem_raises_unavailable() -> None:
    dem = _NoTiles(Path("/nonexistent"), allow_download=False)
    with pytest.raises(DemUnavailable):
        hz.compute_mask(-89.0, 0.0, 2.0, CFG, near_dem=dem, far_dem=dem)
    with pytest.raises(ValueError):
        hz.compute_mask(-89.0, 0.0, 200.0, CFG, near_dem=dem, far_dem=dem)
    with pytest.raises(ValueError):
        hz.MaskConfig(n_azimuths=100)


def _cached(site_id: str) -> tuple[float, float]:
    from backend.domain.lunar.model import load_sites

    s = {x.id: x for x in load_sites()}[site_id]
    try:
        hz.compute_mask(s.lat_deg, s.lon_deg_east, 2.0, hz.MaskConfig(n_azimuths=360))
    except DemUnavailable:
        pytest.skip("LOLA tiles not cached (run python -m backend.domain.grazing.prefetch)")
    return s.lat_deg, s.lon_deg_east


def test_real_site_matches_arbiter_within_tolerance() -> None:
    """Malapert: production vs arbiter on the same LOLA tiles (cache only, no download).

    Same grid (10 m / 120 m, 1440 azimuths): mask within 1e-6 deg. Arbiter at its own default
    of 3600 azimuths, linearly interpolated to the production azimuths: within 0.02 deg
    everywhere and 1e-3 deg on average (measured 2026-11-04: 0.0035 and 9e-6 deg), a stated
    tolerance that covers only the azimuth interpolation.
    """
    lat, lon = _cached("malapert-massif")
    m = hz.compute_mask(lat, lon, 2.0)
    near = LolaDem(allow_download=False)
    far = LolaDem(spec=load_lock(dataset_id=FAR_DEM_ID), allow_download=False)
    same = arb.site_mask(lat, lon, 2.0, arb.MaskConfig(n_azimuths=1440), near_dem=near, far_dem=far)
    assert np.max(np.abs(m.elevation_deg - same["elevation_deg"])) < 1e-6
    fine = arb.site_mask(lat, lon, 2.0, arb.MaskConfig(), near_dem=near, far_dem=far)
    at = arb.mask_at(fine["azimuth_deg"], fine["elevation_deg"], m.azimuth_deg)
    diff = at - m.elevation_deg
    assert np.max(np.abs(diff)) < 0.02 and abs(float(np.mean(diff))) < 1e-3


def test_store_memory_and_disk_cache(tmp_path: Path) -> None:
    lat, lon = _cached("haworth")
    store = hz.MaskStore(tmp_path, capacity=2)
    cfg = hz.MaskConfig(n_azimuths=360)
    a = store.get(lat, lon, 2.0, cfg)
    assert a.from_cache == "computed" and store.computed == 1
    assert store.get(lat, lon, 2.0, cfg).from_cache == "memory"
    fresh = hz.MaskStore(tmp_path)
    b = fresh.get(lat, lon, 2.0, cfg)
    assert b.from_cache == "disk" and fresh.computed == 0
    assert np.array_equal(a.elevation_deg, b.elevation_deg)
    assert hz.MaskStore.key(lat, lon, 2.0, cfg) != hz.MaskStore.key(lat, lon, 10.0, cfg)
    # a corrupted file is ignored and recomputed
    for p in tmp_path.glob("*.json"):
        p.write_text("{", encoding="utf-8")
    again = hz.MaskStore(tmp_path)
    assert again.get(lat, lon, 2.0, cfg).from_cache == "computed"


def test_disk_cache_evicts_entries_independently_of_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mask = _mask([(_flat, np.arange(20.0, 200.0, 20.0))])
    monkeypatch.setattr(hz, "compute_mask", lambda *a, **kw: mask)
    store = hz.MaskStore(tmp_path, capacity=1, max_disk_entries=2)
    for h in (1, 2, 3, 4):
        store.get(LAT0, LON0, h)
    assert len(list(tmp_path.glob("*.json"))) == 2
    fresh = hz.MaskStore(tmp_path, max_disk_entries=2)
    assert fresh.get(LAT0, LON0, 4).from_cache == "disk"
    assert fresh.get(LAT0, LON0, 1).from_cache == "computed"
    assert len(list(tmp_path.glob("*.json"))) == 2


def test_disk_cache_enforces_bytes_and_custom_terrain_total_on_each_mask_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    from backend.domain.grazing import dem_cache
    from backend.domain.raven.custom_terrain import TerrainStore

    mask = _mask([(_flat, np.arange(20.0, 200.0, 20.0))])
    monkeypatch.setattr(hz, "compute_mask", lambda *a, **kw: mask)
    budget = len(json.dumps(mask.to_json("a" * 64), separators=(",", ":")).encode()) + 128
    catalogue = tmp_path / "catalogue"
    catalogue.mkdir()
    retained = catalogue / "tile.f32"
    retained.write_bytes(b"catalogue")
    custom = tmp_path / "custom"
    custom.mkdir()
    (custom / "old.f32").write_bytes(b"x" * 4000)
    store = TerrainStore(custom, fallback=catalogue, max_bytes=budget)
    for h in (1, 2, 3):
        store.masks.get(LAT0, LON0, h)
        assert dem_cache.usage_bytes(custom) <= budget
    assert len(list((custom / "horizon").glob("*.json"))) == 1
    assert retained.read_bytes() == b"catalogue"


def test_failed_disk_write_is_logged_and_partial_file_is_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    mask = _mask([(_flat, np.arange(20.0, 200.0, 20.0))])
    monkeypatch.setattr(hz, "compute_mask", lambda *a, **kw: mask)
    write = Path.write_text

    def fail(path: Path, data: str, **kwargs: Any) -> int:
        write(path, "partial", **kwargs)
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_text", fail)
    assert hz.MaskStore(tmp_path).get(LAT0, LON0, 2).from_cache == "computed"
    assert not list(tmp_path.glob("*.part"))
    assert "horizon disk cache write failed" in caplog.text


def test_unavailable_eviction_quota_does_not_allow_additional_disk_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    mask = _mask([(_flat, np.arange(20.0, 200.0, 20.0))])
    monkeypatch.setattr(hz, "compute_mask", lambda *a, **kw: mask)
    store = hz.MaskStore(tmp_path, max_disk_entries=1)
    store.get(LAT0, LON0, 1)
    unlink = Path.unlink

    def refuse(path: Path, **kwargs: Any) -> None:
        if path.suffix == ".json":
            raise PermissionError("eviction denied")
        unlink(path, **kwargs)

    monkeypatch.setattr(Path, "unlink", refuse)
    store.get(LAT0, LON0, 2)
    assert len(list(tmp_path.glob("*.json"))) == 1
    assert not list(tmp_path.glob("*.part"))
    assert "quota unavailable; mask not persisted" in caplog.text
