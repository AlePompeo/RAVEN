# SPDX-License-Identifier: Apache-2.0
"""S7 mission state and objectives (docs/domain/raven-model.md, 2.10; migration step M6).

`link_usable = RF closes AND DSN visible` where RF closes means margin >= `required_margin_db`
(0 dB until the unification of M8, then 3 dB: D3) or, for a KNOWN far-terrain block, False. Unknown
inputs make it unknown. `useful = state == operational AND link_usable`; the unknown steps are
counted apart and never as useful. Definitions are design choices (tag I), stated, not validated.

`link_available` (used by S4 before S7 runs) is the same rule: `link_usable_series`.
"""

from dataclasses import dataclass
from typing import Any

import numpy as np

from backend.domain.lunar.runs import longest_run
from backend.domain.raven.known import Known, k_and
from backend.domain.raven.s4_power import Power
from backend.domain.raven.s5_rf import RfLink
from backend.domain.raven.s6_dsn import Dsn

__all__ = ["LIMITING", "STATES", "Mission", "link_usable_series", "mission"]

STATES = ("operational", "comms_only", "survival", "dark", "unknown")
LIMITING = ("energy", "link", "visibility", "multiple")


@dataclass(frozen=True)
class Mission:
    link_usable: list[Known[bool]]
    state: list[str]
    useful: list[Known[bool]]
    limiting: list[Known[str]]
    metrics: dict[str, Any]
    first_unknown_index: int | None


def _rf_ok(rf: RfLink, i: int, required_margin_db: float) -> Known[bool]:
    m = rf.margin_db[i]
    if m is not None:
        return m >= required_margin_db
    return rf.closes[i]  # False for a known far-terrain block, None when unknown


def link_usable_series(rf: RfLink, dsn: Dsn, required_margin_db: float) -> list[Known[bool]]:
    """RF closes (3-state) AND DSN visible (3-state), step by step."""
    return [
        k_and(_rf_ok(rf, i, required_margin_db), dsn.any_visible[i])
        for i in range(len(dsn.any_visible))
    ]


def mission(
    pw: Power, rf: RfLink, dsn: Dsn, step_min: float, required_margin_db: float = 0.0
) -> Mission:
    n = len(pw.state)
    dt_h = step_min / 60.0
    prefix = pw.known_steps
    link = link_usable_series(rf, dsn, required_margin_db)
    useful: list[Known[bool]] = []
    limiting: list[Known[str]] = []
    for k in range(n):
        if k >= prefix:
            useful.append(None)
            limiting.append(None)
            continue
        u = pw.state[k] == "operational" and bool(link[k])
        useful.append(u)
        if u:
            limiting.append(None)
            continue
        causes = []
        if pw.state[k] != "operational":
            causes.append("energy")
        if _rf_ok(rf, k, required_margin_db) is False:
            causes.append("link")
        if dsn.any_visible[k] is False:
            causes.append("visibility")
        limiting.append(causes[0] if len(causes) == 1 else "multiple")
    u_arr = np.array([bool(v) for v in useful], dtype=bool)
    dark = [k for k, s in enumerate(pw.state) if s == "dark"]
    lim_counts = {c: sum(1 for v in limiting if v == c) for c in LIMITING}
    metrics: dict[str, Any] = {
        "n_steps": n,
        "known_steps": prefix,
        "unknown_steps": n - prefix,
        "useful_hours": float(u_arr.sum()) * dt_h,
        "useful_fraction": float(u_arr.sum()) / n,
        "useful_fraction_of_known": float(u_arr.sum()) / prefix if prefix else None,
        "unknown_hours": (n - prefix) * dt_h,
        "state_hours": {s: sum(1 for v in pw.state if v == s) * dt_h for s in STATES},
        "limiting_fraction": {c: lim_counts[c] / n for c in LIMITING},
        "min_soc": pw.min_soc,
        "min_soc_scope": "known steps only" if prefix < n else "all steps",
        "time_to_first_blackout_h": dark[0] * dt_h if dark else None,
        "blackout_within_known": bool(dark),
        "unmet_wh": pw.unmet_wh,
        "harvested_wh": pw.harvested_wh,
        "sun_hours": float(sum(1 for g in pw.gen_w[:prefix] if g is not None and g > 0.0)) * dt_h,
        "longest_unuseful_h": (
            longest_run(u_arr[np.arange(n) < prefix], False) * dt_h if prefix else None
        ),
    }
    return Mission(link, list(pw.state), useful, limiting, metrics, pw.first_unknown_index)
