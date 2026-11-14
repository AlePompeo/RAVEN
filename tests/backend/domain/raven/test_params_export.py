# SPDX-License-Identifier: Apache-2.0
"""Generated registry metadata (RAVEN M2): committed files equal the registry (no Node needed)."""

import json
from pathlib import Path

from backend.domain.raven import export
from backend.domain.raven import params as reg

ROOT = Path(__file__).resolve().parents[4]


def test_committed_json_matches_the_registry() -> None:
    text = (ROOT / export.JSON_PATH).read_text(encoding="utf-8")
    assert text == export.params_json(), "run `python contracts/gen.py`"
    doc = json.loads(text)
    assert [p["key"] for p in doc["parameters"]] == list(reg.REGISTRY)
    assert {p["tag"] for p in doc["parameters"]} <= {"V", "D", "I"}


def test_committed_ts_matches_the_registry() -> None:
    text = (ROOT / export.TS_PATH).read_text(encoding="utf-8")
    assert text == export.params_ts(), "run `python contracts/gen.py`"
    for key in reg.REGISTRY:
        assert f'"{key}"' in text


def test_export_is_deterministic() -> None:
    assert export.params_json() == export.params_json()
    assert export.params_ts() == export.params_ts()
