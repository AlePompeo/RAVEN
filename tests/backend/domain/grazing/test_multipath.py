# SPDX-License-Identifier: Apache-2.0
import numpy as np
import pytest
from scipy.integrate import quad

from backend.domain.grazing.multipath import (
    NOT_APPLICABLE,
    fresnel_coefficients,
    legacy_script_roughness_factor,
    reflection_coefficient,
    roughness_field_factor,
    two_ray,
)
from backend.domain.lunar.link import SPEED_OF_LIGHT_M_S

LAM = SPEED_OF_LIGHT_M_S / 8.4e9
EPS = complex(3.7, -0.01)
PSI = [0.1, 0.5, 1, 2, 5, 10, 30, 45, 90]


@pytest.mark.parametrize("psi,sigma", [(0.1, 0.25), (1.0, 0.25), (5.0, 0.05), (30.0, 0.01)])
def test_roughness_field_against_independent_gaussian_phase_integral(
    psi: float, sigma: float
) -> None:
    q = 4.0 * np.pi / LAM * np.sin(np.radians(psi)) * sigma
    expected, _ = quad(
        lambda z: 2.0 * np.exp(-z * z / 2.0) / np.sqrt(2.0 * np.pi),
        0.0,
        np.inf,
        weight="cos",
        wvar=q,
        epsabs=1e-12,
    )
    assert float(roughness_field_factor(psi, sigma, LAM)) == pytest.approx(expected, abs=1e-10)


@pytest.mark.parametrize("permittivity", [3.7, 5.0])
def test_lossless_circular_power_against_explorer35_basis(permittivity: float) -> None:
    """NASA CR-119032, printed pp.13-14: pure-circular power ratio, real coefficients.

    Snell's angle construction is independent of the production grazing-angle coefficients.
    This checks power, not reflected phase, lossy materials or hardware handedness.
    """
    psi = np.array([0.1, 1.0, 27.47, 45.0, 89.9, 90.0])
    incidence = np.radians(90.0 - psi)
    index = np.sqrt(permittivity)
    refraction = np.arcsin(np.sin(incidence) / index)
    ci, cr = np.cos(incidence), np.cos(refraction)
    rho_h = (ci - index * cr) / (ci + index * cr)
    rho_v = (index * ci - cr) / (index * ci + cr)
    ratio = ((rho_v + rho_h) / (rho_v - rho_h)) ** 2
    total_reflected_power = (rho_v**2 + rho_h**2) / 2
    expected_power = total_reflected_power * ratio / (1 + ratio)
    actual = reflection_coefficient(psi, "circular_co", eps_r=complex(permittivity, 0.0))
    np.testing.assert_allclose(np.abs(actual) ** 2, expected_power, rtol=1e-12, atol=1e-15)


def test_fresnel_magnitudes_t7() -> None:
    gh, gv = fresnel_coefficients(PSI)
    co = reflection_coefficient(PSI, "circular_co")
    h = [0.9979, 0.9894, 0.9790, 0.9584, 0.8994, 0.8098, 0.5491, 0.4334, 0.3159]
    v = [0.9922, 0.9615, 0.9244, 0.8543, 0.6723, 0.4400, 0.0371, 0.1878, 0.3159]
    c = [0.9950, 0.9754, 0.9517, 0.9064, 0.7858, 0.6249, 0.2560, 0.1228, 0.0]
    np.testing.assert_allclose(np.abs(gh), h, atol=1e-4)
    np.testing.assert_allclose(np.abs(gv), v, atol=1e-4)
    np.testing.assert_allclose(np.abs(co), c, atol=1e-4)
    limit = (np.sqrt(3.7) - 1) / (np.sqrt(3.7) + 1)
    assert abs(gh[-1]) == pytest.approx(limit, abs=1e-4)


def test_sign_convention_matches_jpl226_eq_48_49() -> None:
    """JPL226 p. 20: R_par = +(e2 cos t - e1 cos i)/(...), R_perp = -(e2 cos i - e1 cos t)/(...), with
    eta2 = eta1/sqrt(eps) and Snell on the refractive indices (the source prints eps, a typo).
    The script convention is the opposite sign: R_JPL = -Gamma_script."""
    psi = np.radians(np.array(PSI, dtype=float))
    ti = np.pi / 2 - psi
    n = np.sqrt(EPS)
    ct = np.sqrt(1 - (np.sin(ti) / n) ** 2)
    ci = np.cos(ti)
    eta1, eta2 = 1.0, 1.0 / n
    r_par = (eta2 * ct - eta1 * ci) / (eta2 * ct + eta1 * ci)
    r_perp = -(eta2 * ci - eta1 * ct) / (eta2 * ci + eta1 * ct)
    gh, gv = fresnel_coefficients(PSI)
    np.testing.assert_allclose(r_perp, -gh, atol=1e-12)
    np.testing.assert_allclose(r_par, -gv, atol=1e-12)
    # circular co-polar vanishes at normal incidence (Gamma_h = -Gamma_v there)
    assert abs(gh[-1] + gv[-1]) < 1e-12


def test_brewster_vertical() -> None:
    _, gv = fresnel_coefficients([27.47])
    assert abs(gv[0]) < 0.01


def test_corrected_roughness_factor_t8() -> None:
    sigma = 0.25
    rows = [(0.5, 0.5543, 0.7445), (1.0, 0.0944, 0.3073), (2.0, 0.0001, 0.0089)]
    for psi, script, correct in rows:
        assert float(roughness_field_factor(psi, sigma, LAM)) == pytest.approx(correct, abs=5e-4)
        assert float(legacy_script_roughness_factor(psi, sigma, LAM)) == pytest.approx(
            script, abs=5e-4
        )
    # the legacy factor is the square of the corrected one (documented comparison)
    assert float(legacy_script_roughness_factor(1.0, sigma, LAM)) == pytest.approx(
        float(roughness_field_factor(1.0, sigma, LAM)) ** 2
    )


def _envelope(psi: float, rough_factor: float) -> tuple[float, float]:
    g = float(abs(fresnel_coefficients([psi])[0][0])) * rough_factor
    return float(20 * np.log10(1 - g)), float(20 * np.log10(1 + g))


def test_envelope_at_one_degree_corrected_vs_legacy() -> None:
    lo, hi = _envelope(1.0, float(roughness_field_factor(1.0, 0.25, LAM)))
    assert (lo, hi) == pytest.approx((-3.11, 2.28), abs=0.03)
    lo_s, hi_s = _envelope(1.0, float(legacy_script_roughness_factor(1.0, 0.25, LAM)))
    assert (lo_s, hi_s) == pytest.approx((-0.84, 0.77), abs=0.03)


def test_two_ray_gain_matches_t8_horizontal() -> None:
    psi = [0.05, 0.1, 0.2, 0.5, 1.0, 2.0]
    r = two_ray(psi, 2.0, LAM, polarization="horizontal", sigma_m=0.25)
    np.testing.assert_allclose(r.gain_db, [-4.38, 1.18, 5.28, -10.79, -2.91, -0.06], atol=0.02)
    assert r.applicable.all() and set(r.status) == {"ok"}
    np.testing.assert_allclose(r.specular_distance_m, [2292, 1146, 573, 229, 115, 57], rtol=0.01)


def test_specular_beyond_ridge_not_applicable() -> None:
    r = two_ray(
        [0.05, 0.5, 2.0, -1.0], 2.0, LAM, polarization="horizontal", ridge_distance_m=2000.0
    )
    assert list(r.applicable) == [False, True, True, False]
    assert r.status[0] == NOT_APPLICABLE and r.gain_db[0] == 0.0
    assert r.reason[0] == "specular point beyond the ridge" and r.reason[3] == "elevation <= 0"


def test_two_ray_validation() -> None:
    with pytest.raises(ValueError):
        two_ray([float("nan")], 2.0, LAM)
    with pytest.raises(ValueError):
        two_ray([1.0], 0.0, LAM)
    with pytest.raises(ValueError):
        reflection_coefficient([1.0], "diagonal")  # type: ignore[arg-type]


def test_numeric_angle_floor_does_not_move_the_specular_point() -> None:
    r = two_ray([0.01], 2.0, LAM, ridge_distance_m=5000.0)
    assert r.psi_used_deg[0] == 0.05
    assert r.specular_distance_m[0] == pytest.approx(11459.155786261179)
    assert not r.applicable[0]
    assert r.gain_db[0] == 0.0
    assert r.reason[0] == "specular point beyond the ridge"
    within = two_ray([0.01], 2.0, LAM, ridge_distance_m=20000.0)
    assert within.applicable[0]


def test_fade_depth_order_of_magnitude_against_jpl_42_243() -> None:
    """JPL IPN PR 42-243 (Sanchez Net 2025) says multipath fades can exceed 20 dB at low Earth elevation (S-band).

    Plausibility only: the report gives no plotted values, so the check is the order of magnitude. The depth depends on the
    unknown roughness: deep fades for smooth ground, about 10 dB with the JPL-script roughness of 0.25 m.
    """
    psi = np.linspace(0.5, 5.0, 4000)
    wavelength = 299792458.0 / 2.4e9
    smooth = two_ray(psi, 2.0, wavelength, polarization="circular_co", sigma_m=0.0).gain_db.min()
    rough = two_ray(psi, 2.0, wavelength, polarization="circular_co", sigma_m=0.25).gain_db.min()
    assert smooth < -20.0
    assert -15.0 < rough < -5.0
