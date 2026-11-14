# SPDX-License-Identifier: Apache-2.0
"""Mission hours: vectorised implementation vs a scalar brute-force re-implementation."""

import math
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from backend.domain.lunar.mission import analyze, rank_sites
from backend.domain.lunar.model import (
    AnalysisWindow,
    EnergyParams,
    LinkParams,
    ParamError,
    load_sites,
)
from backend.domain.lunar.visibility import DSN_STATIONS
from backend.ephemeris import kernels

try:
    from backend.ephemeris.engine import get_engine

    ENGINE: Any = get_engine()
except kernels.EphemerisUnavailable:  # pragma: no cover
    ENGINE = None

needs_kernels = pytest.mark.skipif(ENGINE is None, reason="kernels missing (make ephemeris)")
SITES = {s.id: s for s in load_sites()}


def _brute(site: Any, window: AnalysisWindow, link: LinkParams, en: EnergyParams) -> dict[str, Any]:
    """Scalar, step-by-step, no numpy vectorisation of the model; only the engine is shared."""
    k_db = -228.6  # dBW/K/Hz, as specified (exact 10log10(k) = -228.599)
    lam = 299792458.0 / (link.frequency_ghz * 1e9)
    soc = en.initial_soc * en.battery_capacity_wh
    dt = window.dt_h
    useful: list[bool] = []
    margins: list[float] = []
    min_soc = 1e9
    sun_n = earth_n = 0
    for i in range(window.n_steps):
        t = window.start_utc + timedelta(minutes=window.step_min * i)
        sun = ENGINE.topocentric_azel("moon", site.lat_deg, site.lon_deg_east, "sun", t)
        ear = ENGINE.topocentric_azel("moon", site.lat_deg, site.lon_deg_east, "earth", t)
        au = float(ENGINE.distance_km("moon", "sun", t)) / 149597870.7
        sun_up = float(sun.el_deg) + 0.27 >= en.sun_elevation_mask_deg
        ear_vis = float(ear.el_deg) >= link.earth_site_elevation_mask_deg
        dsn_vis = any(
            float(
                ENGINE.topocentric_azel(
                    "earth", d.lat_deg, d.lon_deg_east, "moon", t, h_m=d.height_m
                ).el_deg
            )
            >= link.ground_station_min_elevation_deg
            for d in DSN_STATIONS
        )
        eirp = 10 * math.log10(link.tx_power_w) + link.tx_antenna_gain_dbi
        fspl = 20 * math.log10(4 * math.pi * float(ear.range_km) * 1e3 / lam)
        cn0 = eirp - fspl - link.pointing_loss_db - link.other_losses_db + link.ground_gt_dbk - k_db
        margin = cn0 - 10 * math.log10(link.data_rate_bps) - link.implementation_loss_db
        margin -= link.required_ebn0_db
        link_ok = ear_vis and dsn_vis and margin >= link.required_margin_db
        s_el = math.radians(float(sun.el_deg))
        p = (
            1360.8
            / au**2
            * en.array_area_m2
            * en.cell_efficiency
            * en.packing_factor
            * (1 - en.degradation_fraction)
            * max(0.0, math.sin(s_el))
            if sun_up
            else 0.0
        )
        avail = p >= en.active_load_w or soc > en.min_soc * en.battery_capacity_wh
        load = en.survival_load_w
        if avail:
            load = en.active_load_w + (
                en.comms_duty * link.tx_power_w / en.pa_efficiency if link_ok else 0.0
            )
        net = (p - load) * dt
        if net >= 0:
            soc = min(en.battery_capacity_wh, soc + net * en.charge_efficiency)
        else:
            soc = max(0.0, soc + net / en.discharge_efficiency)
        min_soc = min(min_soc, soc / en.battery_capacity_wh)
        useful.append(avail and link_ok)
        margins.append(margin)
        sun_n += sun_up
        earth_n += ear_vis
    return {
        "useful": useful,
        "margins": margins,
        "min_soc": min_soc,
        "sun_n": sun_n,
        "earth_n": earth_n,
    }


@needs_kernels
def test_mission_hours_match_brute_force_exactly() -> None:
    window = AnalysisWindow.build("2027-04-07T00:00:00Z", 14, 240)
    base = LinkParams.from_overrides()
    en = replace(EnergyParams.from_overrides(), battery_capacity_wh=800.0, initial_soc=0.5)
    ids = ["apollo17", "malapert-massif"]
    sites = [SITES[i] for i in ids]
    # threshold in the middle of the range of margins so that the margin test is not trivial
    probe = _brute(sites[0], window, base, en)["margins"]
    thr = sorted(probe)[len(probe) // 2]
    link = replace(base, required_margin_db=thr)
    res = analyze(ENGINE, sites, window, link, en)
    assert len(res.sites) == 2
    for sa, sid in zip(res.sites, ids, strict=True):
        b = _brute(SITES[sid], window, link, en)
        assert list(sa.useful) == b["useful"]
        assert sa.metrics["useful_hours"] == pytest.approx(sum(b["useful"]) * window.dt_h)
        assert sa.metrics["useful_fraction"] == pytest.approx(sum(b["useful"]) / window.n_steps)
        assert sa.metrics["sun_fraction"] == pytest.approx(b["sun_n"] / window.n_steps)
        assert sa.metrics["earth_fraction"] == pytest.approx(b["earth_n"] / window.n_steps)
        assert sa.margin_db == pytest.approx(b["margins"], abs=1e-9)
        assert sa.metrics["energy"]["min_soc"] == pytest.approx(b["min_soc"], abs=1e-9)
    # the margin test and the visibility test both actually bite on this case
    u = res.sites[0]
    assert 0 < u.useful.sum() < window.n_steps
    assert (u.margin_db < thr).any() and (u.margin_db >= thr).any()


@needs_kernels
def test_gap_and_window_metrics_consistent() -> None:
    window = AnalysisWindow.build("2027-04-07T00:00:00Z", 10, 60)
    res = analyze(
        ENGINE,
        [SITES["apollo11"]],
        window,
        LinkParams.from_overrides(),
        EnergyParams.from_overrides(),
    )
    m = res.sites[0].metrics
    u = res.sites[0].useful
    runs = int(((u[1:] & ~u[:-1]).sum()) + (1 if u[0] else 0))
    assert m["n_windows"] == runs
    assert m["longest_gap_h"] <= (window.n_steps - u.sum()) * window.dt_h
    assert m["min_margin_db"] <= m["mean_margin_db"]


def _m(uf: float, soc: float) -> dict[str, Any]:
    return {"useful_fraction": uf, "energy": {"min_soc": soc}}


def test_ranking_rule_and_components() -> None:
    r = rank_sites({"a": _m(0.8, 0.2), "b": _m(0.4, 0.8), "c": _m(0.0, 0.0)})
    by = {x["site_id"]: x for x in r}
    assert by["a"]["components"]["useful_fraction"]["normalised"] == 1.0
    assert by["a"]["components"]["energy_margin"]["normalised"] == pytest.approx(0.25)
    assert by["a"]["score"] == pytest.approx((1.0 + 0.25) / 2)
    assert by["b"]["score"] == pytest.approx((0.5 + 1.0) / 2)
    assert [x["site_id"] for x in r] == ["b", "a", "c"] and by["b"]["rank"] == 1
    w = rank_sites(
        {"a": _m(0.8, 0.2), "b": _m(0.4, 0.8)}, {"useful_fraction": 3, "energy_margin": 1}
    )
    assert w[0]["site_id"] == "a" and w[0]["score"] == pytest.approx((3 + 0.25) / 4)
    for bad in ({"x": 1}, {"useful_fraction": -1}, {"useful_fraction": 0, "energy_margin": 0}):
        with pytest.raises(ParamError):
            rank_sites({"a": _m(1, 1)}, bad)
    assert rank_sites({"a": _m(0, 0)})[0]["score"] == 0.0


def test_window_helper_dates_are_utc() -> None:
    w = AnalysisWindow.build("2027-04-07T00:00:00Z", 1, 60)
    assert w.instants()[0] == datetime(2027, 4, 7, tzinfo=UTC)
