# SPDX-License-Identifier: Apache-2.0
"""Final account of a site search: which proposed site is the best for the brief, decided by the engine and explained in words.

The facts come only from the finished job (every number was computed by the RAVEN core or the uncertainty step; nothing is typed by the client).
The best site is the first of the ranking the search produced (probability of meeting the objectives, then useful time; without objectives the
search order). A language model may only write the explanation: its text is kept only if it names the same site and uses no number that is not in
the facts (`check_text`). Without a model, or when its text is rejected, a template built from the same facts is used. Unknown stays unknown.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from typing import Any, Final

_NUM = re.compile(r"\d+(?:\.\d+)?")
ORDER_LABEL: Final = {
    "useful_fraction": ("useful time", "tempo utile"),
    "sun_fraction": ("time with Sun", "tempo con il Sole"),
    "rf_fraction": ("time with a usable radio link", "tempo con collegamento radio utilizzabile"),
}


def _pct(v: object) -> int | None:
    return (
        round(float(v) * 100)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
        else None
    )


def label(p: Mapping[str, Any]) -> str:
    """How the text names a site: its catalogue name, else its rank."""
    return str(p["name"]) if p.get("name") else f"site {p['rank']}"


def _site(p: Mapping[str, Any]) -> dict[str, Any]:
    core, unc = p.get("core") or {}, p.get("uncertainty") or {}
    return {
        "label": label(p),
        "rank": p["rank"],
        "lat_deg": round(float(p["lat_deg"]), 2),
        "lon_deg_east": round(float(p["lon_deg_east"]), 1),
        "useful_percent": _pct(core.get("useful_fraction")),
        "sun_percent": _pct(core.get("sun_fraction")),
        "radio_percent": _pct(core.get("rf_fraction")),
        "meets_objectives": p.get("meets_objectives"),
        "on_pareto_front": bool(p.get("on_front")),
        "p_meet_percent": _pct(unc.get("p_meet")),
        "p_low_percent": _pct(unc.get("p_low")),
        "p_high_percent": _pct(unc.get("p_high")),
    }


def facts(result: Mapping[str, Any]) -> dict[str, Any] | None:
    """The facts of the account, or None when the search found nothing."""
    props: Sequence[Mapping[str, Any]] = result.get("proposals") or []
    if not props:
        return None
    sites = [_site(p) for p in props]
    brief = result.get("brief") or {}
    return {
        "best": sites[0],
        "second": sites[1] if len(sites) > 1 else None,
        "n_sites": len(sites),
        "n_front": len(result.get("pareto") or []),
        "n_meet": sum(1 for s in sites if s["meets_objectives"] is True),
        "has_objectives": any(s["meets_objectives"] is not None for s in sites),
        "evaluated": int(result.get("evaluated") or 0),
        "not_comparable": int(result.get("not_comparable") or 0),
        "order": list(result.get("order") or []),
        "region": result.get("region") or "polar",
        "days": brief.get("days"),
        "priority": brief.get("priority"),
        "terrain": (props[0].get("terrain") or ""),
    }


def template_text(f: Mapping[str, Any], lang: str = "en") -> str:
    """The account without any model, built only from the facts."""
    it = lang == "it"
    b, s = f["best"], f["second"]

    def val(v: int | None) -> str:
        return ("non noto" if it else "unknown") if v is None else f"{v} %"

    if it:
        out = (
            f"Il sito migliore per questa richiesta è {b['label']} ({b['lat_deg']}°, {b['lon_deg_east']}° E): "
            f"tempo utile {val(b['useful_percent'])}, Sole {val(b['sun_percent'])}, radio {val(b['radio_percent'])}."
        )
        if b["p_meet_percent"] is not None:
            out += f" Probabilità di rispettare gli obiettivi {b['p_meet_percent']} % (intervallo {b['p_low_percent']}–{b['p_high_percent']} %)."
        if s is not None and s["useful_percent"] is not None and b["useful_percent"] is not None:
            out += f" Il secondo, {s['label']}, ha tempo utile {s['useful_percent']} %."
        out += (
            f" Su {f['n_sites']} siti proposti {f['n_front']} sono sul fronte di Pareto"
            f"{f', {f["n_meet"]} rispettano gli obiettivi' if f['has_objectives'] else ''}; "
            f"il motore ha valutato {f['evaluated']} siti e {f['not_comparable']} non erano confrontabili."
        )
        out += " Sono stime con ipotesi illustrative: l'ordine dipende dalla priorità scelta e non da un punteggio unico."
        return out
    out = (
        f"The best site for this request is {b['label']} ({b['lat_deg']}°, {b['lon_deg_east']}° E): "
        f"useful time {val(b['useful_percent'])}, Sun {val(b['sun_percent'])}, radio {val(b['radio_percent'])}."
    )
    if b["p_meet_percent"] is not None:
        out += f" Probability of meeting the objectives {b['p_meet_percent']} % (interval {b['p_low_percent']}-{b['p_high_percent']} %)."
    if s is not None and s["useful_percent"] is not None and b["useful_percent"] is not None:
        out += f" The runner-up, {s['label']}, has useful time {s['useful_percent']} %."
    out += (
        f" Of {f['n_sites']} proposed sites {f['n_front']} are on the Pareto front"
        f"{f', {f["n_meet"]} meet the objectives' if f['has_objectives'] else ''}; "
        f"the engine evaluated {f['evaluated']} sites and {f['not_comparable']} could not be compared."
    )
    out += " These are estimates with illustrative assumptions: the order follows the chosen priority, not a single score."
    return out


def supplied_numbers(f: Mapping[str, Any]) -> set[str]:
    out: set[str] = set()

    def add(v: object) -> None:
        if isinstance(v, bool):
            return
        if isinstance(v, (int, float)) and math.isfinite(v):
            out.update({f"{v:.0f}", f"{v:.1f}", f"{v:.2f}", f"{v:g}", f"{abs(v):g}"})
        elif isinstance(v, Mapping):
            for x in v.values():
                add(x)

    for k in (
        "best",
        "second",
        "n_sites",
        "n_front",
        "n_meet",
        "evaluated",
        "not_comparable",
        "days",
    ):
        add(f.get(k))
    return out


def check_text(text: str, f: Mapping[str, Any]) -> bool:
    """A model-written account is accepted only if it names the best site and uses no number that is not in the facts."""
    t = text.strip()
    if not (60 <= len(t) <= 1200):
        return False
    best = f["best"]["label"].lower()
    if best not in t.lower() and f"site {f['best']['rank']}" not in t.lower():
        return False
    allowed = supplied_numbers(f) | {
        "0",
        "1",
        "2",
        "90",
    }  # 90: the stated confidence level of the intervals
    return all(n in allowed for n in _NUM.findall(t))
