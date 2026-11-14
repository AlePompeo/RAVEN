# SPDX-License-Identifier: Apache-2.0
import math

import numpy as np
import pytest

from backend.domain.grazing.antenna import (
    STATIONS,
    antenna_table,
    diameter_for_gain_m,
    gain_dbi,
    gimbal_assessment,
    hpbw_deg,
    hpbw_factor_uniform,
    implied_eta,
    pointing_loss_airy_db,
    pointing_loss_compare,
    pointing_loss_db,
    required_gain_dbi,
)

F = 8.4e9


def test_gain_and_hpbw_table_t9() -> None:
    d = np.array([0.05, 0.10, 0.20, 0.30, 0.50, 1.00, 34.0])
    np.testing.assert_allclose(
        gain_dbi(d, F), [10.28, 16.30, 22.32, 25.84, 30.28, 36.30, 66.93], atol=0.01
    )
    np.testing.assert_allclose(
        hpbw_deg(d, F), [49.97, 24.98, 12.49, 8.33, 5.00, 2.50, 0.073], atol=0.01
    )
    assert float(gain_dbi(34.0, F, 1.0)) == pytest.approx(69.52, abs=0.01)
    assert float(gain_dbi(18.0, F, 0.55)) == pytest.approx(61.40, abs=0.01)


def test_uniform_hpbw_constant_58_96() -> None:
    assert hpbw_factor_uniform() == pytest.approx(58.96, abs=0.01)
    h70, hu = float(hpbw_deg(0.5, F)), float(hpbw_deg(0.5, F, "uniform"))
    assert h70 / hu == pytest.approx(70.0 / 58.96, rel=1e-3)


def test_station_gains_are_tagged_and_eta_is_stated() -> None:
    s34, s18 = STATIONS["dsn34"], STATIONS["dsn18"]
    assert s34.gain_tag == "I" and s18.gain_tag == "I"
    assert implied_eta(68.0, 34.0, F) == pytest.approx(0.704, abs=0.001)
    assert implied_eta(62.5, 18.0, F) == pytest.approx(0.708, abs=0.001)
    d34 = s34.to_dict(F)
    assert d34["implied_eta"] == pytest.approx(0.704, abs=0.001)
    assert d34["reference_range_dbi"] == [68.21, 68.29] and "0.704" in d34["note"]
    assert d34["ideal_gain_eta1_dbi"] == pytest.approx(69.52, abs=0.01)


def test_required_gain_table_equals_model_doc() -> None:
    t34 = {r["rate_bps"]: r for r in antenna_table(STATIONS["dsn34"])}
    assert t34[1e3]["required_gain_dbi"] == pytest.approx(-30.7, abs=0.06)
    assert t34[1e6]["required_gain_dbi"] == pytest.approx(-0.7, abs=0.06)
    assert t34[1e6]["type"].startswith("omni")
    assert t34[1e7]["required_gain_dbi"] == pytest.approx(9.3, abs=0.06)
    assert t34[1e7]["diameter_m"] == pytest.approx(0.04, abs=0.006)
    assert t34[1e7]["hpbw_script_deg"] == pytest.approx(55.9, abs=0.6)
    assert t34[1e8]["required_gain_dbi"] == pytest.approx(19.3, abs=0.06)
    assert t34[1e8]["diameter_m"] == pytest.approx(0.14, abs=0.006)
    assert t34[1e8]["hpbw_script_deg"] == pytest.approx(17.7, abs=0.3)
    assert t34[1e8]["hpbw_uniform_deg"] < t34[1e8]["hpbw_script_deg"]
    t18 = {r["rate_bps"]: r for r in antenna_table(STATIONS["dsn18"])}
    assert t18[1e6]["required_gain_dbi"] == pytest.approx(4.8, abs=0.06)
    assert t18[1e7]["required_gain_dbi"] == pytest.approx(14.8, abs=0.06)
    assert t18[1e7]["hpbw_script_deg"] == pytest.approx(29.7, abs=0.4)
    assert t18[1e8]["required_gain_dbi"] == pytest.approx(24.8, abs=0.06)
    assert t18[1e8]["diameter_m"] == pytest.approx(0.27, abs=0.01)
    assert t18[1e8]["hpbw_script_deg"] == pytest.approx(9.4, abs=0.2)
    # +/- 1 sigma of the station gain moves the requirement dB for dB
    a = required_gain_dbi(1e6, 68.0)
    assert required_gain_dbi(1e6, 67.0) - a == pytest.approx(1.0)


def test_diameter_inverse_of_gain() -> None:
    d = diameter_for_gain_m(15.0, F)
    assert d == pytest.approx(0.0861, abs=0.0005)
    assert float(gain_dbi(d, F)) == pytest.approx(15.0)
    assert float(hpbw_deg(d, F)) == pytest.approx(29.0, abs=0.1)


def test_pointing_loss_variants_t9() -> None:
    hp = 10.0
    x = np.array([0.1, 0.25, 0.5, 0.75, 1.0])
    np.testing.assert_allclose(
        pointing_loss_db(x * hp, hp, "gaussian"), [0.120, 0.752, 3.010, 6.774, 12.041], atol=0.002
    )
    np.testing.assert_allclose(pointing_loss_db(x * hp, hp, "script"), 12 * x**2, atol=1e-12)
    assert 10 * math.log10(math.e) * 4 * math.log(2) == pytest.approx(12.0411, abs=1e-4)
    # Airy at err/HPBW_uniform: 0.114 / 0.719 / 3.010 / 7.439 / 16.276
    d = 0.5
    hu = float(hpbw_deg(d, F, "uniform"))
    airy = pointing_loss_airy_db(x * hu, d, F)
    # (the doc's 16.276 uses the exact asin form of the HPBW; paraxial here: 0.05 dB apart at err = HPBW)
    np.testing.assert_allclose(airy, [0.114, 0.719, 3.010, 7.439, 16.276], atol=0.06)
    assert float(pointing_loss_airy_db(0.0, d, F)) == 0.0


def test_compare_reports_the_difference_in_db() -> None:
    c = pointing_loss_compare(2.0, 0.5, F)  # 2 deg error on a 0.5 m dish (HPBW 5 deg script)
    assert c["hpbw_script_70_deg"] == pytest.approx(5.0, abs=0.01)
    assert c["hpbw_uniform_deg"] == pytest.approx(4.21, abs=0.01)
    assert c["script_db"] == pytest.approx(12 * (2 / 5.0) ** 2, abs=0.01)
    assert c["constant_difference_db"] == pytest.approx(0.0411 * 0.16, abs=1e-3)
    assert c["gaussian_hpbw_uniform_db"] > c["script_db"]  # narrower true beam, larger loss
    assert abs(c["script_minus_airy_db"]) > 0.1 and "4.3" in c["note"]


def test_gimbal_need_versus_libration() -> None:
    # 15 dBi rover antenna: HPBW 29 deg; libration excursion hypot(6.7, 7.9) = 10.36 deg
    hp = float(hpbw_deg(diameter_for_gain_m(15.0, F), F))
    g = gimbal_assessment(hp, math.hypot(6.7, 7.9), max_loss_db=3.0, model="script")
    assert g["fixed_mount_loss_db"] == pytest.approx(1.53, abs=0.02) and not g["gimbal_needed"]
    narrow = gimbal_assessment(2.5, 10.36, max_loss_db=1.0)
    assert narrow["gimbal_needed"] and narrow["validity"].startswith("beyond")
    assert narrow["max_error_for_budget_deg"] == pytest.approx(
        2.5 * math.sqrt(1 / 12.0411), rel=1e-4
    )
    with pytest.raises(ValueError):
        gimbal_assessment(0.0, 1.0)


@pytest.mark.parametrize("bad", [0.0, -1.0])
def test_invalid_inputs(bad: float) -> None:
    with pytest.raises(ValueError):
        gain_dbi(bad, F)
    with pytest.raises(ValueError):
        pointing_loss_db(1.0, bad)
    with pytest.raises(ValueError):
        pointing_loss_db(1.0, math.nan)
