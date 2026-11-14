# SPDX-License-Identifier: Apache-2.0
"""Three-state logic (RAVEN M3): truth table of the unknown."""

import itertools

from backend.domain.raven.known import (
    Reason,
    all_known,
    count_known,
    first_reason,
    k_and,
    k_not,
    k_or,
)

T, F, U = True, False, None


def test_and_truth_table() -> None:
    table = {
        (T, T): T,
        (T, F): F,
        (T, U): U,
        (F, F): F,
        (F, U): F,  # a known "no" stays known
        (U, U): U,
    }
    for (a, b), want in table.items():
        assert k_and(a, b) is want, (a, b)
        assert k_and(b, a) is want, (b, a)


def test_or_truth_table() -> None:
    table = {
        (T, T): T,
        (T, F): T,
        (T, U): T,  # a known "yes" stays known
        (F, F): F,
        (F, U): U,
        (U, U): U,
    }
    for (a, b), want in table.items():
        assert k_or(a, b) is want, (a, b)
        assert k_or(b, a) is want, (b, a)


def test_not_and_de_morgan() -> None:
    assert k_not(T) is F and k_not(F) is T and k_not(U) is U
    for a, b in itertools.product((T, F, U), repeat=2):
        assert k_not(k_and(a, b)) is k_or(k_not(a), k_not(b))


def test_unknown_never_becomes_true() -> None:
    assert k_and(U, U) is not True and k_or(U, F) is not True
    assert all_known([T, U, T]) is U
    assert all_known([T, U, F]) is F
    assert all_known([]) is T
    assert all_known([T, T]) is T


def test_count_known_keeps_unknown_apart() -> None:
    assert count_known([T, F, U, U, T]) == (2, 1, 2)
    assert count_known([]) == (0, 0, 0)


def test_first_reason() -> None:
    assert first_reason() is Reason.OK
    assert first_reason(Reason.OK, Reason.MISSING_DEM, Reason.OUTSIDE_MODEL) is Reason.MISSING_DEM
    assert Reason("upstream_unknown") is Reason.UPSTREAM_UNKNOWN
    assert {r.value for r in Reason} == {
        "ok",
        "missing_dem",
        "outside_coverage",
        "missing_ephemeris",
        "unknown_station",
        "outside_model",
        "blocked_far_terrain",
        "upstream_unknown",
    }
