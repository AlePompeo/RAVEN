# SPDX-License-Identifier: Apache-2.0
"""Run-length helpers on boolean time series."""

import numpy as np
from numpy.typing import NDArray

__all__ = ["longest_run", "n_runs", "run_lengths"]


def run_lengths(mask: NDArray[np.bool_], value: bool = True) -> list[int]:
    """Lengths (in steps) of the maximal runs of `value` in `mask`."""
    m = np.asarray(mask, dtype=bool)
    if not value:
        m = ~m
    if m.size == 0:
        return []
    padded = np.concatenate(([False], m, [False]))
    d = np.diff(padded.astype(np.int8))
    starts = np.flatnonzero(d == 1)
    ends = np.flatnonzero(d == -1)
    return [int(x) for x in ends - starts]


def longest_run(mask: NDArray[np.bool_], value: bool = True) -> int:
    runs = run_lengths(mask, value)
    return max(runs) if runs else 0


def n_runs(mask: NDArray[np.bool_], value: bool = True) -> int:
    return len(run_lengths(mask, value))
