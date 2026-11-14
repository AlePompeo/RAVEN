# SPDX-License-Identifier: Apache-2.0
"""Rotte /api/grazing: validazione, nessun eco dell'input, 503 senza DEM, motore reale se i dati esistono."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("numpy")
pytest.importorskip("scipy")

from backend.bootstrap import build_app
from backend.domain.grazing.dem import DEFAULT_DIR
from backend.domain.raven.meta import MODEL_VERSION
from backend.ephemeris import kernels

try:
    kernels.require_kernels()
    HAVE_KERNELS = True
except kernels.EphemerisUnavailable:  # pragma: no cover
    HAVE_KERNELS = False

needs_kernels = pytest.mark.skipif(not HAVE_KERNELS, reason="kernels missing (make ephemeris)")
HAVE_TILES = DEFAULT_DIR.is_dir() and any(DEFAULT_DIR.glob("*.f32"))
needs_tiles = pytest.mark.skipif(not HAVE_TILES, reason="LOLA tiles missing (make grazing-dem)")
START = "2027-04-07T00:00:00Z"


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    mp = pytest.MonkeyPatch()
    mp.setenv("GRAZING_DEM_ALLOW_DOWNLOAD", "0")  # tests never touch the network
    mp.setenv("RATE_LIMIT_PER_MIN", "100000")
    try:
        yield TestClient(build_app())
    finally:
        mp.undo()


def _ridge_profile() -> dict[str, list[float]]:
    d = [5.0 * i for i in range(801)]  # 4 km
    z = [max(40.0 - (x - 2000.0) ** 2 / 200.0, 0.0) for x in d]  # 40 m ridge, R = 100 m at 2 km
    return {"distance_m": d, "height_m": z}


SWEEP_BODY: dict[str, Any] = {
    "start_utc": START,
    "days": 2,
    "step_min": 30,
    "profile": _ridge_profile(),
    "earth_sweep": {"el_start_deg": 0.0, "el_end_deg": 3.0},
    "overrides": {"rate_bps": 1e4},
}


def test_status_and_defaults(client: TestClient) -> None:
    s = client.get("/api/raven/experiments/status").json()
    assert s["dem"]["product"]["id"] == "ldem_85s_20m_float"
    assert s["dem"]["mode"] == "cache-only" and "scarica" in s["dem"]["hint"]
    assert s["compensation_table"]["version"] and len(s["compensation_table"]["file_sha256"]) == 64
    cov = {x["id"]: x["dem_covered"] for x in s["sites"]}
    assert cov["shackleton"] is True and cov["apollo11"] is False
    d = client.get("/api/raven/experiments/defaults").json()
    assert d["parameters"] and all(r["status"] in "VDI" and r["source"] for r in d["parameters"])
    tags = {r["key"]: r["status"] for r in d["parameters"]}
    assert (
        tags["fresnel_zone_n"] == "V"
        and tags["tx_power_dbw"] == "I"
        and tags["wavelength_m"] == "D"
    )
    assert any("Ostacolo singolo" in x for x in d["declared_limits"])
    assert {x["key"]: x["gain_tag"] for x in d["stations"]} == {"dsn34": "I", "dsn18": "I"}
    assert "x-content-type-options" in {
        k.lower() for k in client.get("/api/raven/experiments/status").headers
    }


def test_compensation_table_for_charts(client: TestClient) -> None:
    c = client.get("/api/raven/compensation").json()
    assert len(c["radius_m"]) == 8 and len(c["nu"]) == 91
    assert len(c["correction_db"]) == 8 and len(c["correction_db"][0]) == 91
    assert c["info"]["provenance"]["seed"] == 3
    assert (
        c["inconsistency"]["jpl226_claim_db"] == 0.0 and "politica" in c["inconsistency"]["status"]
    )


def test_antenna_matches_model_doc(client: TestClient) -> None:
    r = client.post("/api/raven/experiments/antenna", json={}).json()
    rows = {x["rate_bps"]: x for x in r["required_gain"]}
    assert rows[1e6]["required_gain_dbi"] == pytest.approx(-0.7, abs=0.06)
    assert rows[1e8]["required_gain_dbi"] == pytest.approx(19.3, abs=0.06)
    assert r["station"]["implied_eta"] == pytest.approx(0.704, abs=0.001)
    assert r["station"]["gain_tag"] == "I"
    assert r["uniform_hpbw_factor"] == pytest.approx(58.96, abs=0.01)
    assert r["dishes"][0]["pointing"][0]["constant_difference_db"] >= 0.0
    r18 = client.post("/api/raven/experiments/antenna", json={"station": "dsn18"}).json()
    assert {x["rate_bps"]: x for x in r18["required_gain"]}[1e6]["required_gain_dbi"] == (
        pytest.approx(4.8, abs=0.06)
    )


def test_compensator_monotone(client: TestClient) -> None:
    margins = [float(m) for m in range(-5, 30)] * 40  # sweeps through the threshold region
    body = {"margin_db": margins, "reference_rate_bps": 1e4, "seed": 5}
    r = client.post("/api/raven/experiments/compensator", json=body).json()
    outs = [row["outages"] for row in r["rows"]]
    sched = [row["scheduled_bits"] for row in r["rows"]]
    assert outs == sorted(outs, reverse=True) and sched == sorted(sched, reverse=True)
    assert r["rows"][0]["gaussian_outage_pct"] == pytest.approx(50.0)
    assert (
        client.post("/api/raven/experiments/compensator", json=body).json() == r
    )  # cached and seeded
    assert "rinforzo" in r["note"]


def test_analyze_known_ridge_without_ephemeris_or_dem(client: TestClient) -> None:
    resp = client.post("/api/raven/experiments/analyze", json=SWEEP_BODY)
    assert resp.status_code == 200, resp.text
    r = resp.json()
    w = r["windows"]
    assert w["transition_hours"] > 0 and w["real_hours"] > w["geometric_hours"]
    assert (
        r["flags"]["terrain"]["source"] == "user" and r["flags"]["geometry_source"] == "user-sweep"
    )
    assert r["flags"]["correction"]["status"] == "itu"
    assert r["declared_limits"] and r["correction_inconsistency"]["text"]
    assert all(p["status"] in "VDI" for p in r["parameters"])
    assert r["model_version"] == MODEL_VERSION and r["mission_evaluation"] is False
    assert r["scope"] == "educational_single_obstacle"
    parameters = {p["key"]: p for p in r["parameters"]}
    assert parameters["frequency_ghz"]["value"] == 8.425
    assert parameters["frequency_ghz"]["status"] == "V"
    assert parameters["station_gain_dbi"]["value"] == 68.29
    assert client.post("/api/raven/experiments/analyze", json=SWEEP_BODY).json() == r  # LRU hit


def test_experiments_never_enable_implicit_downloads(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRAZING_DEM_ALLOW_DOWNLOAD", "1")
    app = build_app()
    assert app.state.rf_experiments.allow_download is False


def test_gimbal_unavailable_is_reported_without_fallback(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import backend.domain.grazing.gimbal as gimbal_module

    monkeypatch.setattr(gimbal_module, "EXECUTABLE", tmp_path / "missing-gimbal")
    body = {**SWEEP_BODY, "overrides": {"rate_bps": 1e4, "mount": "gimbal"}}
    response = client.post("/api/raven/experiments/analyze", json=body)
    assert response.status_code == 503
    assert response.json()["detail"] == "simulatore gimbal C non disponibile"


@pytest.mark.parametrize(
    "patch",
    [
        {"days": 91},
        {"days": 0},
        {"step_min": 0.5},
        {"days": 90, "step_min": 15},  # > 5000 samples
        {"overrides": {"nope": 1}},
        {"overrides": {"tx_power_dbw": 999}},
        {"overrides": {"station": "dsn70"}},
        {"overrides": {"rate_bps": 12345}},
        {"start_utc": "yesterday"},
        {"extra_field": 1},
        {"earth_sweep": {"el_start_deg": 99, "el_end_deg": 0}},
        {"profile": {"distance_m": [0, 10, 5], "height_m": [0, 0, 0]}},
        {"profile": {"distance_m": [0, 10], "height_m": [0, 0, 0]}},
        {"profile": {"distance_m": [0, 10], "height_m": [0, 1e9]}},
        {"profile": {"distance_m": [5, 10], "height_m": [0, 1]}},
        {"site_id": "nowhere", "profile": None, "earth_sweep": None},
        {"site_id": None, "profile": None, "earth_sweep": None},
    ],
)
def test_analyze_validation_is_422_without_echo(client: TestClient, patch: dict[str, Any]) -> None:
    body = {**SWEEP_BODY, **patch}
    resp = client.post("/api/raven/experiments/analyze", json=body)
    assert resp.status_code == 422
    for secret in ("nowhere", "yesterday", "12345"):
        if secret in str(patch):
            assert secret not in resp.text


def test_profile_cap_and_nan_rejected(client: TestClient) -> None:
    big = {"distance_m": [float(i) for i in range(1501)], "height_m": [0.0] * 1501}
    assert (
        client.post(
            "/api/raven/experiments/analyze", json={**SWEEP_BODY, "profile": big}
        ).status_code
        == 422
    )
    raw = '{"start_utc": "2027-04-07T00:00:00Z", "earth_sweep": {"el_start_deg": NaN, "el_end_deg": 1}}'
    r = client.post(
        "/api/raven/experiments/analyze", content=raw, headers={"Content-Type": "application/json"}
    )
    assert r.status_code == 422


def test_antenna_and_compensator_validation(client: TestClient) -> None:
    for path, body in (
        ("antenna", {"eta": 5}),
        ("antenna", {"station": "dsn70"}),
        ("antenna", {"rates_bps": []}),
        ("antenna", {"junk": 1}),
        ("compensator", {"margin_db": []}),
        ("compensator", {"margin_db": [1.0], "k_values": [99]}),
        ("compensator", {"margin_db": [1.0] * 2001}),
        ("compensator", {"margin_db": [1.0], "rates_bps": [0]}),
        ("compensator", {"margin_db": [1.0], "seed": -1}),
    ):
        assert client.post(f"/api/raven/experiments/{path}", json=body).status_code == 422


@needs_kernels
def test_site_outside_dem_is_422_clear(client: TestClient) -> None:
    body = {"site_id": "apollo11", "start_utc": START, "days": 1, "step_min": 60}
    r = client.post("/api/raven/experiments/analyze", json=body)
    assert r.status_code == 422 and "fuori copertura DEM" in r.json()["detail"]
    assert "apollo11" not in r.text


def test_site_outside_dem_is_422_even_without_kernels(client: TestClient) -> None:
    body = {"site_id": "apollo17", "start_utc": START, "days": 1, "step_min": 60}
    r = client.post("/api/raven/experiments/analyze", json=body)
    assert r.status_code == 422 and "fuori copertura DEM" in r.json()["detail"]


@needs_kernels
def test_no_dem_cache_is_503_generic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRAZING_DEM_DIR", str(tmp_path))
    monkeypatch.setenv("GRAZING_DEM_ALLOW_DOWNLOAD", "0")
    c = TestClient(build_app())
    body = {"site_id": "shackleton", "start_utc": START, "days": 1, "step_min": 60}
    r = c.post("/api/raven/experiments/analyze", json=body)
    assert r.status_code == 503 and r.json()["detail"] == "dati DEM non disponibili"
    assert str(tmp_path) not in r.text and r.headers["retry-after"] == "30"
    st = c.get("/api/raven/experiments/status").json()
    assert st["dem"]["available"] is False and st["dem"]["cached_tiles"] == 0


@needs_kernels
@needs_tiles
def test_real_engine_and_lola_cache(client: TestClient) -> None:
    body = {"site_id": "malapert-massif", "start_utc": START, "days": 5, "step_min": 30}
    r = client.post("/api/raven/experiments/analyze", json=body)
    if r.status_code == 503:  # pragma: no cover  (tiles of this site not cached)
        pytest.skip("tiles of the site not cached")
    assert r.status_code == 200, r.text
    j = r.json()
    t = j["flags"]["terrain"]
    assert t["source"] == "lola" and t["product_id"] == "ldem_85s_20m_float" and not t["synthetic"]
    assert j["flags"]["geometry_source"] == "ephemeris"
    assert j["windows"]["total_hours"] == pytest.approx(120.0)
