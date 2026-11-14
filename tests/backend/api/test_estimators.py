# SPDX-License-Identifier: Apache-2.0
import math
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.bootstrap import build_app
from backend.contracts_models import StateEstimate

pytest.importorskip("imufusion")

URL = "/api/estimators/estimator-imu/update"
GYRO = {"gyro_x_dps": 0.0, "gyro_y_dps": 0.0, "gyro_z_dps": 30.0}


def client() -> TestClient:
    c = TestClient(build_app())
    c.headers["X-Estimator-Owner"] = c.get("/api/estimators/session").headers["X-Estimator-Owner"]
    return c


def test_update_returns_valid_state_estimate() -> None:
    r = client().post(URL, json={"measurement": GYRO, "dt_s": 0.01})
    assert r.status_code == 200
    body = r.json()
    StateEstimate.model_validate(body)
    assert "covariance" not in body
    assert "yaw_deg" in body["state"]


def test_state_persists_between_calls_per_id() -> None:
    c = client()
    c.post(URL, json={"measurement": GYRO, "dt_s": 0.01})
    r1 = c.post(URL, json={"measurement": GYRO})  # dt_s omesso: riusa l'ultimo
    r2 = c.post(URL, json={"measurement": GYRO})
    assert r2.status_code == 200
    # il filtro e' stateful: lo yaw avanza (30 dps * 0.01 s = 0.3 deg per passo)
    assert math.isclose(
        r2.json()["state"]["yaw_deg"] - r1.json()["state"]["yaw_deg"], 0.3, abs_tol=0.01
    )
    # istanza nuova dell'app: stato nuovo
    r3 = client().post(URL, json={"measurement": GYRO, "dt_s": 0.01})
    assert r3.json()["state"]["yaw_deg"] < r2.json()["state"]["yaw_deg"]


def test_unknown_id_is_404() -> None:
    assert (
        client().post("/api/estimators/nope/update", json={"measurement": GYRO}).status_code == 404
    )


def test_other_kind_id_is_404() -> None:
    r = client().post("/api/estimators/example-sim/update", json={"measurement": GYRO})
    assert r.status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"measurement": GYRO},  # nessun dt_s mai impostato -> ValueError del plugin
        {"measurement": GYRO, "dt_s": 0},
        {"measurement": GYRO, "dt_s": -1},
        {"measurement": {"gyro_x_dps": 0.0}, "dt_s": 0.01},  # chiavi mancanti
        {"measurement": {**GYRO, "accel_x_g": 0.0}, "dt_s": 0.01},  # accel parziale
    ],
)
def test_value_errors_are_422(body: dict[str, Any]) -> None:
    assert client().post(URL, json=body).status_code == 422


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "x", None])
def test_non_finite_or_non_numeric_422(bad: Any) -> None:
    c = client()
    raw = '{"measurement": {"gyro_x_dps": 0, "gyro_y_dps": 0, "gyro_z_dps": %s}, "dt_s": 0.01}' % (
        bad if bad in ("NaN", "Infinity") else ('"x"' if bad == "x" else "null")
    )
    r = c.post(URL, content=raw, headers={"content-type": "application/json"})
    assert r.status_code == 422


def test_rejected_update_keeps_state() -> None:
    c = client()
    c.post(URL, json={"measurement": GYRO, "dt_s": 0.01})
    before = c.post(URL, json={"measurement": GYRO}).json()["state"]["yaw_deg"]
    assert c.post(URL, json={"measurement": {"gyro_x_dps": 0.0}}).status_code == 422
    after = c.post(URL, json={"measurement": GYRO}).json()["state"]["yaw_deg"]
    assert math.isclose(after - before, 0.3, abs_tol=0.01)


def test_concurrent_calls_are_serialized() -> None:
    from concurrent.futures import ThreadPoolExecutor

    c = client()
    c.post(URL, json={"measurement": GYRO, "dt_s": 0.01})
    with ThreadPoolExecutor(8) as ex:
        codes = list(
            ex.map(lambda _: c.post(URL, json={"measurement": GYRO}).status_code, range(32))
        )
    assert codes == [200] * 32
    final = c.post(URL, json={"measurement": GYRO}).json()["state"]["yaw_deg"]
    # 1 + 32 + 1 passi da 0.3 deg: nessun passo perso ne' doppio
    assert math.isclose(final, 34 * 0.3, abs_tol=0.05)
