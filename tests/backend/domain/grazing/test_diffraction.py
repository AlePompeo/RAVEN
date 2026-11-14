# SPDX-License-Identifier: Apache-2.0
import numpy as np
import pytest

from backend.domain.grazing.diffraction import (
    NO_CORRECTION,
    fresnel_zone_radius_m,
    itu_knife_edge_db,
    knife_edge_loss_db,
    nu_from_angle,
    nu_from_geometry,
)
from backend.domain.lunar.link import SPEED_OF_LIGHT_M_S, fspl_db

LAM = SPEED_OF_LIGHT_M_S / 8.4e9


@pytest.mark.parametrize(
    ("nu", "db"),
    [(-1.0, -1.001), (0.0, 6.021), (1.0, 13.864), (2.4, 20.618), (-3.0, -0.444), (5.0, 26.936)],
)
def test_knife_edge_exact_model_doc_t1(nu: float, db: float) -> None:
    assert float(knife_edge_loss_db(nu)) == pytest.approx(db, abs=1e-3)


def test_knife_edge_asymptote() -> None:
    assert float(knife_edge_loss_db(10.0)) == pytest.approx(32.954, abs=1e-3)
    assert 13.0 + 20 * np.log10(2.4) == pytest.approx(20.604, abs=1e-3)


def test_itu_approximation_within_0123_db() -> None:
    nu = np.linspace(-0.7799, 5.0, 4000)
    err = np.abs(itu_knife_edge_db(nu) - knife_edge_loss_db(nu))
    assert err.max() <= 0.1235
    assert float(itu_knife_edge_db(-1.0)) == 0.0  # no oscillations below -0.78
    assert float(itu_knife_edge_db(2.4)) == pytest.approx(20.539, abs=1e-3)


def test_fspl_222_629() -> None:
    assert fspl_db(384_400.0, 8.4) == pytest.approx(222.629, abs=1e-3)


def test_fresnel_zone_table_t6() -> None:
    d2 = 384_400e3
    for d1, r in [(10, 0.597), (100, 1.889), (1000, 5.974), (2000, 8.449), (10_000, 18.891)]:
        assert float(fresnel_zone_radius_m(d1, d2, LAM)) == pytest.approx(r, abs=2e-3)
    assert float(fresnel_zone_radius_m(1000, 1000, LAM)) == pytest.approx(4.224, abs=2e-3)


def test_nu_sign_and_consistency() -> None:
    d1, d2 = 2000.0, 384_400e3
    r1 = float(fresnel_zone_radius_m(d1, d2, LAM))
    assert float(nu_from_geometry(r1, d1, d2, LAM)) == pytest.approx(np.sqrt(2.0), rel=1e-9)
    # 60 % rule: h = -0.6 r1 -> nu = -0.849, J = -0.374 dB (model doc 2.5)
    nu = float(nu_from_geometry(-0.6 * r1, d1, d2, LAM))
    assert nu == pytest.approx(-0.849, abs=1e-3)
    assert float(knife_edge_loss_db(nu)) == pytest.approx(-0.374, abs=2e-3)
    # angle form (model doc T3): el - th = -0.5 deg -> th above LOS by 0.5 deg
    nu_a = float(nu_from_angle(np.radians(0.5), d1, 1e12, LAM))
    assert nu_a == pytest.approx(2.922, abs=2e-3)
    assert float(knife_edge_loss_db(nu_a)) == pytest.approx(22.29, abs=0.02)
    assert float(nu_from_angle(np.radians(-0.5), d1, 1e12, LAM)) < 0


def test_invalid_arguments() -> None:
    with pytest.raises(ValueError):
        nu_from_geometry(1.0, 0.0, 10.0, LAM)
    with pytest.raises(ValueError):
        fresnel_zone_radius_m(1.0, 1.0, 0.0)


def test_rounded_ridge_stub_not_available() -> None:
    r = NO_CORRECTION.correction_db(1.0, 100.0)
    assert r.db == 0.0 and r.status == "not-available"
    with pytest.raises(ValueError):
        NO_CORRECTION.correction_db(float("nan"), 1.0)


# --- ITU-R P.526-9 (2005), checked on the text 2026-11-04 (docs/domain/validation.md, "Validazione radio") ---
# Independent re-implementation: C, S by numerical quadrature of sec. 2.7 eq. (7a)-(7b), not scipy.special.fresnel.


def _cs_quad(v: float) -> tuple[float, float]:
    from scipy.integrate import quad

    c = quad(lambda s: np.cos(np.pi * s * s / 2.0), 0.0, v, limit=400)[0]
    s = quad(lambda s: np.sin(np.pi * s * s / 2.0), 0.0, v, limit=400)[0]
    return c, s


@pytest.mark.parametrize("nu", [-2.0, -0.78, -0.3, 0.0, 0.5, 1.0, 2.4, 4.0])
def test_exact_knife_edge_equals_p526_eq26_by_quadrature(nu: float) -> None:
    c, s = _cs_quad(nu)
    j26 = -20.0 * np.log10(np.sqrt((1.0 - c - s) ** 2 + (c - s) ** 2) / 2.0)  # P.526-9 eq. (26)
    assert float(knife_edge_loss_db(nu)) == pytest.approx(j26, abs=1e-7)


@pytest.mark.parametrize("nu", [-0.7, 0.0, 1.0, 3.0])
def test_itu_approx_is_p526_eq27(nu: float) -> None:
    x = nu - 0.1
    assert float(itu_knife_edge_db(nu)) == pytest.approx(
        6.9 + 20.0 * np.log10(np.sqrt(x * x + 1.0) + x), abs=1e-12
    )


def test_nu_forms_p526_eq22_eq23_and_zone_eq2() -> None:
    lam, d1, d2, h = 0.0357, 2000.0, 5.0e4, 7.5
    nu22 = h * np.sqrt(2.0 / lam * (1.0 / d1 + 1.0 / d2))  # eq. (22)
    assert float(nu_from_geometry(h, d1, d2, lam)) == pytest.approx(nu22, rel=1e-12)
    theta = h / d1 + h / d2  # diffraction angle for small angles, sign of h
    nu23 = theta * np.sqrt(2.0 / (lam * (1.0 / d1 + 1.0 / d2)))  # eq. (23)
    assert float(nu_from_angle(theta, d1, d2, lam)) == pytest.approx(nu23, rel=1e-12)
    assert nu23 == pytest.approx(nu22, rel=1e-9)  # the two equivalent forms of sec. 4.1
    assert float(nu_from_geometry(-h, d1, d2, lam)) == pytest.approx(-nu22)  # h < 0 below the line
    r1 = np.sqrt(lam * d1 * d2 / (d1 + d2))  # eq. (2), n = 1
    assert float(fresnel_zone_radius_m(d1, d2, lam)) == pytest.approx(r1, rel=1e-12)
    assert nu22 == pytest.approx(np.sqrt(2.0) * h / r1, rel=1e-12)
