# SPDX-License-Identifier: Apache-2.0
"""Three-state values for the RAVEN chain: unknown stays unknown (docs/domain/raven-model.md, 2.2).

`Known[T]` is `T | None` (None = unknown) with a parallel `Reason` per step. Rules:

* an operation with an unknown input is unknown (`Reason.UPSTREAM_UNKNOWN`), never a default;
* `False and unknown = False` (a known "no" stays known), `True and unknown = unknown`;
* `True or unknown = True`, `False or unknown = unknown`;
* counts are done on the known steps only and the unknown ones are reported apart.

Same rule as `coupled.couple` and `horizon.disc_criteria`, made shared.
"""

from collections.abc import Iterable, Sequence
from enum import StrEnum

__all__ = [
    "Known",
    "Reason",
    "all_known",
    "count_known",
    "first_reason",
    "k_and",
    "k_not",
    "k_or",
]

type Known[T] = T | None


class Reason(StrEnum):
    OK = "ok"
    MISSING_DEM = "missing_dem"
    OUTSIDE_COVERAGE = "outside_coverage"
    MISSING_EPHEMERIS = "missing_ephemeris"
    UNKNOWN_STATION = "unknown_station"
    OUTSIDE_MODEL = "outside_model"
    BLOCKED_FAR_TERRAIN = "blocked_far_terrain"  # KNOWN: far terrain closes the link (D4)
    UPSTREAM_UNKNOWN = "upstream_unknown"


def k_and(a: Known[bool], b: Known[bool]) -> Known[bool]:
    """Three-state conjunction: a known False wins over an unknown."""
    if a is False or b is False:
        return False
    if a is None or b is None:
        return None
    return True


def k_or(a: Known[bool], b: Known[bool]) -> Known[bool]:
    """Three-state disjunction: a known True wins over an unknown."""
    if a is True or b is True:
        return True
    if a is None or b is None:
        return None
    return False


def k_not(a: Known[bool]) -> Known[bool]:
    return None if a is None else not a


def all_known(values: Iterable[Known[bool]]) -> Known[bool]:
    """Conjunction of a sequence (empty = True)."""
    out: Known[bool] = True
    for v in values:
        out = k_and(out, v)
        if out is False:
            return False
    return out


def first_reason(*reasons: Reason) -> Reason:
    """The first reason that is not OK (OK if all are OK)."""
    for r in reasons:
        if r is not Reason.OK:
            return r
    return Reason.OK


def count_known(values: Sequence[Known[bool]]) -> tuple[int, int, int]:
    """(true, false, unknown) counts: the unknown steps are never counted as true."""
    t = sum(1 for v in values if v is True)
    f = sum(1 for v in values if v is False)
    return t, f, len(values) - t - f
