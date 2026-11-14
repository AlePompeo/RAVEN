# SPDX-License-Identifier: Apache-2.0
"""Rotte /api/lunar con i kernel reali (saltati se assenti) e senza kernel (503)."""

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("numpy")

from backend.ephemeris import kernels
from scripts.raven_reference import build_reference_app as build_app

try:
    kernels.require_kernels()
    HAVE = True
except kernels.EphemerisUnavailable:  # pragma: no cover
    HAVE = False

needs_kernels = pytest.mark.skipif(not HAVE, reason="kernels missing (make ephemeris)")
BODY: dict[str, Any] = {
    "site_ids": ["apollo11", "malapert-massif"],
    "start_utc": "2026-12-22T00:00:00Z",
    "days": 5,
    "step_min": 30,
}


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(build_app())


def test_sites_and_defaults(client: TestClient) -> None:
    s = client.get("/api/lunar/sites").json()
    assert len(s["sites"]) == 51 and len(s["dsn_stations"]) == 3
    assert all(d["verified"] for d in s["dsn_stations"])
    d = client.get("/api/lunar/defaults").json()
    rows = {r["key"]: r for r in d["parameters"]}
    assert (
        rows["required_margin_db"]["status"] == "V"
        and "TP-2019-220391" in rows["required_margin_db"]["source"]
    )
    assert rows["tx_power_w"]["source"] == "illustrative"
    assert "potenziale" in d["disclaimer"]
    for r in d["parameters"]:
        assert r["source"] and r["unit"] and r["status"] in "VDI"
    assert "x-content-type-options" in {k.lower() for k in client.get("/api/lunar/sites").headers}


@needs_kernels
def test_solar_terrain_missing_tiles_and_coverage_are_not_clear_sky(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    monkeypatch.setenv("GRAZING_DEM_DIR", str(tmp_path))
    response = client.post("/api/lunar/solar-terrain", json={**BODY, "days": 0.1, "step_min": 60})
    assert response.status_code == 200, response.text
    data = response.json()
    assert len(data["series_time_unix"]) == 2
    for row, expected in zip(data["sites"], ["outside_coverage", "missing_dem"], strict=True):
        assert row["state"] == [expected, expected]
        assert row["horizon_deg"] == [None, None]
        assert row["energy_sensitivity"] == {"status": "unknown_terrain"}


@needs_kernels
def test_solar_terrain_matches_timeline_instants(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import numpy as np

    from backend.domain.grazing import horizon as hz
    from backend.domain.grazing import solar_terrain

    seen: list[float] = []

    def mask(_site: dict[str, Any], h: float) -> hz.HorizonMask:
        seen.append(h)
        n = 360
        return hz.HorizonMask(
            -89.0, 0.0, h, 0.0, np.full(n, -1.0), np.full(n, 1e4), np.ones(n, dtype=bool), 0.0,
            hz.MaskConfig(n_azimuths=n), [],
        )  # fmt: skip

    monkeypatch.setattr(solar_terrain, "_store_mask", mask)
    body = {**BODY, "days": 0.1, "step_min": 60}
    timeline = client.post("/api/lunar/timeline", json=body)
    result = client.post("/api/lunar/solar-terrain", json={**body, "observer_height_m": 5})
    assert timeline.status_code == result.status_code == 200
    data = result.json()
    assert data["series_time_unix"] == timeline.json()["series_time_unix"]
    assert data["assumptions"]["lunar_frame"] == "MOON_ME_DE440_ME421"
    assert data["assumptions"]["ephemeris"]["kernels"]["de440s.bsp"]
    assert data["assumptions"]["observer_height_m"] == 5 and set(seen) == {5.0}
    assert 0.25 < data["sun_semidiameter_mean_deg"] < 0.28
    assert all(
        len(row["state"]) == 2
        and all(value is not None for value in row["horizon_deg"])
        and all(0.0 <= f <= 1.0 for f in row["disc_fraction"])
        for row in data["sites"]
    )
    assert all(
        row["energy_sensitivity"]["status"] == "available"
        and len(row["energy_sensitivity"]["soc"]) == 2
        for row in data["sites"]
    )
    for bad in (-1, 101, "2"):
        r = client.post("/api/lunar/solar-terrain", json={**body, "observer_height_m": bad})
        assert r.status_code == 422


def test_solar_terrain_limits_before_computation(client: TestClient) -> None:
    response = client.post("/api/lunar/solar-terrain", json={**BODY, "days": 10, "step_min": 30})
    assert response.status_code == 422
    assert "troppi campioni" in response.json()["detail"]


def test_coupled_sensitivity_validates_inputs_and_uses_rf_power(client: TestClient) -> None:
    sample = {
        "time_unix": 1000,
        "gen_w": 100,
        "sun_up": True,
        "earth_visible": True,
        "dsn_visible": True,
        "rf_ok": True,
        "solar_state": "upper_above_profile",
    }
    body = {
        "samples": [sample, {**sample, "time_unix": 4600, "dsn_visible": False}],
        "step_min": 60,
        "tx_power_dbw": 10,
        "station": "dsn34",
        "energy": {},
    }
    response = client.post("/api/lunar/coupled-sensitivity", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["link_available"] == [True, False]
    assert response.json()["tx_power_w"] == 10
    unknown = {**body, "samples": [{**sample, "solar_state": "missing_dem"}]}
    assert client.post("/api/lunar/coupled-sensitivity", json=unknown).json() == {
        "status": "unknown_terrain"
    }
    for invalid in (
        {**body, "station": "dsn18"},
        {**body, "samples": [sample, {**sample, "time_unix": 4601}]},
        {**body, "energy": {"tx_power_w": 20}},
        {**body, "samples": [{**sample, "rf_ok": 1}]},
    ):
        assert client.post("/api/lunar/coupled-sensitivity", json=invalid).status_code == 422


def test_horizon_reports_uncovered_site_and_validates_height(client: TestClient) -> None:
    r = client.post("/api/lunar/horizon", json={"site_id": "apollo11", "observer_height_m": 2})
    assert r.status_code == 200
    data = r.json()
    assert len(data["samples"]) == 72
    assert {sample["state"] for sample in data["samples"]} == {"outside_coverage"}
    assert all(sample["elevation_deg"] is None for sample in data["samples"])
    assert data["observer_height_m"] == 2
    for patch in (
        {"site_id": "not-a-site"},
        {"site_id": "apollo11", "observer_height_m": -1},
        {"site_id": "apollo11", "observer_height_m": True},
    ):
        assert client.post("/api/lunar/horizon", json=patch).status_code == 422


def test_custom_horizon_validates_identity_and_coverage(client: TestClient) -> None:
    custom = {"id": "custom-a", "lat_deg": 0, "lon_deg_east": 30}
    response = client.post(
        "/api/lunar/horizon", json={"site_id": "custom-a", "custom_site": custom}
    )
    assert response.status_code == 200
    assert {row["state"] for row in response.json()["samples"]} == {"outside_coverage"}
    for data in (
        {"site_id": "custom-a"},
        {"site_id": "apollo11", "custom_site": custom},
        {"site_id": "custom-a", "custom_site": {**custom, "lat_deg": 91}},
        {"site_id": "custom-a", "custom_site": {**custom, "lat_deg": True}},
        {"site_id": "custom-a", "custom_site": {**custom, "id": "apollo11"}},
    ):
        assert client.post("/api/lunar/horizon", json=data).status_code == 422


@needs_kernels
def test_custom_timeline_coordinates_and_cache(client: TestClient) -> None:
    body = {
        **BODY,
        "site_ids": ["custom-a"],
        "custom_sites": [{"id": "custom-a", "lat_deg": 0, "lon_deg_east": 30}],
        "days": 0.1,
        "step_min": 60,
    }
    first = client.post("/api/lunar/timeline", json=body)
    assert first.status_code == 200, first.text
    row = first.json()["sites"][0]
    assert row["site"]["lat_deg"] == 0
    assert row["site"]["lon_deg_east"] == 30
    assert row["site"]["verified"] is False
    changed = {**body, "custom_sites": [{**body["custom_sites"][0], "lon_deg_east": 45}]}
    second = client.post("/api/lunar/timeline", json=changed)
    assert second.status_code == 200, second.text
    assert second.json()["sites"][0]["site"]["lon_deg_east"] == 45
    assert second.json()["sites"][0]["series"]["sun_el_deg"] != row["series"]["sun_el_deg"]
    assert (
        client.post(
            "/api/lunar/timeline",
            json={**body, "custom_sites": body["custom_sites"] * 2},
        ).status_code
        == 422
    )


@pytest.mark.parametrize(
    "patch",
    [
        {"site_ids": []},
        {"site_ids": ["nowhere"]},
        {"site_ids": ["apollo11", "apollo11"]},
        {"days": 367},
        {"days": 0},
        {"step_min": 9},
        {"start_utc": "2027-04-07"},
        {"start_utc": "1900-01-01T00:00:00Z"},
        {"overrides": {"tx_power_w": -1}},
        {"overrides": {"tx_power_w": "SECRET-VALUE"}},
        {"overrides": {"nope": 1}},
        {"overrides": {"days": 3}},
        {"overrides": {"orientation": "SECRET-VALUE"}},
        {"weights": {"useful_fraction": -1}},
        {"extra": 1},
    ],
)
def test_validation_422_generic_no_echo(client: TestClient, patch: dict[str, Any]) -> None:
    r = client.post("/api/lunar/analyze", json={**BODY, **patch})
    assert r.status_code == 422, r.text
    assert "SECRET-VALUE" not in r.text and "nowhere" not in r.text


def test_nan_and_garbage_rejected(client: TestClient) -> None:
    r = client.post(
        "/api/lunar/analyze",
        content='{"site_ids":["apollo11"],"start_utc":"2027-04-07T00:00:00Z","overrides":{"tx_power_w":NaN}}',
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 422
    assert (
        client.post(
            "/api/lunar/analyze", content="{", headers={"content-type": "application/json"}
        ).status_code
        == 422
    )


@needs_kernels
def test_analyze_end_to_end_cache_and_caps(client: TestClient) -> None:
    svc = client.app.state.lunar  # type: ignore[attr-defined]
    before = svc.computed
    r = client.post("/api/lunar/analyze", json=BODY)
    assert r.status_code == 200, r.text
    j = r.json()
    assert svc.computed == before + 1
    assert j["label"] == "potential under stated assumptions"
    assert [s["site"]["id"] for s in j["sites"]] == BODY["site_ids"]
    a11 = j["sites"][0]
    assert a11["metrics"]["earth_fraction"] == 1.0
    assert a11["metrics"]["sun_fraction"] > 0.9
    assert set(a11["series"]) == set(j["series_names"])
    npts = len(j["series_time_unix"])
    assert all(len(v) == npts for v in a11["series"].values())
    assert {x["site_id"] for x in j["ranking"]} == set(BODY["site_ids"])
    assert j["ranking"][0]["components"]["useful_fraction"]["weight"] == 1.0
    assert j["assumptions"]["link"]["frequency_ghz"] == 8.425
    assert j["assumptions"]["dsn_stations"][0]["source"]["url"].endswith("301P.pdf")
    # identical request: served from the cache (no new computation)
    r2 = client.post("/api/lunar/analyze", json=BODY)
    assert r2.json() == j and svc.computed == before + 1
    # an override changes the result and the echoed assumptions
    r3 = client.post(
        "/api/lunar/analyze",
        json={**BODY, "overrides": {"tx_power_w": 1.0, "orientation": "tracking"}},
    )
    assert r3.status_code == 200 and svc.computed == before + 2
    assert r3.json()["assumptions"]["link"]["tx_power_w"] == 1.0
    assert r3.json()["assumptions"]["energy"]["orientation"] == "tracking"


@needs_kernels
def test_total_points_capped(client: TestClient) -> None:
    svc = client.app.state.lunar  # type: ignore[attr-defined]
    r = client.post(
        "/api/lunar/analyze",
        json={
            **BODY,
            "site_ids": [s["id"] for s in client.get("/api/lunar/sites").json()["sites"]][:8],
            "days": 120,
            "step_min": 10,
        },
    )
    assert r.status_code == 200
    j = r.json()
    total = sum(len(v) for s in j["sites"] for v in s["series"].values())
    assert total <= svc.max_total_points
    assert j["window"]["n_steps"] == 120 * 144
    json.dumps(j, allow_nan=False)  # strictly JSON-valid (null for missing margins)


@needs_kernels
def test_timeline_uses_unaggregated_step_samples(client: TestClient) -> None:
    request = {**BODY, "days": 1, "step_min": 10.01}
    r = client.post("/api/lunar/timeline", json=request)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["series_step_min"] == request["step_min"]
    assert len(j["series_time_unix"]) == j["window"]["n_steps"]
    assert j["series_time_unix"][1] - j["series_time_unix"][0] == pytest.approx(600.6)
    assert "flat horizon" in j["sampling"]
    assert "orizzonte locale piatto" in j["disclaimer"]
    for row in j["sites"]:
        series = row["series"]
        assert set(series) == set(j["series_names"])
        assert all(len(values) == j["window"]["n_steps"] for values in series.values())
        assert all(type(v) is bool for v in series["sun_up"])
        assert all(v is not None and v >= 0 for v in series["gen_w"])
        assert all(v is not None and 0 <= v <= 1 for v in series["soc"])
        assert all(
            not link or (earth and dsn)
            for link, earth, dsn in zip(
                series["link_ok"], series["earth_visible"], series["dsn_visible"], strict=True
            )
        )
        assert all(
            not useful or link
            for useful, link in zip(series["useful"], series["link_ok"], strict=True)
        )
        assert sum(series["sun_up"]) / len(series["sun_up"]) == pytest.approx(
            row["metrics"]["sun_fraction"]
        )
        assert all(
            visible or margin is None
            for visible, margin in zip(series["earth_visible"], series["margin_db"], strict=True)
        )
    json.dumps(j, allow_nan=False)
    assert client.post("/api/lunar/timeline", json=request).json() == j
    # The existing decimated endpoint has a different representation and cache entry.
    assert "sampling" not in client.post("/api/lunar/analyze", json=request).json()


@needs_kernels
def test_timeline_rejects_too_many_points(client: TestClient) -> None:
    limits = client.get("/api/lunar/defaults").json()["limits"]
    assert limits["timeline_series_per_site"] == 12
    r = client.post("/api/lunar/timeline", json={**BODY, "days": 120, "step_min": 10})
    assert r.status_code == 422
    assert "timeline troppo grande" in r.json()["detail"]


@needs_kernels
def test_timeline_solar_panel_overrides_change_generated_power(client: TestClient) -> None:
    request = {
        "site_ids": ["de-gerlache"],
        "start_utc": "2027-04-07T00:00:00Z",
        "days": 0.1,
        "step_min": 60,
        "overrides": {"orientation": "tracking", "sun_elevation_mask_deg": -5, "array_area_m2": 1},
    }
    one = client.post("/api/lunar/timeline", json=request)
    two = client.post(
        "/api/lunar/timeline",
        json={**request, "overrides": {**request["overrides"], "array_area_m2": 2}},
    )
    assert one.status_code == two.status_code == 200
    a, b = one.json()["sites"][0], two.json()["sites"][0]
    assert a["series"]["gen_w"][0] > 0
    assert b["series"]["gen_w"] == pytest.approx([2 * v for v in a["series"]["gen_w"]])
    assert b["metrics"]["energy"]["harvested_wh"] == pytest.approx(
        2 * a["metrics"]["energy"]["harvested_wh"]
    )
    assert two.json()["assumptions"]["energy"]["array_area_m2"] == 2


def test_503_without_kernels(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    from backend.ephemeris.engine import reset_engine

    monkeypatch.setenv("EPHEMERIS_DIR", str(tmp_path))
    reset_engine()
    try:
        c = TestClient(build_app())
        r = c.post("/api/lunar/analyze", json=BODY)
        timeline = c.post("/api/lunar/timeline", json=BODY)
    finally:
        reset_engine()
    assert r.status_code == 503 and r.headers["retry-after"]
    assert timeline.status_code == 503 and timeline.headers["retry-after"]
    assert c.get("/api/lunar/defaults").status_code == 200


def test_busy_returns_503(client: TestClient) -> None:
    svc = client.app.state.lunar  # type: ignore[attr-defined]
    import asyncio

    async def hold() -> None:
        for _ in range(svc.max_concurrent):
            await svc.sem.acquire()

    loop = asyncio.new_event_loop()
    try:
        # semaphore bound to another loop: replace it with one we can fill without awaiting
        svc.sem = asyncio.Semaphore(0)
        r = client.post("/api/lunar/analyze", json={**BODY, "days": 1.5})
        assert r.status_code == 503
    finally:
        svc.sem = asyncio.Semaphore(svc.max_concurrent)
        loop.close()
