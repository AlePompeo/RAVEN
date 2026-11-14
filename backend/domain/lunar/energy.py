# SPDX-License-Identifier: Apache-2.0
"""Solar array power and battery state-of-charge simulation (potential under stated assumptions).

    S        = S_1AU / r_AU^2,  S_1AU = 1360.8 W/m2 (Kopp & Lean 2011, SORCE/TIM), r = Sun-Moon distance
    cos(inc) = max(0, n . s)    n = array normal, s = unit vector to the Sun, both in local ENU
    P_array  = S A eta packing (1 - degradation) cos(inc)   if the Sun is up (upper limb above mask)

Battery, per step of length dt (Wh):

    direct   = min(P_array, P_load)
    surplus  -> stored energy +eta_c * surplus * dt, capped at capacity (rest curtailed)
    deficit  -> drawn energy deficit * dt / eta_d, limited by the stored energy (rest UNMET)

Mode: operations (`active_load_w` + average comms power while the link is available) when the array
covers the active load OR the stored energy is above the reserve `min_soc`; otherwise survival load.
No thermal model, no temperature effect on cells or battery, no lunar dust, no terrain shadowing.
"""

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from backend.domain.lunar.model import EnergyParams
from backend.domain.lunar.runs import longest_run

__all__ = [
    "SOLAR_CONSTANT_1AU_W_M2",
    "EnergyResult",
    "array_power_w",
    "cos_incidence",
    "irradiance_w_m2",
    "simulate_energy",
]

SOLAR_CONSTANT_1AU_W_M2 = 1360.8
Arr = NDArray[np.float64]
BoolArr = NDArray[np.bool_]


def irradiance_w_m2(sun_distance_au: Arr | float) -> Arr:
    """Total solar irradiance at the Moon, inverse-square scaling of the 1 AU value."""
    return np.asarray(SOLAR_CONSTANT_1AU_W_M2 / np.asarray(sun_distance_au, dtype=np.float64) ** 2)


def cos_incidence(sun_az_deg: Arr, sun_el_deg: Arr, p: EnergyParams) -> Arr:
    """cos of the angle between array normal and Sun direction, clipped at 0 (back face = 0)."""
    az, el = np.radians(sun_az_deg), np.radians(sun_el_deg)
    if p.orientation == "tracking":
        c = np.ones_like(el)
    else:
        s_e, s_n, s_u = np.cos(el) * np.sin(az), np.cos(el) * np.cos(az), np.sin(el)
        if p.orientation == "horizontal":
            c = s_u
        else:
            t, a = math.radians(p.tilt_deg), math.radians(p.tilt_azimuth_deg)
            c = (
                math.sin(t) * math.sin(a) * s_e
                + math.sin(t) * math.cos(a) * s_n
                + math.cos(t) * s_u
            )
    return np.asarray(np.clip(c, 0.0, None), dtype=np.float64)


def array_power_w(irradiance: Arr, cos_inc: Arr, sun_up: BoolArr, p: EnergyParams) -> Arr:
    """Electrical power of the array (W); zero when the Sun is below the mask."""
    k = p.array_area_m2 * p.cell_efficiency * p.packing_factor * (1.0 - p.degradation_fraction)
    return np.asarray(np.where(sun_up, irradiance * k * cos_inc, 0.0), dtype=np.float64)


@dataclass(frozen=True)
class EnergyResult:
    gen_w: Arr
    load_w: Arr
    soc: Arr  # fraction of capacity at the END of each step
    power_available: BoolArr
    harvested_wh: float
    sun_hours: float
    longest_dark_h: float
    min_soc: float
    hours_power_available: float
    survived: bool  # the demanded load was served at every step (no unmet energy)
    unmet_wh: float
    curtailed_wh: float
    charge_loss_wh: float
    discharge_loss_wh: float
    load_served_wh: float
    stored_delta_wh: float
    # per step: 0 survival, 1 comms-only (only with comms_only=True), 2 active; unserved energy
    mode: NDArray[np.int8] | None = None
    unmet_step_wh: Arr | None = None


MODE_SURVIVAL, MODE_COMMS_ONLY, MODE_ACTIVE = 0, 1, 2


def simulate_energy(
    gen_w: Arr,
    sun_up: BoolArr,
    link_available: BoolArr,
    dt_h: float,
    p: EnergyParams,
    tx_power_w: float,
    *,
    comms_only: bool = False,
) -> EnergyResult:
    """Step the battery. `link_available` = geometry and margin allow a transmission.

    `comms_only=True` adds a third mode used by the coupled mission evaluation: when the active
    mode is not available but the link is, and the array alone covers survival + comms load,
    the step runs survival + comms (the battery reserve is not touched for comms).
    """
    n = len(gen_w)
    cap = p.battery_capacity_wh
    min_wh = p.min_soc * cap
    comms_w = p.comms_duty * tx_power_w / p.pa_efficiency
    soc_wh = p.initial_soc * cap
    soc0 = soc_wh
    load = np.zeros(n)
    soc = np.zeros(n)
    avail = np.zeros(n, dtype=bool)
    mode = np.zeros(n, dtype=np.int8)
    unmet_step = np.zeros(n)
    unmet = curtailed = closs = dloss = served_load = 0.0
    ec, ed = p.charge_efficiency, p.discharge_efficiency
    for i in range(n):
        g = float(gen_w[i])
        a = g >= p.active_load_w or soc_wh > min_wh
        avail[i] = a
        if a:
            mode[i] = MODE_ACTIVE
            ld = p.active_load_w + (comms_w if link_available[i] else 0.0)
        elif comms_only and link_available[i] and g >= p.survival_load_w + comms_w:
            mode[i] = MODE_COMMS_ONLY
            ld = p.survival_load_w + comms_w
        else:
            ld = p.survival_load_w
        load[i] = ld
        direct = min(g, ld)
        served_load += direct * dt_h
        surplus_wh = (g - direct) * dt_h
        if surplus_wh > 0.0:
            accepted = min(surplus_wh * ec, cap - soc_wh)
            soc_wh += accepted
            closs += accepted / ec - accepted
            curtailed += surplus_wh - accepted / ec
        deficit_wh = (ld - direct) * dt_h
        if deficit_wh > 0.0:
            drawn = min(deficit_wh / ed, soc_wh)
            soc_wh -= drawn
            served = drawn * ed
            dloss += drawn - served
            served_load += served
            unmet += deficit_wh - served
            unmet_step[i] = deficit_wh - served
        soc[i] = soc_wh / cap if cap > 0 else 0.0
    harvested = float(np.sum(gen_w)) * dt_h
    dark = ~np.asarray(sun_up, dtype=bool)
    return EnergyResult(
        gen_w=gen_w,
        load_w=load,
        soc=soc,
        power_available=avail,
        harvested_wh=harvested,
        sun_hours=float(np.sum(sun_up)) * dt_h,
        longest_dark_h=longest_run(dark) * dt_h,
        min_soc=float(soc.min()) if n and cap > 0 else 0.0,
        hours_power_available=float(avail.sum()) * dt_h,
        survived=unmet <= 1e-9,
        unmet_wh=unmet,
        curtailed_wh=curtailed,
        charge_loss_wh=closs,
        discharge_loss_wh=dloss,
        load_served_wh=served_load,
        stored_delta_wh=soc_wh - soc0,
        mode=mode,
        unmet_step_wh=unmet_step,
    )
