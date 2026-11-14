# SPDX-License-Identifier: Apache-2.0
import math
import threading
import time
from collections.abc import Mapping
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.bootstrap import build_app

URL = "/api/estimators/estimator-imu/update"
RESET = "/api/estimators/estimator-imu/reset"
GYRO = {"gyro_x_dps": 0.0, "gyro_y_dps": 0.0, "gyro_z_dps": 30.0}


def imu_client() -> TestClient:
    pytest.importorskip("imufusion")
    c = TestClient(build_app())
    c.headers["X-Estimator-Owner"] = c.get("/api/estimators/session").headers["X-Estimator-Owner"]
    return c


def yaw(c: TestClient, session: str | None = None, dt: float | None = None) -> float:
    body: dict[str, Any] = {"measurement": GYRO}
    if session:
        body["session"] = session
    if dt:
        body["dt_s"] = dt
    r = c.post(URL, json=body)
    assert r.status_code == 200, r.text
    return float(r.json()["state"]["yaw_deg"])


def fake_client(factory: Any, monkeypatch: pytest.MonkeyPatch | None = None) -> TestClient:
    app = build_app()
    app.state.registry.create = lambda kind, id: factory()
    c = TestClient(app)
    c.headers["X-Estimator-Owner"] = c.get("/api/estimators/session").headers["X-Estimator-Owner"]
    return c


class Fake:
    def __init__(self) -> None:
        self.n = 0

    def predict(self, dt_s: float) -> None: ...

    def reset(self) -> None:
        self.n = 0

    def update(self, measurement: Mapping[str, float], dt_s: float | None = None) -> Any:
        self.n += 1
        return {"n": float(self.n)}


FAKE_URL = "/api/estimators/any/update"


# (1) atomicita' di dt
def test_422_with_dt_leaves_state_and_dt_unchanged() -> None:
    c = imu_client()
    yaw(c, dt=0.01)
    base = yaw(c)
    bad = c.post(URL, json={"measurement": {"gyro_x_dps": 0.0}, "dt_s": 0.5})
    assert bad.status_code == 422
    after = yaw(c)
    assert math.isclose(after - base, 0.3, abs_tol=0.01)  # dt ancora 0.01, non 0.5


def test_422_first_call_with_dt_does_not_set_dt() -> None:
    c = imu_client()
    assert c.post(URL, json={"measurement": {"gyro_x_dps": 0.0}, "dt_s": 0.5}).status_code == 422
    r = c.post(URL, json={"measurement": GYRO})  # nessun dt valido mai impostato
    assert r.status_code == 422


# (2) sessioni
def test_sessions_are_independent() -> None:
    c = imu_client()
    yaw(c, "a", dt=0.01)
    yaw(c, "b", dt=0.01)
    a2 = yaw(c, "a")
    a3 = yaw(c, "a")
    b2 = yaw(c, "b")
    assert a3 > a2 > b2 - 0.0001 and math.isclose(a3 - a2, 0.3, abs_tol=0.01)
    assert math.isclose(b2, 0.6, abs_tol=0.01)  # b ha fatto solo 2 passi


@pytest.mark.parametrize("bad", ["", "a b", "a/b", "x" * 65, "à"])
def test_bad_session_422(bad: str) -> None:
    r = imu_client().post(URL, json={"measurement": GYRO, "dt_s": 0.01, "session": bad})
    assert r.status_code == 422


def test_reset_returns_to_initial_state() -> None:
    c = imu_client()
    yaw(c, "s", dt=0.01)
    yaw(c, "s")
    assert c.post(RESET, json={"session": "s"}).status_code == 200
    # dopo il reset dt va reimpostato e l'assetto riparte da zero
    assert c.post(URL, json={"measurement": GYRO, "session": "s"}).status_code == 422
    assert math.isclose(yaw(c, "s", dt=0.01), 0.3, abs_tol=0.01)


def test_reset_only_affects_its_session_and_unknown_is_404() -> None:
    c = imu_client()
    yaw(c, "a", dt=0.01)
    yaw(c, "a")
    yaw(c, "b", dt=0.01)
    c.post(RESET, json={"session": "b"})
    assert math.isclose(yaw(c, "a"), 0.9, abs_tol=0.02)
    assert c.post("/api/estimators/nope/reset", json={}).status_code == 404
    assert c.post(RESET, json={"session": "bad session"}).status_code == 422


def test_lru_cap_holds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ESTIMATOR_MAX_SESSIONS", "2")
    app = build_app()
    created: list[Fake] = []

    def make(kind: str, id: str) -> Fake:
        f = Fake()
        created.append(f)
        return f

    app.state.registry.create = make
    c = TestClient(app)
    c.headers["X-Estimator-Owner"] = c.get("/api/estimators/session").headers["X-Estimator-Owner"]

    def hit(s: str) -> float:
        r = c.post(FAKE_URL, json={"measurement": {"x": 1.0}, "session": s})
        assert r.status_code == 200
        return float(r.json()["state"]["n"])

    assert hit("a") == 1
    assert hit("b") == 1
    assert hit("a") == 2  # a e' piu' recente di b
    assert hit("c") == 1  # evince b (LRU)
    assert len(created) == 3
    assert hit("a") == 3  # a sopravvive
    assert hit("b") == 1  # b e' stato evinto: stato nuovo
    assert len(created) == 4


# (3) mappatura errori
def test_foreign_value_error_is_not_echoed() -> None:
    class Leaky(Fake):
        def update(self, measurement: Mapping[str, float], dt_s: float | None = None) -> Any:
            raise ValueError("internal/path/secret")

    c = fake_client(Leaky)
    r = c.post(FAKE_URL, json={"measurement": {"x": 1.0}})
    assert r.status_code == 502
    assert "secret" not in r.text and "internal" not in r.text


def test_unexpected_exception_is_502_generic() -> None:
    class Boom(Fake):
        def update(self, measurement: Mapping[str, float], dt_s: float | None = None) -> Any:
            raise RuntimeError("numpy exploded at /srv/x")

    r = fake_client(Boom).post(FAKE_URL, json={"measurement": {"x": 1.0}})
    assert r.status_code == 502
    assert "numpy" not in r.text and "/srv" not in r.text


def test_own_validation_error_is_422_with_message() -> None:
    from backend.core.errors import InvalidMeasurement

    class Strict(Fake):
        def update(self, measurement: Mapping[str, float], dt_s: float | None = None) -> Any:
            raise InvalidMeasurement("gyro_z_dps non finito")

    r = fake_client(Strict).post(FAKE_URL, json={"measurement": {"x": 1.0}})
    assert r.status_code == 422
    assert "gyro_z_dps" in r.text


# (4) lock per sessione, create fuori dal lock
def test_slow_session_does_not_block_another() -> None:
    gate = threading.Event()
    entered = threading.Event()

    class Slow(Fake):
        def update(self, measurement: Mapping[str, float], dt_s: float | None = None) -> Any:
            if measurement.get("slow"):
                entered.set()
                gate.wait(5)
            return super().update(measurement, dt_s)

    c = fake_client(Slow)
    result: dict[str, int] = {}
    t = threading.Thread(
        target=lambda: result.update(
            code=c.post(FAKE_URL, json={"measurement": {"slow": 1.0}, "session": "s1"}).status_code
        )
    )
    t.start()
    assert entered.wait(5)
    t0 = time.monotonic()
    r = c.post(FAKE_URL, json={"measurement": {"x": 1.0}, "session": "s2"})
    assert r.status_code == 200 and time.monotonic() - t0 < 2
    gate.set()
    t.join(5)
    assert result["code"] == 200


def test_registry_create_not_called_under_lock() -> None:
    gate = threading.Event()
    entered = threading.Event()
    app = build_app()
    calls: list[str] = []

    def make(kind: str, id: str) -> Fake:
        calls.append(id)
        if len(calls) == 1:
            entered.set()
            gate.wait(5)
        return Fake()

    app.state.registry.create = make
    c = TestClient(app)
    c.headers["X-Estimator-Owner"] = c.get("/api/estimators/session").headers["X-Estimator-Owner"]
    t = threading.Thread(
        target=lambda: c.post(FAKE_URL, json={"measurement": {"x": 1.0}, "session": "s1"})
    )
    t.start()
    assert entered.wait(5)
    r = c.post(FAKE_URL, json={"measurement": {"x": 1.0}, "session": "s2"})
    assert r.status_code == 200  # non bloccata dalla create lenta di s1
    gate.set()
    t.join(5)


def test_clients_cannot_share_or_reset_a_guessed_session() -> None:
    pytest.importorskip("imufusion")
    app = build_app()
    a, b = TestClient(app), TestClient(app)
    for c in (a, b):
        c.headers["X-Estimator-Owner"] = c.get("/api/estimators/session").headers[
            "X-Estimator-Owner"
        ]
    for session in ("default", "known-name"):
        assert yaw(a, session, dt=0.01) == pytest.approx(0.3, abs=0.01)
        assert b.post(URL, json={"session": session, "measurement": GYRO}).status_code == 422
        assert b.post(RESET, json={"session": session}).status_code == 200
        assert yaw(a, session) == pytest.approx(0.6, abs=0.01)


def test_missing_owner_never_reuses_another_clients_default_state() -> None:
    pytest.importorskip("imufusion")
    c = TestClient(build_app())
    first = c.post(URL, json={"measurement": GYRO, "dt_s": 0.01})
    assert first.status_code == 200 and "X-Estimator-Owner" in first.headers
    assert "set-cookie" not in first.headers
    assert first.headers["cache-control"] == "no-store"
    assert c.post(URL, json={"measurement": GYRO}).status_code == 422
    resumed = c.post(
        URL,
        json={"measurement": GYRO},
        headers={"X-Estimator-Owner": first.headers["X-Estimator-Owner"]},
    )
    assert resumed.json()["state"]["yaw_deg"] == pytest.approx(0.6, abs=0.01)


@pytest.mark.parametrize("owner", ["default", "A" * 43 + "." + "0" * 64, "A" * 43 + "." + "z" * 64])
def test_forged_owner_is_rejected(owner: str) -> None:
    c = fake_client(Fake)
    assert (
        c.post(
            FAKE_URL,
            json={"measurement": {"x": 1.0}},
            headers={"X-Estimator-Owner": owner},
        ).status_code
        == 403
    )
