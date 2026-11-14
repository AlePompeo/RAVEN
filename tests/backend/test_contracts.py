# SPDX-License-Identifier: Apache-2.0
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[2]

SAMPLE: dict[str, Any] = {
    "schema_version": "1.0.0",
    "t_utc": "2026-10-12T10:00:00Z",
    "site_id": "shackleton-1",
    "power_w": 12.5,
    "link_margin_db": 3.2,
    "sun": {"az_deg": 10.0, "el_deg": 1.5},
    "earth": {"az_deg": 200.0, "el_deg": 5.0},
}

ESTIMATE: dict[str, Any] = {
    "schema_version": "1.0.0",
    "t_utc": "2026-10-12T10:00:00Z",
    "state": {"yaw_deg": 0.0, "pitch_deg": 1.0},
}


def _validator(name: str) -> Draft202012Validator:
    schema = json.loads((ROOT / f"contracts/{name}.schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def test_schema_requires_version_and_utc() -> None:
    s = json.loads((ROOT / "contracts/telemetry.schema.json").read_text())
    assert "schema_version" in s["required"] and "t_utc" in s["required"]


def test_valid_samples_pass() -> None:
    _validator("telemetry").validate(SAMPLE)
    _validator("telemetry").validate({k: SAMPLE[k] for k in list(SAMPLE)[:4]})
    _validator("state_estimate").validate(ESTIMATE)


@pytest.mark.parametrize("name,sample", [("telemetry", SAMPLE), ("state_estimate", ESTIMATE)])
@pytest.mark.parametrize("missing", ["schema_version", "t_utc"])
def test_missing_required_rejected(name: str, sample: dict[str, Any], missing: str) -> None:
    bad = {k: v for k, v in sample.items() if k != missing}
    assert not _validator(name).is_valid(bad)


@pytest.mark.parametrize("name,sample", [("telemetry", SAMPLE), ("state_estimate", ESTIMATE)])
def test_extra_field_rejected(name: str, sample: dict[str, Any]) -> None:
    assert not _validator(name).is_valid({**sample, "extra": 1})


def test_bad_values_rejected() -> None:
    v = _validator("telemetry")
    assert not v.is_valid({**SAMPLE, "schema_version": "one"})
    assert not v.is_valid({**SAMPLE, "t_utc": "yesterday"})
    assert not v.is_valid({**SAMPLE, "sun": {"az_deg": 1.0}})


@pytest.mark.skipif(
    not (ROOT / "frontend/node_modules/.bin/json2ts").exists(),
    reason="run `npm ci` in frontend/ to enable the contracts drift check",
)
def test_generated_files_are_in_sync() -> None:
    r = subprocess.run([sys.executable, "contracts/gen.py", "--check"], check=False, cwd=ROOT)
    assert r.returncode == 0
