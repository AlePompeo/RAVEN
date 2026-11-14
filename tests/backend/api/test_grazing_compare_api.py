# SPDX-License-Identifier: Apache-2.0
"""POST /api/grazing/compare: limiti, nessun numero per i siti fuori DEM, classifica coerente con /analyze."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("numpy")
pytest.importorskip("scipy")

from backend.domain.grazing import compare as cmp
from backend.domain.grazing.dem import DEFAULT_DIR
from backend.ephemeris import kernels
from scripts.raven_reference import build_reference_app as build_app

try:
    kernels.require_kernels()
    HAVE_KERNELS = True
except kernels.EphemerisUnavailable:  # pragma: no cover
    HAVE_KERNELS = False

needs_kernels = pytest.mark.skipif(not HAVE_KERNELS, reason="kernels missing (make ephemeris)")
HAVE_TILES = DEFAULT_DIR.is_dir() and any(DEFAULT_DIR.glob("*.f32"))
needs_tiles = pytest.mark.skipif(not HAVE_TILES, reason="LOLA tiles missing (make grazing-dem)")
START = "2027-04-07T00:00:00Z"
BODY: dict[str, Any] = {
    "site_ids": ["shackleton", "malapert-massif"],
    "start_utc": START,
    "days": 3,
    "step_min": 30,
    "overrides": {"rate_bps": 1e4},
}


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    mp = pytest.MonkeyPatch()
    mp.setenv("GRAZING_DEM_ALLOW_DOWNLOAD", "0")
    mp.setenv("RATE_LIMIT_PER_MIN", "100000")
    try:
        yield TestClient(build_app())
    finally:
        mp.undo()


def test_rank_rows_order_and_ties() -> None:
    def row(i: str, hours: float, med: float | None) -> dict[str, Any]:
        return {
            "site": {"id": i},
            "covered": True,
            "real_hours": hours,
            "margin_median_db": med,
            "rank": None,
        }

    unc = {"site": {"id": "z"}, "covered": False, "rank": None}
    rows = [row("a", 10, 1.0), row("b", 12, -3.0), row("c", 10, 2.0), row("d", 10, 2.0), unc]
    assert cmp.rank_rows(rows) == ["b", "c", "d", "a"]
    assert [r["rank"] for r in rows] == [4, 1, 2, 3, None]


@pytest.mark.parametrize(
    "patch",
    [
        {"site_ids": []},
        {"site_ids": ["a"] * 9},
        {"site_ids": ["nowhere"]},
        {"days": 0},
        {"days": 91},
        {"step_min": 0.5},
        {"days": 30, "step_min": 10},  # > 1500 passi per sito
        {
            "site_ids": ["shackleton", "haworth", "malapert-massif", "nobile-rim", "de-gerlache"],
            "days": 30,
            "step_min": 30,
        },
        {"overrides": {"nope": 1}},
        {"overrides": {"rate_bps": 12345}},
        {"overrides": {"station": "dsn70"}},
        {"start_utc": "yesterday"},
        {"extra": 1},
    ],
)
def test_validation_is_generic_422(client: TestClient, patch: dict[str, Any]) -> None:
    r = client.post("/api/grazing/compare", json={**BODY, **patch})
    assert r.status_code == 422, r.text
    for secret in ("nowhere", "yesterday", "12345", "dsn70"):
        assert secret not in r.text


def test_uncovered_sites_only_have_no_numbers_even_without_tiles(client: TestClient) -> None:
    body = {**BODY, "site_ids": ["apollo11", "mons-mouton"]}
    r = client.post("/api/grazing/compare", json=body)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["ranking"] == [] and j["uncovered_state"] == cmp.UNCOVERED_STATE
    for row in j["sites"]:
        assert (
            row["state"] == cmp.UNCOVERED_STATE and row["covered"] is False and row["rank"] is None
        )
        assert set(row) == {"site", "state", "covered", "rank"}


def test_custom_sites_are_request_scoped_and_uncovered_without_dem(client: TestClient) -> None:
    custom = {"id": "custom-a", "lat_deg": 0, "lon_deg_east": 30}
    body = {**BODY, "site_ids": ["custom-a"], "custom_sites": [custom]}
    response = client.post("/api/grazing/compare", json=body)
    assert response.status_code == 200, response.text
    row = response.json()["sites"][0]
    assert row["covered"] is False
    assert row["site"]["lon_deg_east"] == 30
    changed = {**body, "custom_sites": [{**custom, "lon_deg_east": 45}]}
    assert (
        client.post("/api/grazing/compare", json=changed).json()["sites"][0]["site"]["lon_deg_east"]
        == 45
    )
    for data in (
        {**body, "custom_sites": []},
        {**body, "custom_sites": [custom, custom]},
        {**body, "custom_sites": [{**custom, "lat_deg": -91}]},
        {**body, "site_ids": ["apollo11"]},
    ):
        assert client.post("/api/grazing/compare", json=data).status_code == 422


@needs_kernels
def test_no_dem_is_503_generic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GRAZING_DEM_DIR", str(tmp_path))
    monkeypatch.setenv("GRAZING_DEM_ALLOW_DOWNLOAD", "0")
    c = TestClient(build_app())
    r = c.post("/api/grazing/compare", json=BODY)
    assert r.status_code == 503 and r.json()["detail"] == "dati DEM non disponibili"
    assert str(tmp_path) not in r.text


@needs_kernels
@needs_tiles
def test_ranking_matches_analyze_on_two_sites(client: TestClient) -> None:
    body = {**BODY, "site_ids": ["shackleton", "malapert-massif", "apollo11"]}
    r = client.post("/api/grazing/compare", json=body)
    if r.status_code == 503:  # pragma: no cover
        pytest.skip("tiles of the sites not cached")
    assert r.status_code == 200, r.text
    j = r.json()
    rows = {x["site"]["id"]: x for x in j["sites"]}
    assert rows["apollo11"]["state"] == cmp.UNCOVERED_STATE and "real_hours" not in rows["apollo11"]
    per: dict[str, dict[str, Any]] = {}
    for sid in ("shackleton", "malapert-massif"):
        a = client.post(
            "/api/grazing/analyze",
            json={
                "site_id": sid,
                "start_utc": START,
                "days": 3,
                "step_min": 30,
                "overrides": {"rate_bps": 1e4},
            },
        )
        assert a.status_code == 200, a.text
        per[sid] = a.json()
        w = per[sid]["windows"]
        x = rows[sid]
        assert x["real_hours"] == w["real_hours"] and x["geometric_hours"] == w["geometric_hours"]
        assert x["transition_hours"] == w["transition_hours"]
        ch = per[sid]["compensator"]["chosen"]
        assert x["compensator"]["outage_pct"] == ch["outage_pct"]
        assert x["compensator"]["delivered_bits"] == ch["delivered_bits"]
        assert x["terrain"]["radius_resolved"] == per[sid]["flags"]["radius_resolved"]
        assert x["terrain"]["correction_status"] == per[sid]["flags"]["correction"]["status"]
    expect = sorted(per, key=lambda s: (-per[s]["windows"]["real_hours"], s))
    if (
        per["shackleton"]["windows"]["real_hours"]
        != per["malapert-massif"]["windows"]["real_hours"]
    ):
        assert j["ranking"] == expect
    assert sorted(j["ranking"]) == ["malapert-massif", "shackleton"]
    assert {rows[s]["rank"] for s in j["ranking"]} == {1, 2}
    assert (
        j["ranking_columns"] == ["real_hours", "margin_median_db"] and "peso" in j["ranking_rule"]
    )
    assert all(p["status"] in "VDI" for p in j["parameters"])
    assert client.post("/api/grazing/compare", json=body).json() == j  # cache
    detailed = client.post("/api/grazing/compare", json={**body, "timeline": True})
    assert detailed.status_code == 200, detailed.text
    detailed_rows = {x["site"]["id"]: x for x in detailed.json()["sites"]}
    assert "window_samples" not in rows["shackleton"]
    assert "window_samples" not in detailed_rows["apollo11"]
    for sid in ("shackleton", "malapert-massif"):
        samples = detailed_rows[sid]["window_samples"]
        assert all(len(v) == j["window"]["n_steps"] for v in samples.values())
        assert sum(samples["link_ok"]) * 0.5 == rows[sid]["real_hours"]
