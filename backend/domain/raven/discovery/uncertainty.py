# SPDX-License-Identifier: Apache-2.0
"""Propagation of the uncertainty of the illustrative parameters (tag I) into the probability that a proposed site meets the objectives.

The core is deterministic for one parameter set: the same site can meet the objectives with a panel of 1 m2 and fail with 0.7 m2. The
parameters the user did not set (array area, battery, loads, antenna gain, losses) are illustrative, so their spread is an ASSUMPTION
(`SPREADS`, tag I, documented below), not a measurement. Scrambled-Sobol samples over those spreads are evaluated by the core, and the answer
is the share of samples that meet the objectives, with a Wilson interval for the finite number of samples, plus which parameter moves the
outcome most. With the user's own values for a parameter, that parameter is fixed and drops out of the draw.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray
from scipy.stats import qmc

Arr = NDArray[np.float64]
Z90: Final = 1.645


@dataclass(frozen=True)
class Spread:
    group: str  # "energy" or "rf": which override dictionary the parameter belongs to
    name: str
    kind: str  # "rel": default x [1 - w, 1 + w]; "abs": default + [-w, +w]
    width: float
    why: str


# ASSUMPTIONS (tag I): the parameters are illustrative placeholders of a mission that is not specified, so the spread is wide on purpose.
SPREADS: Final = (
    Spread("energy", "array_area_m2", "rel", 0.30, "solar array sized for an unspecified lander"),
    Spread("energy", "battery_capacity_wh", "rel", 0.30, "battery sized for an unspecified lander"),
    Spread("energy", "active_load_w", "rel", 0.30, "operating load of an unspecified payload"),
    Spread("energy", "comms_duty", "rel", 0.30, "share of the active time spent transmitting"),
    Spread(
        "rf",
        "tx_gain_dbi",
        "abs",
        2.0,
        "transmit antenna gain and pointing of an unspecified lander",
    ),
    Spread("rf", "misc_loss_db", "abs", 1.0, "miscellaneous link losses"),
)


def sample(
    defaults: dict[str, dict[str, float]],
    n: int,
    seed: int = 0,
    fixed: frozenset[str] = frozenset(),
) -> list[dict[str, dict[str, float]]]:
    """`n` parameter sets: scrambled Sobol points over the spreads of the parameters that are not `fixed`. Deterministic for a seed.
    `defaults` maps "energy"/"rf" to their default values; a parameter missing from it is left out (it cannot be varied)."""
    free = [s for s in SPREADS if s.name not in fixed and s.name in defaults.get(s.group, {})]
    if not free or n <= 0:
        return [{"energy": {}, "rf": {}} for _ in range(max(n, 0))]
    m = max(
        1, math.ceil(math.log2(n))
    )  # Sobol points keep their balance for a power of two: draw 2**m and keep the first n
    pts = qmc.Sobol(d=len(free), scramble=True, seed=seed).random_base2(m)[:n]
    out: list[dict[str, dict[str, float]]] = []
    for row in pts:
        d: dict[str, dict[str, float]] = {"energy": {}, "rf": {}}
        for u, s in zip(row, free, strict=True):
            base = defaults[s.group][s.name]
            lo, hi = (
                (base * (1 - s.width), base * (1 + s.width))
                if s.kind == "rel"
                else (base - s.width, base + s.width)
            )
            d[s.group][s.name] = float(lo + u * (hi - lo))
        out.append(d)
    return out


def wilson(k: int, n: int, z: float = Z90) -> tuple[float, float]:
    """Wilson score interval of a proportion (90 % by default): the uncertainty of the share because the samples are few."""
    if n <= 0:
        return 0.0, 1.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return min(p, max(0.0, c - h)), max(
        p, min(1.0, c + h)
    )  # rounding must not put the estimate outside its own interval


@dataclass(frozen=True)
class Summary:
    n: int  # samples that the core could evaluate
    p_meet: float | None  # None when no sample could be evaluated, or no objective was set
    p_low: float | None
    p_high: float | None
    drivers: list[
        tuple[str, float]
    ]  # parameter, correlation with the margin (indicative: few samples)


def summarise(
    params: list[dict[str, dict[str, float]]],
    outcomes: list[dict[str, float] | None],
    min_sun: float | None,
    min_rf: float | None,
) -> Summary:
    """Share of the evaluated samples that meet the objectives, its Wilson interval, and the parameters most correlated with the margin."""
    ok = [(p, o) for p, o in zip(params, outcomes, strict=True) if o is not None]
    if not ok or (min_sun is None and min_rf is None):
        return Summary(len(ok), None, None, None, [])

    def margin(o: dict[str, float]) -> float:
        m = []
        if min_sun is not None:
            m.append(o["sun_fraction"] - min_sun)
        if min_rf is not None:
            m.append(o["rf_fraction"] - min_rf)
        return min(m)

    marg = np.array([margin(o) for _p, o in ok])
    k = int((marg >= 0).sum())
    lo, hi = wilson(k, len(ok))
    drivers: list[tuple[str, float]] = []
    if len(ok) >= 6 and marg.std() > 1e-12:
        for s in SPREADS:
            col = np.array([p[s.group].get(s.name, math.nan) for p, _o in ok])
            if np.isfinite(col).all() and col.std() > 1e-12:
                drivers.append((s.name, float(np.corrcoef(col, marg)[0, 1])))
        drivers.sort(key=lambda t: -abs(t[1]))
    return Summary(len(ok), k / len(ok), lo, hi, drivers[:3])
