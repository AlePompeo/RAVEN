# SPDX-License-Identifier: Apache-2.0
import math

import numpy as np
import pytest

from backend.domain.raven.discovery import surrogate as sg


def _world(n: int, seed: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Cells on a disc with features and a target that is a smooth physical trend plus a local bump the linear mean cannot see."""
    rng = np.random.default_rng(seed)
    lat = rng.uniform(-90, -75, n)
    lon = rng.uniform(0, 360, n)
    sun = np.clip(0.5 + 0.4 * np.sin(np.radians(lon) * 2) + rng.normal(0, 0.05, n), 0, 1)
    slope = rng.uniform(0, 15, n)
    x = np.column_stack([lat, np.sin(np.radians(lon)), np.cos(np.radians(lon)), sun, slope])
    y = (
        0.8 * sun
        - 0.01 * slope
        + 0.15 * np.exp(-((lat + 85) ** 2) / 4.0) * np.cos(np.radians(lon))
        + rng.normal(0, 0.02, n)
    )
    return x, y, lat, lon


def test_the_surrogate_learns_the_trend_and_the_bump_on_unseen_cells() -> None:
    x, y, _la, _lo = _world(300, 1)
    xt, yt, _la2, _lo2 = _world(1500, 2)
    f = sg.fit(x, y)
    mean, std = f.predict(xt)
    rmse = float(np.sqrt(np.mean((mean - yt) ** 2)))
    assert rmse < 0.05  # the noise of the world is 0.02 and its spread is about 0.3
    lin_only = np.hstack([np.ones((len(x), 1)), (x - f.mu_x) / f.sd_x]) @ f.beta
    assert rmse < float(
        np.sqrt(np.mean((lin_only[:1] * 0 + 0.3 - yt) ** 2))
    )  # far better than the average
    assert np.all(std > 0) and np.all(np.isfinite(mean))


def test_intervals_cover_unseen_spatial_blocks_close_to_the_nominal_level() -> None:
    x, y, lat, lon = _world(400, 3)
    blocks = sg.spatial_blocks(lat, lon, 6)
    cal = sg.fit_calibrated(x, y, blocks, alpha=0.1)
    xt, yt, _la, _lo = _world(2000, 4)
    mean, _std, half = cal.predict(xt)
    coverage = float(np.mean(np.abs(yt - mean) <= half))
    assert 0.83 <= coverage <= 0.99, coverage
    assert cal.n_oof == 800  # 400 left out by spatial block and 400 left out at random


def test_uncertainty_grows_away_from_the_data() -> None:
    x, y, _la, _lo = _world(200, 5)
    f = sg.fit(x, y)
    near = x[:50]
    far = near.copy()
    far[:, 0] -= 40.0  # 40 degrees south of anything seen
    far[:, 4] += 30.0
    assert sg.fit(x, y).predict(far)[1].mean() > 1.5 * f.predict(near)[1].mean()


def test_one_block_or_too_few_points_say_i_do_not_know() -> None:
    x, y, _lat, _lon = _world(60, 6)
    cal = sg.fit_calibrated(x, y, np.zeros(len(x), dtype=np.int64))
    assert math.isinf(cal.q) and cal.n_oof == 0
    with pytest.raises(ValueError):
        sg.fit(x[:5], y[:5])
    bad = x.copy()
    bad[0, 0] = np.nan
    with pytest.raises(ValueError):
        sg.fit(bad, y)


def test_the_fit_is_deterministic() -> None:
    x, y, _la, _lo = _world(120, 7)
    a = sg.fit(x, y).predict(x[:10])[0]
    b = sg.fit(x, y).predict(x[:10])[0]
    assert np.array_equal(a, b)


def test_spatial_blocks_are_compact_longitude_sectors() -> None:
    lon = np.array([0.0, 59.9, 60.0, 119.0, 359.9, 360.0, -1.0])
    assert sg.spatial_blocks(np.zeros(7), lon, 6).tolist() == [0, 0, 1, 1, 5, 0, 5]
    assert math.isinf(sg.conformal_quantile(np.array([]), 0.1))


def test_intervals_hold_when_a_whole_region_was_never_sampled() -> None:
    x, y, lat, lon = _world(600, 8)
    held = (lon >= 0) & (lon < 60)  # one sector of longitude is never in the training data
    cal = sg.fit_calibrated(
        x[~held], y[~held], sg.spatial_blocks(lat[~held], lon[~held], 6), alpha=0.1
    )
    mean, _std, half = cal.predict(x[held])
    coverage = float(np.mean(np.abs(y[held] - mean) <= half))
    assert coverage >= 0.8, coverage
