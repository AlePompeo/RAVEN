# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy

import numpy as np
import pytest

from backend.domain.lunar.energy import (
    array_power_w,
    cos_incidence,
    irradiance_w_m2,
    simulate_energy,
)
from backend.domain.lunar.model import EnergyParams, LinkParams
from backend.domain.lunar.terrain_energy import terrain_energy_sensitivity, terrain_generation_w

AZ, EL, AU = [90.0, 90.0, 90.0], [3.0, 3.0, -1.0], [1.0, 1.0, 1.0]


@pytest.fixture
def samples() -> tuple[dict, dict]:
    timeline = {
        "series_time_unix": [1, 2, 3],
        "window": {"step_min": 60},
        "sites": [
            {
                "site": {"id": "test"},
                "series": {"sun_az_deg": AZ, "sun_el_deg": EL, "link_ok": [False, True, False]},
            }
        ],
    }
    solar = {
        "series_time_unix": [1, 2, 3],
        "sites": [
            {
                "site_id": "test",
                "state": ["upper_above_profile", "upper_above_profile", "upper_below_profile"],
                "disc_fraction": [1.0, 0.5, 0.0],
            }
        ],
    }
    return timeline, solar


def _full(p: EnergyParams) -> np.ndarray:
    cosi = cos_incidence(np.array(AZ), np.array(EL), p)
    return array_power_w(irradiance_w_m2(np.array(AU)), cosi, np.ones(3, dtype=bool), p)


def test_generation_scales_with_visible_disc_fraction() -> None:
    p = EnergyParams.from_overrides()
    full = _full(p)
    gen = terrain_generation_w(AZ, EL, AU, [1.0, 0.5, 0.0], p)
    assert gen == pytest.approx([full[0], 0.5 * full[1], 0.0])
    assert np.isnan(terrain_generation_w(AZ, EL, AU, [1.0, None, 0.0], p)[1])
    with pytest.raises(ValueError):
        terrain_generation_w(AZ, EL, AU[:2], [1.0, 1.0, 1.0], p)


def test_sensitivity_uses_disc_fraction_and_keeps_baseline(samples: tuple[dict, dict]) -> None:
    timeline, solar = samples
    p = EnergyParams.from_overrides()
    before = deepcopy(timeline)
    terrain_energy_sensitivity(timeline, solar, {}, AU)
    actual = solar["sites"][0]["energy_sensitivity"]
    gen = terrain_generation_w(AZ, EL, AU, [1.0, 0.5, 0.0], p)
    expected = simulate_energy(
        gen,
        np.array([True, True, False]),
        np.array([False, True, False]),
        1.0,
        p,
        LinkParams.from_overrides().tx_power_w,
    )
    assert actual["status"] == "available"
    assert actual["gen_w"] == pytest.approx(expected.gen_w.tolist())
    assert actual["soc"] == pytest.approx(expected.soc.tolist())
    assert timeline == before


def test_unknown_disc_fraction_prevents_battery_result(samples: tuple[dict, dict]) -> None:
    timeline, solar = samples
    solar["sites"][0]["state"][1] = "missing_dem"
    solar["sites"][0]["disc_fraction"][1] = None
    terrain_energy_sensitivity(timeline, solar, {}, AU)
    assert solar["sites"][0]["energy_sensitivity"] == {"status": "unknown_terrain"}


def test_sensitivity_rejects_unsynchronised_data(samples: tuple[dict, dict]) -> None:
    timeline, solar = samples
    solar["series_time_unix"][1] += 1
    with pytest.raises(ValueError, match="timelines do not match"):
        terrain_energy_sensitivity(timeline, solar, {}, AU)
