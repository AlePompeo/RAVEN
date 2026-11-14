# SPDX-License-Identifier: Apache-2.0
"""Read-only views (RAVEN): snapshot, scene, horizon equal the legacy views where the rules coincide."""

from datetime import UTC, datetime
from typing import Any

import pytest

from backend.domain.grazing.analysis import LinkInputs, ProfileCache
from backend.domain.grazing.dem import LolaDem
from backend.domain.grazing.snapshot import snapshot as legacy_snapshot
from backend.domain.raven import s0_context as s0
from backend.domain.raven import views
from scripts import raven_golden as rg

pytestmark = pytest.mark.skipif(
    not (rg.have_kernels() and rg.have_tiles()), reason="kernels or LOLA tiles missing"
)
T = datetime(2027, 4, 7, tzinfo=UTC)
# sites whose far terrain hides the Earth (measurement D4): the intended difference
D4_SITES = {"haworth", "nobile-rim"}


def _engine() -> Any:
    from backend.ephemeris.engine import get_engine

    return get_engine()


def test_snapshot_equals_the_legacy_snapshot_where_the_rules_coincide() -> None:
    eng = _engine()
    inp = LinkInputs()  # legacy radio set: the only difference left is the D4 rule
    new = views.snapshot(T, inp, eng)
    old = legacy_snapshot(T, inp, eng, lambda: LolaDem(allow_download=False), ProfileCache())
    assert [s["id"] for s in new["sites"]] == [s["id"] for s in old["sites"]]
    checked = {"d4": 0, "same": 0, "curvature": 0}
    for n, o in zip(new["sites"], old["sites"], strict=True):
        for k in (
            "earth_az_deg",
            "earth_el_deg",
            "earth_el_geocentric_deg",
            "parallax_deg",
            "earth_range_km",
            "fspl_delta_db",
            "dem_covered",
        ):
            assert n[k] == o[k], (n["id"], k)
        if o["state"] == "unavailable" and n["state"] == "unknown":
            # a terrain tile of this site is not cached: the new model keeps the cause (missing_dem) and the margin unknown
            assert n["terrain_reason"] == "missing_dem" and n["margin_db"] is None
        elif o["state"] in ("out_of_coverage", "unavailable"):
            assert n["state"] == o["state"]
        elif n["terrain_reason"] != "ok":
            assert n["id"] in D4_SITES, n["id"]  # only the sites of the D4 measurement may differ
            # far terrain: a known block or an unknown, never the old open/transition
            assert n["state"] in ("blocked", "unknown"), n["id"]
            assert n["terrain_reason"] in ("blocked_far_terrain", "outside_model")
            checked["d4"] += 1
        elif n["rf_reason"] == "outside_model":
            assert n["id"] in {"shackleton", "de-gerlache"}
            assert n["state"] == "unknown" and n["margin_db"] is None
            checked["curvature"] += 1
        else:
            assert n["state"] == o["state"] and n["margin_db"] == o["margin_db"], n["id"]
            checked["same"] += 1
            assert n["ridge_angle_above_los_deg"] == pytest.approx(
                o["ridge_angle_above_los_deg"],
                abs=5e-4,  # legacy rounds to 3 decimals
            )
    assert checked["same"] >= 2  # Malapert and Nobile; unresolved obstructing curvature is unknown
    assert checked["curvature"] == 2
    assert new["dsn"]["min_elevation_deg"] == old["dsn"]["min_elevation_deg"] == 6.0
    for n, o in zip(new["dsn"]["complexes"], old["dsn"]["complexes"], strict=True):
        assert (n["complex"], n["moon_az_deg"], n["moon_el_deg"], n["sees_moon"]) == (
            o["complex"],
            o["moon_az_deg"],
            o["moon_el_deg"],
            o["sees_moon"],
        )


def test_snapshot_carries_the_true_earth_moon_range_and_its_fspl_delta() -> None:
    eng = _engine()
    inp = LinkInputs()
    new = views.snapshot(T, inp, eng)
    old = legacy_snapshot(T, inp, eng, lambda: LolaDem(allow_download=False), ProfileCache())
    assert 356_000 < new["earth_moon_range_km"] < 407_000  # the Moon's physical range
    assert new["earth_moon_range_km"] == old["earth_moon_range_km"]
    assert new["fspl_delta_db"] == old["fspl_delta_db"]
    assert abs(new["fspl_delta_db"]) < 0.6


def test_snapshot_dsn_complexes_list_both_antennas_for_the_viewer() -> None:
    new = views.snapshot(T, LinkInputs(), _engine())
    assert new["dsn"]["complexes"]
    for c in new["dsn"]["complexes"]:
        assert [a["id"] for a in c["antennas"]] == ["dsn34", "dsn18"]
        assert c["antennas"][1]["coordinates_verified"] is False


def test_scene_numbers_equal_the_legacy_scene_and_add_the_model_block() -> None:
    from backend.domain.grazing.scene import scene as legacy_scene

    eng, dem, cache = _engine(), LolaDem(allow_download=False), ProfileCache()
    site = s0.resolve_site("malapert-massif")
    inp = LinkInputs()
    new = views.scene(T, site, inp, eng, dem, cache)
    old = legacy_scene(
        t=T,
        site=(site.lat_deg, site.lon_deg_east),
        site_id=site.id,
        inputs=inp,
        engine=eng,
        dem=dem,
        cache=cache,
    )
    model = new.pop("model")
    assert new == old
    assert model["state"] in ("open", "transition", "blocked")
    assert model["terrain_reason"] == "ok" and model["heights"]["antenna_height_m"] == 2.0


def test_scene_of_a_far_terrain_site_reports_the_d4_state() -> None:
    eng, dem, cache = _engine(), LolaDem(allow_download=False), ProfileCache()
    m = views.scene(T, s0.resolve_site("haworth"), LinkInputs(), eng, dem, cache)["model"]
    assert m["terrain_reason"] in ("blocked_far_terrain", "outside_model")
    assert m["far_terrain_hides_earth"] is True and m["far_terrain_loss_db"] is not None


def test_scene_with_unknown_obstructing_curvature_keeps_geometry_but_no_complete_margin() -> None:
    scene = views.scene(
        T,
        s0.resolve_site("shackleton"),
        LinkInputs(),
        _engine(),
        LolaDem(allow_download=False),
        ProfileCache(),
    )
    assert scene["model"]["terrain_reason"] == "ok"
    assert scene["model"]["rf_reason"] == "outside_model"
    assert scene["model"]["margin_db"] is None
    assert scene["link"]["state"] == "unknown" and scene["link"]["margin_db"] is None
    assert scene["diffraction"]["correction_db"] is None
    assert scene["diffraction"]["total_loss_db"] is None
    assert scene["terrain"]["profile"]["e_m"]
    assert scene["earth"]["range_km"] > 350_000


def test_horizon_view_gives_mask_and_metadata_and_marks_unknown() -> None:
    h = views.horizon(s0.resolve_site("shackleton"), 2.0)
    assert h["state"] == "ok" and len(h["elevation_deg"]) == 1440 == len(h["distance_m"])
    assert h["meta"]["complete_azimuth_fraction"] == 1.0 and h["azimuth_step_deg"] == 0.25
    out = views.horizon(s0.resolve_site("apollo11"), 2.0)
    assert out["state"] == "outside_coverage" and out["mask"] is None
    assert "elevation_deg" not in out  # never a clear horizon for an uncovered site
