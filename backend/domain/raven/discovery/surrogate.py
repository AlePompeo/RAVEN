# SPDX-License-Identifier: Apache-2.0
"""A light statistical surrogate of the RAVEN core for the automatic site search: a "physics + residual" Gaussian process.

The mean is a ridge regression on the features derived from the overlays (the physical proxy: sunlight share, Earth share, both at once, gaps,
slope...); a Gaussian process on the residuals corrects it where the core has been evaluated and says how sure it is elsewhere. Intervals are
calibrated by split-conformal prediction on out-of-fold residuals that leave whole SPATIAL BLOCKS out (neighbouring cells are never in both the
training and the test part, otherwise the error looks smaller than it is). Pure numpy/scipy: nothing to install beyond the sky extra, a few
hundred training points, milliseconds per prediction. The surrogate only chooses where to look: every site shown to the user is re-evaluated by
the core.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray
from scipy.linalg import cho_factor, cho_solve

Arr = NDArray[np.float64]
RIDGE: Final = 1e-3
CHUNK: Final = 4000
LENGTH_SCALES: Final = (0.5, 1.0, 2.0, 4.0)
SIGNAL_SCALES: Final = (0.5, 1.0, 2.0)
NOISE_SCALES: Final = (0.01, 0.05, 0.2)


@dataclass(frozen=True)
class Fit:
    """A fitted surrogate for one target."""

    mu_x: Arr
    sd_x: Arr
    beta: Arr  # [intercept, weights...] of the linear mean, in standardised features
    train: Arr  # standardised training features
    alpha: Arr  # K^-1 residuals
    chol: tuple[Arr, bool]
    length: float
    signal: float
    noise: float
    resid_sd: float

    def predict(self, x: Arr) -> tuple[Arr, Arr]:
        """Mean and standard deviation (predictive, including the noise) at the rows of `x`."""
        z = (np.atleast_2d(x) - self.mu_x) / self.sd_x
        mean = np.empty(len(z))
        std = np.empty(len(z))
        for i in range(0, len(z), CHUNK):
            zc = z[i : i + CHUNK]
            k = _rbf(zc, self.train, self.length, self.signal)
            lin = self.beta[0] + zc @ self.beta[1:]
            mean[i : i + CHUNK] = lin + k @ self.alpha
            v = cho_solve(self.chol, k.T)
            var = self.signal - np.einsum("ij,ji->i", k, v) + self.noise
            std[i : i + CHUNK] = np.sqrt(np.maximum(var, 1e-12))
        return mean, std


def _rbf(a: Arr, b: Arr, length: float, signal: float) -> Arr:
    d2 = (a * a).sum(1)[:, None] + (b * b).sum(1)[None, :] - 2.0 * a @ b.T
    return np.asarray(signal * np.exp(-0.5 * np.maximum(d2, 0.0) / (length * length)))


def fit(x: Arr, y: Arr) -> Fit:
    """Fit the surrogate. `x` is (n, d), `y` is (n,). Needs at least 8 points and finite values."""
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    if x.ndim != 2 or y.shape != (len(x),) or len(x) < 8:
        raise ValueError("need at least 8 points: x (n, d) and y (n,)")
    if not (np.isfinite(x).all() and np.isfinite(y).all()):
        raise ValueError("non-finite training data")
    mu, sd = x.mean(0), x.std(0)
    sd = np.where(sd > 1e-12, sd, 1.0)
    z = (x - mu) / sd
    design = np.hstack([np.ones((len(z), 1)), z])
    reg = RIDGE * len(z) * np.eye(design.shape[1])
    reg[0, 0] = 0.0
    beta = np.linalg.solve(design.T @ design + reg, design.T @ y)
    r = y - design @ beta
    var_r = max(float(r.var()), 1e-10)
    d = z.shape[1]
    best: tuple[float, float, float, float] | None = None
    for ls in LENGTH_SCALES:
        length = ls * math.sqrt(d)
        for sig in SIGNAL_SCALES:
            for noi in NOISE_SCALES:
                signal, noise = sig * var_r, noi * var_r
                k = _rbf(z, z, length, signal) + noise * np.eye(len(z))
                try:
                    c = cho_factor(k, lower=True)
                except np.linalg.LinAlgError:
                    continue
                a = cho_solve(c, r)
                ll = -0.5 * float(r @ a) - float(np.log(np.diag(c[0])).sum())
                if best is None or ll > best[0]:
                    best = (ll, length, signal, noise)
    if best is None:
        raise ValueError("the covariance matrix is not positive definite for any setting")
    _ll, length, signal, noise = best
    k = _rbf(z, z, length, signal) + noise * np.eye(len(z))
    chol = cho_factor(k, lower=True)
    return Fit(mu, sd, beta, z, cho_solve(chol, r), chol, length, signal, noise, math.sqrt(var_r))


def spatial_blocks(lat: Arr, lon: Arr, k: int) -> NDArray[np.int64]:
    """Block label (0..k-1) of every point: k sectors of longitude, so that the folds are compact regions, not random cells."""
    ang = np.mod(np.asarray(lon, dtype=np.float64), 360.0)
    return np.minimum((ang / 360.0 * k).astype(np.int64), k - 1)


def conformal_quantile(z_abs: Arr, alpha: float) -> float:
    """Split-conformal quantile of the normalised absolute residuals for a (1 - alpha) interval."""
    n = len(z_abs)
    if n == 0:
        return math.inf
    level = min(1.0, math.ceil((n + 1) * (1.0 - alpha)) / n)
    return float(np.quantile(z_abs, level, method="higher"))


@dataclass(frozen=True)
class Calibrated:
    fit: Fit
    q: float  # interval = mean +- q * std
    alpha: float
    n_oof: int

    def predict(self, x: Arr) -> tuple[Arr, Arr, Arr]:
        """Mean, standard deviation and the half width of the (1 - alpha) interval."""
        mean, std = self.fit.predict(x)
        return mean, std, self.q * std


def _oof_z(x: Arr, y: Arr, groups: NDArray[np.int64]) -> list[float]:
    """Normalised absolute residuals of the cells of each group predicted by a surrogate trained without that group."""
    out: list[float] = []
    for g in np.unique(groups):
        test = groups == g
        train = ~test
        if test.sum() == 0 or train.sum() < 8:
            continue
        mean, std = fit(x[train], y[train]).predict(x[test])
        out.extend((np.abs(y[test] - mean) / std).tolist())
    return out


def fit_calibrated(
    x: Arr, y: Arr, blocks: NDArray[np.int64], alpha: float = 0.1, seed: int = 0, folds: int = 6
) -> Calibrated:
    """Fit on all the points and calibrate the interval on out-of-fold residuals in TWO regimes and keep the stricter quantile: leaving whole
    spatial blocks out (extrapolating into a region not sampled) and leaving random cells out (interpolating between sampled cells). The
    normalised residuals differ between the two (a missing neighbourhood already inflates the predictive deviation), so either alone
    can under-cover the other case. With fewer than two blocks (or too few points left to train) the interval is infinite: the surrogate
    says it does not know."""
    full = fit(x, y)
    z_block = _oof_z(x, y, blocks) if len(np.unique(blocks)) >= 2 else []
    rng = np.random.default_rng(seed)
    z_rand = _oof_z(x, y, rng.integers(0, folds, len(x)).astype(np.int64))
    if not z_block or not z_rand:
        return Calibrated(full, math.inf, alpha, 0)
    q = max(
        conformal_quantile(np.asarray(z_block), alpha),
        conformal_quantile(np.asarray(z_rand), alpha),
    )
    return Calibrated(full, q, alpha, len(z_block) + len(z_rand))
