# SPDX-License-Identifier: Apache-2.0
"""Simplified direct-to-Earth link budget: pure functions, units in the names.

    FSPL_dB   = 20 log10(4 pi d / lambda),   lambda = c / f
    EIRP_dBW  = 10 log10(P_W) + G_tx_dBi
    C/N0_dBHz = EIRP - FSPL - L_other + G/T - k_dBW_per_K_Hz,   k = -228.6 dBW/K/Hz
    Eb/N0_dB  = C/N0 - 10 log10(R_bps) - L_impl
    margin_dB = Eb/N0 - Eb/N0_required

Simplifications (see docs/domain/method.md): free space only (no atmosphere, rain, ionosphere),
constant ground G/T (clear sky, zenith), antenna gain independent of pointing angle (pointing
loss is a fixed number), uncoded modulation threshold unless the user supplies another one.
"""

import math
from typing import overload

import numpy as np
from numpy.typing import NDArray

from backend.domain.lunar.model import LinkParams

__all__ = [
    "BOLTZMANN_DBW_PER_K_HZ",
    "SPEED_OF_LIGHT_M_S",
    "cn0_dbhz",
    "dish_gain_dbi",
    "ebn0_db",
    "eirp_dbw",
    "fspl_db",
    "fspl_db_rounded_constant",
    "link_margin_db",
    "tx_gain_dbi",
    "wavelength_m",
]

SPEED_OF_LIGHT_M_S = 299_792_458.0
BOLTZMANN_DBW_PER_K_HZ = -228.6  # 10 log10(1.380649e-23) = -228.599

Arr = NDArray[np.float64]


def wavelength_m(frequency_ghz: float) -> float:
    return SPEED_OF_LIGHT_M_S / (frequency_ghz * 1e9)


@overload
def fspl_db(distance_km: float, frequency_ghz: float) -> float: ...
@overload
def fspl_db(distance_km: Arr, frequency_ghz: float) -> Arr: ...
def fspl_db(distance_km: float | Arr, frequency_ghz: float) -> float | Arr:
    """Free-space path loss 20 log10(4 pi d / lambda), d in km, f in GHz."""
    lam = wavelength_m(frequency_ghz)
    return 20.0 * np.log10(4.0 * math.pi * np.asarray(distance_km) * 1000.0 / lam)


def fspl_db_rounded_constant(distance_km: float, frequency_ghz: float) -> float:
    """The fspl-c plugin form: 92.45 + 20 log10(d_km) + 20 log10(f_GHz).

    The constant is 20 log10(4 pi 1e12 / c) = 92.44778 rounded to 92.45: it differs from
    `fspl_db` by a constant +0.00222 dB.
    """
    return 92.45 + 20.0 * math.log10(distance_km) + 20.0 * math.log10(frequency_ghz)


def dish_gain_dbi(diameter_m: float, frequency_ghz: float, efficiency: float) -> float:
    """Parabolic dish gain 10 log10(eta (pi D / lambda)^2)."""
    return 10.0 * math.log10(efficiency * (math.pi * diameter_m / wavelength_m(frequency_ghz)) ** 2)


def eirp_dbw(tx_power_w: float, tx_gain_dbi: float) -> float:
    return 10.0 * math.log10(tx_power_w) + tx_gain_dbi


def cn0_dbhz(
    eirp_dbw_: float, fspl_db_: float | Arr, other_losses_db: float, gt_dbk: float
) -> float | Arr:
    return eirp_dbw_ - fspl_db_ - other_losses_db + gt_dbk - BOLTZMANN_DBW_PER_K_HZ


def ebn0_db(
    cn0_dbhz_: float | Arr, data_rate_bps: float, implementation_loss_db: float
) -> float | Arr:
    return cn0_dbhz_ - 10.0 * math.log10(data_rate_bps) - implementation_loss_db


def tx_gain_dbi(p: LinkParams) -> float:
    """Dish diameter (if > 0) replaces the direct gain value."""
    if p.tx_dish_diameter_m > 0.0:
        return dish_gain_dbi(p.tx_dish_diameter_m, p.frequency_ghz, p.tx_aperture_efficiency)
    return p.tx_antenna_gain_dbi


def link_margin_db(range_km: float | Arr, p: LinkParams) -> float | Arr:
    """Margin over the required Eb/N0 at the given site-Earth range (km)."""
    eirp = eirp_dbw(p.tx_power_w, tx_gain_dbi(p))
    loss = fspl_db(np.asarray(range_km, dtype=np.float64), p.frequency_ghz)
    ebn0 = ebn0_db(
        cn0_dbhz(eirp, loss, p.pointing_loss_db + p.other_losses_db, p.ground_gt_dbk),
        p.data_rate_bps,
        p.implementation_loss_db,
    )
    return ebn0 - p.required_ebn0_db
