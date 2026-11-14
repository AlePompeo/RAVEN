# SPDX-License-Identifier: Apache-2.0
import numpy as np

from backend.domain.raven.discovery import search as se
from backend.domain.raven.discovery.features import Features

N = 3000


def _feat(seed: int = 0) -> Features:
    """Candidate cells of a synthetic polar region: features and (below) a hidden truth the 'core' computes."""
    rng = np.random.default_rng(seed)
    lat = rng.uniform(-90, -75, N)
    lon = rng.uniform(0, 360, N)
    sun = np.clip(0.5 + 0.4 * np.sin(np.radians(lon) * 2) + rng.normal(0, 0.05, N), 0, 1)
    slope = rng.uniform(0, 15, N)
    x = np.column_stack([lat, np.sin(np.radians(lon)), np.cos(np.radians(lon)), sun, slope])
    return Features(
        lat, lon, x, ("lat", "sin", "cos", "sun", "slope"), np.arange(N, dtype=np.int64), 0
    )


def _truth(f: Features, i: int) -> dict[str, float]:
    sun, slope, lat, lon = f.x[i, 3], f.x[i, 4], f.lat[i], f.lon[i]
    bump = 0.25 * np.exp(-(((lat + 84) ** 2) / 6.0 + ((lon - 120) ** 2) / 900.0))
    rf = float(np.clip(0.55 + 0.3 * np.cos(np.radians(lon)) - 0.01 * slope + bump, 0, 1))
    sun_f = float(np.clip(sun, 0, 1))
    return {
        "useful_fraction": float(np.clip(0.9 * sun_f * rf - 0.2 * bump, 0, 1)),
        "sun_fraction": sun_f,
        "rf_fraction": rf,
    }


def _run(seed: int = 0, **kw: object) -> tuple[se.Result, Features, list[int]]:
    f = _feat()
    calls: list[int] = []

    def evaluate(i: int) -> dict[str, float] | None:
        calls.append(i)
        return _truth(f, i)

    r = se.discover(
        f, evaluate, kw.pop("cons", se.Constraints(k=5, min_distance_km=30.0)), seed=seed, **kw
    )  # type: ignore[arg-type]
    return r, f, calls


def test_the_search_beats_random_sampling_with_the_same_budget() -> None:
    r, f, calls = _run(budget=70, init=20, batch=8)
    assert len(calls) == r.evaluated <= 70 and len(set(calls)) == len(calls)
    truth = np.array([_truth(f, i)["useful_fraction"] for i in range(N)])
    best_k = np.sort(truth)[-5:].mean()
    found = np.mean([p.core["useful_fraction"] for p in r.proposals])
    rng = np.random.default_rng(1)
    random_k = np.mean(
        [np.sort(truth[rng.choice(N, 70, replace=False)])[-5:].mean() for _ in range(200)]
    )
    assert found >= 0.9 * best_k and found > random_k, (found, best_k, random_k)


def test_proposals_are_core_values_ordered_and_separated() -> None:
    r, _f, _c = _run(budget=60, init=20)
    vals = [p.core["useful_fraction"] for p in r.proposals]
    assert vals == sorted(vals, reverse=True) and len(r.proposals) == 5
    for i, a in enumerate(r.proposals):
        for b in r.proposals[:i]:
            assert se.haversine_km(a.lat, a.lon, np.array([b.lat]), np.array([b.lon]))[0] >= 30.0


def test_objectives_put_the_cells_that_meet_them_first_and_report_probabilities() -> None:
    cons = se.Constraints(min_sun=0.7, min_rf=0.6, k=5, min_distance_km=20.0)
    r, _f, _c = _run(budget=80, init=24, cons=cons)
    assert all(p.meets is not None for p in r.proposals)
    met = [p.meets for p in r.proposals]
    assert met == sorted(
        met, reverse=True
    )  # the cells that meet the objectives come before those that do not
    assert np.isfinite(r.p_meet).sum() == len(r.p_meet)  # a probability for every candidate
    assert all(
        r.p_meet[p.cell] in (0.0, 1.0) for p in r.proposals
    )  # core evaluated: 1 or 0, not a guess


def test_same_seed_same_answer_and_a_different_seed_still_works() -> None:
    a, _f, ca = _run(seed=3, budget=50, init=16)
    b, _f2, cb = _run(seed=3, budget=50, init=16)
    assert ca == cb and [p.cell for p in a.proposals] == [p.cell for p in b.proposals]
    c, _f3, _cc = _run(seed=4, budget=50, init=16)
    assert len(c.proposals) == 5


def test_a_cell_the_core_cannot_evaluate_is_not_comparable_and_never_trained_on() -> None:
    f = _feat()
    unknown = {i for i in range(N) if f.lat[i] < -88}  # no terrain near the pole in this scenario

    def evaluate(i: int) -> dict[str, float] | None:
        return None if i in unknown else _truth(f, i)

    r = se.discover(f, evaluate, se.Constraints(k=5), budget=60, init=24, seed=0)
    assert set(r.not_comparable) <= unknown and all(p.cell not in unknown for p in r.proposals)
    assert r.evaluated + len(r.not_comparable) <= 60


def test_latitude_limits_budget_and_deadline_are_respected() -> None:
    _r, f, calls = _run(cons=se.Constraints(k=3, lat_max_deg=-85.0), budget=40, init=16)
    assert all(f.lat[c] <= -85.0 for c in calls)
    ticks = iter(range(10_000))
    r2 = se.discover(
        f,
        lambda i: _truth(f, i),
        se.Constraints(k=3),
        budget=500,
        init=16,
        deadline_s=0.5,
        clock=lambda: float(next(ticks)),
    )
    assert r2.stop == "deadline" and r2.evaluated < 500


def test_the_surrogate_reports_an_honest_prediction_for_each_proposal() -> None:
    r, _f, _c = _run(budget=80, init=24)
    p = r.proposals[0]
    assert set(p.predicted) == set(se.TARGETS)
    mean, half = p.predicted["useful_fraction"]
    assert np.isfinite(mean) and half > 0 and "conformal" in r.coverage_note


def test_the_pareto_front_keeps_only_cells_nothing_else_beats() -> None:
    core = {
        0: {"useful_fraction": 0.9, "sun_fraction": 0.5, "rf_fraction": 0.5},
        1: {"useful_fraction": 0.5, "sun_fraction": 0.9, "rf_fraction": 0.5},
        2: {
            "useful_fraction": 0.4,
            "sun_fraction": 0.4,
            "rf_fraction": 0.4,
        },  # beaten by 0 and 1 on everything
        3: {
            "useful_fraction": 0.9,
            "sun_fraction": 0.5,
            "rf_fraction": 0.5,
        },  # equal to 0: neither dominates the other
        4: {"useful_fraction": 0.5, "sun_fraction": 0.5, "rf_fraction": 0.95},
    }
    assert se.pareto_front(core) == [0, 1, 3, 4]
    assert se.pareto_front({}) == [] and se.pareto_front({7: core[0]}) == [7]


def test_the_search_reports_the_front_and_the_users_order_changes_the_ranking() -> None:
    r, _f, _c = _run(budget=70, init=20)
    assert r.front and all(p.on_front for p in r.front)
    assert any(
        p.on_front for p in r.proposals
    )  # the best by the default order is not beaten on every component
    by_sun, _f2, _c2 = _run(
        budget=70,
        init=20,
        cons=se.Constraints(
            k=5, min_distance_km=30.0, order=("sun_fraction", "useful_fraction", "rf_fraction")
        ),
    )
    top_default = r.proposals[0].core
    top_sun = by_sun.proposals[0].core
    assert (
        top_sun["sun_fraction"] >= top_default["sun_fraction"] - 1e-9
    )  # ordering by Sun first puts a sunnier cell first
    assert [p.core["sun_fraction"] for p in by_sun.proposals] == sorted(
        [p.core["sun_fraction"] for p in by_sun.proposals], reverse=True
    )
