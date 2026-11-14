# SPDX-License-Identifier: Apache-2.0
"""Validation status per stage and parameter group (RAVEN): complete, with evidence."""

from pathlib import Path

from backend.domain.raven import params as reg
from backend.domain.raven import validation as v

ROOT = Path(__file__).resolve().parents[4]


def test_every_stage_has_an_entry() -> None:
    stages = {e.stage for e in v.ENTRIES}
    assert set(reg.STAGES) <= stages and "time" in stages
    assert len({e.id for e in v.ENTRIES}) == len(v.ENTRIES)


def test_statuses_are_the_four_allowed_and_phrases_exist() -> None:
    for e in v.ENTRIES:
        assert e.status in v.STATUSES, e.id
        assert e.phrase and e.what and e.against, e.id


def test_verified_entries_have_evidence_and_it_exists() -> None:
    for e in v.ENTRIES:
        if e.status == "verified":
            assert e.evidence and e.residual and e.against, e.id
        for path in e.evidence:
            assert (ROOT / path).exists(), (e.id, path)


def test_no_entry_claims_more_than_the_matrix_allows() -> None:
    by = {e.id: e for e in v.ENTRIES}
    for i in ("s4.energy", "s5.rounded_ridge", "s5.multipath", "s2.rf_obstacle", "s7.mission"):
        assert by[i].status == "not_validated", i
    for i in ("s2.s3.lroc", "s2.literature", "s5.nasa_differential"):
        assert by[i].status == "plausibility_only", i
    assert by["claims.not_rerun"].status == "unknown"


def test_parameter_groups_cover_the_registry_and_follow_the_tags() -> None:
    groups = v.parameter_groups()
    keys = [k for g in groups for k in g["keys"]]
    assert sorted(keys) == sorted(reg.REGISTRY)
    for g in groups:
        assert g["status"] == ("not_validated" if g["tag"] == "I" else "verified")


def test_report_is_plain_data() -> None:
    r = v.validation_report()
    assert r["statuses"] == list(v.STATUSES) and r["stages"] and r["parameter_groups"]
