# SPDX-License-Identifier: Apache-2.0
import math
from typing import Any

from fastapi.testclient import TestClient

from backend.bootstrap import build_app
from backend.core.errors import InvalidOutput, SimulationTimeout


def client() -> TestClient:
    return TestClient(build_app())


def _with_fake(fake: Any) -> TestClient:
    app = build_app()
    app.state.registry.create = lambda kind, id: fake
    return TestClient(app)


def test_health_and_security_headers() -> None:
    r = client().get("/health")
    assert r.status_code == 200
    assert r.headers["content-security-policy"] == "default-src 'self'"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert "strict-transport-security" not in r.headers
    assert "set-cookie" not in r.headers


def test_hsts_only_in_prod(monkeypatch: Any) -> None:
    monkeypatch.setenv("ENV", "prod")
    assert "strict-transport-security" in client().get("/health").headers


def test_cors_default_none_and_configured(monkeypatch: Any) -> None:
    h = {"Origin": "https://evil.example"}
    assert "access-control-allow-origin" not in client().get("/health", headers=h).headers
    monkeypatch.setenv("CORS_ORIGINS", "https://ok.example")
    c = client()
    ok = c.get("/health", headers={"Origin": "https://ok.example"})
    assert ok.headers["access-control-allow-origin"] == "https://ok.example"
    assert "access-control-allow-origin" not in c.get("/health", headers=h).headers


def test_plugins_listing_exposes_errors() -> None:
    body = client().get("/api/plugins").json()
    assert any(p["id"] == "example-sim" for p in body["plugins"])
    assert isinstance(body["errors"], list)


def test_run_example_sim() -> None:
    r = client().post("/api/simulations/example-sim/run", json={"inputs": {"x": 3.0}})
    assert r.json()["outputs"]["y"] == 9.0


def test_unknown_sim_is_404() -> None:
    assert client().post("/api/simulations/nope/run", json={"inputs": {}}).status_code == 404


def test_non_numeric_inputs_rejected_422() -> None:
    r = client().post("/api/simulations/example-sim/run", json={"inputs": {"x": "a"}})
    assert r.status_code == 422


def test_timeout_maps_to_504() -> None:
    class Slow:
        async def run(self, inputs: Any, *, timeout_s: float) -> Any:
            raise SimulationTimeout("t")

    assert _with_fake(Slow()).post("/api/simulations/x/run", json={"inputs": {}}).status_code == 504


def test_invalid_output_maps_to_502() -> None:
    class Bad:
        async def run(self, inputs: Any, *, timeout_s: float) -> Any:
            raise InvalidOutput("x")

    assert _with_fake(Bad()).post("/api/simulations/x/run", json={"inputs": {}}).status_code == 502


def test_manifest_timeout_is_passed() -> None:
    seen: dict[str, float] = {}

    class Spy:
        async def run(self, inputs: Any, *, timeout_s: float) -> Any:
            seen["t"] = timeout_s
            return {"y": 1.0}

    app = build_app()
    app.state.registry.create = lambda kind, id: Spy()
    TestClient(app).post("/api/simulations/example-sim/run", json={"inputs": {}})
    assert seen["t"] == 5


def test_nan_inf_outputs_never_reach_client() -> None:
    class Nan:
        async def run(self, inputs: Any, *, timeout_s: float) -> Any:
            return {"y": math.nan, "z": math.inf}

    r = _with_fake(Nan()).post("/api/simulations/x/run", json={"inputs": {}})
    assert r.status_code == 502
    assert "nan" not in r.text.lower() and "inf" not in r.text.lower()


def test_nan_input_rejected() -> None:
    r = client().post(
        "/api/simulations/example-sim/run",
        content='{"inputs": {"x": NaN}}',
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 422


def test_rate_limit_returns_429(monkeypatch: Any) -> None:
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "3")
    c = client()
    codes = [c.get("/api/plugins").status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]
    assert "retry-after" in c.get("/api/plugins").headers
    assert c.get("/health").status_code == 200  # health non limitato
