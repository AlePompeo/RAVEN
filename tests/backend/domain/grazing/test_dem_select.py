# SPDX-License-Identifier: Apache-2.0
"""Product selection, tile planning (the dry-run numbers) and the LRU cache of custom-site tiles."""

import math
import os
import re
from pathlib import Path

import numpy as np
import pytest

from backend.domain.grazing import dem_cache
from backend.domain.grazing.dem import TILE, load_lock
from backend.domain.grazing.dem_select import (
    GLOBAL_ID,
    MAX_SITE_BYTES,
    NEAR_20M,
    POLAR_240M,
    TILE_BYTES,
    WIRE_FACTOR,
    plan_site,
)

pytest.importorskip("numpy")


def test_global_product_is_locked_with_full_hash() -> None:
    s = load_lock(dataset_id=GLOBAL_ID)
    assert s.size == 23040 * 46080 * 4 == 4_246_732_800
    assert s.projection == "cylindrical" and s.pixels_per_deg == 128.0
    assert re.fullmatch(r"[0-9a-f]{64}", s.sha256) and re.fullmatch(r"[0-9a-f]{64}", s.label_sha256)
    assert s.url.startswith("https://pds-geosciences.wustl.edu/") and s.etag
    assert abs(s.scale_m - 236.901) < 1e-6


def test_cylindrical_pixel_math() -> None:
    from backend.domain.grazing.dem import LolaDem

    d = LolaDem(Path("/nonexistent"), load_lock(dataset_id=GLOBAL_ID), allow_download=False)
    # pixel registration: the centre of the first pixel is half a pixel from the corner
    assert d.pixel(90.0, 0.0) == (-0.5, -0.5)
    r, c = d.pixel(0.0, 180.0)
    assert (r, c) == (11519.5, 23039.5)  # LINE/SAMPLE_PROJECTION_OFFSET of the label
    assert (
        d.pixel(0.0, -180.0)[1] == d.pixel(0.0, 180.0)[1]
    )  # the seam: -180 and 180 are the same column
    assert d.pixel(10.0, 359.0)[1] == d.pixel(10.0, -1.0)[1]


@pytest.mark.parametrize(
    ("lat", "near", "far", "res"),
    [
        (-89.54, NEAR_20M, POLAR_240M, 20.0),
        (-86.0, NEAR_20M, POLAR_240M, 20.0),
        (-85.02, POLAR_240M, POLAR_240M, 240.0),  # the 10 km disc would leave the 20 m product
        (-78.0, POLAR_240M, POLAR_240M, 240.0),
        (0.0, GLOBAL_ID, GLOBAL_ID, 236.901),
        (-60.0, GLOBAL_ID, GLOBAL_ID, 236.901),
        (45.0, GLOBAL_ID, GLOBAL_ID, 236.901),
    ],
)
def test_product_by_latitude(lat: float, near: str, far: str, res: float) -> None:
    p = plan_site(lat, 33.0)
    assert (p.status, p.near_id, p.far_id) == ("ok", near, far)
    assert p.resolution_m == res
    assert p.bytes_total == p.n_tiles * TILE_BYTES
    assert p.bytes_total * WIRE_FACTOR <= MAX_SITE_BYTES
    assert p.range_m is not None and 30_000.0 <= p.range_m <= 200_000.0
    assert p.config is not None and p.config.far_m == p.range_m


def test_too_large_near_the_north_pole_is_unknown_not_flat() -> None:
    p = plan_site(89.9, 10.0)  # the cylindrical grid degenerates: far over the 10 MB cap
    assert p.status == "exceeds_site_cap" and p.bytes_total * WIRE_FACTOR > MAX_SITE_BYTES


def test_estimate_equals_tile_math_at_the_equator() -> None:
    """Independent count: at lat 0 a tile is 128 px * 236.9 m = 30.3 km on a side."""
    p = plan_site(0.0, 40.0)
    assert p.range_m is not None
    tile_m = TILE * 236.901
    disc = math.pi * (p.range_m / tile_m) ** 2
    bbox = (2.0 * p.range_m / tile_m + 2.0) ** 2
    assert disc <= p.n_tiles <= bbox  # tiles of a disc: more than its area, less than its box
    # every tile of a dense random cloud of points inside the planned range is in the plan
    spec = load_lock(dataset_id=GLOBAL_ID)
    rng = np.random.default_rng(7)
    ang = rng.uniform(0.0, 2.0 * math.pi, 20000)
    dist = p.range_m * np.sqrt(rng.uniform(0.0, 1.0, 20000))
    lat = np.degrees(dist * np.sin(ang) / 1_737_400.0)
    lon = 40.0 + np.degrees(dist * np.cos(ang) / 1_737_400.0)
    r, c = spec.pixel_arrays(lat, lon)
    have = set(p.tiles[GLOBAL_ID])
    miss = {(int(a) // TILE, int(b) // TILE) for a, b in zip(r, c, strict=True)} - have
    assert not miss


def test_polar_estimate_matches_the_catalogue_prefetch_radius() -> None:
    """The 20 m part is the disc of 10 km around the site: 20 m tiles are 2.56 km wide."""
    p = plan_site(-89.54, 129.78)
    t20 = p.tiles[NEAR_20M]
    disc = math.pi * (10_000.0 / (TILE * 20.0)) ** 2
    assert disc <= len(t20) <= (2 * 10_000.0 / (TILE * 20.0) + 2) ** 2


def test_the_seam_and_the_pole_do_not_crash_and_wrap() -> None:
    for lat, lon in [(0.0, 359.9), (0.0, -179.9), (-75.2, 180.0), (-90.0, 0.0), (90.0, 0.0)]:
        p = plan_site(lat, lon)
        assert p.status in {"ok", "exceeds_site_cap"}
    p = plan_site(10.0, 0.01)  # the product is 0..360 east: its seam is lon 0
    cols = {tj for _, tj in p.tiles[GLOBAL_ID]}
    assert 0 in cols and 359 in cols  # wraps around the seam


def test_cache_evicts_oldest_first_and_keeps_protected(tmp_path: Path) -> None:
    for i in range(5):
        f = tmp_path / f"x.t128.{i}_0.f32"
        f.write_bytes(b"0" * 1000)
        (tmp_path / f"x.t128.{i}_0.sha256").write_bytes(b"0" * 10)
        os.utime(f, (1000 + i, 1000 + i))
        os.utime(tmp_path / f"x.t128.{i}_0.sha256", (1000 + i, 1000 + i))
    assert dem_cache.usage_bytes(tmp_path) == 5 * 1010
    protect = (tmp_path / "x.t128.0_0.f32",)  # the oldest, but protected
    removed = dem_cache.enforce_limit(tmp_path, 2 * 1010, protect=protect)
    left = sorted(p.name for p in dem_cache.cache_files(tmp_path) if p.suffix == ".f32")
    assert left == ["x.t128.0_0.f32", "x.t128.4_0.f32"]  # kept: protected + newest
    assert dem_cache.usage_bytes(tmp_path) <= 2 * 1010 + 10
    assert "x.t128.1_0.f32" in removed and "x.t128.3_0.f32" in removed
    assert dem_cache.clear_cache(tmp_path) > 0 and dem_cache.cache_files(tmp_path) == []


def test_cache_cap_env() -> None:
    assert dem_cache.max_cache_bytes({}) == 300_000_000
    assert dem_cache.max_cache_bytes({"GRAZING_DEM_CACHE_MAX_MB": "50"}) == 50_000_000
    assert dem_cache.max_cache_bytes({"GRAZING_DEM_CACHE_MAX_MB": "-3"}) == 300_000_000
    assert dem_cache.max_cache_bytes({"GRAZING_DEM_CACHE_MAX_MB": "abc"}) == 300_000_000
