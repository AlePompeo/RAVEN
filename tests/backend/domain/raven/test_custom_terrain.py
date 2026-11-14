# SPDX-License-Identifier: Apache-2.0
"""Custom-site terrain: masks over the 0/360 seam and near the poles use only the planned tiles."""

from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("scipy")

from backend.domain.grazing.dem_select import plan_site
from backend.domain.raven import s0_context as s0
from backend.domain.raven.custom_terrain import TerrainStore
from tests.backend.fake_pds import FakePds


@pytest.mark.parametrize(("lat", "lon"), [(5.0, 0.02), (5.0, 359.98), (-60.0, 0.0), (70.0, 90.0)])
def test_mask_is_complete_with_exactly_the_planned_tiles(
    lat: float, lon: float, tmp_path: Path
) -> None:
    pds = FakePds()
    st = TerrainStore(tmp_path / "c", fallback=tmp_path / "none", opener=pds)
    site = s0.custom_site("c-seam", lat, lon, strict=True)
    plan = plan_site(site.lat_deg, site.lon_deg_east)
    assert plan.status == "ok"
    assert st.download([site]) == plan.n_tiles
    mask = st.kwargs(site, 10_000.0)["mask_for"](site.lat_deg, site.lon_deg_east, 2.0)
    assert mask.unknown_fraction == 0.0 and bool(np.all(mask.complete))
    assert [p["tiles_missing"] for p in mask.products] == [0] * len(mask.products)
    assert mask.metadata()["far_range_m"][1] == plan.range_m
    # the site height comes from the product: synthetic values are within the label range
    assert -1000.0 <= mask.site_height_m <= 1000.0


def test_a_missing_tile_makes_the_azimuth_unknown_never_flat(tmp_path: Path) -> None:
    pds = FakePds()
    st = TerrainStore(tmp_path / "c", fallback=tmp_path / "none", opener=pds)
    site = s0.custom_site("c-miss", 5.0, 40.0, strict=True)
    st.download([site])
    victim = sorted((tmp_path / "c").glob("*.f32"))[7]  # remove one planned tile
    victim.unlink()
    victim.with_suffix(".sha256").unlink()
    mask = st.kwargs(site, 10_000.0)["mask_for"](site.lat_deg, site.lon_deg_east, 2.0)
    assert mask.unknown_fraction > 0.0 and not bool(np.all(mask.complete))
    assert sum(p["tiles_missing"] for p in mask.products) == 1
    est = st.estimate([site])
    assert est["needs_download"] and est["sites"][0]["tiles_to_download"] == 1


def test_lru_touch_keeps_recently_read_tiles(tmp_path: Path) -> None:
    pds = FakePds()
    st = TerrainStore(tmp_path / "c", fallback=tmp_path / "none", opener=pds, max_bytes=10**9)
    a = s0.custom_site("c-a", 5.0, 40.0, strict=True)
    st.download([a])
    files = sorted((tmp_path / "c").glob("*.f32"))
    assert len(files) == plan_site(5.0, 40.0).n_tiles
    # a tile that is loaded again becomes the newest
    d = st.dem(plan_site(5.0, 40.0).near_id or "")
    ti, tj = plan_site(5.0, 40.0).tiles[plan_site(5.0, 40.0).near_id or ""][0]
    before = d._tile_path(ti, tj).stat().st_mtime_ns
    d.tile(ti, tj)
    assert d._tile_path(ti, tj).stat().st_mtime_ns >= before
