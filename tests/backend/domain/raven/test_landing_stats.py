# SPDX-License-Identifier: Apache-2.0
import pytest

from backend.domain.raven import landing_stats as s


def test_wilson_matches_known_values() -> None:
    lo, hi = s.wilson(5, 10)
    assert lo == pytest.approx(0.237, abs=1e-3) and hi == pytest.approx(0.763, abs=1e-3)
    assert s.wilson(0, 10)[0] == 0.0 and s.wilson(10, 10)[1] == 1.0
    with pytest.raises(ValueError):
        s.wilson(0, 0)


def test_estimate_widens_for_ambiguous_outcomes_and_keeps_unknowns_unknown() -> None:
    r = s.estimate()
    ls = r["landing_success"]
    assert r["attempts"] == len(s.ATTEMPTS) and r["tag"] == "I"
    assert ls["min"] < ls["typical"] < ls["max"]
    assert r["landing_failure"]["min"] == pytest.approx(1 - ls["max"], abs=0.011)
    assert r["component_failure_rates"] is None  # no source read: unknown, not zero


def test_every_outcome_is_marked_checked_and_the_counts_match_the_table() -> None:
    r = s.estimate()
    assert all(m["checked"] for m in r["missions"]) and len(r["missions"]) == r["attempts"] == 13
    assert (r["successes"], r["ambiguous"]) == (5, 3)
    assert "NOT checked against the primary reports" in r["source"]
