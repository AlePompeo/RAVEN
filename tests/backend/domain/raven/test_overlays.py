# SPDX-License-Identifier: Apache-2.0
import base64

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.bootstrap import build_app
from backend.domain.raven import overlays as ov


def decode(o: dict) -> np.ndarray:
    return np.frombuffer(base64.b64decode(o["data_b64"]), dtype=np.uint8).reshape(
        o["size"], o["size"]
    )


def test_coverage_classes_follow_latitude_and_the_corners_are_no_data() -> None:
    o = ov.compute_overlay("coverage", size=64)
    a = decode(o)
    assert a[0, 0] == ov.NODATA and a[-1, -1] == ov.NODATA  # outside the disc
    assert a[32, 32] == 2  # the pole is inside the 20 m product
    lat, _lon, inside = ov.disc(64, -75.0)
    assert set(np.unique(a[inside])) == {1, 2}
    assert (a[inside & (lat <= -85.0)] == 2).all() and (a[inside & (lat > -85.0)] == 1).all()
    assert [c["value"] for c in o["classes"]] == [1, 2]


def test_elevation_uses_the_sampler_and_unreadable_cells_stay_no_data() -> None:
    def sampler(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
        h = (lat + 90.0) * 100.0  # grows away from the pole
        h[(lon > 170) & (lat < -80)] = np.nan  # a hole
        return h

    o = ov.compute_overlay("elevation", size=96, sampler=sampler)
    a = decode(o)
    _lat, _lon, inside = ov.disc(96, -75.0)
    assert (a[~inside] == 0).all()
    lat2, lon2, inside2 = ov.disc(96, -75.0)
    hole = inside2 & (lon2 > 170) & (lat2 < -80)
    assert hole.any() and (a[hole] == 0).all()  # never a value for a cell that could not be read
    assert a[inside2 & ~hole].min() >= 1
    assert o["unit"] == "m" and o["tag"] == "D" and o["min"] < o["max"]


def test_slope_of_a_plane_is_constant_and_edges_of_holes_are_no_data() -> None:
    o = ov.compute_overlay("slope", size=96, sampler=lambda lat, lon: np.full(lat.shape, 1000.0))
    a = decode(o)
    assert o["unit"] == "deg" and o["cell_m"] > 1000
    inner = a[10:-10, 10:-10]
    assert (inner[inner > 0] == inner[inner > 0][0]).all()  # flat: the same value everywhere


def test_bad_parameters_are_refused() -> None:
    with pytest.raises(ValueError):
        ov.compute_overlay("nope")
    with pytest.raises(ValueError):
        ov.compute_overlay("elevation", size=8, sampler=lambda a, b: a)
    with pytest.raises(ValueError):
        ov.compute_overlay("elevation")  # no sampler


def test_route_serves_the_coverage_layer_and_refuses_bad_queries() -> None:
    c = TestClient(build_app())
    r = c.get("/api/raven/overlay", params={"layer": "coverage", "size": 64})
    assert r.status_code == 200 and r.json()["layer"] == "coverage" and r.json()["size"] == 64
    assert c.get("/api/raven/overlay", params={"layer": "nope"}).status_code == 422
    assert (
        c.get("/api/raven/overlay", params={"layer": "coverage", "size": 9999}).status_code == 422
    )


def test_shipped_rasters_are_valid_and_served_without_any_terrain_data() -> None:
    for layer, unit in (("elevation", "m"), ("slope", "deg")):
        o = ov.load_precomputed(layer, ov.PRECOMPUTED_SIZE, ov.DEFAULT_LIMIT_LAT)
        assert o is not None and o["unit"] == unit and o["tag"] == "D" and o["min"] < o["max"]
        a = decode(o)
        _lat, _lon, inside = ov.disc(o["size"], o["limit_lat_deg"])
        assert (a[~inside] == 0).all()  # nothing outside the disc
        assert (
            a[inside] > 0
        ).mean() > 0.95  # almost the whole disc has a value; the rest is honest no data
    assert (
        ov.load_precomputed("elevation", 256, -75.0) is None
    )  # another size is not the shipped one
    c = TestClient(build_app())
    r = c.get("/api/raven/overlay", params={"layer": "slope"})
    assert (
        r.status_code == 200
        and r.json()["unit"] == "deg"
        and r.json()["size"] == ov.PRECOMPUTED_SIZE
    )


def _grid(size: int, wall_row: int | None = None) -> np.ndarray:
    h = np.zeros((size, size))
    _lat, _lon, inside = ov.disc(size, -75.0)
    h[~inside] = np.nan
    if wall_row is not None:
        h[wall_row, :] = 3000.0
    return h


def test_flat_ground_is_lit_where_the_sun_is_up() -> None:
    size = 96
    hz, trusted = ov.horizon_grid(_grid(size), -75.0)
    f = ov.visibility_fraction(hz, trusted, -75.0, np.array([-10.0]), np.array([0.0]))
    lat, lon, _ = ov.disc(size, -75.0)
    el, _az = ov._alt_az_of(lat, lon, -10.0, 0.0)
    ok = np.isfinite(f)
    assert ok.sum() > 1000
    assert (f[ok & (el > 1.0)] == 1.0).all() and (f[ok & (el < -1.0)] == 0.0).all()


def test_a_ridge_to_the_north_shades_a_low_sun_from_the_north_only() -> None:
    size = 128
    n = size // 2
    row, col = n - n // 2, n  # a cell at map angle 0 (the top), half way to the rim
    hz, trusted = ov.horizon_grid(_grid(size, wall_row=row - 8), -75.0)
    assert trusted[row, col]
    lat, _lon, _ = ov.disc(size, -75.0)
    lat_cell = float(lat[row, col])
    north = ov.visibility_fraction(
        hz, trusted, -75.0, np.array([lat_cell + 89.0]), np.array([0.0])
    )  # sun 1 degree up, azimuth 0
    south = ov.visibility_fraction(
        hz, trusted, -75.0, np.array([-91.0 - lat_cell]), np.array([180.0])
    )  # 1 degree up, azimuth 180
    assert north[row, col] == 0.0  # the 3000 m ridge 57 km to the north hides it
    assert south[row, col] == 1.0  # nothing stands to the south


def test_unreadable_heights_and_the_outer_ring_have_no_horizon() -> None:
    size = 96
    h = _grid(size)
    h[40:44, 40:44] = np.nan
    hz, trusted = ov.horizon_grid(h, -75.0)
    assert not trusted[41, 41]  # an unreadable cell
    assert not trusted[size // 2, 1]  # the rim: its rays leave the disc
    f = ov.visibility_fraction(hz, trusted, -75.0, np.array([-10.0]), np.array([0.0]))
    assert np.isnan(f[41, 41]) and np.isnan(f[size // 2, 1])
    o = ov.fraction_overlay("sun", f, size, -75.0, "x", "y")
    a = decode(o)
    assert a[41, 41] == 0 and o["unit"] == "%" and (o["min"], o["max"]) == (0.0, 100.0)
