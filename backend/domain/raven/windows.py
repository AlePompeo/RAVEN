# SPDX-License-Identifier: Apache-2.0
"""Window edges refined by bisection (docs/domain/raven-model.md, 2.10; migration step M9).

The chain samples a fixed grid, so a window edge found on the grid has the resolution of the step.
Here each edge is refined to `tol_s` (default 1 s) by bisection of a criterion evaluated at an
exact instant (the pipeline provides it from S1-S3, S5 and S6 at one instant).

Assumption, stated: inside one step the criterion changes at most once (monotone between two
samples). A narrower feature than the step (two edges inside one step) is not seen by the grid and
cannot be recovered by this refinement. An edge next to an unknown step is not refined: it stays
at the step boundary and is flagged unresolved. Never an unknown instant counted as inside.
"""

from collections.abc import Callable, Sequence
from typing import Any

from backend.domain.raven.known import Known

__all__ = ["Predicate", "find_windows", "refine_edge"]

Predicate = Callable[[float], Known[bool]]


def refine_edge(
    pred: Predicate, t_known: float, t_other: float, tol_s: float = 1.0
) -> tuple[float, bool]:
    """Bisect the instant where `pred` changes between `t_known` and `t_other`.

    `pred(t_known)` must be known and differ from `pred(t_other)`. Returns (edge_unix, resolved):
    the edge lies within `tol_s` of the returned value when resolved; if the predicate is unknown at
    a midpoint, the bracket stops there and `resolved` is False.
    """
    if tol_s <= 0:
        raise ValueError("tolerance must be positive")
    a, b = t_known, t_other
    va = pred(a)
    if va is None:
        return (a + b) / 2.0, False
    while abs(b - a) > tol_s:
        m = (a + b) / 2.0
        vm = pred(m)
        if vm is None:
            return m, False
        if vm == va:
            a = m
        else:
            b = m
    return (a + b) / 2.0, True


def find_windows(
    t_unix: Sequence[float],
    flags: Sequence[Known[bool]],
    step_s: float,
    pred: Predicate | None = None,
    tol_s: float = 1.0,
) -> list[dict[str, Any]]:
    """Maximal runs of known True flags as windows, with edges refined by `pred` when given.

    A window touching the first or last sample is `open_start` / `open_end` (it may continue outside
    the grid). Edges next to an unknown step are `*_resolved: False` (not refined).
    """
    n = len(flags)
    out: list[dict[str, Any]] = []
    i = 0
    while i < n:
        if flags[i] is not True:
            i += 1
            continue
        j = i
        while j + 1 < n and flags[j + 1] is True:
            j += 1
        start, start_ok = float(t_unix[i]), True
        end, end_ok = float(t_unix[j]) + step_s, True
        open_start, open_end = i == 0, j == n - 1
        if not open_start:
            if flags[i - 1] is False and pred is not None:
                start, start_ok = refine_edge(pred, float(t_unix[i]), float(t_unix[i - 1]), tol_s)
            else:
                start_ok = False
        if not open_end:
            if flags[j + 1] is False and pred is not None:
                end, end_ok = refine_edge(pred, float(t_unix[j]), float(t_unix[j + 1]), tol_s)
            else:
                end_ok = False
        out.append(
            {
                "start_unix": start,
                "end_unix": end,
                "start_resolved": start_ok and not open_start,
                "end_resolved": end_ok and not open_end,
                "open_start": open_start,
                "open_end": open_end,
                "tolerance_s": tol_s,
                "first_sample": i,
                "last_sample": j,
            }
        )
        i = j + 1
    return out
