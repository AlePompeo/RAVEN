# SPDX-License-Identifier: Apache-2.0
"""Window edges by bisection (RAVEN M9): analytic sinusoidal Sun, unknown neighbours, real data."""

import math
from datetime import UTC, datetime

import pytest

from backend.domain.raven import s0_context as s0
from backend.domain.raven.known import Known
from backend.domain.raven.pipeline import evaluate, legacy_scenario, refined_windows
from backend.domain.raven.windows import find_windows, refine_edge
from scripts import raven_golden as rg

PERIOD = 29.53 * 86400.0  # a synodic month
THR = 0.2


def sun(t: float) -> float:
    return math.sin(2 * math.pi * t / PERIOD)


def lit(t: float) -> Known[bool]:
    return sun(t) > THR


def test_refine_edge_hits_the_analytic_root_within_one_second() -> None:
    root = PERIOD * math.asin(THR) / (2 * math.pi)  # sun(t) = THR, rising
    a, b = root - 1500.0, root + 1500.0
    t, ok = refine_edge(lit, b, a, tol_s=1.0)
    assert ok and abs(t - root) <= 1.0
    # falling edge
    root2 = PERIOD / 2 - root
    t2, ok2 = refine_edge(lit, root2 - 2000.0, root2 + 2000.0, tol_s=1.0)
    assert ok2 and abs(t2 - root2) <= 1.0


def test_windows_on_a_sampled_sinusoid_are_exact_to_one_second() -> None:
    step = 3600.0
    n = int(2 * PERIOD / step)
    t = [i * step for i in range(n)]
    flags = [lit(x) for x in t]
    w = find_windows(t, flags, step, lit, 1.0)
    # sun > THR on (root, PERIOD/2 - root) of each cycle
    root = PERIOD * math.asin(THR) / (2 * math.pi)
    assert len(w) == 2
    for k, win in enumerate(w):
        s_true, e_true = k * PERIOD + root, k * PERIOD + PERIOD / 2 - root
        assert win["start_resolved"] and win["end_resolved"] or win["open_end"]
        assert abs(win["start_unix"] - s_true) <= 1.0
        if win["end_resolved"]:
            assert abs(win["end_unix"] - e_true) <= 1.0
    # without refinement the edge is only known to the step and is flagged so
    coarse = find_windows(t, flags, step, None)
    assert not coarse[0]["start_resolved"]
    assert coarse[0]["tolerance_s"] == 1.0 and not coarse[0]["end_resolved"]


def test_edges_next_to_unknown_steps_are_not_refined_and_not_resolved() -> None:
    t = [0.0, 60.0, 120.0, 180.0, 240.0]
    flags: list[Known[bool]] = [None, True, True, None, False]
    calls: list[float] = []

    def pred(x: float) -> Known[bool]:
        calls.append(x)
        return True

    w = find_windows(t, flags, 60.0, pred)
    assert len(w) == 1 and calls == []  # unknown neighbours: no evaluation at all
    assert not w[0]["start_resolved"] and not w[0]["end_resolved"]
    assert w[0]["start_unix"] == 60.0 and w[0]["end_unix"] == 180.0


def test_open_edges_and_unknown_never_count_as_inside() -> None:
    t = [0.0, 60.0, 120.0]
    w = find_windows(t, [True, True, True], 60.0, lit)
    assert w[0]["open_start"] and w[0]["open_end"] and not w[0]["start_resolved"]
    assert find_windows(t, [None, None, None], 60.0, lit) == []
    assert find_windows(t, [False, None, False], 60.0, lit) == []


def test_unknown_midpoint_stops_the_bracket() -> None:
    def pred(x: float) -> Known[bool]:
        return None if 40.0 < x < 60.0 else x < 50.0

    t, ok = refine_edge(pred, 0.0, 100.0, 1.0)
    assert ok is False and 40.0 < t < 60.0
    with pytest.raises(ValueError):
        refine_edge(lit, 0.0, 10.0, 0.0)


@pytest.mark.skipif(not (rg.have_kernels() and rg.have_tiles()), reason="kernels or tiles missing")
def test_real_site_edges_stay_within_one_step_of_the_grid_edges() -> None:
    from backend.ephemeris.engine import get_engine

    eng = get_engine()
    sc = legacy_scenario(
        s0.resolve_site("malapert-massif"),
        s0.TimeWindow(datetime(2027, 1, 1, tzinfo=UTC), 60.0, 60.0),
    )
    ev = evaluate(sc, eng)
    wins = refined_windows(ev, sc, eng, tol_s=1.0)
    lit_w = wins["lit"]
    assert lit_w, "Malapert has lit windows in 60 days"
    step = 3600.0
    t = ev.grid.t_unix
    inner = [w for w in lit_w if w["start_resolved"] and w["end_resolved"]]
    assert inner
    for w in inner:
        i, j = w["first_sample"], w["last_sample"]
        assert t[i] - step < w["start_unix"] <= t[i]
        assert t[j] <= w["end_unix"] < t[j] + step
        assert w["tolerance_s"] == 1.0
    assert all(not w["start_resolved"] and not w["end_resolved"] for w in wins["useful"])


def test_refinement_budget_leaves_edges_unresolved_instead_of_running_for_minutes() -> None:
    """A long period would need hundreds of instant evaluations: past the budget the predicate answers
    unknown, so the edge stays inside its step and is flagged unresolved (never a guessed value)."""
    from backend.domain.raven.pipeline import _budgeted

    calls: list[float] = []

    def pred(t: float) -> Known[bool]:
        calls.append(t)
        return sun(t) > THR

    limited = _budgeted({"lit": pred}, 5)["lit"]
    edge, resolved = refine_edge(limited, 0.0, 3600.0 * 12, 1.0)
    assert len(calls) == 5 and resolved is False and 0.0 <= edge <= 3600.0 * 12
    assert limited(1.0) is None and len(calls) == 5
