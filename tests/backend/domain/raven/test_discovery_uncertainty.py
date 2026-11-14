# SPDX-License-Identifier: Apache-2.0
import numpy as np

from backend.domain.raven.discovery import uncertainty as un

DEFAULTS = {
    "energy": {
        "array_area_m2": 1.0,
        "battery_capacity_wh": 10000.0,
        "active_load_w": 50.0,
        "comms_duty": 0.25,
    },
    "rf": {"tx_gain_dbi": 10.0, "misc_loss_db": 2.0},
}


def test_samples_stay_inside_the_declared_spreads_and_are_reproducible() -> None:
    a = un.sample(DEFAULTS, 16, seed=1)
    assert a == un.sample(DEFAULTS, 16, seed=1) and a != un.sample(DEFAULTS, 16, seed=2)
    assert len(a) == 16
    for s in a:
        assert 0.7 <= s["energy"]["array_area_m2"] <= 1.3
        assert 7000 <= s["energy"]["battery_capacity_wh"] <= 13000
        assert 8.0 <= s["rf"]["tx_gain_dbi"] <= 12.0 and 1.0 <= s["rf"]["misc_loss_db"] <= 3.0
    areas = np.array([s["energy"]["array_area_m2"] for s in a])
    assert (
        areas.std() > 0.05 and abs(areas.mean() - 1.0) < 0.08
    )  # a spread around the default, not a constant


def test_a_parameter_the_user_set_is_fixed_and_a_missing_default_cannot_be_varied() -> None:
    s = un.sample(DEFAULTS, 8, seed=0, fixed=frozenset({"array_area_m2"}))
    assert all("array_area_m2" not in x["energy"] for x in s)
    only_rf = un.sample({"rf": DEFAULTS["rf"]}, 4)
    assert all(
        x["energy"] == {} and set(x["rf"]) == {"tx_gain_dbi", "misc_loss_db"} for x in only_rf
    )
    assert un.sample({}, 3) == [{"energy": {}, "rf": {}}] * 3 and un.sample(DEFAULTS, 0) == []


def test_wilson_interval_widens_with_few_samples_and_stays_in_zero_one() -> None:
    lo, hi = un.wilson(8, 10)
    lo2, hi2 = un.wilson(80, 100)
    assert 0 < lo < 0.8 < hi < 1 and (hi - lo) > (hi2 - lo2) > 0
    assert (
        un.wilson(0, 10)[0] == 0.0 and un.wilson(10, 10)[1] == 1.0 and un.wilson(0, 0) == (0.0, 1.0)
    )


def test_summary_counts_the_samples_that_meet_both_objectives_and_names_the_driver() -> None:
    params = un.sample(DEFAULTS, 16, seed=3)
    # a synthetic core: the sun share grows with the array area, the radio share does not depend on the parameters
    outcomes: list[dict[str, float] | None] = [
        {"sun_fraction": 0.5 * p["energy"]["array_area_m2"], "rf_fraction": 0.9} for p in params
    ]
    s = un.summarise(params, outcomes, min_sun=0.5, min_rf=0.8)
    expect = sum(o["sun_fraction"] >= 0.5 for o in outcomes if o) / 16
    assert (
        s.n == 16
        and s.p_meet == expect
        and s.p_low is not None
        and s.p_low <= expect <= (s.p_high or 1.0)
    )
    assert s.drivers and s.drivers[0][0] == "array_area_m2" and s.drivers[0][1] > 0.9


def test_unevaluable_samples_are_left_out_and_no_objective_means_no_probability() -> None:
    params = un.sample(DEFAULTS, 8)
    outcomes: list[dict[str, float] | None] = [None] * 3 + [
        {"sun_fraction": 0.9, "rf_fraction": 0.9}
    ] * 5
    s = un.summarise(params, outcomes, 0.5, None)
    assert s.n == 5 and s.p_meet == 1.0
    none = un.summarise(params, outcomes, None, None)
    assert none.p_meet is None and none.n == 5
    assert un.summarise(params, [None] * 8, 0.5, 0.5).p_meet is None
