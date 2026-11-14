# SPDX-License-Identifier: Apache-2.0
"""S5 RF link (RAVEN M5): equality with the legacy `analyze`, D4 states, unknown propagation."""

import json
import math
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from backend.domain.grazing.analysis import AnalysisWindow, EarthSweep, LinkInputs, analyze
from backend.domain.grazing.horizon import HorizonMask, MaskConfig
from backend.domain.grazing.terrain import synthetic_ridge_profile
from backend.domain.raven import s0_context as s0
from backend.domain.raven import s2_terrain as s2
from backend.domain.raven import s5_rf as s5
from backend.domain.raven.known import Reason
from backend.domain.raven.s1_geometry import Geometry
from scripts import raven_golden as rg

SITE = s0.custom_site("synthetic-site", -89.0, 10.0)
START = "2027-04-07T00:00:00Z"


def _geo(el: np.ndarray, az: float = 0.0, rng: float = 384_400.0) -> Geometry:
    n = el.size
    z = np.zeros(n)
    f = np.full
    return Geometry(
        sun_az_deg=z,
        sun_el_deg=z,
        sun_range_km=f(n, 1.5e8),
        sun_semidiameter_deg=f(n, 0.2665),
        earth_az_deg=f(n, az),
        earth_el_deg=el,
        earth_range_km=f(n, rng),
        earth_semidiameter_deg=f(n, 0.95),
        earth_el_geocentric_deg=z,
        parallax_deg=z,
        sub_earth_lat_deg=z,
        sub_earth_lon_deg_east=z,
        dsn_complexes=("a", "b", "c"),
        dsn_moon_el_deg=np.zeros((3, n)),
    )


def _mask(elev: float, dist: float = 50_000.0) -> HorizonMask:
    cfg = MaskConfig()
    n = cfg.n_azimuths
    return HorizonMask(
        SITE.lat_deg, SITE.lon_deg_east, 2.0, 0.0, np.full(n, elev), np.full(n, dist),
        np.ones(n, dtype=bool), 0.0, cfg,
    )  # fmt: skip


def _terrain(geo: Geometry, mask: HorizonMask, inputs: LinkInputs) -> s2.Terrain:
    prof = synthetic_ridge_profile(2000.0, 40.0, length_m=4000.0)
    p = s5.terrain_params(inputs)
    return s2.terrain(SITE, geo, p, mask_for=lambda *a: mask, profile_for=lambda az: prof)


@pytest.mark.parametrize(
    ("gain", "source_rate", "source_margin"),
    [(-3.0, 960.0, 9.8), (17.0, 122880.0, 8.7)],
)
def test_current_s5_against_surveyor_absolute_design_budget(
    gain: float, source_rate: float, source_margin: float
) -> None:
    """NASA CR-69102 Table 10-3: absolute budget sum in the unobstructed design limit.

    Construct range ONLY to inject the reported space loss; this does not validate source range.
    Rebase the result to source rate without changing the production bitrate catalogue.
    """
    inputs = s5.unified_link_inputs(
        {
            "frequency_ghz": 2.295,
            "tx_power_dbw": 3.0,
            "tx_gain_dbi": gain,
            "station_gain_dbi": 61.0,
            "tsys_k": 215.0,
            "ebn0_db": 8.3,
            "misc_loss_db": 2.6 + 0.3 + 4.1,
            "rate_bps": 10000.0,
            "tracking_error_deg": 0.0,
            "apply_multipath": False,
            "apply_correction": False,
        }
    )
    equivalent_range_km = 299792458.0 / 2.295e9 / (4 * math.pi) * 10 ** (211.4 / 20) / 1000
    geo = _geo(np.full(2, 30.0), rng=equivalent_range_km)
    terr = _terrain(geo, _mask(-10.0), inputs)
    unobstructed = []
    for ridge in terr.rf_obstacle:
        assert ridge is not None
        unobstructed.append(replace(ridge, nu=-np.inf, blocks_los=False))
    rf = s5.rf_link(geo, replace(terr, rf_obstacle=unobstructed), inputs, 30.0)
    assert all(reason is Reason.OK for reason in rf.reason)
    np.testing.assert_allclose(rf.fspl_db, 211.4, atol=1e-10, rtol=0)
    np.testing.assert_allclose(rf.knife_edge_db, 0.0, atol=1e-12)
    for margin in rf.margin_db:
        assert margin is not None
        at_source_rate = margin + 10 * math.log10(inputs.rate_bps / source_rate)
        assert at_source_rate == pytest.approx(source_margin, abs=0.1)


def test_equals_the_legacy_analysis_on_a_synthetic_ridge() -> None:
    inputs = LinkInputs.from_overrides({"rate_bps": 1e4})
    w = AnalysisWindow.build(START, 2, 30)
    el = np.linspace(0.0, 3.0, w.n_steps)
    ref = analyze(
        window=w,
        inputs=inputs,
        profile=synthetic_ridge_profile(2000.0, 40.0, length_m=4000.0),
        sweep=EarthSweep(0.0, 3.0),
        include_window_samples=True,
    )
    geo = _geo(el)
    terr = _terrain(geo, _mask(-10.0), inputs)  # mask far below the Earth: no far-terrain effect
    rf = s5.rf_link(geo, terr, inputs, 30.0)
    want = ref["window_samples"]["margin_db"]
    np.testing.assert_allclose(rf.margin_db, want, atol=1e-9)
    np.testing.assert_allclose(rf.chosen_rate_bps, ref["window_samples"]["chosen_rate_bps"])
    assert rf.geometric_visible == ref["window_samples"]["geometric_visible"]
    assert all(r is Reason.OK for r in rf.reason)
    assert rf.closes == ref["window_samples"]["link_ok"]
    assert set(rf.rf_state) <= {"open", "transition", "blocked"}


def test_fspl_uses_the_true_distance() -> None:
    inputs = LinkInputs()
    el = np.full(3, 2.0)
    near = s5.rf_link(
        _geo(el, rng=363_300.0), _terrain(_geo(el, rng=363_300.0), _mask(-10), inputs), inputs, 30.0
    )
    far = s5.rf_link(
        _geo(el, rng=405_500.0), _terrain(_geo(el, rng=405_500.0), _mask(-10), inputs), inputs, 30.0
    )
    d = far.fspl_db[0] - near.fspl_db[0]  # type: ignore[operator]
    assert d == pytest.approx(20 * np.log10(405_500.0 / 363_300.0), abs=1e-9)


def test_missing_obstructing_radius_is_not_silently_a_sharp_edge() -> None:
    inputs = s5.unified_link_inputs()
    geo = _geo(np.array([0.0]))
    terr = _terrain(geo, _mask(-10.0), inputs)
    ridge = terr.rf_obstacle[0]
    assert ridge is not None and ridge.nu > 0.0
    missing = replace(ridge, radius_of_curvature_m=math.nan, radius_resolved=False)
    terr = replace(terr, rf_obstacle=[missing])
    result = s5.rf_link(geo, terr, inputs, 30.0)
    assert result.reason == [Reason.OUTSIDE_MODEL]
    assert result.margin_db == [None] and result.closes == [None]
    assert result.ridge_correction_db == [None]
    sharp_inputs = s5.unified_link_inputs({"apply_correction": False})
    sharp = s5.rf_link(geo, terr, sharp_inputs, 30.0)
    assert sharp.reason == [Reason.OK]
    assert sharp.margin_db[0] is not None
    assert sharp.ridge_correction_db == [0.0]


def test_compensator_changes_selected_rate_not_fixed_rate_margin() -> None:
    geo = _geo(np.linspace(0.0, 3.0, 96))
    optimistic = s5.unified_link_inputs({"compensator_k": 0.0})
    conservative = s5.unified_link_inputs({"compensator_k": 6.0})
    terrain = _terrain(geo, _mask(-10.0), optimistic)
    a = s5.rf_link(geo, terrain, optimistic, 30)
    b = s5.rf_link(geo, terrain, conservative, 30)
    assert a.margin_db == b.margin_db and a.margin_db_by_rate == b.margin_db_by_rate
    assert all(
        x is not None and y is not None and x >= y
        for x, y in zip(a.chosen_rate_bps, b.chosen_rate_bps, strict=True)
    )
    assert a.chosen_rate_bps != b.chosen_rate_bps
    missing = s5.rf_link(geo, _terrain(geo, _mask(1.0), optimistic), conservative, 30)
    assert any(value is None for value in missing.chosen_rate_bps)
    assert all(
        rate is None
        for rate, margin in zip(missing.chosen_rate_bps, missing.margin_db, strict=True)
        if margin is None
    )


def test_unknown_radius_does_not_break_other_gimbal_steps_or_override_a_known_far_block() -> None:
    inputs = s5.unified_link_inputs({"mount": "gimbal"})
    geo = _geo(np.array([0.0, 1.0, 2.0, 3.0]))
    terr = _terrain(geo, _mask(-10.0), inputs)
    ridge = terr.rf_obstacle[0]
    assert ridge is not None and ridge.nu > 0
    missing = replace(ridge, radius_of_curvature_m=math.nan, radius_resolved=False)
    terr = replace(terr, rf_obstacle=[missing, *terr.rf_obstacle[1:]])
    rf = s5.rf_link(geo, terr, inputs, 30)
    assert rf.reason[0] is Reason.OUTSIDE_MODEL and rf.margin_db[0] is None
    assert all(reason is Reason.OK for reason in rf.reason[1:])
    assert all(margin is not None for margin in rf.margin_db[1:])
    blocked = replace(terr, terrain_reason=[Reason.BLOCKED_FAR_TERRAIN, *terr.terrain_reason[1:]])
    rf = s5.rf_link(geo, blocked, inputs, 30)
    assert rf.reason[0] is Reason.BLOCKED_FAR_TERRAIN and rf.closes[0] is False


def test_known_far_terrain_block_is_a_known_no() -> None:
    inputs = LinkInputs()
    geo = _geo(np.full(4, 0.5))
    terr = _terrain(geo, _mask(10.0, dist=40_000.0), inputs)
    rf = s5.rf_link(geo, terr, inputs, 30.0)
    assert all(c is False for c in rf.closes)
    assert all(s == "blocked" for s in rf.rf_state)
    assert all(m is None for m in rf.margin_db)  # the number is outside the model
    assert all(r is Reason.BLOCKED_FAR_TERRAIN for r in rf.reason)


def test_outside_model_is_unknown_never_open() -> None:
    inputs = LinkInputs()
    geo = _geo(np.full(4, 0.5))
    terr = _terrain(geo, _mask(1.0, dist=40_000.0), inputs)  # above the Earth centre, < 30 dB
    rf = s5.rf_link(geo, terr, inputs, 30.0)
    assert all(c is None for c in rf.closes) and all(s is None for s in rf.rf_state)
    assert all(m is None for m in rf.margin_db)
    assert all(r is Reason.OUTSIDE_MODEL for r in rf.reason)


def test_missing_profile_is_unknown() -> None:
    inputs = LinkInputs()
    geo = _geo(np.full(3, 2.0))
    site = s0.custom_site("flat", 0.0, 0.0)  # outside the DEM, no injected profile
    terr = s2.terrain(
        site,
        geo,
        s5.terrain_params(inputs),
        mask_for=lambda *a: _mask(-10.0),
    )
    rf = s5.rf_link(geo, terr, inputs, 30.0)
    assert all(c is None for c in rf.closes) and all(
        r is Reason.OUTSIDE_COVERAGE for r in rf.reason
    )


def test_inconsistent_heights_are_refused_and_deterministic() -> None:
    geo = _geo(np.full(3, 2.0))
    terr = _terrain(geo, _mask(-10.0), LinkInputs())
    with pytest.raises(ValueError):
        s5.rf_link(geo, terr, LinkInputs.from_overrides({"antenna_height_m": 5.0}), 30.0)
    a = s5.rf_link(geo, terr, LinkInputs(), 30.0)
    assert a == s5.rf_link(geo, terr, LinkInputs(), 30.0)


@pytest.mark.skipif(not (rg.have_kernels() and rg.have_tiles()), reason="kernels or tiles missing")
def test_real_site_equals_the_grazing_golden() -> None:
    from datetime import UTC, datetime

    from backend.domain.raven import s1_geometry as s1
    from backend.ephemeris.engine import get_engine

    gold: dict[str, Any] = json.loads(
        (Path(__file__).parents[1] / "golden" / "real.json").read_text(encoding="utf-8")
    )["outputs"]["grazing_analyze_shackleton"]["response"]["series"]
    grid = s0.build_grid(s0.TimeWindow(datetime.fromisoformat(START).astimezone(UTC), 2, 60))
    site = s0.resolve_site("shackleton")
    geo = s1.geometry(get_engine(), site, grid)
    inputs = LinkInputs()
    terr = s2.terrain(site, geo, s5.terrain_params(inputs))
    rf = s5.rf_link(geo, terr, inputs, 60.0)
    missing = [
        i
        for i, ridge in enumerate(terr.rf_obstacle)
        if ridge is not None and ridge.nu > 0 and not math.isfinite(ridge.radius_of_curvature_m)
    ]
    assert missing
    known = [i for i in range(grid.n_steps) if i not in missing]
    for i in missing:
        assert rf.reason[i] is Reason.OUTSIDE_MODEL and rf.margin_db[i] is None
    for i in known:
        assert rf.reason[i] is Reason.OK
        assert rf.margin_db[i] == pytest.approx(gold["margin_chosen_rate_db"][i], abs=2e-3)
    # The archived budget silently omitted rounded correction. Reproduce only in explicit sharp-edge mode.
    sharp = s5.rf_link(geo, terr, replace(inputs, apply_correction=False), 60.0)
    archived_sharp = [i for i in missing if gold["ridge_correction_db"][i] == 0.0]
    assert archived_sharp
    np.testing.assert_allclose(
        [sharp.margin_db[i] for i in archived_sharp],
        [gold["margin_chosen_rate_db"][i] for i in archived_sharp],
        atol=2e-3,
        rtol=1e-4,
    )
    np.testing.assert_allclose(
        [sharp.fspl_db[i] for i in archived_sharp],
        [gold["fspl_db"][i] for i in archived_sharp],
        atol=2e-3,
    )
    np.testing.assert_allclose(
        [sharp.chosen_rate_bps[i] for i in archived_sharp],
        [gold["chosen_rate_bps"][i] for i in archived_sharp],
    )
