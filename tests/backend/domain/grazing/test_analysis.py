# SPDX-License-Identifier: Apache-2.0
import math
from typing import Any

import numpy as np
import pytest

from backend.domain.grazing.analysis import (
    MAX_SAMPLES,
    AnalysisWindow,
    EarthSweep,
    GrazingParamError,
    LinkInputs,
    ProfileCache,
    _quantise_az,
    analyze,
)
from backend.domain.grazing.dem import DemOutOfCoverage, DemUnavailable, LolaDem
from backend.domain.grazing.terrain import (
    TerrainError,
    dominant_ridge,
    profile_from_user,
    synthetic_ridge_profile,
)
from backend.domain.lunar.model import load_sites
from backend.ephemeris import kernels

try:
    from backend.ephemeris.engine import get_engine

    ENGINE: Any = get_engine()
except kernels.EphemerisUnavailable:  # pragma: no cover
    ENGINE = None

needs_kernels = pytest.mark.skipif(ENGINE is None, reason="kernels missing (make ephemeris)")
START = "2027-04-07T00:00:00Z"
RIDGE_D, RIDGE_H = 2000.0, 40.0  # tip ~1.06 deg above the antenna horizon
PROFILE = synthetic_ridge_profile(RIDGE_D, RIDGE_H, ridge_radius_m=100.0)


def _run(rate: float = 1e5, el0: float = 0.0, el1: float = 3.0, **kw: Any) -> dict[str, Any]:
    return analyze(
        window=AnalysisWindow.build(START, 2, 30),
        inputs=LinkInputs.from_overrides({"rate_bps": rate, **kw}),
        profile=PROFILE,
        sweep=EarthSweep(el0, el1),
    )


def test_synthetic_ridge_known_blocked_and_unblocked() -> None:
    r = _run()
    assert r["flags"]["terrain"]["synthetic"] is True
    assert r["flags"]["terrain"]["source"] == "synthetic"
    assert "sintetico" in r["flags"]["terrain"]["label"]
    # the tip elevation computed independently by the terrain engine splits the sweep
    tip = dominant_ridge(PROFILE, 0.0, 0.0357).tip_elevation_deg
    assert tip == pytest.approx(math.degrees(math.atan2(RIDGE_H - 2.0, RIDGE_D)), abs=0.06)
    n = r["window"]["n_steps"]
    el = np.linspace(0.0, 3.0, n)
    expected = float((el > tip).mean())
    hours = r["windows"]["geometric_hours"]
    assert hours == pytest.approx(expected * r["windows"]["total_hours"], abs=0.6)
    vis = r["series"]["geometric_visible"]
    assert vis[0] == 0.0 and vis[-1] == 1.0  # el = 0 is blocked, el = 3 deg is clear
    assert r["flags"]["blocked_fraction"] == pytest.approx(1 - expected, abs=0.02)


def test_real_window_exceeds_geometric_in_the_transition_zone() -> None:
    low, high = _run(1e4), _run(3e6)
    wl, wh = low["windows"], high["windows"]
    assert wl["geometric_hours"] == wh["geometric_hours"]
    assert wl["transition_hours"] > wh["transition_hours"] > 0.0  # lower rate closes deeper
    for w in (wl, wh):
        assert w["both_hours"] + w["transition_hours"] == pytest.approx(w["real_hours"])
        assert w["both_hours"] + w["geometric_not_closing_hours"] == pytest.approx(
            w["geometric_hours"]
        )
        assert w["transition_intervals_unix"]
    assert wl["real_hours"] > wl["geometric_hours"]


def test_optional_timeline_contains_exact_step_flags() -> None:
    from backend.domain.grazing.compare import summarise

    r = analyze(
        window=AnalysisWindow.build(START, 2, 30),
        inputs=LinkInputs.from_overrides({"rate_bps": 1e4}),
        profile=PROFILE,
        sweep=EarthSweep(0, 3),
        include_window_samples=True,
    )
    samples = r["window_samples"]
    assert all(len(v) == r["window"]["n_steps"] for v in samples.values())
    assert all(isinstance(value, bool) for value in samples["link_ok"])
    assert sum(samples["link_ok"]) * 0.5 == r["windows"]["real_hours"]
    assert sum(samples["geometric_visible"]) * 0.5 == r["windows"]["geometric_hours"]
    assert all(
        ok == (margin >= 0)
        for ok, margin in zip(samples["link_ok"], samples["margin_db"], strict=True)
    )
    assert samples["geometric_visible"][0] is False and samples["geometric_visible"][-1] is True
    assert summarise({"id": "test", "name": "test"}, r)["window_samples"] == samples
    assert "window_samples" not in _run()


def test_flags_parameters_and_declared_limits() -> None:
    r = _run()
    f = r["flags"]
    assert f["geometry_source"] == "user-sweep"
    assert f["correction"]["status"] == "itu"
    assert f["radius_resolved"] is True
    assert f["ridge_radius_median_m"] == pytest.approx(100.0, rel=0.25)
    assert f["multipath"]["status"] in {"applicato", "parziale", "non applicabile"}
    assert "ITU-R P.526-9" in f["correction"]["label"] and "split-step" in f["correction"]["label"]
    assert f["correction"]["max_itu_minus_splitstep_db"] >= 0.0
    assert f["correction"]["table"]["provenance"]["seed"] == 3
    assert all(p["status"] in {"V", "D", "I"} and p["source"] for p in r["parameters"])
    keys = {p["key"] for p in r["parameters"]}
    assert {
        "station_gain_dbi",
        "tx_power_dbw",
        "ebn0_db",
        "regolith_eps_real",
        "wavelength_m",
    } <= keys
    limits = " ".join(r["declared_limits"])
    assert (
        "Ostacolo singolo" in limits and "Nessuna misura radio" in limits and "regolite" in limits
    )
    inc = r["correction_inconsistency"]
    assert inc["jpl226_claim_db"] == 0.0 and inc["p526_max_db"] > inc["table_max_db"]
    assert r["antenna"]["station"]["gain_tag"] == "I"
    assert r["antenna"]["hpbw_uniform_deg"] < r["antenna"]["hpbw_script_70_deg"]
    assert r["label"] == "potential under stated assumptions"


def test_correction_switch_changes_the_margin_by_the_table_amount() -> None:
    on, off = _run(), _run(apply_correction=False)
    assert off["flags"]["correction"]["status"] == "off"
    m_on, m_off = on["series"]["margin_chosen_rate_db"], off["series"]["margin_chosen_rate_db"]
    diff = [b - a for a, b in zip(m_on, m_off, strict=True) if a is not None and b is not None]
    assert max(diff) > 0.0 and max(diff) < 6.0  # the ITU cylinder term costs dB, bounded
    s = on["series"]
    for c, u, sp in zip(
        s["ridge_correction_db"],
        s["ridge_correction_uncertainty_db"],
        s["ridge_correction_splitstep_db"],
        strict=True,
    ):
        assert c >= 0.0 and u >= abs(c - sp) - 1e-9  # disagreement shown as uncertainty


def test_multipath_only_where_applicable() -> None:
    r = _run()
    mp = r["series"]["multipath_applicable"]
    g2 = r["series"]["multipath_gain_db"]
    assert mp[0] == 0.0 and g2[0] == 0.0  # el = 0: Earth not above the horizon, term not applied
    off = _run(apply_multipath=False)
    assert off["flags"]["multipath"]["status"] == "non applicabile"
    assert all(v == 0.0 for v in off["series"]["multipath_gain_db"])


def test_compensator_tradeoff_in_the_result() -> None:
    r = _run(compensator_k=2.33)
    t = r["compensator"]["tradeoff"]
    ks = [row["k"] for row in t]
    assert ks == [0.0, 1.0, 2.33, 3.0]
    outs = [row["outages"] for row in t]
    assert outs == sorted(outs, reverse=True)
    assert r["compensator"]["chosen"]["k"] == 2.33
    assert r["compensator"]["seed"] == 3 and "rinforzo" in r["compensator"]["note"]
    again = _run(compensator_k=2.33)
    assert again["compensator"] == r["compensator"]


def test_fixed_mount_adds_pointing_loss_and_gimbal_assessment() -> None:
    tracking, fixed = _run(), _run(mount="fixed", tx_gain_dbi=35.0)
    assert tracking["antenna"]["pointing_loss_max_db"] == 0.0
    assert fixed["antenna"]["mount"] == "fixed"
    assert fixed["antenna"]["gimbal"]["gimbal_needed"] is True  # 35 dBi: narrow beam, 1.5 deg sweep
    assert fixed["antenna"]["pointing_loss_max_db"] > 0.0
    assert fixed["antenna"]["pointing_script_minus_gaussian_max_db"] <= 0.0  # 12 < 12.04


def test_gimbal_tracking_error_reduces_the_link_margin(tmp_path, monkeypatch) -> None:
    import shutil
    import subprocess
    from pathlib import Path

    import backend.domain.grazing.gimbal as gimbal_module

    if not shutil.which("gcc"):
        pytest.skip("gcc assente")
    root = Path(__file__).resolve().parents[4]
    plugin = root / "backend/plugins/servo_ctrl_c"
    binary = tmp_path / "gimbal_tracker"
    subprocess.run(
        [
            "gcc",
            "-std=c99",
            "-O2",
            f"-I{root / 'contracts/hal'}",
            f"-I{plugin}",
            "-o",
            str(binary),
            str(plugin / "gimbal_tracker.c"),
            str(plugin / "control.c"),
            str(root / "contracts/hal/hal_host.c"),
            "-lm",
        ],
        check=True,
    )
    monkeypatch.setattr(gimbal_module, "EXECUTABLE", binary)
    window = AnalysisWindow.build(START, 0.04, 1)
    sweep = EarthSweep(0, 60)
    ideal = analyze(
        window=window,
        inputs=LinkInputs.from_overrides({"tx_gain_dbi": 45}),
        profile=PROFILE,
        sweep=sweep,
    )
    gimbal = analyze(
        window=window,
        inputs=LinkInputs.from_overrides({"mount": "gimbal", "tx_gain_dbi": 45}),
        profile=PROFILE,
        sweep=sweep,
    )
    loss = np.array(gimbal["series"]["pointing_loss_db"])
    ideal_margin = np.array(ideal["series"]["margin_chosen_rate_db"])
    gimbal_margin = np.array(gimbal["series"]["margin_chosen_rate_db"])
    assert gimbal["antenna"]["mount"] == "gimbal"
    assert gimbal["antenna"]["gimbal_mechanical_limit_fraction"] == 0
    assert loss.max() > 0
    np.testing.assert_allclose(ideal_margin - gimbal_margin, loss, atol=0.0011)
    if ENGINE is not None:
        site = next(s for s in load_sites() if s.id == "malapert-massif")
        real = analyze(
            window=AnalysisWindow.build(START, 1, 60),
            inputs=LinkInputs.from_overrides({"mount": "gimbal"}),
            profile=PROFILE,
            site=(site.lat_deg, site.lon_deg_east),
            engine=ENGINE,
        )
        assert real["flags"]["geometry_source"] != "user-sweep"
        assert real["antenna"]["mount"] == "gimbal"
        assert np.isfinite(real["series"]["pointing_loss_db"]).all()


def test_user_profile_validated_and_geometry_fallback() -> None:
    p = profile_from_user([0.0, 100.0, 200.0, 300.0], [0.0, 0.0, 0.0, 0.0])
    r = analyze(
        window=AnalysisWindow.build(START, 1, 60),
        inputs=LinkInputs(),
        profile=p,
        sweep=EarthSweep(5.0, 10.0),
    )
    assert r["flags"]["terrain"]["source"] == "user" and r["flags"]["terrain"]["synthetic"] is False
    assert r["flags"]["blocked_fraction"] == 0.0
    with pytest.raises(TerrainError):
        profile_from_user([0.0, 0.0], [0.0, 1.0])


@pytest.mark.parametrize(
    "bad",
    [
        {"nope": 1.0},
        {"tx_power_dbw": math.nan},
        {"tx_power_dbw": 1e6},
        {"antenna_eta": 0.0},
        {"station": "dsn70"},
        {"mount": "free"},
        {"rate_bps": 12345.0},
        {"apply_correction": 1.0},
    ],
)
def test_overrides_validation(bad: dict[str, Any]) -> None:
    with pytest.raises(GrazingParamError):
        LinkInputs.from_overrides(bad)


def test_window_caps_and_sweep_validation() -> None:
    assert AnalysisWindow.build(START, 30, 15).n_steps == 2880
    with pytest.raises(GrazingParamError):
        AnalysisWindow.build(START, 90, 15)  # 8640 samples > cap
    assert 90 * 1440 / 15 > MAX_SAMPLES
    for d, s in ((0, 15), (30, 0), (math.nan, 15), (100, 60)):
        with pytest.raises(GrazingParamError):
            AnalysisWindow.build(START, d, s)
    with pytest.raises(GrazingParamError):
        EarthSweep(100.0, 0.0)


def test_azimuth_quantisation() -> None:
    assert _quantise_az(12.34) == pytest.approx(12.3) and _quantise_az(359.96) == 0.0
    assert _quantise_az(-0.04) == 0.0


def test_site_outside_dem_is_a_clear_error_not_invented_data() -> None:
    sites = {s.id: s for s in load_sites()}
    s = sites["apollo11"]
    dem = LolaDem(allow_download=False)
    with pytest.raises(DemOutOfCoverage, match="fuori copertura DEM"):
        analyze(
            window=AnalysisWindow.build(START, 1, 60),
            inputs=LinkInputs(),
            site=(s.lat_deg, s.lon_deg_east),
            dem=dem,
        )


def test_no_terrain_source_is_rejected() -> None:
    with pytest.raises(GrazingParamError):
        analyze(window=AnalysisWindow.build(START, 1, 60), inputs=LinkInputs())


def _real_dem() -> LolaDem:
    return LolaDem(allow_download=False)


@needs_kernels
def test_real_lola_site_if_cached() -> None:
    s = next(x for x in load_sites() if x.id == "malapert-massif")
    cache = ProfileCache()
    try:
        r = analyze(
            window=AnalysisWindow.build(START, 30, 15),
            inputs=LinkInputs(),
            site=(s.lat_deg, s.lon_deg_east),
            site_id=s.id,
            dem=_real_dem(),
            engine=ENGINE,
            cache=cache,
        )
    except DemUnavailable:  # pragma: no cover
        pytest.skip("LOLA tiles not cached (make grazing-dem)")
    t = r["flags"]["terrain"]
    assert t["source"] == "lola" and t["product_id"] == "ldem_85s_20m_float" and not t["synthetic"]
    assert r["window"]["n_steps"] == 2880
    # azimuth quantisation: far fewer profile reads than steps
    assert 0 < t["profiles_extracted"] < 400
    assert r["windows"]["total_hours"] == pytest.approx(720.0)
    assert r["flags"]["geometry_source"] == "ephemeris"
    assert 0.0 <= r["flags"]["blocked_fraction"] <= 1.0
    assert r["antenna"]["libration_excursion_deg"] > 1.0
