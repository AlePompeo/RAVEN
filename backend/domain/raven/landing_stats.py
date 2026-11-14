# SPDX-License-Identifier: Apache-2.0
"""RAVEN estimate of the lunar soft-landing transfer probability from public attempt outcomes.

Honesty rules: this is a small-sample tally (tag I) of attempts since 2019, written from public mission records and NOT
re-checked against the primary reports of each agency; it is not a forecast for the user's mission (different vehicle, site and
operator) and not a reliability figure of any component. Ambiguous outcomes (landed but tipped over, partial operation) are
counted both ways so they widen the interval instead of being decided silently. Component failure rates (MIL-HDBK-217F) are
not included: no source was read, so they stay unknown. Stdlib only.
"""

from __future__ import annotations

import math
from typing import Final

MODEL_ID: Final = "raven.landing_stats.v1"
# (mission, year, outcome, checked): `checked` = the outcome was confirmed on a public source on 12 Nov 2026 (see `source`);
# (mission, year, outcome): "success" = soft landing and operation, "failure" = no soft landing or no operation,
# "ambiguous" = landed but tipped or only partly operational
ATTEMPTS: Final[tuple[tuple[str, int, str, bool], ...]] = (
    ("Chang'e 4", 2019, "success", True),
    ("Chandrayaan-2 Vikram", 2019, "failure", True),
    ("Beresheet", 2019, "failure", True),
    ("Chang'e 5", 2020, "success", True),
    ("Chandrayaan-3", 2023, "success", True),
    ("Luna 25", 2023, "failure", True),
    ("Hakuto-R M1", 2023, "failure", True),
    ("SLIM", 2024, "ambiguous", True),
    ("IM-1 Odysseus", 2024, "ambiguous", True),
    ("Chang'e 6", 2024, "success", True),
    ("Blue Ghost M1", 2025, "success", True),
    ("IM-2 Athena", 2025, "ambiguous", True),
    ("Hakuto-R M2 Resilience", 2025, "failure", True),
)


def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion (95 % by default)."""
    if n <= 0:
        raise ValueError("n must be positive")
    p = successes / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, centre - half), min(1.0, centre + half)


def estimate() -> dict[str, object]:
    n = len(ATTEMPTS)
    ok = sum(1 for _, _, o, _c in ATTEMPTS if o == "success")
    amb = sum(1 for _, _, o, _c in ATTEMPTS if o == "ambiguous")
    lo = wilson(ok, n)[0]  # ambiguous counted as failures
    hi = wilson(ok + amb, n)[1]  # ambiguous counted as successes
    return {
        "model": MODEL_ID,
        "tag": "I",
        "attempts": n,
        "successes": ok,
        "ambiguous": amb,
        "landing_success": {"min": round(lo, 2), "typical": round(ok / n, 2), "max": round(hi, 2)},
        "landing_failure": {
            "min": round(1 - hi, 2),
            "typical": round(1 - ok / n, 2),
            "max": round(1 - lo, 2),
        },
        "interval": "95 % Wilson interval; ambiguous outcomes counted both ways",
        "missions": [
            {"mission": m, "year": y, "outcome": o, "checked": c} for m, y, o, c in ATTEMPTS
        ],
        "source": "outcomes of all 13 attempts confirmed on 12 Nov 2026 on public secondary pages (newspaceeconomy.ca 2025-07-14, Discover Magazine, IEEE Spectrum, spaceodysseyhub.com, Space.com, SpaceNews, Roscosmos' preliminary report of 3 Oct 2023 as reported by Reuters/Interfax); NOT checked against the primary reports of each agency",
        "limits": "small sample, mixed vehicles and operators; not a forecast for a specific mission; no launch or component failure rates (unknown)",
        "component_failure_rates": None,
    }
