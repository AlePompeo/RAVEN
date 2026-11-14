# SPDX-License-Identifier: Apache-2.0
"""Active-learning search for the cells that best fit a mission brief.

The surrogate chooses where to look, the RAVEN core (injected as `evaluate`) decides what is true. Loop: a space-filling first design over the
feature space, core evaluations, surrogate refit, then batches of the most promising and most uncertain cells (UCB on the useful fraction,
weighted by the probability of meeting the objectives), spread out by a minimum distance, until the budget or the deadline is reached or the
best K stop changing. A cell the core cannot evaluate (unknown terrain, no mask) is NOT comparable: it is recorded, never given a value, and
never used for training. Every proposed site has a core result; the surrogate is only reported next to it, with its interval.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Final

import numpy as np
from numpy.typing import NDArray
from scipy.special import ndtr

from backend.domain.raven.discovery import surrogate as sg
from backend.domain.raven.discovery.features import SURROGATE_FEATURES, Features

Arr = NDArray[np.float64]
TARGETS: Final = ("useful_fraction", "sun_fraction", "rf_fraction")
DEFAULT_ORDER: Final = (
    "useful_fraction",
    "rf_fraction",
    "sun_fraction",
)  # lexicographic: the first criterion decides, the next break ties
EARTH_RADIUS_KM: Final = 1737.4
Z90: Final = 1.645
Evaluator = Callable[[int], dict[str, float] | None]


@dataclass(frozen=True)
class Constraints:
    """What the search must respect; None = not stated."""

    min_sun: float | None = None  # fraction 0..1 of the window with the Sun
    min_rf: float | None = None  # fraction 0..1 of the window with the link usable
    lat_max_deg: float | None = None
    lat_min_deg: float | None = None
    min_distance_km: float = 0.0
    k: int = 5
    order: tuple[str, ...] = (
        DEFAULT_ORDER  # the user's lexicographic order of the components (no single score)
    )


@dataclass
class Found:
    cell: int  # index into the candidate arrays
    lat: float
    lon: float
    core: dict[str, float]  # what the core computed
    meets: bool | None  # None when no objective was stated
    on_front: bool = False  # not dominated by any other evaluated cell on (useful, sun, radio)
    predicted: dict[str, tuple[float, float]] = field(
        default_factory=dict
    )  # target -> (mean, half width) from the surrogate that never saw it


@dataclass
class Result:
    proposals: list[Found]
    evaluated: int
    not_comparable: list[int]
    rounds: int
    stop: str  # budget | deadline | stable | exhausted
    p_meet: Arr  # per candidate: probability of meeting the objectives (NaN when no objective); 1.0/0.0 where the core evaluated
    mean: dict[str, Arr]  # per candidate surrogate mean per target
    half: dict[
        str, Arr
    ]  # per candidate half width of the interval per target (inf = the surrogate does not know)
    coverage_note: str
    front: list[Found] = field(
        default_factory=list
    )  # every core-evaluated cell that no other one dominates, in the user's order


def _cdf(z: Arr) -> Arr:
    return np.asarray(ndtr(z))


def haversine_km(lat1: float, lon1: float, lat2: Arr, lon2: Arr) -> Arr:
    p1, p2 = math.radians(lat1), np.radians(lat2)
    dl = np.radians(lon2) - math.radians(lon1)
    a = np.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return np.asarray(2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(a, 0, 1))))


def farthest_first(
    z: Arr, n: int, rng: np.random.Generator, allowed: NDArray[np.int64]
) -> list[int]:
    """`n` well-spread rows among `allowed` (farthest-point sampling in the standardised feature space), deterministic for a seed."""
    n = min(n, len(allowed))
    if n == 0:
        return []
    pool = allowed if len(allowed) <= 6000 else np.sort(rng.choice(allowed, 6000, replace=False))
    first = int(rng.integers(0, len(pool)))
    chosen = [int(pool[first])]
    d = ((z[pool] - z[chosen[0]]) ** 2).sum(1)
    while len(chosen) < n:
        j = int(np.argmax(d))
        chosen.append(int(pool[j]))
        d = np.minimum(d, ((z[pool] - z[pool[j]]) ** 2).sum(1))
    return chosen


def _p_meet(cons: Constraints, mean: dict[str, Arr], half: dict[str, Arr]) -> Arr:
    n = len(next(iter(mean.values())))
    if cons.min_sun is None and cons.min_rf is None:
        return np.full(n, np.nan)
    p = np.ones(n)
    for thr, key in ((cons.min_sun, "sun_fraction"), (cons.min_rf, "rf_fraction")):
        if thr is None:
            continue
        sigma = np.where(np.isfinite(half[key]), half[key] / Z90, 1.0)
        p *= _cdf((mean[key] - thr) / np.maximum(sigma, 1e-6))
    return p


def _meets(cons: Constraints, core: dict[str, float]) -> bool | None:
    if cons.min_sun is None and cons.min_rf is None:
        return None
    return (cons.min_sun is None or core["sun_fraction"] >= cons.min_sun) and (
        cons.min_rf is None or core["rf_fraction"] >= cons.min_rf
    )


def discover(
    feat: Features,
    evaluate: Evaluator,
    cons: Constraints,
    *,
    budget: int = 120,
    init: int = 24,
    batch: int = 8,
    deadline_s: float = 90.0,
    seed: int = 0,
    alpha: float = 0.1,
    kappa: float = 1.5,
    clock: Callable[[], float] = time.monotonic,
) -> Result:
    rng = np.random.default_rng(seed)
    t0 = clock()
    cols = [i for i, n in enumerate(feat.names) if n in SURROGATE_FEATURES] or list(
        range(feat.x.shape[1])
    )
    lat, lon, x = feat.lat, feat.lon, feat.x[:, cols]
    ok = np.ones(len(lat), dtype=bool)
    if cons.lat_max_deg is not None:
        ok &= lat <= cons.lat_max_deg
    if cons.lat_min_deg is not None:
        ok &= lat >= cons.lat_min_deg
    allowed = np.flatnonzero(ok).astype(np.int64)
    z = (x - x.mean(0)) / np.where(x.std(0) > 1e-12, x.std(0), 1.0)
    core: dict[int, dict[str, float]] = {}
    bad: list[int] = []
    tried: set[int] = set()

    def run(cells: list[int]) -> None:
        for c in cells:
            if c in tried or len(tried) >= budget:
                continue
            tried.add(c)
            r = evaluate(c)
            if r is None or any(not math.isfinite(r.get(t, math.nan)) for t in TARGETS):
                bad.append(c)
            else:
                core[c] = {t: float(r[t]) for t in r}

    run(farthest_first(z, min(init, budget), rng, allowed))
    stop, rounds, previous_top = "exhausted", 0, None
    cal: dict[str, sg.Calibrated] | None = None
    blocks = sg.spatial_blocks(lat, lon, 6)
    while True:
        if len(tried) >= budget:
            stop = "budget"
            break
        if clock() - t0 >= deadline_s:
            stop = "deadline"
            break
        idx = np.array(sorted(core), dtype=np.int64)
        if len(idx) < 12:
            rest = [int(i) for i in allowed if int(i) not in tried]
            if not rest:
                break
            run(farthest_first(z, batch, rng, np.array(rest, dtype=np.int64)))
            rounds += 1
            continue
        cal = {
            t: sg.fit_calibrated(
                x[idx], np.array([core[int(i)][t] for i in idx]), blocks[idx], alpha, seed
            )
            for t in TARGETS
        }
        pred = {t: cal[t].predict(x[allowed]) for t in TARGETS}
        mean = {t: pred[t][0] for t in TARGETS}
        std = pred["useful_fraction"][1]
        half = {t: pred[t][2] for t in TARGETS}
        pm = _p_meet(cons, mean, half)
        weight = np.where(np.isnan(pm), 1.0, pm)
        acq = (mean["useful_fraction"] + kappa * std) * weight
        acq[np.isin(allowed, np.fromiter(tried, dtype=np.int64, count=len(tried)))] = -np.inf
        order = np.argsort(-acq)
        picked: list[int] = []
        for j in order:
            if not np.isfinite(acq[j]) or len(picked) >= batch:
                break
            c = int(allowed[j])
            if all(
                haversine_km(lat[c], lon[c], lat[[p]], lon[[p]])[0] >= cons.min_distance_km
                for p in picked
            ):
                picked.append(c)
        if not picked:
            stop = "exhausted"
            break
        run(picked)
        rounds += 1
        top = tuple(sorted(_top(core, cons, lat, lon)))
        if previous_top is not None and top == previous_top and len(core) >= max(init, 3 * cons.k):
            stop = "stable"
            break
        previous_top = top

    proposals = _proposals(core, cons, feat)
    note = "no surrogate fitted (too few core evaluations)"
    p_all = np.full(len(lat), np.nan)
    means = {t: np.full(len(lat), np.nan) for t in TARGETS}
    halves = {t: np.full(len(lat), np.inf) for t in TARGETS}
    if cal is not None and len(core) >= 12:
        idx = np.array(sorted(core), dtype=np.int64)
        cal = {
            t: sg.fit_calibrated(
                x[idx], np.array([core[int(i)][t] for i in idx]), blocks[idx], alpha, seed
            )
            for t in TARGETS
        }
        for t in TARGETS:
            m, _s, h = cal[t].predict(x)
            means[t], halves[t] = m, h
        p_all = _p_meet(cons, means, halves)
        for c, r in core.items():
            means_ok = _meets(cons, r)
            p_all[c] = np.nan if means_ok is None else float(means_ok)
        note = f"{int((1 - alpha) * 100)} % conformal intervals from {len(core)} core evaluations (spatial-block and random calibration, the stricter one)"
        for pr in proposals:
            others = np.array([c for c in core if c != pr.cell], dtype=np.int64)
            if len(others) >= 12:
                for t in TARGETS:
                    f = sg.fit_calibrated(
                        x[others],
                        np.array([core[int(i)][t] for i in others]),
                        blocks[others],
                        alpha,
                        seed,
                    )
                    m, _s, h = f.predict(x[[pr.cell]])
                    pr.predicted[t] = (float(m[0]), float(h[0]))
    front_cells = set(pareto_front(core)) if core else set()
    for pr in proposals:
        pr.on_front = pr.cell in front_cells
    front = sorted(front_cells, key=lambda c: _rank_key(cons, c, core[c]), reverse=True)
    res = Result(proposals, len(core), sorted(bad), rounds, stop, p_all, means, halves, note)
    res.front = [
        Found(c, float(feat.lat[c]), float(feat.lon[c]), core[c], _meets(cons, core[c]), True)
        for c in front[:30]
    ]
    return res


def pareto_front(core: dict[int, dict[str, float]], comps: tuple[str, ...] = TARGETS) -> list[int]:
    """The cells that no other cell dominates. A dominates B when A is at least as good on every component (larger is better) and strictly
    better on at least one. Equal cells do not dominate each other. A few hundred cells at most: O(n^2) is fine."""
    cells = sorted(core)
    return [
        b
        for b in cells
        if not any(
            all(core[a][c] >= core[b][c] for c in comps)
            and any(core[a][c] > core[b][c] for c in comps)
            for a in cells
            if a != b
        )
    ]


def _rank_key(cons: Constraints, c: int, r: dict[str, float]) -> tuple[float, ...]:
    meets = _meets(cons, r)
    return (0.0 if meets is False else 1.0, *(r[k] for k in cons.order), -float(c))


def _top(core: dict[int, dict[str, float]], cons: Constraints, lat: Arr, lon: Arr) -> list[int]:
    ranked = sorted(core, key=lambda c: _rank_key(cons, c, core[c]), reverse=True)
    out: list[int] = []
    for c in ranked:
        if all(
            haversine_km(lat[c], lon[c], lat[[p]], lon[[p]])[0] >= cons.min_distance_km for p in out
        ):
            out.append(c)
        if len(out) >= cons.k:
            break
    return out


def _proposals(core: dict[int, dict[str, float]], cons: Constraints, feat: Features) -> list[Found]:
    return [
        Found(c, float(feat.lat[c]), float(feat.lon[c]), core[c], _meets(cons, core[c]))
        for c in _top(core, cons, feat.lat, feat.lon)
    ]


def evaluate_all(
    feat: Features,
    evaluate: Evaluator,
    cons: Constraints,
    *,
    budget: int = 200,
    deadline_s: float = 90.0,
    clock: Callable[[], float] = time.monotonic,
) -> Result:
    """For a short list of candidates (the catalogue sites): the core evaluates all of them, in order, up to the budget and the deadline; no surrogate
    is needed. A candidate the core cannot evaluate is not comparable. Ranking, Pareto front and objectives work as in `discover`."""
    t0 = clock()
    core: dict[int, dict[str, float]] = {}
    bad: list[int] = []
    stop = "exhausted"
    for i in range(len(feat.lat)):
        if len(core) + len(bad) >= budget:
            stop = "budget"
            break
        if clock() - t0 >= deadline_s:
            stop = "deadline"
            break
        r = evaluate(i)
        if r is None or any(not math.isfinite(r.get(t, math.nan)) for t in TARGETS):
            bad.append(i)
        else:
            core[i] = {k: float(v) for k, v in r.items()}
    proposals = _proposals(core, cons, feat)
    front_cells = set(pareto_front(core)) if core else set()
    for pr in proposals:
        pr.on_front = pr.cell in front_cells
    front = sorted(front_cells, key=lambda c: _rank_key(cons, c, core[c]), reverse=True)
    n = len(feat.lat)
    res = Result(
        proposals,
        len(core),
        sorted(bad),
        1,
        stop,
        np.full(n, np.nan),
        {t: np.full(n, np.nan) for t in TARGETS},
        {t: np.full(n, np.inf) for t in TARGETS},
        "every candidate was evaluated by the core: no surrogate involved",
    )
    res.front = [
        Found(c, float(feat.lat[c]), float(feat.lon[c]), core[c], _meets(cons, core[c]), True)
        for c in front[:30]
    ]
    return res
