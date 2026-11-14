# SPDX-License-Identifier: Apache-2.0
"""The single ranking (D5): lexicographic, components visible, no score, unknown kept apart."""

from typing import Any

import pytest

from backend.domain.raven import ranking as rk


def c(useful: float, unknown: float = 0.0, mmin: float | None = 5.0, **kw: Any) -> dict[str, Any]:
    return {
        "useful_hours": useful,
        "unknown_hours": unknown,
        "margin_min_db": mmin,
        "margin_median_db": mmin,
        "min_soc": 0.5,
        "known_steps": 10,
        "n_steps": 10,
        **kw,
    }


def ids(r: dict[str, Any]) -> list[str]:
    return [x["site_id"] for x in r["ranking"]]


def test_default_order_is_useful_then_unknown_then_margin_then_id() -> None:
    sites = [
        ("c", c(10, 0, 3.0)),
        ("a", c(10, 5, 9.0)),  # same useful hours but more unknown: after c
        ("b", c(12, 9, 1.0)),  # most useful hours: first, whatever the rest
        ("d", c(10, 0, 6.0)),  # same as c with a better margin: before c
    ]
    r = rk.rank(sites)
    assert ids(r) == ["b", "d", "c", "a"] and r["score"] is None
    assert r["order"] == list(rk.DEFAULT_ORDER)
    assert all("components" in x for x in r["ranking"])  # components always visible


def test_ties_are_broken_by_id_and_declared() -> None:
    r = rk.rank([("z", c(5)), ("m", c(5)), ("a", c(5))])
    assert ids(r) == ["a", "m", "z"] and r["ranking"][0]["tied_with"] == ["m", "z"]
    assert "site id" in r["tie_break"]


def test_user_order_changes_the_first_component() -> None:
    sites = [("x", c(10, 0, 1.0)), ("y", c(2, 0, 9.0))]
    assert ids(rk.rank(sites)) == ["x", "y"]
    assert ids(rk.rank(sites, ["margin_min_db", "useful_hours"])) == ["y", "x"]
    assert ids(rk.rank(sites, ["unknown_hours", "useful_hours"])) == ["x", "y"]


def test_no_weighted_score_exists() -> None:
    r = rk.rank([("a", c(1)), ("b", c(2))])
    assert r["score"] is None
    assert not any("score" in x for x in r["ranking"])


def test_unknown_components_go_to_not_comparable_never_above_or_below() -> None:
    sites = [
        ("known", c(1, 0, 2.0)),
        ("unk", c(100, 0, None)),
        ("none", c(50, 0, 3.0, known_steps=0)),
    ]
    r = rk.rank(sites)
    assert ids(r) == ["known"]
    assert {x["site_id"] for x in r["not_comparable"]} == {"unk", "none"}
    by = {x["site_id"]: x for x in r["not_comparable"]}
    assert (
        "margin_min_db unknown" in by["unk"]["reasons"] and "no known step" in by["none"]["reasons"]
    )
    # not asked for -> not an obstacle: ordering by useful hours only keeps "unk" comparable
    r2 = rk.rank(sites, ["useful_hours"])
    assert ids(r2)[0] == "unk"


def test_known_far_terrain_block_ranks_last_not_unknown() -> None:
    sites = [("blocked", c(0, 0, None, margin_blocked=True)), ("ok", c(0, 0, -4.0))]
    r = rk.rank(sites)
    assert ids(r) == ["ok", "blocked"] and not r["not_comparable"]


def test_validation_of_order_and_ids() -> None:
    for bad in (["nope"], ["useful_hours", "useful_hours"]):
        with pytest.raises(rk.RankingError):
            rk.rank([("a", c(1))], bad)
    with pytest.raises(rk.RankingError):
        rk.rank([("a", c(1)), ("a", c(2))])


def test_deterministic_and_input_order_independent() -> None:
    s = [("a", c(3)), ("b", c(3, 1)), ("c", c(9, 0, 1.0)), ("d", c(3))]
    assert rk.rank(s) == rk.rank(s)
    assert ids(rk.rank(s)) == ids(rk.rank(list(reversed(s))))
