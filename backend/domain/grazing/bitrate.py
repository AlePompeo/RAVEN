# SPDX-License-Identifier: Apache-2.0
"""Bit-rate compensator: feedforward + statistical margin (NOT reinforcement learning).

Rule (docs/domain/grazinglink-model.md, sec. 2.11, from `compensation_demo.py` part B):

    R_b*(t) = max { R_b in RATES : M_pred(t, R_b) - k sigma >= 0 }
    outage  = M_true(t, R_b*) < 0 ,   M_true = M_base_true(t, R_b*) + N(0, sigma)
    delivered data = sum over non-outage declared steps of R_b* x dt

For a purely Gaussian error the outage probability per declared step is Phi(-k): 50 %, 15.9 %, 0.99 %,
0.13 % for k = 0, 1, 2.33, 3 (`gaussian_outage_pct`). The simulated percentages are lower when most
steps have a margin of tens of dB (the error only matters near the threshold).

Differences from the script: ONE noise vector is drawn per run and shared by all k (common random
numbers: the comparison between k values is then monotone and reproducible), and the generator is a
local seeded `numpy.random.Generator` (the script shares a global one with part A, so its numbers
depend on the call order). All rates, k, sigma are tag I (illustrative).
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import ArrayLike, NDArray

__all__ = [
    "DEFAULT_K_VALUES",
    "DEFAULT_RATES_BPS",
    "DEFAULT_SIGMA_DB",
    "TradeoffRow",
    "gaussian_outage_pct",
    "margin_matrix",
    "select_rates",
    "tradeoff",
]

Arr = NDArray[np.float64]
DEFAULT_RATES_BPS = (1e4, 3e4, 1e5, 3e5, 1e6, 3e6)  # bozza 3.D, tag I
DEFAULT_K_VALUES = (0.0, 1.0, 2.33, 3.0)  # Phi(-2.33) = 0.99 %
DEFAULT_SIGMA_DB = 1.5  # unmodelled error, tag I


def margin_matrix(
    margin_ref_db: ArrayLike, reference_rate_bps: float, rates_bps: Sequence[float]
) -> Arr:
    """Margin [n_steps, n_rates]: M(R_b) = M(R_ref) - 10 log10(R_b / R_ref)."""
    m = np.asarray(margin_ref_db, dtype=np.float64)
    r = np.asarray(rates_bps, dtype=np.float64)
    if m.ndim != 1 or reference_rate_bps <= 0 or r.size == 0 or np.any(r <= 0):
        raise ValueError("invalid margin series or rates")
    return np.asarray(m[:, None] - 10.0 * np.log10(r[None, :] / reference_rate_bps))


def select_rates(pred_db: Arr, rates_bps: Sequence[float], k: float, sigma_db: float) -> Any:
    """Index of the highest rate with `pred - k sigma >= 0` per step; -1 where none closes (outage-free skip)."""
    if k < 0 or sigma_db < 0 or not (math.isfinite(k) and math.isfinite(sigma_db)):
        raise ValueError("k and sigma must be finite and >= 0")
    rates = np.asarray(rates_bps, dtype=np.float64)
    ok = pred_db - k * sigma_db >= 0.0
    score = np.where(ok, rates[None, :], -np.inf)
    best = np.argmax(score, axis=1)
    return np.where(ok.any(axis=1), best, -1)


def gaussian_outage_pct(k: float) -> float:
    """Phi(-k) in percent: the outage rate of a purely Gaussian error with the k sigma backoff."""
    return 50.0 * math.erfc(k / math.sqrt(2.0))


@dataclass(frozen=True)
class TradeoffRow:
    k: float
    backoff_db: float
    declared_steps: int
    outages: int
    outage_pct: float  # of declared steps
    gaussian_outage_pct: float
    scheduled_bits: float  # what the compensator commits: sum of chosen rates x dt
    delivered_bits: float  # same, minus the outage steps
    relative_data: float | None  # delivered / delivered of the first k (None when that is 0)
    mean_rate_bps: float  # over declared steps
    chosen_rate_index: Any  # per step, -1 = link not declared

    def to_dict(self, include_series: bool = False) -> dict[str, Any]:
        d: dict[str, Any] = {
            "k": self.k,
            "backoff_db": self.backoff_db,
            "declared_steps": self.declared_steps,
            "outages": self.outages,
            "outage_pct": round(self.outage_pct, 3),
            "gaussian_outage_pct": round(self.gaussian_outage_pct, 3),
            "scheduled_bits": self.scheduled_bits,
            "delivered_bits": self.delivered_bits,
            "relative_data": None if self.relative_data is None else round(self.relative_data, 4),
            "mean_rate_bps": self.mean_rate_bps,
        }
        if include_series:
            d["chosen_rate_index"] = [int(v) for v in self.chosen_rate_index]
        return d


def tradeoff(
    pred_db: Arr,
    truth_base_db: Arr,
    rates_bps: Sequence[float],
    k_values: Sequence[float] = DEFAULT_K_VALUES,
    sigma_db: float = DEFAULT_SIGMA_DB,
    step_s: float = 900.0,
    seed: int = 3,
) -> list[TradeoffRow]:
    """Outage % versus delivered data for each k on given predicted / 'true base' margin matrices.

    `truth_base_db` is the margin the link really has before the unmodelled Gaussian error
    N(0, sigma); `pred_db` is what the compensator sees. Both are [n_steps, n_rates].
    """
    if pred_db.shape != truth_base_db.shape or pred_db.ndim != 2:
        raise ValueError("pred and truth must be [n_steps, n_rates] of the same shape")
    if pred_db.shape[1] != len(rates_bps) or step_s <= 0:
        raise ValueError("rates do not match the margin matrices")
    if not (np.all(np.isfinite(pred_db)) and np.all(np.isfinite(truth_base_db))):
        raise ValueError("non-finite margin")
    rates = np.asarray(rates_bps, dtype=np.float64)
    noise = np.random.default_rng(seed).normal(0.0, sigma_db, pred_db.shape[0])
    rows: list[TradeoffRow] = []
    ref: float | None = None
    for k in k_values:
        idx = select_rates(pred_db, rates_bps, k, sigma_db)
        declared = idx >= 0
        safe = np.where(declared, idx, 0)
        true_m = truth_base_db[np.arange(len(idx)), safe] + noise
        out = declared & (true_m < 0.0)
        rate = np.where(declared, rates[safe], 0.0)
        delivered = float(np.sum(np.where(declared & ~out, rate, 0.0)) * step_s)
        if ref is None:
            ref = delivered
        n_dec = int(declared.sum())
        rows.append(
            TradeoffRow(
                k=float(k),
                backoff_db=float(k) * sigma_db,
                declared_steps=n_dec,
                outages=int(out.sum()),
                outage_pct=100.0 * float(out.sum()) / max(n_dec, 1),
                gaussian_outage_pct=gaussian_outage_pct(float(k)),
                scheduled_bits=float(rate.sum() * step_s),
                delivered_bits=delivered,
                relative_data=delivered / ref if ref else None,
                mean_rate_bps=float(rate.sum() / n_dec) if n_dec else 0.0,
                chosen_rate_index=idx,
            )
        )
    return rows
