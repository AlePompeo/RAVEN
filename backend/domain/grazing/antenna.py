# SPDX-License-Identifier: Apache-2.0
"""Rover antenna in X band: gain, HPBW, diameter for a link-closing gain, pointing loss, gimbal need.

Formulas of `antenna_directivity.py` (the "script" variant) AND the better-verified variants flagged in
docs/domain/grazinglink-model.md sec. 2.9, always reported side by side with the difference in dB:

    G      = 10 log10( eta (pi D f / c)^2 )         CB79 sec. 2.7 p. 66 (PDF 78): G = 4 pi A_e / lambda^2   (V)
    HPBW   = 70 lambda / D  [deg]                    script: tapered illumination, from memory (I)
           = 58.96 lambda / D                        corrected: uniform circular aperture (Airy), computed (D)
    L_pt   = 12 (err / HPBW)^2                       script (rounded constant)
           = 10 log10(e) 4 ln 2 (err / HPBW)^2       corrected: exact Gaussian beam, 12.04 (D)
           = -20 log10 |2 J1(u) / u|, u = pi D sin(err) / lambda    uniform aperture, exact (D)

The Gaussian formula holds to ~0.03 dB up to err = HPBW/2 and underestimates by 4.3 dB at err = HPBW
versus the Airy pattern (model doc T9). Station gains: DSN 34 m 68 dBi is tag I (implies eta = 0.704, 0.2-0.3 dB
below the 68.21-68.29 dBi of DSN104Q Tab. 7 quoted in assumptions.md, tag V there); the 18 m 62.5 dBi is tag I
(declared a hypothesis by the script, implies eta = 0.708).
"""

import math
from dataclasses import dataclass
from functools import cache
from typing import Any, Literal

import numpy as np
from numpy.typing import ArrayLike, NDArray
from scipy.optimize import brentq
from scipy.special import j1

__all__ = [
    "C_MS",
    "DEFAULT_ETA",
    "HPBW_FACTOR_SCRIPT",
    "STATIONS",
    "Station",
    "antenna_table",
    "diameter_for_gain_m",
    "gain_dbi",
    "gimbal_assessment",
    "hpbw_deg",
    "hpbw_factor_uniform",
    "implied_eta",
    "pointing_loss_airy_db",
    "pointing_loss_compare",
    "pointing_loss_db",
    "required_gain_dbi",
    "wavelength_m",
]

Arr = NDArray[np.float64]
C_MS = 299_792_458.0
DEFAULT_ETA = 0.55  # tag I (CB79 p. 46 uses 0.56 in its scintillation model)
HPBW_FACTOR_SCRIPT = 70.0  # tag I
BOLTZMANN_DBW = -228.599  # tag V: CB79 p. 69 (script: -228.6)
GAUSSIAN_DB_PER_X2 = 10.0 * math.log10(math.e) * 4.0 * math.log(2.0)  # 12.0411
SCRIPT_DB_PER_X2 = 12.0
Illumination = Literal["script_70", "uniform"]
PointingModel = Literal["script", "gaussian", "airy"]


def wavelength_m(frequency_hz: float) -> float:
    if not (math.isfinite(frequency_hz) and frequency_hz > 0):
        raise ValueError("frequency must be positive")
    return C_MS / frequency_hz


@cache
def hpbw_factor_uniform() -> float:
    """HPBW of a uniform circular aperture in units of lambda/D, in degrees (58.96)."""

    def half_power(u: float) -> float:  # |E| = 1/sqrt 2
        return float(2.0 * j1(u) / u - 1.0 / math.sqrt(2.0))

    u = brentq(half_power, 0.5, 3.0)
    return float(math.degrees(2.0 * u / math.pi))  # sin(theta) ~ theta (paraxial)


def gain_dbi(diameter_m: ArrayLike, frequency_hz: float, eta: float = DEFAULT_ETA) -> Arr:
    d = np.asarray(diameter_m, dtype=np.float64)
    if np.any(d <= 0) or not (0 < eta <= 1):
        raise ValueError("diameter must be > 0 and 0 < eta <= 1")
    return np.asarray(
        10.0 * np.log10(eta * (math.pi * d * frequency_hz / C_MS) ** 2), dtype=np.float64
    )


def diameter_for_gain_m(gain_db: float, frequency_hz: float, eta: float = DEFAULT_ETA) -> float:
    if not (0 < eta <= 1):
        raise ValueError("0 < eta <= 1")
    return wavelength_m(frequency_hz) / math.pi * math.sqrt(10.0 ** (gain_db / 10.0) / eta)


def implied_eta(gain_db: float, diameter_m: float, frequency_hz: float) -> float:
    """Aperture efficiency implied by a stated gain: 68 dBi on 34 m at 8.4 GHz -> 0.704."""
    return float(10.0 ** (gain_db / 10.0) / (math.pi * diameter_m * frequency_hz / C_MS) ** 2)


def hpbw_deg(
    diameter_m: ArrayLike, frequency_hz: float, illumination: Illumination = "script_70"
) -> Arr:
    d = np.asarray(diameter_m, dtype=np.float64)
    if np.any(d <= 0):
        raise ValueError("diameter must be > 0")
    k = HPBW_FACTOR_SCRIPT if illumination == "script_70" else hpbw_factor_uniform()
    return np.asarray(k * wavelength_m(frequency_hz) / d, dtype=np.float64)


def pointing_loss_db(
    err_deg: ArrayLike, hpbw: float, model: Literal["script", "gaussian"] = "gaussian"
) -> Arr:
    """Loss for a pointing error: script 12 (err/HPBW)^2 or the exact Gaussian constant 12.0411."""
    if not (math.isfinite(hpbw) and hpbw > 0):
        raise ValueError("hpbw must be positive")
    e = np.abs(np.asarray(err_deg, dtype=np.float64))
    c = SCRIPT_DB_PER_X2 if model == "script" else GAUSSIAN_DB_PER_X2
    return np.asarray(c * (e / hpbw) ** 2, dtype=np.float64)


def pointing_loss_airy_db(err_deg: ArrayLike, diameter_m: float, frequency_hz: float) -> Arr:
    """Exact loss of a uniform circular aperture: -20 log10 |2 J1(u)/u|, u = pi D sin(err) / lambda."""
    e = np.radians(np.abs(np.asarray(err_deg, dtype=np.float64)))
    u = math.pi * diameter_m * np.sin(e) / wavelength_m(frequency_hz)
    safe = np.where(u < 1e-9, 1.0, u)
    amp = np.where(u < 1e-9, 1.0, 2.0 * j1(safe) / safe)
    return np.asarray(-20.0 * np.log10(np.maximum(np.abs(amp), 1e-12)), dtype=np.float64)


def pointing_loss_compare(err_deg: float, diameter_m: float, frequency_hz: float) -> dict[str, Any]:
    """Script and corrected variants for the SAME antenna and the same absolute error, in dB."""
    h70 = float(hpbw_deg(diameter_m, frequency_hz, "script_70"))
    hun = float(hpbw_deg(diameter_m, frequency_hz, "uniform"))
    script = float(pointing_loss_db(err_deg, h70, "script"))
    gauss70 = float(pointing_loss_db(err_deg, h70, "gaussian"))
    gauss_u = float(pointing_loss_db(err_deg, hun, "gaussian"))
    airy = float(pointing_loss_airy_db(err_deg, diameter_m, frequency_hz))
    return {
        "err_deg": err_deg,
        "hpbw_script_70_deg": h70,
        "hpbw_uniform_deg": hun,
        "hpbw_ratio_70_over_uniform": h70 / hun,
        "script_db": script,
        "gaussian_hpbw70_db": gauss70,
        "gaussian_hpbw_uniform_db": gauss_u,
        "airy_exact_db": airy,
        "constant_difference_db": gauss70 - script,
        "script_minus_airy_db": script - airy,
        "note": "Gaussian: valid to ~0.03 dB up to err = HPBW/2; at HPBW it understates the Airy loss by 4.3 dB",
    }


@dataclass(frozen=True)
class Station:
    key: str
    name: str
    diameter_m: float
    gain_dbi: float
    gain_tag: str  # V | D | I
    gain_source: str
    reference_range_dbi: tuple[float, float] | None
    note: str

    def to_dict(self, frequency_hz: float) -> dict[str, Any]:
        eta = implied_eta(self.gain_dbi, self.diameter_m, frequency_hz)
        return {
            "key": self.key,
            "name": self.name,
            "diameter_m": self.diameter_m,
            "diameter_tag": "I",
            "gain_dbi": self.gain_dbi,
            "gain_tag": self.gain_tag,
            "gain_source": self.gain_source,
            "implied_eta": round(eta, 3),
            "ideal_gain_eta1_dbi": round(float(gain_dbi(self.diameter_m, frequency_hz, 1.0)), 2),
            "reference_range_dbi": list(self.reference_range_dbi)
            if self.reference_range_dbi
            else None,
            "note": self.note,
        }


STATIONS: dict[str, Station] = {
    "dsn34": Station(
        "dsn34",
        "DSN 34 m",
        34.0,
        68.0,
        "I",
        "antenna_directivity.py (illustrative); DSN104Q Tab. 7 via assumptions.md quotes 68.21-68.29 dBi at 8425 MHz (V there)",
        (68.21, 68.29),
        "68 dBi implies eta = 0.704 and is 0.2-0.3 dB below the quoted range; 34 m ideal (eta = 1) is 69.52 dBi",
    ),
    "dsn18": Station(
        "dsn18",
        "Stazione 18 m (ipotesi)",
        18.0,
        62.5,
        "I",
        "antenna_directivity.py (the script itself declares it a hypothesis)",
        None,
        "62.5 dBi implies eta = 0.708; with eta = 0.55 the same 18 m gives 61.40 dBi; no source for the station",
    ),
}


def required_gain_dbi(
    rate_bps: float,
    station_gain_dbi: float,
    *,
    distance_m: float = 384_400e3,
    frequency_hz: float = 8.4e9,
    tx_power_dbw: float = 10.0,
    tsys_k: float = 30.0,
    ebn0_db: float = 2.5,
    losses_db: float = 3.0,
    margin_db: float = 3.0,
) -> float:
    """Rover gain G_t that closes the link (`antenna_directivity.py` part 2, K = -228.599 dBW/K/Hz)."""
    if rate_bps <= 0 or tsys_k <= 0 or distance_m <= 0:
        raise ValueError("rate, Tsys and distance must be positive")
    n0 = BOLTZMANN_DBW + 10.0 * math.log10(tsys_k)
    fspl = 20.0 * math.log10(4.0 * math.pi * distance_m * frequency_hz / C_MS)
    return (
        margin_db
        + ebn0_db
        + 10.0 * math.log10(rate_bps)
        + n0
        - tx_power_dbw
        - station_gain_dbi
        + fspl
        + losses_db
    )


def antenna_table(
    station: Station,
    rates_bps: tuple[float, ...] = (1e3, 1e4, 1e5, 1e6, 1e7, 1e8),
    *,
    frequency_hz: float = 8.4e9,
    eta: float = DEFAULT_ETA,
    **link: float,
) -> list[dict[str, Any]]:
    """Gain, diameter and HPBW (script 70 lambda/D and uniform 58.96 lambda/D) per rate."""
    rows: list[dict[str, Any]] = []
    for rb in rates_bps:
        need = required_gain_dbi(rb, station.gain_dbi, frequency_hz=frequency_hz, **link)
        row: dict[str, Any] = {"rate_bps": rb, "required_gain_dbi": round(need, 2)}
        if need < 3.0:
            row.update(type="omnidirezionale / patch", diameter_m=None, hpbw_script_deg=None)
            row["hpbw_uniform_deg"] = None
        else:
            dm = diameter_for_gain_m(need, frequency_hz, eta)
            row.update(
                type="parabola",
                diameter_m=round(dm, 3),
                hpbw_script_deg=round(float(hpbw_deg(dm, frequency_hz, "script_70")), 2),
                hpbw_uniform_deg=round(float(hpbw_deg(dm, frequency_hz, "uniform")), 2),
            )
        rows.append(row)
    return rows


def gimbal_assessment(
    hpbw: float,
    excursion_deg: float,
    *,
    max_loss_db: float = 1.0,
    model: Literal["script", "gaussian"] = "gaussian",
) -> dict[str, Any]:
    """Is a fixed mount enough? `excursion_deg` = largest angle between the Earth direction and the
    mount axis (libration range, from the ephemerides in the analysis; script: hypot(6.7, 7.9) = 10.4)."""
    if hpbw <= 0 or excursion_deg < 0 or max_loss_db <= 0:
        raise ValueError("invalid gimbal arguments")
    loss = float(pointing_loss_db(excursion_deg, hpbw, model))
    c = SCRIPT_DB_PER_X2 if model == "script" else GAUSSIAN_DB_PER_X2
    return {
        "hpbw_deg": hpbw,
        "excursion_deg": excursion_deg,
        "fixed_mount_loss_db": loss,
        "max_loss_budget_db": max_loss_db,
        "max_error_for_budget_deg": hpbw * math.sqrt(max_loss_db / c),
        "gimbal_needed": loss > max_loss_db,
        "validity": "gaussian beam: err <= HPBW/2"
        if excursion_deg <= hpbw / 2
        else "beyond HPBW/2: loss understated",
    }
