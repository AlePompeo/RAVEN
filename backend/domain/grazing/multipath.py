# SPDX-License-Identifier: Apache-2.0
"""Two-ray multipath on the regolith: Fresnel reflection, rms roughness, circular or linear polarization.

Equations (docs/domain/grazinglink-model.md, sec. 2.6), time convention e^{+j w t}, eps_r = eps' - j eps'':

    s = sin(psi),  q = sqrt(eps_r - cos^2 psi)
    Gamma_h = (s - q) / (s + q)                 horizontal (TE)    = -R_perp of JPL226 eq. (49) p. 20
    Gamma_v = (eps_r s - q) / (eps_r s + q)     vertical (TM)      = -R_par  of JPL226 eq. (48) p. 20
    Gamma_co = (Gamma_h + Gamma_v) / 2          circular, same sense as the receive antenna
                                                (from memory: non verificato sulla fonte)
    rho (field) = exp(-(q_z s_rms)^2 / 2),  q_z s_rms = 4 pi s_rms sin(psi) / lambda
    E = 1 + Gamma rho exp(-j 4 pi h sin(psi) / lambda)          gain = 20 log10 |E|

The roughness exponent is HALF of the one in `compensation_demo.py`: JPL226 eq. (87), (90), (94)
p. 26-28 give exp(-(q_z s)^2) on the coherent POWER, so the FIELD factor has half the exponent. The
script variant is kept as `legacy_script_roughness_factor` for documented comparison only.

Applicability: the specular point of a flat ground lies at h / tan(psi) from the antenna. If it lies
beyond the ridge (distance to the ridge < h / tan(psi)) the flat-ground image does not exist: the term
is marked 'non applicabile' and NOT applied (gain 0 dB), never applied silently.
"""

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import ArrayLike, NDArray

__all__ = [
    "MIN_GRAZING_DEG",
    "NOT_APPLICABLE",
    "Polarization",
    "TwoRayResult",
    "fresnel_coefficients",
    "legacy_script_roughness_factor",
    "reflection_coefficient",
    "roughness_field_factor",
    "two_ray",
]

Arr = NDArray[np.float64]
CArr = NDArray[np.complex128]
Polarization = Literal["horizontal", "vertical", "circular_co"]
MIN_GRAZING_DEG = 0.05  # as the script: avoids the exact cancellation at psi -> 0 (Gamma -> -1)
NOT_APPLICABLE = "non applicabile"
DEFAULT_EPS_R = complex(3.7, -0.01)  # tag I (JPL226 Tab. 1 p. 35 simulation input)


def fresnel_coefficients(psi_deg: ArrayLike, eps_r: complex = DEFAULT_EPS_R) -> tuple[CArr, CArr]:
    """(Gamma_h, Gamma_v) for grazing angle psi (0 < psi <= 90 deg)."""
    psi = np.radians(np.asarray(psi_deg, dtype=np.float64))
    if np.any(psi <= 0) or np.any(psi > math.pi / 2 + 1e-12):
        raise ValueError("grazing angle must be in (0, 90] deg")
    s = np.sin(psi)
    q = np.sqrt(eps_r - np.cos(psi) ** 2 + 0j)
    gh = (s - q) / (s + q)
    gv = (eps_r * s - q) / (eps_r * s + q)
    return np.asarray(gh, dtype=np.complex128), np.asarray(gv, dtype=np.complex128)


def reflection_coefficient(
    psi_deg: ArrayLike, polarization: Polarization = "circular_co", eps_r: complex = DEFAULT_EPS_R
) -> CArr:
    gh, gv = fresnel_coefficients(psi_deg, eps_r)
    if polarization == "horizontal":
        return gh
    if polarization == "vertical":
        return gv
    if polarization == "circular_co":
        return np.asarray((gh + gv) / 2.0, dtype=np.complex128)
    raise ValueError("unknown polarization")


def roughness_field_factor(psi_deg: ArrayLike, sigma_m: float, wavelength_m: float) -> Arr:
    """Coherent FIELD factor exp(-(4 pi sigma sin(psi) / lambda)^2 / 2) (JPL226 eq. (87), (94))."""
    if sigma_m < 0 or wavelength_m <= 0:
        raise ValueError("sigma must be >= 0 and wavelength > 0")
    s = np.sin(np.radians(np.asarray(psi_deg, dtype=np.float64)))
    g = (4.0 * math.pi * sigma_m * s / wavelength_m) ** 2
    return np.asarray(np.exp(-g / 2.0), dtype=np.float64)


def legacy_script_roughness_factor(psi_deg: ArrayLike, sigma_m: float, wavelength_m: float) -> Arr:
    """WRONG variant of `compensation_demo.py` (exponent not halved on the field). Comparison only."""
    return np.asarray(roughness_field_factor(psi_deg, sigma_m, wavelength_m) ** 2, dtype=np.float64)


@dataclass(frozen=True)
class TwoRayResult:
    """Multipath gain per sample. Where `applicable` is False the gain is 0 dB (term not applied)."""

    gain_db: Arr
    applicable: NDArray[np.bool_]
    status: list[str]  # "ok" or `NOT_APPLICABLE`
    reason: list[str]  # "" / "specular point beyond the ridge" / "elevation <= 0"
    specular_distance_m: Arr  # h / tan(psi), nan for psi <= 0
    reflection_magnitude: Arr  # |Gamma rho|
    psi_used_deg: Arr


def two_ray(
    psi_deg: ArrayLike,
    antenna_height_m: float,
    wavelength_m: float,
    *,
    polarization: Polarization = "circular_co",
    eps_r: complex = DEFAULT_EPS_R,
    sigma_m: float = 0.25,
    ridge_distance_m: float | None = None,
    min_psi_deg: float = MIN_GRAZING_DEG,
) -> TwoRayResult:
    """Two-ray gain (dB) for grazing angles `psi_deg` (elevation over a horizontal ground).

    `ridge_distance_m`: distance from the antenna to the dominant ridge along the Earth azimuth; when
    the specular point (h / tan psi) lies beyond it the term is 'non applicabile'. psi <= 0 (Earth
    below the horizon) is also not applicable. Angles below `min_psi_deg` are clamped to it.
    """
    if antenna_height_m <= 0 or wavelength_m <= 0:
        raise ValueError("height and wavelength must be positive")
    psi = np.atleast_1d(np.asarray(psi_deg, dtype=np.float64))
    if not np.all(np.isfinite(psi)):
        raise ValueError("non-finite grazing angle")
    valid = psi > 0.0
    used = np.where(valid, np.maximum(psi, min_psi_deg), 1.0)
    actual = np.where(valid, psi, 1.0)
    spec = np.where(valid, antenna_height_m / np.tan(np.radians(actual)), np.nan)
    if ridge_distance_m is None:
        beyond = np.zeros_like(valid)
    else:
        beyond = valid & (spec > ridge_distance_m)
    ok = valid & ~beyond
    gamma = reflection_coefficient(used, polarization, eps_r)
    rho = roughness_field_factor(used, sigma_m, wavelength_m)
    s = np.sin(np.radians(used))
    phase = np.exp(-1j * 4.0 * math.pi * antenna_height_m * s / wavelength_m)
    field = np.abs(1.0 + gamma * rho * phase)
    gain = np.where(ok, 20.0 * np.log10(np.maximum(field, 1e-12)), 0.0)
    reason = [
        "" if o else ("elevation <= 0" if not v else "specular point beyond the ridge")
        for o, v in zip(ok, valid, strict=True)
    ]
    return TwoRayResult(
        gain_db=np.asarray(gain, dtype=np.float64),
        applicable=np.asarray(ok),
        status=["ok" if o else NOT_APPLICABLE for o in ok],
        reason=reason,
        specular_distance_m=np.asarray(spec, dtype=np.float64),
        reflection_magnitude=np.asarray(np.abs(gamma) * rho, dtype=np.float64),
        psi_used_deg=np.asarray(np.where(valid, used, np.nan), dtype=np.float64),
    )
