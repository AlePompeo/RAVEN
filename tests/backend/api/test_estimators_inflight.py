# SPDX-License-Identifier: Apache-2.0
import threading
from collections.abc import Mapping
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.bootstrap import build_app

URL = "/api/estimators/any/update"


class Counting:
    """Conta gli update; se `measurement["hold"]`, resta bloccato finche' `gate` e' impostato."""

    gate = threading.Event()
    entered = threading.Event()

    def __init__(self) -> None:
        self.n = 0

    def predict(self, dt_s: float) -> None: ...

    def reset(self) -> None:
        self.n = 0

    def update(self, measurement: Mapping[str, float], dt_s: float | None = None) -> Any:
        self.n += 1
        if measurement.get("hold"):
            Counting.entered.set()
            assert Counting.gate.wait(5)
        return {"n": float(self.n)}


@pytest.fixture(autouse=True)
def _fresh_events() -> None:
    Counting.gate = threading.Event()
    Counting.entered = threading.Event()


def make_client(monkeypatch: pytest.MonkeyPatch, cap: int) -> tuple[TestClient, list[Counting]]:
    monkeypatch.setenv("ESTIMATOR_MAX_SESSIONS", str(cap))
    app = build_app()
    created: list[Counting] = []

    def make(kind: str, id: str) -> Counting:
        c = Counting()
        created.append(c)
        return c

    app.state.registry.create = make
    c = TestClient(app)
    c.headers["X-Estimator-Owner"] = c.get("/api/estimators/session").headers["X-Estimator-Owner"]
    return c, created


def post(c: TestClient, session: str, **m: float) -> Any:
    return c.post(URL, json={"measurement": m or {"x": 1.0}, "session": session})


def test_in_flight_session_is_not_evicted(monkeypatch: pytest.MonkeyPatch) -> None:
    c, created = make_client(monkeypatch, cap=2)
    codes: list[int] = []
    t = threading.Thread(target=lambda: codes.append(post(c, "busy", hold=1.0).status_code))
    t.start()
    assert Counting.entered.wait(5)  # "busy" e' dentro update(), con il lock tenuto
    for i in range(5):  # cap + 3 sessioni nuove: devono ruotare tra loro, mai evincere "busy"
        assert post(c, f"other{i}").status_code == 200
    Counting.gate.set()
    t.join(5)
    assert codes == [200]
    r = post(c, "busy")
    assert r.json()["state"]["n"] == 2.0  # stessa istanza: lo stato continua
    assert len(created) == 1 + 5  # nessuna istanza "busy" ricreata


def test_all_in_flight_at_cap_returns_503(monkeypatch: pytest.MonkeyPatch) -> None:
    c, _ = make_client(monkeypatch, cap=1)
    t = threading.Thread(target=lambda: post(c, "busy", hold=1.0))
    t.start()
    assert Counting.entered.wait(5)
    r = post(c, "new")
    assert r.status_code == 503
    assert "troppe sessioni attive" in r.text
    Counting.gate.set()
    t.join(5)
    assert post(c, "new").status_code == 200  # a carico finito la sessione entra (evince busy)


def test_inflight_counter_released_after_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    c, _ = make_client(monkeypatch, cap=1)
    assert c.post(URL, json={"measurement": {"x": "bad"}, "session": "a"}).status_code == 422
    assert post(c, "a").status_code == 200
    assert post(c, "b").status_code == 200  # "a" non e' rimasta in-flight
