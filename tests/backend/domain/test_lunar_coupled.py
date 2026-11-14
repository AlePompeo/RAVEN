# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy

import numpy as np
import pytest

from backend.domain.lunar.coupled import couple, coupled_sensitivity
from backend.domain.lunar.energy import simulate_energy
from backend.domain.lunar.model import EnergyParams


@pytest.fixture
def samples() -> list[dict]:
    return [
        {
            "time_unix": 60 * i,
            "gen_w": 100.0,
            "sun_up": True,
            "earth_visible": True,
            "dsn_visible": dsn,
            "rf_ok": rf,
            "solar_state": state,
        }
        for i, (dsn, rf, state) in enumerate(
            [
                (True, True, "upper_above_profile"),
                (False, True, "upper_below_profile"),
                (True, False, "upper_above_profile"),
            ]
        )
    ]


def test_couples_rf_dsn_and_solar_to_battery(samples: list[dict]) -> None:
    energy = EnergyParams.from_overrides()
    before = deepcopy(samples)
    result = coupled_sensitivity(samples, 60, energy, 10.0)
    expected = simulate_energy(
        np.array([100.0, 0.0, 100.0]),
        np.array([True, False, True]),
        np.array([True, False, False]),
        1.0,
        energy,
        10.0,
    )
    assert result["gen_w"] == [100.0, 0.0, 100.0]
    assert result["link_available"] == [True, False, False]
    assert result["soc"] == pytest.approx(expected.soc.tolist())
    assert result["useful"] == [True, False, False]
    assert result["tx_power_w"] == 10.0
    assert samples == before


def test_unknown_solar_sample_has_no_aggregate(samples: list[dict]) -> None:
    samples[1]["solar_state"] = "missing_dem"
    assert coupled_sensitivity(samples, 60, EnergyParams.from_overrides(), 10) == {
        "status": "unknown_terrain"
    }


# --- coupled mission evaluation: analytic cases -----------------------------------------------
# 100 Wh battery, reserve 20 %, lossless, survival 10 W, active 50 W, comms 10 W (duty 1, PA 1)
SIMPLE = EnergyParams.from_overrides(
    {
        "battery_capacity_wh": 100.0,
        "initial_soc": 1.0,
        "min_soc": 0.2,
        "charge_efficiency": 1.0,
        "discharge_efficiency": 1.0,
        "survival_load_w": 10.0,
        "active_load_w": 50.0,
        "pa_efficiency": 1.0,
        "comms_duty": 1.0,
    }
)


def _couple(gen: list, margin: list, dsn: list, p: EnergyParams = SIMPLE) -> dict:
    return couple(60.0, gen, margin, dsn, p, 10.0)


def test_constant_sun_link_on_is_operational_every_step() -> None:
    r = _couple([100.0] * 4, [5.0] * 4, [True] * 4)
    assert r["series"]["state"] == ["operational"] * 4
    assert r["series"]["useful"] == [True] * 4 and r["series"]["soc"] == [1.0] * 4
    m = r["metrics"]
    assert m["useful_hours"] == 4.0 and m["min_soc"] == 1.0
    assert m["time_to_first_blackout_h"] is None and m["unknown_steps"] == 0


def test_no_sun_battery_arithmetic_and_first_blackout() -> None:
    # step 1: active 50 + comms 10 = 60 Wh from 100 -> 40; step 2: 60 demanded, 40 available
    # -> SOC 0 and 20 Wh unmet (dark); then survival 10 W unmet (dark)
    r = _couple([0.0] * 4, [5.0] * 4, [True] * 4)
    assert r["series"]["soc"] == pytest.approx([0.4, 0.0, 0.0, 0.0])
    assert r["series"]["state"] == ["operational", "dark", "dark", "dark"]
    assert r["series"]["useful"] == [True, False, False, False]
    m = r["metrics"]
    assert m["time_to_first_blackout_h"] == 1.0 and m["unmet_wh"] == pytest.approx(
        20.0 + 10.0 + 10.0
    )
    assert m["limiting_fraction"]["energy"] == 0.75 and m["min_soc"] == 0.0


def test_link_and_dsn_gaps_limit_useful_steps() -> None:
    r = _couple([100.0] * 4, [5.0, -1.0, 5.0, -2.0], [True, True, False, False])
    assert r["series"]["link_usable"] == [True, False, False, False]
    assert r["series"]["useful"] == [True, False, False, False]
    assert r["series"]["limiting"] == [None, "link", "visibility", "multiple"]
    lim = r["metrics"]["limiting_fraction"]
    assert lim == {"energy": 0.0, "link": 0.25, "visibility": 0.25, "multiple": 0.25}


def test_comms_only_when_sun_covers_survival_plus_comms() -> None:
    low = EnergyParams.from_overrides({**SIMPLE.to_dict(), "initial_soc": 0.2})
    r = _couple([30.0, 30.0, 15.0], [5.0] * 3, [True] * 3, low)
    # step 1: battery at the reserve, array 30 W < 50 W active but >= 10 + 10 W: comms-only,
    # 10 Wh surplus stored (SOC 0.3); step 2: SOC above the reserve -> active again
    assert r["series"]["state"][:2] == ["comms_only", "operational"]
    assert r["series"]["soc"][0] == pytest.approx(0.3)
    assert r["series"]["useful"][:2] == [False, True]
    assert r["series"]["limiting"][0] == "energy"


def test_unknown_inputs_propagate_and_are_never_ok() -> None:
    r = _couple([100.0, None, 100.0], [5.0] * 3, [True] * 3)
    assert r["series"]["state"] == ["operational", "unknown", "unknown"]
    assert r["series"]["soc"][1:] == [None, None] and r["series"]["useful"][1:] == [None, None]
    assert r["metrics"]["min_soc_scope"] == "known steps only" and r["first_unknown_index"] == 1
    assert r["metrics"]["useful_hours"] == 1.0 and r["metrics"]["unknown_hours"] == 2.0
    # unknown DSN (18 m hypothesis) and unknown RF margin
    r = _couple([100.0] * 2, [5.0, 5.0], [None, None])
    assert r["series"]["state"] == ["unknown", "unknown"] and r["metrics"]["useful_hours"] == 0.0
    r = _couple([100.0] * 2, [None, 5.0], [True, True])
    assert r["series"]["link_usable"][0] is None and r["series"]["state"] == ["unknown"] * 2
    with pytest.raises(ValueError):
        _couple([100.0], [5.0, 5.0], [True])
