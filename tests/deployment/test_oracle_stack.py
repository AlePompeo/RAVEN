# SPDX-License-Identifier: Apache-2.0
"""Opt-in checks against the actual production stack, not an in-process test app.

RAVEN_DEPLOY_TEST_URL=http://127.0.0.1:8080 .venv/bin/python -m pytest tests/deployment
For the isolated local proxy rate test, also set RAVEN_TEST_PROXY_RATE_LIMIT=3
and start the stack with RATE_LIMIT_PER_MIN=3. Never run that test on a public origin.
"""

import itertools
import os
import re
from collections.abc import Iterator
from urllib.parse import urljoin, urlsplit

import httpx
import pytest

from backend.domain.raven.meta import MODEL_VERSION, registry_sha256
from backend.domain.raven.validation import validation_report

URL = os.environ.get("RAVEN_DEPLOY_TEST_URL", "")
LOCAL = urlsplit(URL).hostname in ("127.0.0.1", "::1", "localhost")
pytestmark = pytest.mark.skipif(not URL, reason="set RAVEN_DEPLOY_TEST_URL to a running stack")
_CLIENTS = itertools.count(1)


@pytest.fixture
def client() -> Iterator[httpx.Client]:
    # Emulate Cloudflare only through the explicitly selected local test proxy.
    headers = {"CF-Connecting-IP": f"192.0.2.{next(_CLIENTS)}"} if LOCAL else {}
    with httpx.Client(base_url=URL, headers=headers, timeout=120) as c:
        yield c


def test_frontend_and_hardened_api_share_the_origin(client: httpx.Client) -> None:
    page = client.get("/")
    assert page.status_code == 200 and "text/html" in page.headers["content-type"]
    assert "set-cookie" not in page.headers
    scripts = re.findall(r'<script\b[^>]*src=["\']([^"\']+)', page.text)
    assert scripts
    for src in scripts:
        asset_url = urljoin(f"{URL.rstrip('/')}/", src)
        assert urlsplit(asset_url).netloc == urlsplit(URL).netloc
        asset = client.get(asset_url)
        assert asset.status_code == 200 and "javascript" in asset.headers["content-type"]
    model = client.get("/api/raven/model")
    assert model.status_code == 200
    assert model.json()["model_version"] == MODEL_VERSION
    assert model.json()["registry_sha256"] == registry_sha256()
    assert model.json()["validation"] == validation_report()
    assert model.headers["x-content-type-options"] == "nosniff"
    assert model.headers["strict-transport-security"].startswith("max-age=")
    assert client.get("/api/lunar").status_code == 410


def test_persisted_terrain_and_real_calculation(client: httpx.Client) -> None:
    sites = client.get("/api/raven/sites")
    assert sites.status_code == 200 and sites.json()["ephemeris"]["available"] is True
    terrain = client.get("/api/raven/horizon", params={"site": "malapert-massif"})
    assert terrain.status_code == 200 and terrain.json()["state"] == "ok"
    assert (
        client.get("/api/raven/horizon", params={"site": "apollo11"}).json()["state"]
        == "outside_coverage"
    )
    result = client.post(
        "/api/raven/evaluate",
        json={
            "site_id": "malapert-massif",
            "start_utc": "2027-01-01T00:00:00Z",
            "days": 0.125,
            "step_min": 60,
        },
    )
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["implemented_stages"][-1] == "s7"
    assert body["mask"]["complete_azimuth_fraction"] == 1.0
    assert body["window"]["n_steps"] == 3
    assert all(len(series) == 3 for series in body["steps"].values())


def test_assistant_stream_survives_the_proxy(client: httpx.Client) -> None:
    events: list[str] = []
    with client.stream(
        "POST",
        "/api/assistant/chat",
        json={
            "messages": [{"role": "user", "content": "Why does lunar terrain matter?"}],
            "lang": "en",
        },
    ) as stream:
        assert stream.status_code == 200
        assert stream.headers["content-type"].startswith("text/event-stream")
        assert "no-cache" in stream.headers["cache-control"]
        for line in stream.iter_lines():
            if line.startswith("event:"):
                events.append(line.partition(":")[2].strip())
    assert "meta" in events and "token" in events and "done" in events
    assert "error" not in events


def test_public_training_is_explicitly_disabled(client: httpx.Client) -> None:
    for method, path in (("POST", "/api/train"), ("GET", "/api/jobs/example")):
        response = client.request(method, path)
        assert response.status_code == 403
        assert "disabled" in response.json()["detail"]


def test_estimator_owner_is_preserved_by_the_proxy(client: httpx.Client) -> None:
    url = "/api/estimators/estimator-imu/update"
    gyro = {"gyro_x_dps": 0, "gyro_y_dps": 0, "gyro_z_dps": 30}
    first = client.post(url, json={"measurement": gyro, "dt_s": 0.01})
    assert first.status_code == 200 and "set-cookie" not in first.headers
    assert first.headers["cache-control"] == "no-store"
    owner = {"X-Estimator-Owner": first.headers["X-Estimator-Owner"]}
    assert client.post(url, json={"measurement": gyro}).status_code == 422
    assert client.post("/api/estimators/estimator-imu/reset", json={}).status_code == 200
    resumed = client.post(url, json={"measurement": gyro}, headers=owner)
    assert resumed.status_code == 200
    assert resumed.json()["state"]["yaw_deg"] == pytest.approx(0.6, abs=0.01)
    assert (
        client.post(
            url, json={"measurement": gyro}, headers={"X-Estimator-Owner": "forged"}
        ).status_code
        == 403
    )


@pytest.mark.skipif(
    not (LOCAL and os.environ.get("RAVEN_TEST_PROXY_RATE_LIMIT") == "3"),
    reason="requires an isolated loopback proxy with rate limit 3",
)
def test_spoofed_xff_cannot_bypass_per_client_limits(client: httpx.Client) -> None:
    for i in range(3):
        assert (
            client.get(
                "/api/raven/model", headers={"X-Forwarded-For": f"198.51.100.{i}"}
            ).status_code
            == 200
        )
    rejected = client.get("/api/raven/model", headers={"X-Forwarded-For": "198.51.100.99"})
    assert rejected.status_code == 429 and int(rejected.headers["retry-after"]) > 0
    assert (
        client.get("/api/raven/model", headers={"CF-Connecting-IP": "192.0.2.250"}).status_code
        == 200
    )
    assert client.get("/health").status_code == 200
