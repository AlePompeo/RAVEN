# SPDX-License-Identifier: Apache-2.0
import hashlib
import json
import math

import numpy as np
import pytest

from backend.domain.grazing.compensation import (
    TABLE_PATH,
    TableCorrection,
    consistency_diagnostic,
    default_correction,
    load_table,
    p526_rounded_term_db,
    ridge_correction,
    table_correction,
)
from backend.domain.grazing.diffraction import NO_CORRECTION
from scripts import gen_compensation_table as gen

TB = load_table()


def test_regenerated_subset_matches_stored_simulation() -> None:
    radii = (0, 50, 400)
    nus = gen.NUS[::9]
    sim = gen.simulate_residuals(radii, nus)
    for i, r in enumerate(radii):
        k = list(TB.radius_m).index(r)
        cols = [list(np.round(TB.nu, 2)).index(round(float(v), 2)) for v in nus]
        np.testing.assert_allclose(sim[i], TB.simulated_db[k, cols], atol=2e-3)


def test_provenance_and_script_hash() -> None:
    raw = json.loads(TABLE_PATH.read_text(encoding="utf-8"))
    p = raw["provenance"]
    assert p["generator_sha256"] == hashlib.sha256(gen.HERE.read_bytes()).hexdigest(), (
        "generator changed: regenerate the table (scripts/gen_compensation_table.py)"
    )
    assert p["seed"] == 3 and p["parameters"]["mad_k"] == 4.0
    for lib in ("python", "numpy", "scipy", "scikit-learn"):
        assert p["libraries"][lib]
    assert p["generated_utc"] and raw["version"] == TB.version
    assert len(TB.file_sha256) == 64 and TB.info()["status"] == "simulata, non validata"


def test_table_matches_model_doc_numbers() -> None:
    # docs/domain/grazinglink-model.md sec. 6: residual per radius (mean / max)
    mx = {r: float(TB.simulated_db[k].max()) for k, r in enumerate(TB.radius_m)}
    assert mx[0.0] == pytest.approx(0.07, abs=0.02)
    assert mx[400.0] == pytest.approx(2.43, abs=0.02)
    assert float(TB.simulated_db[-1].mean()) == pytest.approx(0.88, abs=0.02)
    assert TB.validation["anomalies"] == 18 and TB.validation["anomalies_nu_lt_m078"] == 12
    assert TB.validation["missing_cells"] == 182
    assert TB.anomaly.sum() == 18


def test_nodes_are_reproduced_and_interpolation_is_bounded() -> None:
    k, j = 7, int(np.argmin(np.abs(TB.nu - 2.0)))
    c, _u, _a, clamped = table_correction(2.0, 400.0, TB)
    assert float(c) == pytest.approx(TB.correction_db[k, j], abs=1e-9) and not clamped
    a = TB.correction_db[k, j]
    b = TB.correction_db[k, j + 1]
    c2, *_ = table_correction(2.0 + 0.025, 400.0, TB)
    assert min(a, b) - 1e-9 <= float(c2) <= max(a, b) + 1e-9
    c3, *_ = table_correction(2.0, 70.0, TB)
    lo, hi = sorted((TB.correction_db[4, j], TB.correction_db[5, j]))
    assert lo - 1e-9 <= float(c3) <= hi + 1e-9


def test_correction_grows_with_radius_in_the_smooth_region() -> None:
    vals = [float(table_correction(2.0, r, TB)[0]) for r in (20, 50, 100, 200, 400)]
    assert vals == sorted(vals) and vals[-1] > 1.0
    # small radii: the simulated residual is slightly NEGATIVE (R = 5, 10 m), not hidden
    assert float(table_correction(2.0, 5.0, TB)[0]) < 0.0


def test_clamping_is_flagged_and_uncertain() -> None:
    c, u, _a, k = table_correction([5.0, -4.0, 2.0], [100.0, 100.0, 5000.0], TB)
    assert k.all()
    assert np.all(u >= np.abs(c) - 1e-12)
    _c, _u, _a, k2 = table_correction(0.0, 400.0, TB)
    assert not k2


@pytest.mark.parametrize(
    ("nu", "r"), [(math.nan, 10.0), (1.0, math.nan), (1.0, -1.0), (math.inf, 5.0)]
)
def test_invalid_inputs_raise(nu: float, r: float) -> None:
    with pytest.raises(ValueError):
        table_correction(nu, r, TB)
    with pytest.raises(ValueError):
        TableCorrection(TB).correction_db(nu, r)


def test_oscillations_are_uncertainty_not_correction() -> None:
    m = TB.nu < -0.78
    env = TB.envelope_db
    # measured amplitude of the wiggles of the RESIDUAL below nu = -0.78 (small: <= 0.02 dB), larger
    # than in the smooth region, and reported as uncertainty
    assert 0.005 < env[:, m].max() < 0.05
    assert env[:, ~m].max() < env[:, m].max() / 2
    sim, corr = TB.simulated_db[:, m], TB.correction_db[:, m]
    assert np.abs(np.diff(corr, axis=1)).max() < np.abs(np.diff(sim, axis=1)).max()
    assert TB.anomaly[:, m].sum() == 12


def test_protocol_implementation() -> None:
    corr = default_correction()
    res = corr.correction_db(1.0, 100.0)
    assert res.status == "table" and res.db > 0 and res.uncertainty_db >= 0
    assert NO_CORRECTION.correction_db(1.0, 100.0).status == "not-available"


def test_inconsistency_is_quantified_not_hidden() -> None:
    # model doc T4: P.526-9 T at d1 = 2000 m, R = 400 m, nu = 2 -> 3.00 dB; split-step 1.63 dB
    t = float(p526_rounded_term_db(2.0, 400.0, 2000.0, 1e12, 0.0357))
    assert t == pytest.approx(3.0, abs=0.01)
    assert float(table_correction(2.0, 400.0, TB)[0]) == pytest.approx(1.63, abs=0.02)
    d = consistency_diagnostic(TB)
    assert d["jpl226_claim_db"] == 0.0 and d["table_max_db"] == pytest.approx(2.43, abs=0.02)
    assert d["p526_max_db"] > d["table_max_db"]
    assert 0.2 < d["ratio_table_over_p526_min"] <= d["ratio_table_over_p526_max"] < 0.65
    assert d["p526_max_db"] == pytest.approx(4.223, abs=0.01)  # model doc T4, R=400 nu=3
    assert d["splitstep_converged"] is False and "ITU-R P.526-9" in d["policy"]


def _t_p526(nu: float, r: float, d1: float, d2: float, lam: float) -> float:
    """Independent re-implementation of ITU-R P.526-9 sec. 4.2 eq. (22), (30a)-(32), scalar math only."""
    h = nu / math.sqrt(2.0 / lam * (1.0 / d1 + 1.0 / d2))  # eq. (22) solved for h
    m = r * ((d1 + d2) / (d1 * d2)) / (math.pi * r / lam) ** (1.0 / 3.0)  # eq. (31)
    n = h * (math.pi * r / lam) ** (2.0 / 3.0) / r  # eq. (32)
    if m * n <= 4.0:  # eq. (30a)
        return 7.2 * m**0.5 - (2.0 - 12.5 * n) * m + 3.6 * m**1.5 - 0.8 * m**2
    return (
        -6.0
        - 20.0 * math.log10(m * n)
        + 7.2 * m**0.5
        - (2.0 - 17.0 * n) * m
        + 3.6 * m**1.5
        - 0.8 * m**2
    )


@pytest.mark.parametrize(
    ("nu", "r", "d1", "d2"),
    [
        (0.0, 50.0, 2000.0, 1e12),
        (1.0, 400.0, 2000.0, 1e12),
        (3.0, 400.0, 300.0, 3.8e8),
        (8.0, 2000.0, 500.0, 1e12),
        (2.0, 100.0, 5000.0, 2.0e4),
        (-0.5, 200.0, 2000.0, 1e12),
    ],
)
def test_p526_term_matches_independent_formula(nu: float, r: float, d1: float, d2: float) -> None:
    got = float(p526_rounded_term_db(nu, r, d1, d2, 0.0357))
    assert got == pytest.approx(_t_p526(nu, r, d1, d2, 0.0357), abs=1e-9)


def test_p526_term_limits() -> None:
    # sec. 4.2: "as R tends to zero, T(m,n) also tend to zero"
    assert float(p526_rounded_term_db(2.0, 0.0, 2000.0, 1e12, 0.0357)) == 0.0
    assert float(p526_rounded_term_db(2.0, 1e-4, 2000.0, 1e12, 0.0357)) < 0.05
    # distant Earth: T converges to a non-zero value (m -> R / (d1 (pi R / lambda)^(1/3)))
    far = float(p526_rounded_term_db(3.0, 400.0, 2000.0, 1e12, 0.0357))
    moon = float(p526_rounded_term_db(3.0, 400.0, 2000.0, 3.844e8, 0.0357))
    assert far == pytest.approx(moon, abs=1e-4) and far > 4.0


def test_policy_itu_default_split_step_as_band() -> None:
    nus = np.array([-1.0, 0.0, 1.0, 3.0, 5.0])
    c, u, _a, k, s = ridge_correction(nus, 400.0, 2000.0, 0.0357, table=TB)
    t = p526_rounded_term_db(nus, 400.0, 2000.0, 1e12, 0.0357)
    assert np.allclose(c, np.maximum(t, 0.0))
    assert np.allclose(s, table_correction(nus, 400.0, TB)[0])
    assert np.all(u >= np.abs(c - s) - 1e-12) and np.all(c >= 0.0)
    assert bool(k[-1]) and not bool(
        k[2]
    )  # nu = 5 outside the comparison grid: flagged, ITU still applies
    z = ridge_correction(1.0, 0.0, 2000.0, 0.0357, table=TB)
    assert float(z[0]) == 0.0  # knife edge
