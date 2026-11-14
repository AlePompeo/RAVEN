# SPDX-License-Identifier: Apache-2.0
from dataclasses import replace

import numpy as np
import pytest

from backend.domain.lunar.energy import (
    SOLAR_CONSTANT_1AU_W_M2,
    array_power_w,
    cos_incidence,
    irradiance_w_m2,
    simulate_energy,
)
from backend.domain.lunar.model import EnergyParams

P = EnergyParams.from_overrides()
ONES = np.ones(1)


def test_irradiance_scaling() -> None:
    assert irradiance_w_m2(1.0) == pytest.approx(1360.8)
    # perihelion/aphelion factors quoted in docs/domain/assumptions.md (1407.5 / 1316.4 W/m2)
    assert float(irradiance_w_m2(147.095e6 / 149.5978707e6)) == pytest.approx(1407.5, abs=0.2)
    assert float(irradiance_w_m2(152.100e6 / 149.5978707e6)) == pytest.approx(1316.4, abs=0.2)
    assert SOLAR_CONSTANT_1AU_W_M2 == 1360.8


def test_sun_at_zenith_power() -> None:
    p = replace(
        P, array_area_m2=2.0, cell_efficiency=0.3, packing_factor=0.9, degradation_fraction=0.1
    )
    s = irradiance_w_m2(np.array([1.0]))
    c = cos_incidence(np.array([0.0]), np.array([90.0]), p)
    pw = array_power_w(s, c, np.array([True]), p)
    assert pw[0] == pytest.approx(1360.8 * 2.0 * 0.3 * 0.9 * 0.9)


def test_orientations() -> None:
    az, el = np.array([90.0]), np.array([30.0])
    assert cos_incidence(az, el, P)[0] == pytest.approx(0.5)  # horizontal: sin(el)
    tr = replace(P, orientation="tracking")
    assert cos_incidence(az, el, tr)[0] == 1.0
    # panel tilted 60 deg towards East (az 90) is normal to the Sun at az 90, el 30
    ti = replace(P, orientation="tilted", tilt_deg=60.0, tilt_azimuth_deg=90.0)
    assert cos_incidence(az, el, ti)[0] == pytest.approx(1.0)
    # facing away: zero (clipped), never negative
    away = replace(P, orientation="tilted", tilt_deg=60.0, tilt_azimuth_deg=270.0)
    assert cos_incidence(az, el, away)[0] == 0.0
    # Sun below horizon gives 0 for horizontal
    assert cos_incidence(az, np.array([-10.0]), P)[0] == 0.0


def test_night_soc_decreases_linearly_by_load() -> None:
    p = replace(
        P,
        battery_capacity_wh=1000.0,
        discharge_efficiency=1.0,
        charge_efficiency=1.0,
        min_soc=0.0,
        initial_soc=1.0,
        active_load_w=20.0,
        survival_load_w=5.0,
    )
    n = 24
    r = simulate_energy(np.zeros(n), np.zeros(n, bool), np.zeros(n, bool), 1.0, p, 20.0)
    assert r.soc[0] == pytest.approx(1 - 20 / 1000)
    assert np.allclose(np.diff(r.soc), -20 / 1000)
    assert r.min_soc == pytest.approx(1 - 24 * 20 / 1000)
    assert r.survived and r.sun_hours == 0 and r.longest_dark_h == 24.0
    assert r.harvested_wh == 0.0


def test_survival_mode_below_reserve_and_brownout() -> None:
    p = replace(
        P,
        battery_capacity_wh=100.0,
        discharge_efficiency=1.0,
        min_soc=0.5,
        initial_soc=1.0,
        active_load_w=50.0,
        survival_load_w=10.0,
    )
    r = simulate_energy(np.zeros(20), np.zeros(20, bool), np.zeros(20, bool), 1.0, p, 20.0)
    # 1 h active (50 Wh) reaches the 50 % reserve, then survival 10 W: 190 Wh demanded, 50 Wh left -> 140 Wh unmet
    assert r.power_available[0] and not r.power_available[1]
    assert r.load_w[1] == 10.0
    assert not r.survived and r.unmet_wh == pytest.approx(140.0)
    assert r.soc[-1] == 0.0


def test_round_trip_efficiency() -> None:
    p = replace(
        P,
        battery_capacity_wh=1000.0,
        charge_efficiency=0.9,
        discharge_efficiency=0.8,
        initial_soc=0.0,
        min_soc=0.0,
        active_load_w=0.0,
        survival_load_w=0.0,
        comms_duty=0.0,
    )
    g = np.array([100.0, 0.0])
    r1 = simulate_energy(g[:1], np.array([True]), np.array([False]), 1.0, p, 20.0)
    stored = r1.soc[0] * 1000.0
    assert stored == pytest.approx(100 * 0.9)
    # now discharge through a 10 W load for 1 h at eta_d: battery drops by 10/0.8
    p2 = replace(p, initial_soc=0.5, active_load_w=10.0, survival_load_w=10.0)
    r2 = simulate_energy(np.zeros(1), np.array([False]), np.array([False]), 1.0, p2, 20.0)
    assert (0.5 - r2.soc[0]) * 1000.0 == pytest.approx(10 / 0.8)
    assert 0.9 * 0.8 == pytest.approx(0.72)


def test_energy_conservation_random_series() -> None:
    rng = np.random.default_rng(1234)
    n = 500
    g = np.where(rng.random(n) < 0.5, rng.random(n) * 120.0, 0.0)
    up = g > 0
    link = rng.random(n) < 0.4
    p = replace(
        P,
        battery_capacity_wh=300.0,
        charge_efficiency=0.93,
        discharge_efficiency=0.91,
        initial_soc=0.6,
        min_soc=0.25,
        active_load_w=40.0,
        survival_load_w=8.0,
        comms_duty=0.5,
    )
    r = simulate_energy(g, up, link, 0.25, p, 20.0)
    assert r.harvested_wh == pytest.approx(
        r.load_served_wh
        + r.stored_delta_wh
        + r.curtailed_wh
        + r.charge_loss_wh
        + r.discharge_loss_wh,
        rel=1e-9,
    )
    assert (r.soc >= 0).all() and (r.soc <= 1 + 1e-12).all()
    assert r.curtailed_wh >= 0 and r.unmet_wh >= 0


def test_comms_load_only_when_link_available() -> None:
    p = replace(
        P,
        battery_capacity_wh=1000.0,
        comms_duty=0.5,
        pa_efficiency=0.5,
        active_load_w=10.0,
        initial_soc=1.0,
    )
    link = np.array([False, True])
    r = simulate_energy(np.zeros(2), np.zeros(2, bool), link, 1.0, p, 20.0)
    assert r.load_w[0] == 10.0
    assert r.load_w[1] == pytest.approx(10.0 + 0.5 * 20.0 / 0.5)
