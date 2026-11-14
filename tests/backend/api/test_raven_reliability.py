# SPDX-License-Identifier: Apache-2.0
import math
from dataclasses import asdict

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.raven_report import build_report_router
from backend.domain.raven.reliability import Component


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(build_report_router())
    return TestClient(app)


def study(**changes: float | None) -> dict:
    component = asdict(
        Component(
            "computer",
            launch_failure_probability=0,
            landing_failure_probability=0,
            launch_loss_fraction=0,
            landing_loss_fraction=0,
            failure_rate_per_hour=0,
            upset_rate_per_hour=0,
            restart_success_probability=1,
            mean_recovery_hours=0,
            degradation_rate_per_hour=0,
            minimum_performance_fraction=0.8,
            thermal_min_c=-20,
            thermal_max_c=40,
            rated_min_c=-40,
            rated_max_c=85,
            dose_rate_krad_h=0.001,
            shield_transmission=0.5,
            tid_limit_krad=10,
        )
    )
    component.update(changes)
    return {
        "profile": {
            "enabled": True,
            "basis": "Synthetic test assumptions, not qualified hardware.",
            "launch_success_probability": 1,
            "cruise_success_probability": 1,
            "landing_success_probability": 1,
            "cruise_hours": 10,
            "components": [component],
        },
        "windows": [{"id": "A", "start_unix": 1800000000, "step_hours": 1, "useful": [True] * 10}],
    }


def result(client: TestClient, body: dict) -> dict:
    response = client.post("/api/raven/report/reliability", json=body)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["qualification"] == "not_validated"
    return data["scenarios"][0]


def test_series_shocks_and_absorbing_hazard_have_analytic_integral(client: TestClient) -> None:
    body = study(
        launch_failure_probability=0.1, landing_failure_probability=0.2, failure_rate_per_hour=0.01
    )
    body["profile"]["launch_success_probability"] = 0.9
    r = result(client, body)
    initial = 0.9 * 0.9 * 0.8
    assert r["hardware_survival_probability"] == pytest.approx(initial * math.exp(-0.1))
    assert r["expected_available_hours"] == pytest.approx(initial * -math.expm1(-0.1) / 0.01)
    assert r["expected_unavailable_hours"] == pytest.approx(10 - r["expected_available_hours"])
    assert r["stages"][0]["survival_probability"] == pytest.approx(0.81)


def test_recovery_is_not_counted_as_permanent_failure(client: TestClient) -> None:
    r = result(client, study(upset_rate_per_hour=0.5, mean_recovery_hours=2))
    assert r["hardware_survival_probability"] == 1
    assert r["conditional_operational_probability"] == pytest.approx(0.5 + 0.5 * math.exp(-10))
    assert r["expected_available_hours"] == pytest.approx(5 + 0.5 * -math.expm1(-10))
    c = r["components"][0]
    assert c["expected_restart_count_full_exposure"] == 5
    assert c["malfunction_probability"] == pytest.approx(-math.expm1(-5))
    instant = result(client, study(upset_rate_per_hour=100, mean_recovery_hours=0))
    assert instant["expected_available_hours"] == 10
    failed_restart = result(client, study(upset_rate_per_hour=0.1, restart_success_probability=0))
    assert failed_restart["hardware_survival_probability"] == pytest.approx(math.exp(-1))


def test_independent_series_recovery_integrates_cross_terms(client: TestClient) -> None:
    body = study(upset_rate_per_hour=0.2, mean_recovery_hours=1)
    other = {**body["profile"]["components"][0], "id": "radio"}
    body["profile"]["components"].append(other)
    r = result(client, body)
    a, b = 1 / 1.2, 0.2 / 1.2
    expected = a * a * 10 + 2 * a * b * -math.expm1(-12) / 1.2 + b * b * -math.expm1(-24) / 2.4
    assert r["expected_available_hours"] == pytest.approx(expected)
    assert r["conditional_operational_probability"] == pytest.approx((a + b * math.exp(-12)) ** 2)


def test_degradation_crossing_interrupts_operation_and_includes_cruise(client: TestClient) -> None:
    r = result(
        client,
        study(
            launch_loss_fraction=0.1,
            landing_loss_fraction=0.1,
            degradation_rate_per_hour=0.01,
            minimum_performance_fraction=0.7,
        ),
    )
    crossing = math.log(0.81 / 0.7) / 0.01 - 10
    assert r["components"][0]["performance_cutoff_hours"] == pytest.approx(crossing)
    assert r["conditional_operational_probability"] == 0
    assert r["hardware_survival_probability"] == 1
    assert r["expected_available_hours"] == pytest.approx(crossing)


def test_performance_already_below_minimum_is_unavailable_at_surface_start(
    client: TestClient,
) -> None:
    r = result(client, study(landing_loss_fraction=0.5))
    assert r["expected_available_hours"] == 0
    assert r["components"][0]["performance_cutoff_hours"] == 0
    assert r["timeline"][0]["conditional_operational"] == 0
    assert r["timeline"][0]["hardware_survival"] == 1


def test_unknowns_stay_unknown_but_explicit_zero_and_bounds_are_preserved(
    client: TestClient,
) -> None:
    body = study()
    body["windows"][0]["useful"] = [True, None, False]
    r = result(client, body)
    assert r["expected_useful_hours"] is None
    assert r["expected_useful_lower_hours"] == 1
    assert r["expected_useful_upper_hours"] == 2
    missing = result(client, study(failure_rate_per_hour=None))
    assert missing["hardware_survival_probability"] is None
    assert missing["expected_available_hours"] is None
    assert "failure_rate_per_hour" in missing["components"][0]["missing"]
    missing_recovery = result(client, study(mean_recovery_hours=None))
    assert missing_recovery["hardware_survival_probability"] == 1
    assert missing_recovery["expected_available_hours"] is None
    body = study()
    body["profile"]["launch_success_probability"] = 0
    assert result(client, body)["expected_available_hours"] == 0


def test_thermal_and_radiation_checks_do_not_invent_failure_probabilities(
    client: TestClient,
) -> None:
    r = result(client, study(thermal_min_c=-100, dose_rate_krad_h=10))
    c = r["components"][0]
    assert c["thermal_margin_c"] == -60
    assert c["dose_krad"] == 100 and c["radiation_margin_krad"] == -90
    assert c["environment_status"] == "outside_declared_envelope"
    assert (
        c["failure_probability"] == 0
    )  # Conditional rate arithmetic, not an environmental prediction.
    unknown = result(client, study(shield_transmission=None))
    assert unknown["components"][0]["dose_krad"] is None
    assert unknown["components"][0]["environment_status"] == "unknown"


@pytest.mark.parametrize(
    "change",
    [
        {"failure_rate_per_hour": True},
        {"launch_failure_probability": 1.1},
        {"upset_rate_per_hour": -1},
        {"thermal_min_c": 90, "thermal_max_c": 20},
        {"rated_min_c": -300},
        {"mean_recovery_hours": 1e-10},
    ],
)
def test_invalid_component_inputs_are_rejected(client: TestClient, change: dict) -> None:
    assert client.post("/api/raven/report/reliability", json=study(**change)).status_code == 422


def test_missing_source_and_duplicate_components_are_rejected(client: TestClient) -> None:
    body = study()
    body["profile"]["basis"] = ""
    assert client.post("/api/raven/report/reliability", json=body).status_code == 422
    body = study()
    body["profile"]["components"] *= 2
    assert client.post("/api/raven/report/reliability", json=body).status_code == 422


def test_extreme_valid_small_inputs_do_not_leak_nonfinite_results(client: TestClient) -> None:
    r = result(client, study(minimum_performance_fraction=5e-324, degradation_rate_per_hour=5e-324))
    assert r["expected_available_hours"] == 10
    assert r["components"][0]["performance_cutoff_hours"] is None
