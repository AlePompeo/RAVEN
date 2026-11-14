# SPDX-License-Identifier: Apache-2.0
"""The single site ranking (decision D5): lexicographic, components always visible, no score.

Every site returns its components: useful hours, unknown hours, minimum and median RF margin over
the steps where a margin is known, minimum state of charge and time to the first blackout. The order
is lexicographic on a list of components chosen by the user (default: useful hours, then unknown hours
(fewer is better), then minimum margin); ties are broken by the site id, which is declared. There is
NO weighted mean and NO single number.

A site whose compared components are unknown (no known step, or no known margin) is not ordered
above or below the others: it goes to the group `not_comparable` with the reason.

This module takes plain values; `components_of` reads an `Evaluation` by attribute (no import of
the pipeline: ranking and pipeline are siblings in the layers contract).
"""

import statistics
from collections.abc import Sequence
from typing import Any

__all__ = [
    "COMPONENTS",
    "DEFAULT_ORDER",
    "RankingError",
    "components_of",
    "rank",
]

# component -> (direction, label). "desc": larger is better; "asc": smaller is better.
COMPONENTS: dict[str, tuple[str, str]] = {
    "useful_hours": ("desc", "hours with state operational and link usable"),
    "unknown_hours": ("asc", "hours that depend on unknown inputs (never counted as useful)"),
    "margin_min_db": ("desc", "minimum RF margin over steps with a known margin"),
    "margin_median_db": ("desc", "median RF margin over steps with a known margin"),
    "min_soc": ("desc", "minimum state of charge over the known steps"),
}
DEFAULT_ORDER = ("useful_hours", "unknown_hours", "margin_min_db")


class RankingError(ValueError):
    pass


def components_of(ev: Any) -> dict[str, Any]:
    """The components of one `Evaluation` (read by attribute)."""
    m = ev.mission.metrics
    margins = [x for x in ev.rf.margin_db if x is not None]
    # no margin number but every step is a KNOWN "no" (far-terrain block): the worst known case,
    # not an unknown (the number is outside the single-obstacle model, the answer is not)
    blocked = not margins and bool(ev.rf.closes) and all(c is False for c in ev.rf.closes)
    return {
        "margin_blocked": blocked,
        "useful_hours": m["useful_hours"],
        "unknown_hours": m["unknown_hours"],
        "margin_min_db": min(margins) if margins else None,
        "margin_median_db": statistics.median(margins) if margins else None,
        "min_soc": m["min_soc"],
        "time_to_first_blackout_h": m["time_to_first_blackout_h"],
        "known_steps": m["known_steps"],
        "n_steps": m["n_steps"],
    }


def _unknown_reasons(c: dict[str, Any], order: Sequence[str]) -> list[str]:
    reasons = [
        f"{k} unknown"
        for k in order
        if c.get(k) is None and not (k.startswith("margin_") and c.get("margin_blocked"))
    ]
    if c.get("known_steps", 1) == 0:
        reasons.append("no known step")
    return reasons


def rank(
    sites: Sequence[tuple[str, dict[str, Any]]], order: Sequence[str] | None = None
) -> dict[str, Any]:
    """Rank `(site_id, components)` pairs. Returns the ordered `ranking`, the `not_comparable`
    group, the order used and the declared tie-break; every row keeps all its components."""
    use = tuple(order) if order else DEFAULT_ORDER
    if not use or len(set(use)) != len(use) or any(k not in COMPONENTS for k in use):
        raise RankingError("order")
    ids = [i for i, _ in sites]
    if len(set(ids)) != len(ids):
        raise RankingError("site_ids")
    comparable: list[tuple[str, dict[str, Any]]] = []
    other: list[dict[str, Any]] = []
    for sid, c in sites:
        why = _unknown_reasons(c, use)
        if why:
            other.append({"site_id": sid, "components": c, "reasons": why})
        else:
            comparable.append((sid, c))

    def key(item: tuple[str, dict[str, Any]]) -> tuple[Any, ...]:
        sid, c = item

        def val(k: str) -> float:
            v = c[k]
            if v is None:  # margin of a site whose steps are all known far-terrain blocks
                return float("inf") if COMPONENTS[k][0] == "desc" else float("-inf")
            return float(-v if COMPONENTS[k][0] == "desc" else v)

        parts = [val(k) for k in use]
        return (*parts, sid)

    ordered = sorted(comparable, key=key)
    rows = []
    for pos, (sid, c) in enumerate(ordered, start=1):
        tied = [o for o, oc in ordered if o != sid and all(oc[k] == c[k] for k in use)]
        rows.append({"rank": pos, "site_id": sid, "components": c, "tied_with": tied})
    return {
        "order": list(use),
        "directions": {k: COMPONENTS[k][0] for k in use},
        "tie_break": "site id, ascending (declared; not a physical criterion)",
        "score": None,
        "ranking": rows,
        "not_comparable": other,
        "components_legend": {k: v[1] for k, v in COMPONENTS.items()},
    }
