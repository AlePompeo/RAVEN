# SPDX-License-Identifier: Apache-2.0
"""Single knife-edge diffraction (exact and ITU approximation), Fresnel zones, nu from geometry.

Conventions (docs/domain/grazinglink-model.md, sec. 2.3 and 2.5): losses are POSITIVE dB; a negative
value is a gain (Fresnel oscillations in the illuminated zone). nu > 0 when the ridge tip is ABOVE
the line of sight (JPL226 eq. (38)-(39), note 9 p. 15).

    J(nu) = -20 log10 | (1+j)/2 * ((1/2 - C(nu)) - j (1/2 - S(nu))) |        exact, JPL226 eq. (38)
    nu    = h sqrt( 2 (d1 + d2) / (lambda d1 d2) ) = sqrt(2) h / r1          JPL226 eq. (39)
    r_n   = sqrt( n lambda d1 d2 / (d1 + d2) )                                CB79 sec. 2.3 eq. (2) p. 43

Checked on the text of ITU-R P.526-9 (2005), local copy docs/sources/itu-p526-9.pdf (not in git), 2026-11-04:
 * sec. 2.7 eq. (6)-(7b) p. 4: C, S defined with cos/sin(pi s^2 / 2) (same as scipy.special.fresnel);
 * sec. 4.1 eq. (26) p. 16: J = -20 log10( sqrt((1-C-S)^2 + (C-S)^2) / 2 ), algebraically equal to the
   JPL226 eq. (38) form used here;
 * sec. 4.1 eq. (27) p. 16: J ~= 6.9 + 20 log10( sqrt((nu-0.1)^2+1) + nu - 0.1 ), stated only for nu > -0.78;
 * sec. 4.1 eq. (22)-(23) p. 14: nu = h sqrt(2/lambda (1/d1 + 1/d2)) = theta sqrt(2/(lambda (1/d1 + 1/d2)));
   h < 0 below the line joining the ends, theta has the sign of h and is assumed < ~0.2 rad;
 * sec. 2.1 eq. (2) p. 2: R_n = sqrt(n lambda d1 d2 / (d1 + d2)) (approximation, as CB79).
"""

import math
from dataclasses import dataclass
from typing import Literal, Protocol

import numpy as np
from numpy.typing import ArrayLike, NDArray
from scipy.special import fresnel

__all__ = [
    "ITU_APPROX_SOURCE_STATUS",
    "NO_CORRECTION",
    "CorrectionResult",
    "NotAvailableCorrection",
    "RoundedRidgeCorrection",
    "fresnel_zone_radius_m",
    "itu_knife_edge_db",
    "knife_edge_loss_db",
    "nu_from_angle",
    "nu_from_geometry",
]

Arr = NDArray[np.float64]
ITU_APPROX_SOURCE_STATUS = "V: ITU-R P.526-9 sec. 4.1 p. 16 eq. (27), per nu > -0.78 (testo letto)"
ITU_NU_MIN = -0.78


def knife_edge_loss_db(nu: ArrayLike) -> Arr:
    """Exact knife-edge loss in dB (positive = attenuation) with the Fresnel integrals."""
    v = np.asarray(nu, dtype=np.float64)
    s, c = fresnel(v)
    a = (0.5 - c) - 1j * (0.5 - s)
    mag = np.abs((1.0 + 1.0j) / 2.0 * a)
    return np.asarray(-20.0 * np.log10(mag), dtype=np.float64)


def itu_knife_edge_db(nu: ArrayLike) -> Arr:
    """ITU-R P.526 approximation J(nu) = 6.9 + 20 log10(sqrt((nu-0.1)^2+1) + nu - 0.1), nu > -0.78.

    Below nu = -0.78 this implementation uses 0 dB; equation (27) does not prescribe that value.
    """
    v = np.asarray(nu, dtype=np.float64)
    x = v - 0.1
    j = 6.9 + 20.0 * np.log10(np.sqrt(x * x + 1.0) + x)
    return np.asarray(np.where(v > ITU_NU_MIN, j, 0.0), dtype=np.float64)


def nu_from_geometry(h_m: ArrayLike, d1_m: ArrayLike, d2_m: ArrayLike, wavelength_m: float) -> Arr:
    """nu = h sqrt(2 (d1+d2) / (lambda d1 d2)); h > 0 when the tip is above the line of sight."""
    h = np.asarray(h_m, dtype=np.float64)
    d1 = np.asarray(d1_m, dtype=np.float64)
    d2 = np.asarray(d2_m, dtype=np.float64)
    if wavelength_m <= 0 or np.any(d1 <= 0) or np.any(d2 <= 0):
        raise ValueError("wavelength and distances must be positive")
    return np.asarray(h * np.sqrt(2.0 * (d1 + d2) / (wavelength_m * d1 * d2)), dtype=np.float64)


def nu_from_angle(
    theta_rad: ArrayLike, d1_m: ArrayLike, d2_m: ArrayLike, wavelength_m: float
) -> Arr:
    """nu from the angle theta between line of sight and tip (> 0 = tip above the line of sight).

    nu = theta sqrt(2 d1 d2 / (lambda (d1+d2))), equal to `nu_from_geometry` for h = theta d1 (small angles).
    """
    th = np.asarray(theta_rad, dtype=np.float64)
    d1 = np.asarray(d1_m, dtype=np.float64)
    d2 = np.asarray(d2_m, dtype=np.float64)
    if wavelength_m <= 0 or np.any(d1 <= 0) or np.any(d2 <= 0):
        raise ValueError("wavelength and distances must be positive")
    return np.asarray(th * np.sqrt(2.0 * d1 * d2 / (wavelength_m * (d1 + d2))), dtype=np.float64)


def fresnel_zone_radius_m(d1_m: ArrayLike, d2_m: ArrayLike, wavelength_m: float, n: int = 1) -> Arr:
    """Radius of the n-th Fresnel zone: sqrt(n lambda d1 d2 / (d1 + d2)) (CB79 sec. 2.3 eq. (2))."""
    d1 = np.asarray(d1_m, dtype=np.float64)
    d2 = np.asarray(d2_m, dtype=np.float64)
    if wavelength_m <= 0 or n < 1 or np.any(d1 <= 0) or np.any(d2 <= 0):
        raise ValueError("invalid Fresnel zone arguments")
    return np.asarray(np.sqrt(n * wavelength_m * d1 * d2 / (d1 + d2)), dtype=np.float64)


@dataclass(frozen=True)
class CorrectionResult:
    """Rounded-ridge correction in dB, or `not-available` (no table, or no usable radius).

    `uncertainty_db` is an error bar (Fresnel oscillations below nu = -0.78 are reported here, never as
    correction); `anomaly` marks cells flagged > 4 MAD in the table; `clamped` means (nu, radius) was
    outside the table grid and was saturated to its edge (the uncertainty then equals |correction|).
    """

    db: float
    status: Literal["not-available", "table"]
    uncertainty_db: float = 0.0
    anomaly: bool = False
    clamped: bool = False


class RoundedRidgeCorrection(Protocol):
    """Interface of the rounded-ridge compensation R(nu, radius) read from the versioned table."""

    def correction_db(self, nu: float, radius_m: float) -> CorrectionResult: ...


class NotAvailableCorrection:
    """Placeholder until the compensation table exists: zero correction, explicit status."""

    def correction_db(self, nu: float, radius_m: float) -> CorrectionResult:
        if not (math.isfinite(nu) and math.isfinite(radius_m) and radius_m >= 0):
            raise ValueError("invalid nu or radius")
        return CorrectionResult(0.0, "not-available")


NO_CORRECTION: RoundedRidgeCorrection = NotAvailableCorrection()
