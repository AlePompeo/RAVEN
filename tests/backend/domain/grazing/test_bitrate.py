# SPDX-License-Identifier: Apache-2.0
import numpy as np
import pytest

from backend.domain.grazing.bitrate import (
    DEFAULT_K_VALUES,
    DEFAULT_RATES_BPS,
    gaussian_outage_pct,
    margin_matrix,
    select_rates,
    tradeoff,
)

R = DEFAULT_RATES_BPS


def test_margin_matrix_matches_model_doc_t11() -> None:
    m = margin_matrix([38.70], 1e4, R)[0]
    np.testing.assert_allclose(m, [38.70, 33.93, 28.70, 23.93, 18.70, 13.93], atol=0.01)
    with pytest.raises(ValueError):
        margin_matrix([1.0], 0.0, R)
    with pytest.raises(ValueError):
        margin_matrix([1.0], 1e4, [])


def test_gaussian_reference_values() -> None:
    got = [gaussian_outage_pct(k) for k in DEFAULT_K_VALUES]
    np.testing.assert_allclose(got, [50.0, 15.87, 0.99, 0.135], atol=0.01)


def test_select_rates_rule() -> None:
    pred = margin_matrix([20.0, 3.0, -9.0], 1e4, R)  # margins at 1e4: 20, 3, -9
    idx = select_rates(pred, R, k=0.0, sigma_db=1.5)
    assert list(idx) == [4, 0, -1]  # 20 dB closes 1e6 exactly (20 - 20 = 0 >= 0)
    # backoff 2 sigma = 3 dB: the second step (3 dB) still closes 1e4 exactly
    assert list(select_rates(pred, R, 2.0, 1.5)) == [3, 0, -1]
    assert list(select_rates(pred, R, 2.1, 1.5)) == [3, -1, -1]
    with pytest.raises(ValueError):
        select_rates(pred, R, -1.0, 1.5)


def _sweep(n: int = 20000) -> np.ndarray:
    # margin at 1e5 sweeping through the threshold region (-8 ... +20 dB)
    return margin_matrix(np.linspace(-8.0, 20.0, n) + 10.0, 1e4, R)


def test_higher_k_fewer_outages_less_scheduled_data() -> None:
    pred = _sweep()
    rows = tradeoff(pred, pred, R, DEFAULT_K_VALUES, 1.5, 900.0, seed=3)
    out = [r.outages for r in rows]
    assert out == sorted(out, reverse=True) and out[0] > out[-1]
    sched = [r.scheduled_bits for r in rows]
    assert sched == sorted(sched, reverse=True) and sched[0] > sched[-1]
    assert rows[0].relative_data == pytest.approx(1.0)
    assert rows[-1].delivered_bits < rows[0].delivered_bits * 1.0001 or rows[-1].outages == 0
    for r in rows[1:]:  # never worse than the Gaussian bound (up to sampling noise)
        assert r.outage_pct <= r.gaussian_outage_pct + 0.4
    assert rows[0].outage_pct > 5.0


def test_seed_is_deterministic_and_matters() -> None:
    pred = _sweep(2000)
    a = tradeoff(pred, pred, R, (0.0,), 1.5, 900.0, seed=7)[0]
    b = tradeoff(pred, pred, R, (0.0,), 1.5, 900.0, seed=7)[0]
    c = tradeoff(pred, pred, R, (0.0,), 1.5, 900.0, seed=8)[0]
    assert a.outages == b.outages and a.delivered_bits == b.delivered_bits
    assert c.outages != a.outages


def test_model_error_in_truth_raises_outages() -> None:
    pred = _sweep(4000)
    ok = tradeoff(pred, pred, R, (2.33,), 1.5)[0]
    bad = tradeoff(pred, pred - 3.0, R, (2.33,), 1.5)[0]  # the real link is 3 dB worse
    assert bad.outages > ok.outages


def test_validation() -> None:
    p = _sweep(10)
    with pytest.raises(ValueError):
        tradeoff(p, p[:5], R)
    with pytest.raises(ValueError):
        tradeoff(p[:, :3], p[:, :3], R)
    bad = p.copy()
    bad[0, 0] = np.nan
    with pytest.raises(ValueError):
        tradeoff(bad, p, R)
