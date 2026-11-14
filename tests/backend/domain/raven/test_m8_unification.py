# SPDX-License-Identifier: Apache-2.0
"""M8: the intentional differences of the unified set (docs/domain/raven-changes.md), pinned."""

import math

import numpy as np
import pytest

from backend.domain.grazing.analysis import LinkInputs
from backend.domain.grazing.diffraction import knife_edge_loss_db
from backend.domain.grazing.horizon import HorizonMask, MaskConfig
from backend.domain.grazing.terrain import synthetic_ridge_profile
from backend.domain.raven import params as reg
from backend.domain.raven import s0_context as s0
from backend.domain.raven import s2_terrain as s2
from backend.domain.raven import s5_rf as s5
from backend.domain.raven.pipeline import Scenario, legacy_scenario
from backend.domain.raven.s1_geometry import Geometry

SITE = s0.custom_site("synthetic-site", -89.0, 10.0)


def test_d2_one_radio_set_values_and_tags() -> None:
    g = reg.get
    assert (g("rf.frequency_ghz").default, g("rf.frequency_ghz").tag) == (8.425, "V")
    assert (g("rf.station_gain_dbi").default, g("rf.station_gain_dbi").tag) == (68.29, "D")
    assert (g("rf.tsys_k").default, g("rf.tsys_k").tag) == (26.2, "V")
    assert (g("rf.ebn0_db").default, g("rf.ebn0_db").tag) == (9.6, "D")
    assert (g("rf.ebn0_db_coded_preset").default, g("rf.ebn0_db_coded_preset").tag) == (2.5, "I")
    for k in ("tx_power_dbw", "tx_gain_dbi", "misc_loss_db"):
        assert g(f"rf.{k}").tag == "I"
    gt = reg.value("rf.station_gain_dbi") - 10 * math.log10(reg.value("rf.tsys_k"))
    assert gt == pytest.approx(54.1, abs=0.01)  # the G/T of docs/domain/method.md
    inp = s5.unified_link_inputs()
    assert (inp.frequency_ghz, inp.tsys_k, inp.ebn0_db, inp.station_gain_dbi) == (
        8.425,
        26.2,
        9.6,
        68.29,
    )
    assert (
        LinkInputs().frequency_ghz == 8.4 and LinkInputs().station_gain_dbi is None
    )  # legacy kept


def test_d3_usable_link_threshold_is_3_db_v() -> None:
    assert reg.get("rf.required_margin_db").default == 3.0 == reg.value("lunar.required_margin_db")
    assert reg.get("rf.required_margin_db").tag == "V"
    sc = Scenario(
        SITE,
        s0.TimeWindow(
            __import__("datetime").datetime(2027, 1, 1, tzinfo=__import__("datetime").UTC), 1, 60
        ),
    )
    assert sc.required_margin_db == 3.0
    assert legacy_scenario(SITE, sc.window).required_margin_db == 0.0


def test_d8_two_distinct_heights_with_one_range() -> None:
    p, a = reg.get("rf.panel_height_m"), reg.get("rf.antenna_height_m")
    assert (p.default, p.lo, p.hi, p.tag) == (2.0, 0.1, 100.0, "I")
    assert (a.default, a.lo, a.hi, a.tag) == (2.0, 0.1, 100.0, "I")
    with pytest.raises(Exception):  # noqa: B017
        s5.unified_link_inputs({"antenna_height_m": 0.01})


def _geo(n: int = 3, el: float = 5.0) -> Geometry:
    z = np.zeros(n)
    f = np.full
    return Geometry(
        z, z, f(n, 1.5e8), f(n, 0.2665), f(n, 180.0), f(n, el), f(n, 384_400.0), f(n, 0.95),
        z, z, z, z, ("a", "b", "c"), np.zeros((3, n)),
    )  # fmt: skip


def _mask() -> HorizonMask:
    c = MaskConfig()
    n = c.n_azimuths
    return HorizonMask(
        SITE.lat_deg, SITE.lon_deg_east, 2.0, 0.0, np.full(n, -10.0), np.full(n, 50_000.0),
        np.ones(n, dtype=bool), 0.0, c,
    )  # fmt: skip


def _margin(inp: LinkInputs) -> tuple[float, float]:
    geo = _geo()
    prof = synthetic_ridge_profile(2000.0, 40.0, length_m=4000.0)
    terr = s2.terrain(
        SITE, geo, s5.terrain_params(inp), mask_for=lambda *a: _mask(), profile_for=lambda az: prof
    )
    rf = s5.rf_link(geo, terr, inp, 60.0)
    m, j = rf.margin_db[0], rf.knife_edge_db[0]
    assert m is not None and j is not None
    return m, j


def test_unified_margin_differs_from_legacy_by_the_analytic_amount() -> None:
    """Clear line of sight, no correction, no multipath, no pointing error: every term is closed form."""
    flags = {"apply_correction": False, "apply_multipath": False, "rate_bps": 1e4}
    legacy = LinkInputs.from_overrides(flags)
    uni = s5.unified_link_inputs(flags)
    m_l, j_l = _margin(legacy)
    m_u, j_u = _margin(uni)
    # margin = ... + G_station - N0 - Eb/N0 - FSPL - J, with N0 = k + 10 log10(Tsys)
    expect = (
        (68.29 - 68.0)  # station gain
        + 10 * math.log10(30.0 / 26.2)  # Tsys 30 -> 26.2 K lowers N0
        - (9.6 - 2.5)  # required Eb/N0
        - 20 * math.log10(8.425 / 8.4)  # free-space loss grows with frequency
        - (j_u - j_l)  # knife-edge term (lambda changes nu)
    )
    assert m_u - m_l == pytest.approx(expect, abs=0.01)


def test_threshold_3_db_changes_the_usable_decision() -> None:
    from backend.domain.raven.known import Reason
    from backend.domain.raven.s6_dsn import Dsn
    from backend.domain.raven.s7_mission import link_usable_series
    from tests.backend.domain.raven.test_s4_s6_s7 import _rf

    ds = Dsn({}, [True], "dsn34", 6.0, [Reason.OK])
    two_db = _rf([2.0])
    assert link_usable_series(two_db, ds, 0.0) == [True]  # legacy rule
    assert link_usable_series(two_db, ds, reg.value("rf.required_margin_db")) == [False]  # D3


def test_knife_edge_helper_unchanged() -> None:
    assert float(knife_edge_loss_db(0.0)) == pytest.approx(6.0206, abs=1e-3)
