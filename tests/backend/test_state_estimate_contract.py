# SPDX-License-Identifier: Apache-2.0
"""state_estimate: state e' una mappa nome->numero, covarianza opzionale."""

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from backend.contracts_models import StateEstimate

ROOT = Path(__file__).resolve().parents[2]
BASE: dict[str, Any] = {
    "schema_version": "1.0.0",
    "t_utc": "2026-10-12T10:00:00Z",
    "state": {"yaw_deg": 10.0, "pitch_deg": -1.5},
}


def validator() -> Draft202012Validator:
    schema = json.loads((ROOT / "contracts/state_estimate.schema.json").read_text())
    return Draft202012Validator(schema, format_checker=FormatChecker())


@pytest.mark.parametrize(
    "extra",
    [
        {},
        {"state_order": ["yaw_deg", "pitch_deg"], "covariance": [[1.0, 0.0], [0.0, 1.0]]},
        {"covariance": [[1.0, 0.0], [0.0, 1.0]]},
    ],
)
def test_valid(extra: dict[str, Any]) -> None:
    msg = BASE | extra
    assert validator().is_valid(msg)
    StateEstimate.model_validate(msg)


@pytest.mark.parametrize(
    "bad",
    [
        BASE | {"state": [0.0, 1.0]},  # vecchio formato array
        BASE | {"state": {}},
        BASE | {"state": {"yaw_deg": "x"}},
        BASE | {"state": {"yaw_deg": None}},
        BASE | {"schema_version": "1"},
        BASE | {"t_utc": "ieri"},
        BASE | {"state_order": []},
        BASE | {"covariance": []},
        BASE | {"covariance": [[]]},
        BASE | {"covariance": [["x"]]},
        BASE | {"extra": 1},
    ],
)
def test_invalid(bad: dict[str, Any]) -> None:
    assert not validator().is_valid(bad)
    with pytest.raises(ValueError):
        StateEstimate.model_validate(bad)


def test_duplicate_state_order_rejected_by_schema() -> None:
    # uniqueItems non e' imposto dal modello Pydantic generato: solo lo schema lo verifica.
    assert not validator().is_valid(BASE | {"state_order": ["a", "a"]})


def test_imu_estimator_output_is_a_valid_message() -> None:
    pytest.importorskip("imufusion")
    from backend.core.manifest import load_manifest
    from backend.plugins.estimator_imu.plugin import ImuEstimator

    est = ImuEstimator(load_manifest(ROOT / "backend/plugins/estimator_imu/manifest.toml"))
    est.predict(0.01)
    state = dict(est.update({"gyro_x_dps": 0.0, "gyro_y_dps": 0.0, "gyro_z_dps": 30.0}))
    msg = {"schema_version": "1.0.0", "t_utc": "2026-10-12T10:00:00Z", "state": state}
    assert validator().is_valid(msg)  # nessuna covarianza inventata
    assert "covariance" not in msg
    StateEstimate.model_validate(msg)
