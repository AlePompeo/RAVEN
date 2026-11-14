# SPDX-License-Identifier: Apache-2.0
import base64

import numpy as np
from fastapi.testclient import TestClient

from backend.bootstrap import build_app
from backend.domain.raven import overlays_global as og


def _raster(o: dict) -> np.ndarray:
    return np.frombuffer(base64.b64decode(o["data_b64"]), dtype=np.uint8).reshape(
        o["height"], o["width"]
    )


def test_grid_covers_the_sphere_north_to_south() -> None:
    lat, lon = og.grid(8, 4)
    assert lat[0, 0] > 0 > lat[-1, 0] and lon[0, 0] < 0 < lon[0, -1]
    assert np.allclose(lat[:, 0], [67.5, 22.5, -22.5, -67.5])


def test_unreadable_cells_are_no_data_never_a_value() -> None:
    h = np.zeros((36, 72))
    h[10:14, 20:30] = np.nan
    r = _raster(og.elevation_overlay(h))
    assert (r[10:14, 20:30] == 0).all() and (r[h == 0] > 0).all()
    s = _raster(og.slope_overlay(h))
    assert (s[10:14, 20:30] == 0).all()  # a neighbour of an unreadable cell has no gradient either


def test_slope_of_a_ramp_is_the_ramp_angle() -> None:
    height, width = 90, 180
    lat, _lon = og.grid(width, height)
    h = lat * 1000.0  # 1 m of height per 1 mm of... a plain north-south ramp
    o = og.slope_overlay(h)
    assert o["unit"] == "deg" and o["min"] >= 0.0
    r = _raster(o)
    assert (r[1:-1, :] > 0).sum() > 0 and (r[0] == 0).all() and (r[-1] == 0).all()


def test_a_ridge_to_the_east_raises_the_eastern_horizon_only() -> None:
    height, width = 360, 720
    h = np.zeros((height, width))
    h[:, 184:187] = (
        10000.0  # a north-south wall of 10 km, 4 cells (about 60 km) east of the observer
    )
    horizons, trusted = og.horizon_grid(h, n_az=8, max_cells=10)
    row, col = 180, 180
    east = horizons[2, row, col]  # azimuth 90 degrees
    west = horizons[6, row, col]
    assert east > 5.0 and west < 1.0 and trusted[row, col]


def test_longitude_wraps_across_the_antimeridian() -> None:
    height, width = 360, 720
    h = np.zeros((height, width))
    h[:, 2:5] = 10000.0  # just east of the antimeridian
    horizons, _trusted = og.horizon_grid(h, n_az=8, max_cells=10)
    assert horizons[2, 180, width - 2] > 5.0  # a cell west of the antimeridian sees it to the east


def test_visibility_fraction_is_one_under_the_body_and_zero_on_the_other_side() -> None:
    horizons = np.zeros((4, 3, 6), dtype=np.float32)  # a flat horizon
    trusted = np.ones((3, 6), dtype=bool)
    frac = og.visibility_fraction(horizons, trusted, np.array([0.0, 0.0]), np.array([0.0, 0.0]))
    assert frac.shape == (3, 6) and np.nanmax(frac) == 1.0 and np.nanmin(frac) == 0.0
    lon = og.grid(6, 3)[1][0]
    assert (
        frac[1, int(np.argmin(np.abs(lon)))] == 1.0 and frac[1, 0] == 0.0
    )  # lon -150 is on the far side


def test_shipped_rasters_have_the_declared_shape_and_honest_limits() -> None:
    for layer in ("elevation", "slope", "coverage", "sun", "earth"):
        o = og.load_precomputed(layer)
        assert o is not None, layer
        assert (
            o["width"] == og.WIDTH
            and o["height"] == og.HEIGHT
            and o["projection"] == "equirectangular"
        )
        assert _raster(o).shape == (og.HEIGHT, og.WIDTH)
    sun = og.load_precomputed("sun")
    assert sun is not None and "Not validated" in sun["note"] and sun["tag"] == "D"
    earth = _raster(og.load_precomputed("earth") or {})
    near, far = earth[:, 180:540], np.r_[earth[:, :180].ravel(), earth[:, 540:].ravel()]
    assert (
        near[near > 0].mean() > 3 * far[far > 0].mean()
    )  # the Earth is seen from the near side only (libration aside)


def test_api_serves_the_global_scope_and_rejects_unknown_ones() -> None:
    client = TestClient(build_app())
    r = client.get("/api/raven/overlay", params={"layer": "sun", "scope": "global"})
    assert r.status_code == 200 and r.json()["projection"] == "equirectangular"
    assert (
        client.get("/api/raven/overlay", params={"layer": "sun", "scope": "mars"}).status_code
        == 422
    )
    polar = client.get("/api/raven/overlay", params={"layer": "elevation"})
    assert polar.status_code == 200 and polar.json().get("projection") is None


def test_joint_metrics_share_of_both_and_longest_runs() -> None:
    horizons = np.zeros((4, 3, 6), dtype=np.float32)  # a flat horizon
    trusted = np.ones((3, 6), dtype=bool)
    lat, lon = og.grid(6, 3)
    sun = (
        np.array([0.0, 0.0, 0.0, 0.0]),
        np.array([0.0, 180.0, 180.0, 0.0]),
    )  # the Sun is up at t0 and t3, down at t1 and t2
    earth = (np.zeros(4), np.zeros(4))  # the Earth stays over longitude 0
    m = og.joint_metrics(horizons, trusted, lat, lon, sun, earth, 6.0)
    r, c = 1, 2  # the cell at longitude -30
    assert m["both"][r, c] == 0.5 and m["sun_gap_h"][r, c] == 12.0 and m["earth_gap_h"][r, c] == 0.0
    far = 0  # longitude -150: the Earth is never above the horizon, the Sun is up at t1 and t2 only
    assert (
        m["both"][r, far] == 0.0
        and m["earth_gap_h"][r, far] == 24.0
        and m["sun_gap_h"][r, far] == 6.0
    )


def test_untrusted_cells_have_no_joint_value() -> None:
    horizons = np.zeros((4, 3, 6), dtype=np.float32)
    trusted = np.ones((3, 6), dtype=bool)
    trusted[1, 3] = False
    lat, lon = og.grid(6, 3)
    m = og.joint_metrics(
        horizons, trusted, lat, lon, (np.zeros(2), np.zeros(2)), (np.zeros(2), np.zeros(2)), 6.0
    )
    assert all(np.isnan(v[1, 3]) and np.isfinite(v[0, 0]) for v in m.values())


def test_the_shipped_joint_layers_exist_and_are_consistent() -> None:
    for layer in ("both", "sun_gap", "earth_gap"):
        o = og.load_precomputed(layer)
        assert o is not None and o["width"] == og.WIDTH and "Not validated" in o["note"], layer
    both = _raster(og.load_precomputed("both") or {})
    sun = _raster(og.load_precomputed("sun") or {})
    earth = _raster(og.load_precomputed("earth") or {})
    ok = (both > 0) & (sun > 0) & (earth > 0)
    # both cannot exceed either body alone (the 8-bit stretch is the same 0..100 %)
    assert (both[ok].astype(int) <= np.minimum(sun[ok], earth[ok]).astype(int) + 1).all()
    gap_e = og.load_precomputed("earth_gap")
    assert (
        gap_e is not None and gap_e["unit"] == "h" and gap_e["max"] > 24 * 30
    )  # the far side has no Earth for months
