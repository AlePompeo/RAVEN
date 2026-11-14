# SPDX-License-Identifier: Apache-2.0
"""Retired scientific HTTP contracts must not silently run an older model."""

import pytest
from fastapi.testclient import TestClient

from backend.bootstrap import build_app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(build_app())


@pytest.mark.parametrize(
    "path",
    [
        "/api/lunar",
        "/api/lunar/sites",
        "/api/lunar/defaults",
        "/api/lunar/analyze",
        "/api/lunar/timeline",
        "/api/lunar/solar-terrain",
        "/api/lunar/horizon",
        "/api/lunar/coupled-sensitivity",
        "/api/lunar/mission",
        "/api/grazing",
        "/api/grazing/status",
        "/api/grazing/defaults",
        "/api/grazing/analyze",
        "/api/grazing/compare",
        "/api/grazing/antenna",
        "/api/grazing/snapshot",
        "/api/grazing/scene",
        "/api/grazing/compensation",
        "/api/grazing/compensator",
        "/api/grazing/wave",
        "/api/sky",
        "/api/sky/status",
        "/api/sky/subsolar",
        "/api/sky/series",
    ],
)
@pytest.mark.parametrize("method", ["GET", "POST"])
def test_retired_contracts_return_gone(client: TestClient, path: str, method: str) -> None:
    response = client.request(method, path, params={"secret": "not-echoed"})
    assert response.status_code == 410
    assert response.json()["mission"] == "/api/raven/evaluate"
    assert "not-echoed" not in response.text


def test_only_raven_scientific_routes_are_published(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/raven/evaluate" in paths and "/api/raven/wave" in paths
    assert "/api/raven/sky/subsolar" in paths
    assert not any(path.startswith(("/api/lunar", "/api/grazing", "/api/sky")) for path in paths)
