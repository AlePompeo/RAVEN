# SPDX-License-Identifier: Apache-2.0
"""Which of the two sites of a report is the better choice, decided by the engine and explained in words.

The decision is deterministic and reproducible: a lexicographic order of components chosen by the mission priority (decision D5: no single score,
every component visible), with a tolerance below which two values are a tie (a difference below the tolerance is noise, not a reason). A component that is
unknown for either site cannot decide: the next one does; if none can, the verdict is "undetermined", never a guess. A language model may only write the
explanation (see `check_text`): it cannot change the winner, and its text is accepted only if every number in it is one of the numbers supplied.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from typing import Any, Final

# component -> (direction, label, unit, tolerance): "desc" larger is better, "asc" smaller is better
COMPONENTS: Final[dict[str, tuple[str, str, str, float]]] = {
    "useful_hours": ("desc", "useful hours (operational and link usable)", "h", 1.0),
    "unknown_hours": ("asc", "hours that depend on unknown inputs", "h", 1.0),
    "margin_min_db": ("desc", "minimum RF margin", "dB", 0.5),
    "min_soc": ("desc", "minimum state of charge", "", 0.02),
    "sun_hours": ("desc", "hours with the Sun", "h", 1.0),
}
ORDERS: Final[dict[str, tuple[str, ...]]] = {
    "balanced": ("useful_hours", "unknown_hours", "margin_min_db", "min_soc", "sun_hours"),
    "sun": ("sun_hours", "useful_hours", "min_soc", "unknown_hours", "margin_min_db"),
    "earth": ("margin_min_db", "useful_hours", "unknown_hours", "min_soc", "sun_hours"),
    "radio": ("margin_min_db", "useful_hours", "unknown_hours", "min_soc", "sun_hours"),
}


def _num(v: object) -> float | None:
    return (
        float(v)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
        else None
    )


def decide(
    a: Mapping[str, Any], b: Mapping[str, Any], priority: str | None = None
) -> dict[str, Any]:
    """Compare two sites (mappings with the component values, None = unknown). Returns the winner, the component that decided and every row."""
    order = ORDERS.get(priority or "balanced", ORDERS["balanced"])
    rows: list[dict[str, Any]] = []
    winner: str | None = None
    decided_by: str | None = None
    for comp in order:
        direction, label, unit, tol = COMPONENTS[comp]
        va, vb = _num(a.get(comp)), _num(b.get(comp))
        if va is None or vb is None:
            better = "unknown"
        elif abs(va - vb) <= tol:
            better = "tie"
        else:
            better = "A" if (va > vb) == (direction == "desc") else "B"
        rows.append(
            {
                "component": comp,
                "label": label,
                "unit": unit,
                "a": va,
                "b": vb,
                "tolerance": tol,
                "better": better,
            }
        )
        if winner is None and better in ("A", "B"):
            winner, decided_by = better, comp
    if winner is None:
        known = [r for r in rows if r["better"] != "unknown"]
        verdict = "tie" if known else "undetermined"
    else:
        verdict = winner
    return {
        "winner": verdict,
        "decided_by": decided_by,
        "priority": priority or "balanced",
        "order": list(order),
        "rows": rows,
        "rule": "Lexicographic order by the mission priority; a difference within the tolerance is a tie; an unknown component cannot decide. No score.",
    }


def _fmt(v: float | None, unit: str) -> str:
    if v is None:
        return "unknown"
    s = f"{v:.0f}" if abs(v) >= 100 else f"{v:.1f}" if unit else f"{v:.2f}"
    return f"{s} {unit}".strip()


def template_text(verdict: Mapping[str, Any], names: Sequence[str]) -> str:
    """The explanation without any model: built only from the rows."""
    w = verdict["winner"]
    na, nb = names[0], names[1]
    rows = {r["component"]: r for r in verdict["rows"]}
    if w == "undetermined":
        return f"The engine cannot decide between {na} (A) and {nb} (B): the components that could decide are unknown for at least one of them."
    if w == "tie":
        return f"{na} (A) and {nb} (B) are tied: every comparable component differs by less than its tolerance."
    name, other = (na, nb) if w == "A" else (nb, na)
    r = rows[verdict["decided_by"]]
    lead = f"{name} ({w}) is the better choice over {other} ({'B' if w == 'A' else 'A'}) for this window, decided by {r['label']}: A {_fmt(r['a'], r['unit'])}, B {_fmt(r['b'], r['unit'])}."
    worse = [x for x in verdict["rows"] if x["better"] in ("A", "B") and x["better"] != w]
    if worse:
        x = worse[0]
        lead += f" The other site is better on {x['label']} (A {_fmt(x['a'], x['unit'])}, B {_fmt(x['b'], x['unit'])}), which the priority ranks lower."
    unk = [x["label"] for x in verdict["rows"] if x["better"] == "unknown"]
    if unk:
        lead += " Unknown for at least one site, so not used: " + ", ".join(unk) + "."
    return lead


_NUM = re.compile(r"\d+(?:\.\d+)?")


def supplied_numbers(verdict: Mapping[str, Any]) -> set[str]:
    out: set[str] = set()
    for r in verdict["rows"]:
        for key in ("a", "b", "tolerance"):
            v = _num(r.get(key))
            if v is not None:
                out.update({f"{v:.0f}", f"{v:.1f}", f"{v:.2f}", f"{v:g}"})
    return out


def check_text(text: str, verdict: Mapping[str, Any], names: Sequence[str]) -> bool:
    """A model-written explanation is accepted only if it names the winner of the engine and uses no number that was not supplied (small integers
    like the sentence count are not numbers of the data and are allowed only as 0, 1, 2)."""
    t = text.strip()
    if not (40 <= len(t) <= 900):
        return False
    w = verdict["winner"]
    if (
        w in ("A", "B")
        and names[0 if w == "A" else 1].lower() not in t.lower()
        and f"site {w}".lower() not in t.lower()
    ):
        return False
    if (
        w in ("A", "B")
        and names[1 if w == "A" else 0].lower() in t.lower()
        and f"{names[0 if w == 'A' else 1].lower()}" not in t.lower()
    ):
        return False
    allowed = supplied_numbers(verdict) | {"0", "1", "2"}
    return all(n in allowed for n in _NUM.findall(t))
