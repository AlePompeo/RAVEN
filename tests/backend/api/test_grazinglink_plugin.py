# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from backend.bootstrap import build_app


def test_grazinglink_plugin_is_discoverable_and_uses_the_link_engine() -> None:
    client = TestClient(build_app())
    plugins = client.get("/api/plugins").json()["plugins"]
    assert any(p["id"] == "grazinglink-link" and p["kind"] == "simulation" for p in plugins)

    def run(elevation: float, radius: float) -> dict[str, float]:
        r = client.post(
            "/api/simulations/grazinglink-link/run",
            json={"inputs": {"earth_el_deg": elevation, "ridge_radius_m": radius}},
        )
        assert r.status_code == 200
        return r.json()["outputs"]

    low, high, wide = run(0.3, 100), run(8, 100), run(0.3, 1000)
    assert low["profile_synthetic"] == 1
    assert low["earth_below_horizon"] == 0
    assert run(-1, 100)["earth_below_horizon"] == 1
    assert high["margin_db"] > low["margin_db"]
    assert wide["ridge_correction_db"] != low["ridge_correction_db"]
    assert low["fspl_db"] == pytest.approx(222.629, abs=0.01)


def test_grazinglink_fspl_agrees_with_c_plugin() -> None:
    client = TestClient(build_app())
    plugins = client.get("/api/plugins").json()["plugins"]
    if not any(p["id"] == "fspl-c" for p in plugins):
        pytest.skip("fspl-c non compilato: make build-c")
    response = client.post(
        "/api/simulations/grazinglink-link/run",
        json={"inputs": {"earth_el_deg": 0.3, "ridge_radius_m": 100}},
    )
    assert response.status_code == 200
    low = response.json()["outputs"]
    c_result = client.post(
        "/api/simulations/fspl-c/run",
        json={"inputs": {"distance_km": low["distance_km"], "freq_ghz": low["frequency_ghz"]}},
    )
    assert c_result.status_code == 200
    assert c_result.json()["outputs"]["fspl_db"] == pytest.approx(low["fspl_db"], abs=0.01)


@pytest.mark.parametrize(
    "inputs",
    [
        {},
        {"earth_el_deg": 1},
        {"earth_el_deg": 1, "ridge_radius_m": 0},
        {"earth_el_deg": 61, "ridge_radius_m": 100},
        {"earth_el_deg": 1, "ridge_radius_m": 100, "rate_bps": 123},
        {"earth_el_deg": 1, "ridge_radius_m": 100, "unknown": 1},
    ],
)
def test_grazinglink_plugin_rejects_invalid_inputs(inputs: dict[str, float]) -> None:
    r = TestClient(build_app()).post(
        "/api/simulations/grazinglink-link/run", json={"inputs": inputs}
    )
    assert r.status_code == 502
