# SPDX-License-Identifier: Apache-2.0
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.bootstrap import build_app
from backend.pipeline.service import PipelineService

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)


def row(source: str, site: str, t: datetime, power: float) -> dict[str, Any]:
    return {
        "source_id": source, "site_id": site, "t_utc": t, "schema_version": "1.0.0",
        "power_w": power, "link_margin_db": None, "sun_az_deg": None, "sun_el_deg": None,
        "earth_az_deg": None, "earth_el_deg": None, "received_utc": t + timedelta(seconds=1),
        "raw_file_id": "part-x",
    }  # fmt: skip


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "100000")
    monkeypatch.delenv("PIPELINE_DIR", raising=False)


@pytest.fixture
def service(tmp_path: Path) -> PipelineService:
    svc = PipelineService(tmp_path / "pipe", clock=lambda: NOW, stale_after_s=60)
    svc.store.write(
        "clean", "a", [row("a", "s1", NOW - timedelta(minutes=m), 100.0 + m) for m in range(5)]
    )
    svc.store.write("clean", "old", [row("old", "s1", NOW - timedelta(hours=3), 1.0)])
    svc.metrics.seen("a")
    return svc


@pytest.fixture
def client(service: PipelineService) -> TestClient:
    app = build_app()
    app.state.pipeline = service
    return TestClient(app)


def test_app_without_pipeline_reports_disabled() -> None:
    c = TestClient(build_app())
    assert c.get("/api/pipeline/metrics").json() == {"enabled": False}
    assert c.get("/api/pipeline/query/latest_samples").status_code == 503


def test_metrics_json_shape(client: TestClient) -> None:
    r = client.get("/api/pipeline/metrics")
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is True
    assert set(body["layers"]) == {"raw", "clean", "curated"}
    assert body["sources"]["a"]["status"] == "ok"
    assert {"drain", "curate", "compaction", "retention"} <= set(body["jobs"])
    assert "depth" in body["queue"] and "stale_sources" in body and "quality" in body


def test_metrics_reports_stale_source(service: PipelineService, client: TestClient) -> None:
    service.metrics.register_source("quiet")
    # orologio del servizio fisso: nessuno e' stale finche' non avanza
    assert client.get("/api/pipeline/metrics").json()["stale_sources"] == []
    t = [NOW]
    service.metrics._clock = lambda: t[0]
    t[0] = NOW + timedelta(seconds=61)
    body = client.get("/api/pipeline/metrics").json()
    assert body["sources"]["quiet"]["status"] == "stale" and "quiet" in body["stale_sources"]


def test_query_latest_samples(client: TestClient) -> None:
    r = client.get(
        "/api/pipeline/query/latest_samples", params={"site_id": "s1", "source_id": "a", "limit": 2}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "latest_samples" and body["row_count"] == 2
    assert [x["power_w"] for x in body["rows"]] == [100.0, 101.0]


def test_query_power_hourly_and_stale(client: TestClient) -> None:
    r = client.get("/api/pipeline/query/power_hourly", params={"site_id": "s1", "hours": 2})
    assert r.status_code == 200 and sum(x["n"] for x in r.json()["rows"]) == 5
    r = client.get("/api/pipeline/query/stale_sources", params={"threshold_s": 3600})
    assert [x["source_id"] for x in r.json()["rows"]] == ["old"]
    assert client.get("/api/pipeline/query/power_hourly").status_code == 422  # site_id obbligatorio


@pytest.mark.parametrize(
    "name",
    [
        "nope",
        "select",
        "LATEST_SAMPLES",
        "latest_samples%3Bselect",
        "..%2F..%2Fetc",
        "a" * 100,
        "%00",
    ],
)
def test_unknown_or_malformed_query_name_is_404(client: TestClient, name: str) -> None:
    assert client.get(f"/api/pipeline/query/{name}").status_code == 404


@pytest.mark.parametrize(
    "qs",
    [
        "limit=0", "limit=-5", "limit=1001", "limit=abc", "limit=1.5", "limit=", "limit=1&limit=2",
        "limit=1e3", "unknown=1", "sql=select 1", "site_id=" + "a" * 65, "source_id=A",
        "threshold_s=-1",
    ],
)  # fmt: skip
def test_bad_params_are_422_without_echoing_input(client: TestClient, qs: str) -> None:
    r = client.get("/api/pipeline/query/latest_samples?" + qs)
    assert r.status_code == 422, qs
    assert '"input"' not in r.text and "select 1" not in r.text


INJECTIONS = [
    "x' OR '1'='1",
    "s1'; DROP TABLE clean;--",
    "%27%20OR%201%3D1--",
    "s1) UNION SELECT * FROM read_csv('/etc/passwd')--",
    "../../etc/passwd",
    "s1%00",
    "s1\n",
    "s 1",
    "\u202es1",
    "s1/**/OR/**/1=1",
]


@pytest.mark.parametrize("evil", INJECTIONS)
@pytest.mark.parametrize("name", ["latest_samples", "power_hourly"])
def test_injection_attempts_rejected(client: TestClient, name: str, evil: str) -> None:
    r = client.get(f"/api/pipeline/query/{name}", params={"site_id": evil})
    assert r.status_code == 422
    assert "passwd" not in r.text.lower().replace("../../etc/passwd", "")
    r2 = client.get(f"/api/pipeline/query/{name}", params={"site_id": "s1", "source_id": evil})
    assert r2.status_code == 422
    # i dati restano intatti e interrogabili
    assert (
        client.get("/api/pipeline/query/latest_samples", params={"site_id": "s1"}).json()[
            "row_count"
        ]
        > 0
    )


def test_only_get_is_allowed(client: TestClient) -> None:
    assert client.post("/api/pipeline/query/latest_samples").status_code == 405
    assert client.post("/api/pipeline/metrics").status_code == 405


def test_engine_failure_is_generic_500(
    service: PipelineService, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from backend.pipeline.query_spec import QueryError

    def boom(*a: Any, **k: Any) -> Any:
        raise QueryError("dettaglio interno /home/x")

    monkeypatch.setattr(service.engine, "query", boom)
    r = client.get("/api/pipeline/query/latest_samples")
    assert r.status_code == 500 and "home" not in r.text


def test_scheduler_follows_app_lifespan(service: PipelineService) -> None:
    app = build_app()
    app.state.pipeline = service
    with TestClient(app):
        assert service.scheduler._loop_task is not None
    assert service.scheduler._loop_task is None


def test_env_enables_pipeline(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PIPELINE_DIR", str(tmp_path / "p"))
    app = build_app()
    assert isinstance(app.state.pipeline, PipelineService)
    with TestClient(app) as c:
        assert c.get("/api/pipeline/metrics").json()["enabled"] is True
    monkeypatch.delenv("PIPELINE_DIR")
    assert build_app().state.pipeline is None
