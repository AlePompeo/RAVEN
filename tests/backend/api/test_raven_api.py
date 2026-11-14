# SPDX-License-Identifier: Apache-2.0
"""/api/raven/*: validation, caps, caching, unknown propagation and the real engine (RAVEN M7)."""

import asyncio
import os
import subprocess
import sys
import threading
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

pytest.importorskip("numpy")
pytest.importorskip("scipy")

from backend.bootstrap import build_app
from backend.domain.raven.meta import MODEL_VERSION
from scripts import raven_golden as rg

needs_kernels = pytest.mark.skipif(not rg.have_kernels(), reason="kernels missing")
needs_real = pytest.mark.skipif(
    not (rg.have_kernels() and rg.have_tiles()), reason="kernels or LOLA tiles missing"
)
BODY: dict[str, Any] = {
    "site_id": "malapert-massif",
    "start_utc": "2027-01-01T00:00:00Z",
    "days": 2,
    "step_min": 60,
}


@needs_kernels
@pytest.mark.parametrize("endpoint", ["evaluate", "compare"])
def test_mission_window_must_fit_ephemeris_range(client: TestClient, endpoint: str) -> None:
    from backend.ephemeris.engine import get_engine

    lo, hi = get_engine().supported_range()
    payload = {**BODY, "days": 1, "step_min": 1440}
    if endpoint == "compare":
        payload.pop("site_id")
        payload["site_ids"] = ["malapert-massif", "haworth"]
    for start in (lo - timedelta(minutes=1), hi - timedelta(hours=12)):
        r = client.post(
            f"/api/raven/{endpoint}",
            json={**payload, "start_utc": start.isoformat().replace("+00:00", "Z")},
        )
        assert r.status_code == 422


@needs_kernels
def test_past_ephemerides_and_published_range(client: TestClient) -> None:
    from backend.ephemeris.engine import get_engine

    lo, hi = get_engine().supported_range()
    assert client.get("/api/raven/sites").json()["ephemeris"]["supported_range"] == {
        "start_utc": lo.isoformat().replace("+00:00", "Z"),
        "end_utc": hi.isoformat().replace("+00:00", "Z"),
    }
    for start in (lo.strftime("%Y-%m-%dT%H:%M:%SZ"), "2001-01-01T00:00:00Z"):
        r = client.post(
            "/api/raven/evaluate",
            json={**BODY, "start_utc": start, "days": 1, "step_min": 1440},
        )
        assert r.status_code == 200
        assert all(v is not None for v in r.json()["steps"]["sun_el_deg"])
        assert all(v is not None for v in r.json()["steps"]["earth_el_deg"])


def test_concurrent_first_scientific_requests_do_not_race_imports() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import asyncio
import httpx
from backend.bootstrap import build_app

async def main():
    app = build_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        responses = await asyncio.gather(*[
            client.get(path) for path in (
                "/api/raven/experiments/status",
                "/api/raven/experiments/defaults",
                "/api/raven/parameters",
                "/api/raven/compensation",
            )
        ])
        assert [r.status_code for r in responses] == [200, 200, 200, 200]

asyncio.run(main())
""",
        ],
        cwd=Path(__file__).resolve().parents[3],
        env={
            **os.environ,
            "GRAZING_DEM_ALLOW_DOWNLOAD": "0",
            "ASSISTANT_PROVIDER": "assistant-extractive",
        },
        check=False,
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stderr


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    mp = pytest.MonkeyPatch()
    mp.setenv("GRAZING_DEM_ALLOW_DOWNLOAD", "0")
    mp.setenv("RATE_LIMIT_PER_MIN", "100000")
    try:
        yield TestClient(build_app())
    finally:
        mp.undo()


def test_parameters_and_model(client: TestClient) -> None:
    p = client.get("/api/raven/parameters").json()
    assert p["model_version"] == MODEL_VERSION and len(p["registry_sha256"]) == 64
    rows = {r["key"]: r for r in p["parameters"]}
    assert rows["lunar.required_margin_db"]["tag"] == "V"
    assert rows["common.far_terrain_blocked_loss_db"]["tag"] == "I"
    assert all(r["source"] and r["unit"] and r["tag"] in "VDI" for r in rows.values())
    assert "frequency_ghz" in p["duplicated_concepts"]
    d = p["defaults"]
    assert d["window"]["n_steps"] == 1008 <= d["window"]["max_steps_per_site"] == 1500
    assert d["scenario"]["required_margin_db"] == 3.0 and d["scenario"]["panel_height_m"] == 2.0
    assert d["rf"]["frequency_ghz"] == 8.425 and "shackleton" in d["sites"]
    body = {
        "site_id": "shackleton",
        "start_utc": "2027-01-01T00:00:00Z",
        **{k: d["window"][k] for k in ("days", "step_min")},
    }
    assert client.post(
        "/api/raven/evaluate", json={**body, "include_steps": False}
    ).status_code in (200, 503)
    for r in p[
        "parameters"
    ]:  # one API for every page: value, tag, source and range of each parameter
        assert {"default", "tag", "source", "unit", "min", "max", "stage"} <= set(r)
    m = client.get("/api/raven/model").json()
    assert m["stages"][0]["stage"] == "s0" and m["limits"]["max_steps_per_site"] == 1500
    assert m["registry_sha256"] == p["registry_sha256"]
    assert "x-content-type-options" in {k.lower() for k in client.get("/api/raven/model").headers}


@needs_kernels
def test_parameters_used_are_reported(client: TestClient) -> None:
    r = client.post(
        "/api/raven/evaluate",
        json={
            **BODY,
            "days": 1,
            "include_steps": False,
            "mission_shift_days": 28,
            "rf_overrides": {"tx_gain_dbi": 20.0},
        },
    )
    assert r.status_code == 200
    assert r.json()["base_start_utc"] == BODY["start_utc"]
    assert r.json()["mission_shift_days"] == 28
    assert r.json()["window"]["start_utc"] == "2027-01-29T00:00:00Z"
    u = r.json()["parameters_used"]
    assert u["rf"]["tx_gain_dbi"] == 20.0 and u["rf"]["frequency_ghz"] == 8.425
    assert u["rf"]["station_gain_dbi"] == 68.29 and u["scenario"]["required_margin_db"] == 3.0
    assert "battery_capacity_wh" in u["energy"]
    assert (
        client.post("/api/raven/evaluate", json={**BODY, "mission_shift_days": 4}).status_code
        == 422
    )


def test_compensation_table_is_served_by_the_single_model(client: TestClient) -> None:
    r = client.get("/api/raven/compensation")
    assert r.status_code == 200 and r.json()["model_version"] == MODEL_VERSION
    j = r.json()
    assert len(j["registry_sha256"]) == 64
    assert len(j["radius_m"]) == 8 and len(j["nu"]) == 91
    assert j["info"]["provenance"]["seed"] == 3
    assert client.get("/api/grazing/compensation").status_code == 410


def test_station_18m_keeps_its_own_gain_in_the_unified_set() -> None:
    from backend.domain.raven.s5_rf import unified_link_inputs

    assert unified_link_inputs({"station": "dsn34"}).station_gain_dbi == 68.29
    assert (
        unified_link_inputs({"station": "dsn18"}).station_gain_dbi is None
    )  # table value 62.5 (I)
    assert (
        unified_link_inputs({"station": "dsn18", "station_gain_dbi": 60.0}).station_gain_dbi == 60.0
    )


def test_link_parity_fixture_uses_the_unified_radio_set() -> None:
    import json
    from pathlib import Path

    from backend.domain.raven import params as reg

    fx = json.loads(
        (
            Path(__file__).resolve().parents[3]
            / "frontend/src/pages/simula/fixtures/link_parity.json"
        ).read_text()
    )
    base = fx["cases"][0]["input"]
    assert base["frequencyGhz"] == reg.value("rf.frequency_ghz") == 8.425
    assert base["stationGainDbi"] == reg.value("rf.station_gain_dbi") == 68.29
    assert base["tsysK"] == reg.value("rf.tsys_k") == 26.2
    assert base["ebn0Db"] == reg.value("rf.ebn0_db") == 9.6
    assert reg.value("rf.required_margin_db") == 3.0


def test_sites_catalogue_replaces_legacy_status(client: TestClient) -> None:
    r = client.get("/api/raven/sites")
    assert r.status_code == 200
    j = r.json()
    by = {s["id"]: s for s in j["sites"]}
    assert by["malapert-massif"]["dem_covered"] is True and by["apollo11"]["dem_covered"] is False
    assert {"source_url", "verified", "coordinate_basis"} <= set(by["shackleton"])
    assert j["dem"]["product"]["coverage_north_limit_deg"] == -85
    assert isinstance(j["ephemeris"]["available"], bool) and j["model_version"] == MODEL_VERSION


def test_invalid_requests_are_generic_422_without_echo(client: TestClient) -> None:
    bad_bodies = [
        {**BODY, "days": 400},
        {**BODY, "step_min": 0.5},
        {**BODY, "days": 30, "step_min": 10},  # 4320 steps > 1500 (D9, no decimation)
        {**BODY, "station": "dsn70"},
        {**BODY, "rate_bps": 12345},
        {**BODY, "site_id": "nowhere-zz"},
        {**BODY, "start_utc": "not-a-date-at-all-xxxx"},
        {**BODY, "rf_overrides": {"rate_bps": 1e5}},
        {**BODY, "energy_overrides": {"zzz": 1}},
        {**BODY, "extra": 1},
    ]
    for bad in bad_bodies:
        r = client.post("/api/raven/evaluate", json=bad)
        assert r.status_code == 422, bad
        for secret in ("nowhere-zz", "not-a-date", "12345", "dsn70"):
            assert secret not in r.text


def test_compare_validation_and_total_cap(client: TestClient) -> None:
    body = {k: v for k, v in BODY.items() if k != "site_id"}
    big = {
        **body,
        "days": 62.5,
        "step_min": 60,
        "site_ids": ["shackleton", "haworth", "nobile-rim", "de-gerlache", "malapert-massif"],
    }
    assert (
        client.post("/api/raven/compare", json=big).status_code == 422
    )  # 5 x 1500 = 7500 > 6000 (D9)
    assert client.post("/api/raven/compare", json={**body, "site_ids": []}).status_code == 422
    dup = {
        **body,
        "site_ids": ["a"],
        "custom_sites": [{"id": "custom-a", "lat_deg": 1, "lon_deg_east": 1}],
    }
    assert client.post("/api/raven/compare", json=dup).status_code == 422


@needs_kernels
def test_missing_tiles_are_unknown_not_clear_sky(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("GRAZING_DEM_DIR", str(tmp_path))
    r = client.post("/api/raven/evaluate", json={**BODY, "days": 1})
    assert r.status_code == 200, r.text
    j = r.json()
    assert set(j["steps"]["state"]) == {"unknown"}
    assert all(v is None for v in j["steps"]["useful"] + j["steps"]["soc"] + j["steps"]["lit"])
    assert j["inputs_state"]["terrain_mask"] in ("missing_dem", "outside_coverage")
    assert j["metrics"]["unknown_steps"] == j["window"]["n_steps"]


@needs_kernels
def test_uncovered_site_is_unknown_and_custom_site_is_never_verified(client: TestClient) -> None:
    # outside the 20 m polar product the terrain comes from the global product, after the explicit download consent
    r = client.post("/api/raven/evaluate", json={**BODY, "site_id": "apollo11", "days": 1})
    if r.status_code == 409:
        assert (
            r.json()["detail"] == "needs download"
        )  # nothing cached: no download without the flag
    else:
        assert (
            r.status_code == 200 and r.json()["terrain"]["state"] == "known"
        )  # the tile was already cached
    cs = {
        "id": "c-a",
        "name": "Pole",
        "lat_deg": 89.9,
        "lon_deg_east": 10.0,
    }  # no terrain: nothing to fetch
    r2 = client.post(
        "/api/raven/evaluate",
        json={**BODY, "site_id": "c-a", "custom_site": cs, "days": 1, "include_steps": False},
    )
    assert r2.status_code == 200
    assert r2.json()["site"]["verified"] is False and "steps" not in r2.json()


@needs_real
def test_evaluate_real_site_cache_and_determinism(client: TestClient) -> None:
    r = client.post("/api/raven/evaluate", json=BODY)
    assert r.status_code == 200, r.text
    j = r.json()
    n = j["window"]["n_steps"]
    assert n == 48 and j["implemented_stages"][-1] == "s7"
    assert all(len(v) == n for v in j["steps"].values())
    rate_key = str(int(j["parameters_used"]["rf"]["rate_bps"]))
    assert j["rf_series"][rate_key] == j["steps"]["margin_db"]
    assert all(len(values) == n for values in j["rf_series"].values())
    assert len(j["steps"]["chosen_rate_bps"]) == n
    assert all(
        rate is None
        for rate, margin in zip(j["steps"]["chosen_rate_bps"], j["steps"]["margin_db"], strict=True)
        if margin is None
    )
    assert j["heights"] == {
        "panel_height_m": 2.0,
        "antenna_height_m": 2.0,
        "profile_length_m": 10000.0,
    }
    assert j["mask"]["complete_azimuth_fraction"] == 1.0
    assert client.post("/api/raven/evaluate", json=BODY).json() == j  # LRU hit, same answer
    # unknown stays unknown: an 18 m station never yields a visible/useful step
    r18 = client.post("/api/raven/evaluate", json={**BODY, "station": "dsn18"}).json()
    assert all(v is None for v in r18["steps"]["dsn_visible"])
    assert all(u is not True for u in r18["steps"]["useful"])


@needs_real
def test_evaluate_exposes_the_diffraction_terms(client: TestClient) -> None:
    """nu, J(nu), the rounded-ridge correction T and their sum are returned per step (backward compatible
    addition); a step with an unknown RF link has no term, never zero."""
    s = client.post("/api/raven/evaluate", json=BODY).json()["steps"]
    keys = ("diffraction_nu", "knife_edge_loss_db", "ridge_correction_db", "diffraction_loss_db")
    n = len(s["margin_db"])
    assert all(len(s[k]) == n for k in keys)
    both = [i for i in range(n) if s["knife_edge_loss_db"][i] is not None]
    assert both, "the real site has known diffraction steps"
    for i in both:
        j, t, total = (
            s["knife_edge_loss_db"][i],
            s["ridge_correction_db"][i],
            s["diffraction_loss_db"][i],
        )
        assert s["diffraction_nu"][i] is not None and t is not None
        assert abs(total - (j + t)) < 1e-9
    for i in range(n):
        if s["margin_db"][i] is None:
            assert all(s[k][i] is None for k in keys)


@needs_real
def test_compensator_k_in_rf_overrides_changes_the_chosen_bit_rate(client: TestClient) -> None:
    """The Planner's compensator k travels as rf_overrides.compensator_k and reaches S5: a larger k is more
    conservative, so the bit rate chosen over the window changes (never increases at the same steps)."""
    body = {**BODY, "days": 7, "step_min": 60, "start_utc": "2027-04-16T00:00:00Z"}
    low = client.post("/api/raven/evaluate", json={**body, "rf_overrides": {"compensator_k": 0.0}})
    high = client.post("/api/raven/evaluate", json={**body, "rf_overrides": {"compensator_k": 6.0}})
    assert low.status_code == 200 and high.status_code == 200, (low.text, high.text)
    a, b = low.json()["steps"]["chosen_rate_bps"], high.json()["steps"]["chosen_rate_bps"]
    assert a != b
    assert low.json()["parameters_used"]["rf"]["compensator_k"] == 0.0
    assert high.json()["parameters_used"]["rf"]["compensator_k"] == 6.0
    pairs = [(x, y) for x, y in zip(a, b, strict=True) if x is not None and y is not None]
    assert pairs and all(y <= x for x, y in pairs)
    assert sum(y for _, y in pairs) < sum(x for x, _ in pairs)


@needs_real
def test_compare_reports_components_and_no_score(client: TestClient) -> None:
    body = {k: v for k, v in BODY.items() if k != "site_id"}
    r = client.post("/api/raven/compare", json={**body, "site_ids": ["shackleton", "haworth"]})
    assert r.status_code == 200, r.text
    j = r.json()
    assert [s["site"]["id"] for s in j["sites"]] == ["shackleton", "haworth"]
    rk = j["ranking"]
    assert rk["score"] is None and rk["order"] == ["useful_hours", "unknown_hours", "margin_min_db"]
    got = [x["site_id"] for x in rk["ranking"]] + [x["site_id"] for x in rk["not_comparable"]]
    assert sorted(got) == ["haworth", "shackleton"]
    assert all("components" in x for x in rk["ranking"] + rk["not_comparable"])
    custom = client.post(
        "/api/raven/compare",
        json={**body, "site_ids": ["shackleton", "haworth"], "order": ["useful_hours"]},
    ).json()["ranking"]
    assert custom["order"] == ["useful_hours"]
    assert [row["site_id"] for row in custom["ranking"]] == ["haworth"]
    assert [row["site_id"] for row in custom["not_comparable"]] == ["shackleton"]
    bad = {**body, "site_ids": ["shackleton"], "order": ["nope"]}
    assert client.post("/api/raven/compare", json=bad).status_code == 422
    for s in j["sites"]:
        assert {"useful_hours", "unknown_hours", "min_soc"} <= set(s["metrics"])
        assert "score" not in s and "steps" not in s
    haworth = j["sites"][1]["inputs_state"]["terrain_reason_counts"]
    assert haworth.get("blocked_far_terrain", 0) + haworth.get("outside_model", 0) > 0


@needs_real
def test_windows_are_refined_on_request(client: TestClient) -> None:
    body = {**BODY, "days": 20, "include_steps": False, "include_windows": True}
    j = client.post("/api/raven/evaluate", json=body).json()
    assert set(j["windows"]) == {"lit", "link_usable", "useful"}
    assert all(w["tolerance_s"] == 1.0 for k in j["windows"] for w in j["windows"][k])
    assert "bisected" in j["windows_rule"]


def test_validation_endpoint_and_model_field(client: TestClient) -> None:
    j = client.get("/api/raven/validation").json()
    assert {e["stage"] for e in j["stages"]} >= {f"s{i}" for i in range(8)}
    assert all(e["status"] in j["statuses"] for e in j["stages"])
    assert client.get("/api/raven/model").json()["validation"]["stages"] == j["stages"]


def test_views_validation_and_unknown_site(client: TestClient) -> None:
    t = "2027-04-07T00:00:00Z"
    assert client.get("/api/raven/snapshot", params={"t": "bad"}).status_code == 422
    assert client.get("/api/raven/snapshot", params={"t": t, "rate_bps": 5}).status_code == 422
    assert client.get("/api/raven/scene", params={"site": "nowhere-zz", "t": t}).status_code == 422
    # outside the 20 m product the terrain is the global one: 409 until the consent, 200 once its tiles are cached
    assert client.get("/api/raven/scene", params={"site": "apollo11", "t": t}).status_code in (
        200,
        409,
    )
    r = client.get("/api/raven/horizon", params={"site": "nowhere-zz"})
    assert r.status_code == 422 and "nowhere" not in r.text
    assert (
        client.get("/api/raven/horizon", params={"site": "apollo11", "extra": 1}).status_code == 422
    )


@needs_real
def test_views_real(client: TestClient) -> None:
    t = "2027-04-07T00:00:00Z"
    snap = client.get("/api/raven/snapshot", params={"t": t})
    assert snap.status_code == 200, snap.text
    j = snap.json()
    assert len(j["sites"]) == 51 and j["dsn"]["min_elevation_deg"] == 6.0
    assert client.get("/api/raven/snapshot", params={"t": t}).json() == j  # cached
    # a catalogue site outside the 20 m product is read from the global terrain when its tiles are cached, never guessed
    apollo = next(x for x in j["sites"] if x["id"] == "apollo11")
    assert apollo["state"] in {"open", "transition", "blocked", "unknown", "needs_download"}
    assert apollo["state"] != "out_of_coverage" and apollo["custom"] is False
    if apollo["state"] == "needs_download":
        assert apollo["margin_db"] is None
    sc = client.get("/api/raven/scene", params={"site": "shackleton", "t": t}).json()
    assert sc["model"]["terrain_reason"] == "ok" and sc["terrain"]["patch"]["n"] == 96
    h = client.get("/api/raven/horizon", params={"site": "shackleton"}).json()
    assert h["state"] == "ok" and len(h["elevation_deg"]) == 1440
    r2 = client.get("/api/raven/horizon", params={"site": "apollo11"})
    assert r2.status_code in (
        200,
        409,
    )  # global terrain: after the consent, or when its tiles are already cached
    if r2.status_code == 200:
        assert r2.json()["state"] == "ok"


@needs_real
def test_scene_and_snapshot_take_the_tx_gain_and_a_user_site(client: TestClient) -> None:
    t = "2027-04-07T00:00:00Z"
    base = {"site": "malapert-massif", "t": t}
    lo = client.get("/api/raven/scene", params={**base, "gain_dbi": 10}).json()
    hi = client.get("/api/raven/scene", params={**base, "gain_dbi": 20}).json()
    assert hi["link"]["margin_db"] - lo["link"]["margin_db"] == pytest.approx(10.0, abs=1e-6)
    s_lo = client.get("/api/raven/snapshot", params={"t": t, "gain_dbi": 10}).json()
    s_hi = client.get("/api/raven/snapshot", params={"t": t, "gain_dbi": 20}).json()
    m = {r["id"]: r["margin_db"] for r in s_lo["sites"]}
    n = {r["id"]: r["margin_db"] for r in s_hi["sites"]}
    assert n["malapert-massif"] - m["malapert-massif"] == pytest.approx(10.0, abs=1e-6)
    assert n["shackleton"] is None and m["shackleton"] is None
    custom = {"site": "c-a", "name": "A", "t": t, "lat_deg": -86.0, "lon_deg_east": 0.0}
    assert (
        client.get("/api/raven/scene", params=custom).status_code == 409
    )  # tiles not cached: needs the flag
    out = client.get("/api/raven/scene", params={**custom, "lat_deg": 89.9})
    assert out.status_code == 422 and "copertura DEM" in out.json()["detail"]
    assert client.get("/api/raven/scene", params={**base, "gain_dbi": 99}).status_code == 422
    for v in (lo, s_lo, client.get("/api/raven/horizon", params={"site": "shackleton"}).json()):
        assert v["model_version"] == MODEL_VERSION and len(v["registry_sha256"]) == 64


@needs_real
def test_horizon_of_a_user_site_needs_both_coordinates(client: TestClient) -> None:
    p = {"site": "c-a", "name": "A", "lat_deg": 89.9, "lon_deg_east": 0.0}
    r = client.get("/api/raven/horizon", params=p)
    assert (
        r.status_code == 200
        and r.json()["site"]["id"] == "c-a"
        and r.json()["state"] == "outside_coverage"
    )
    assert r.json()["site"]["verified"] is False
    assert (
        client.get("/api/raven/horizon", params={"site": "c-a", "lat_deg": -86}).status_code == 422
    )
    assert client.get("/api/raven/horizon", params={"site": "c-a"}).status_code == 422


@pytest.mark.parametrize("timeout", [False, True])
async def test_horizon_admission_keeps_worker_lease_after_cancellation_or_timeout(
    monkeypatch: pytest.MonkeyPatch, timeout: bool
) -> None:
    from backend.domain.raven import views

    app = build_app()
    service = app.state.raven
    service.sem = asyncio.Semaphore(1)
    service.compute_timeout_s = 0.05 if timeout else 10
    entered = asyncio.Event()
    gate = threading.Event()
    loop = asyncio.get_running_loop()

    def work(*args: Any, **kwargs: Any) -> dict[str, Any]:
        loop.call_soon_threadsafe(entered.set)
        assert gate.wait(5)
        return {"state": "outside_coverage"}

    monkeypatch.setattr(views, "horizon", work)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        task = asyncio.create_task(c.get("/api/raven/horizon", params={"site": "malapert-massif"}))
        try:
            await asyncio.wait_for(entered.wait(), timeout=3)
            busy = await c.get(
                "/api/raven/horizon", params={"site": "malapert-massif", "height_m": 3}
            )
            assert busy.status_code == 503 and busy.headers["retry-after"] == "2"
            assert (await c.post("/api/raven/evaluate", json=BODY)).status_code == 503
            if timeout:
                assert (await task).status_code == 504
            else:
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            assert service.sem.locked()
            assert (
                await c.get("/api/raven/horizon", params={"site": "malapert-massif", "height_m": 4})
            ).status_code == 503
        finally:
            gate.set()
            await asyncio.wait_for(service.sem.acquire(), timeout=3)
            service.sem.release()
        resumed = await c.get(
            "/api/raven/horizon", params={"site": "malapert-massif", "height_m": 5}
        )
        assert resumed.status_code == 200
