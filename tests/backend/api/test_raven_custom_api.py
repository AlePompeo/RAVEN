# SPDX-License-Identifier: Apache-2.0
"""Custom sites in /api/raven/*: validation, id clash, estimate, 409/413/429/503, unknown terrain, cache."""

import urllib.error
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("numpy")
pytest.importorskip("scipy")

from backend.api.raven_custom import TerrainService
from backend.bootstrap import build_app
from backend.domain.grazing import dem_cache
from backend.domain.grazing.dem_select import TILE_BYTES, plan_site
from backend.domain.raven import s0_context as s0
from backend.domain.raven.custom_terrain import TerrainStore
from scripts import raven_golden as rg
from tests.backend.fake_pds import FakePds

needs_kernels = pytest.mark.skipif(not rg.have_kernels(), reason="kernels missing")
BODY: dict[str, Any] = {"start_utc": "2027-01-01T00:00:00Z", "days": 1, "step_min": 60}
EQ = {"id": "c-eq", "name": "Equator test", "lat_deg": 0.0, "lon_deg_east": 40.0}


class Env:
    def __init__(self, client: TestClient, pds: FakePds, store: TerrainStore, svc: TerrainService):
        self.client, self.pds, self.store, self.svc = client, pds, store, svc


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Env]:
    monkeypatch.setenv("GRAZING_DEM_ALLOW_DOWNLOAD", "0")
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "100000")
    pds = FakePds()
    store = TerrainStore(tmp_path / "custom", fallback=tmp_path / "empty", opener=pds)
    svc = TerrainService(store)
    app = build_app()
    app.state.raven.terrain = svc
    yield Env(TestClient(app), pds, store, svc)


def ev(env: Env, site: dict[str, Any], **extra: Any) -> Any:
    return env.client.post(
        "/api/raven/evaluate", json={**BODY, "site_id": site["id"], "custom_site": site, **extra}
    )


# -- validation ----------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "bad",
    [
        {"lat_deg": 90.1},
        {"lat_deg": -90.1},
        {"lon_deg_east": 360.5},
        {"lon_deg_east": -180.5},
        {"lat_deg": "12"},
        {"lat_deg": True},
        {"id": "shackleton"},  # clashes with the catalogue: only c- ids
        {"id": "C-Upper"},
        {"id": "c-"},
        {"id": "c-" + "a" * 40},
        {"name": "<script>alert(1)</script>"},
        {"name": ""},
        {"name": "x" * 41},
        {"panel_height_m": 0.0},
        {"panel_height_m": 101},
        {"antenna_height_m": -1},
        {"extra": 1},
    ],
)
def test_bad_custom_site_is_a_generic_422_without_echo(env: Env, bad: dict[str, Any]) -> None:
    site = {**EQ, **bad}
    r = ev(env, site)
    assert r.status_code == 422
    for v in bad.values():
        if isinstance(v, str) and len(v) > 3:
            assert v not in r.text
    assert env.pds.urls == []  # nothing was fetched


def test_nan_and_infinity_are_refused(env: Env) -> None:
    for lit in ("NaN", "Infinity", "-Infinity", "1e999"):
        raw = f'{{"sites": [{{"id": "c-x", "name": "X", "lat_deg": {lit}, "lon_deg_east": 1}}]}}'
        r = env.client.post(
            "/api/raven/terrain-estimate", content=raw, headers={"content-type": "application/json"}
        )
        assert r.status_code == 422


def test_catalogue_ids_never_use_the_custom_prefix() -> None:
    assert not any(i.startswith(s0.CUSTOM_PREFIX) for i in s0.load_catalog())


def test_longitude_0_360_is_normalised_and_site_is_never_verified() -> None:
    a = s0.custom_site("c-a", 10.0, 350.0, strict=True)
    assert a.lon_deg_east == -10.0 and a.custom and a.verified is False
    assert s0.custom_site("c-b", 10.0, 180.0, strict=True).lon_deg_east == 180.0
    assert s0.custom_site("c-c", 10.0, -180.0, strict=True).lon_deg_east == -180.0
    with pytest.raises(s0.S0Error):
        s0.custom_site("shackleton", 10.0, 1.0, strict=True)
    with pytest.raises(s0.S0Error):
        s0.sanitise_name("a;b")


def test_at_most_eight_custom_sites_and_unique_ids(env: Env) -> None:
    sites = [{**EQ, "id": f"c-s{i}", "lon_deg_east": 10.0 * i} for i in range(9)]
    r = env.client.post("/api/raven/terrain-estimate", json={"sites": sites})
    assert r.status_code == 422
    dup = [EQ, EQ]
    assert env.client.post("/api/raven/terrain-estimate", json={"sites": dup}).status_code == 422
    cmp = {**BODY, "site_ids": [s["id"] for s in sites], "custom_sites": sites}
    assert env.client.post("/api/raven/compare", json=cmp).status_code == 422


# -- estimate ------------------------------------------------------------------------------------
def test_estimate_numbers_equal_the_tile_math_and_nothing_is_downloaded(env: Env) -> None:
    pts = [
        {"id": "c-pole", "name": "Polar", "lat_deg": -89.54, "lon_deg_east": 129.78},
        {"id": "c-s78", "name": "South 78", "lat_deg": -78.0, "lon_deg_east": 40.0},
        EQ,
    ]
    r = env.client.post("/api/raven/terrain-estimate", json={"sites": pts})
    assert r.status_code == 200, r.text
    j = r.json()
    assert env.pds.urls == [] and env.store.dir.exists() is False  # a dry run touches nothing
    by_id = {s["id"]: s for s in j["sites"]}
    for p in pts:
        plan = plan_site(p["lat_deg"], p["lon_deg_east"])
        row = by_id[p["id"]]
        assert row["tiles"] == plan.n_tiles and row["tiles_to_download"] == plan.n_tiles
        assert row["mb_total"] == round(plan.n_tiles * TILE_BYTES / 1e6, 2)
        assert row["resolution_m"] == plan.resolution_m
        assert row["mb_total"] <= j["caps"]["site_mb"]
    assert by_id["c-pole"]["resolution_m"] == 20.0 and by_id["c-s78"]["resolution_m"] == 240.0
    assert by_id["c-eq"]["resolution_m"] == pytest.approx(236.901)
    assert j["mb_to_download"] == pytest.approx(
        sum(s["mb_to_download"] for s in j["sites"]), abs=0.05
    )
    assert j["caps"] == {"site_mb": 10.0, "request_mb": 40.0, "cache_mb": 300.0}


def test_estimate_sees_what_is_cached(env: Env) -> None:
    plan = plan_site(EQ["lat_deg"], EQ["lon_deg_east"])
    site = s0.custom_site("c-eq", EQ["lat_deg"], EQ["lon_deg_east"], strict=True)
    assert env.store.download([site]) == plan.n_tiles
    est = env.store.estimate([site])
    assert est["needs_download"] is False and est["sites"][0]["tiles_cached"] == plan.n_tiles
    assert env.pds.bytes_served == plan.n_tiles * TILE_BYTES  # the plan, no tile more
    assert all(u.startswith("https://pds-geosciences.wustl.edu/") for u in env.pds.urls)
    assert env.store.download([site]) == 0  # nothing left to fetch


# -- 409 / 413 / 429 / 503 -----------------------------------------------------------------------
@needs_kernels
def test_409_without_allow_download_then_200_with_it(env: Env) -> None:
    r = ev(env, EQ)
    assert r.status_code == 409 and r.json()["detail"] == "needs download"
    est = r.json()["estimate"]
    assert est["needs_download"] and est["sites"][0]["tiles_to_download"] > 0
    assert env.pds.urls == []
    r2 = ev(env, EQ, allow_download=True)
    assert r2.status_code == 200, r2.text
    assert env.pds.bytes_served == est["sites"][0]["tiles_to_download"] * TILE_BYTES
    j = r2.json()
    assert j["terrain"]["state"] == "known"
    assert j["terrain"]["resolution_m"] == pytest.approx(236.901)
    assert j["terrain"]["horizon_range_km"] <= 200.0
    assert j["site"]["custom"] is True and j["site"]["name"] == "Equator test"
    assert ev(env, EQ).status_code == 200  # cached now: no flag needed
    before = env.pds.bytes_served
    assert (
        ev(env, {**EQ, "lon_deg_east": 40.0}).status_code == 200 and env.pds.bytes_served == before
    )


def test_413_over_the_request_cap_downloads_nothing(env: Env) -> None:
    sites = [
        {"id": f"c-e{i}", "name": f"Eq {i}", "lat_deg": 5.0, "lon_deg_east": -170.0 + 45.0 * i}
        for i in range(8)
    ]
    body = {
        **BODY,
        "site_ids": [s["id"] for s in sites],
        "custom_sites": sites,
        "allow_download": True,
    }
    r = env.client.post("/api/raven/compare", json=body)
    assert r.status_code == 413 and r.json()["estimate"]["request_over_cap"] is True
    assert env.pds.urls == []


def test_429_over_the_hourly_budget(env: Env) -> None:
    env.svc.mb_per_hour = 1.0
    r = ev(env, EQ, allow_download=True)
    assert r.status_code == 429 and env.pds.urls == []


def test_503_when_the_pds_node_fails_and_nothing_stays_half_written(env: Env) -> None:
    class Down:
        def open(self, *a: Any, **k: Any) -> Any:
            raise urllib.error.URLError("offline")

    env.store.opener = Down()
    r = ev(env, EQ, allow_download=True)
    assert r.status_code == 503
    assert not list(env.store.dir.glob("*.part"))


def test_the_download_never_follows_a_user_url(env: Env) -> None:
    # the only inputs are numbers: every URL requested is one of the lock
    ev(env, EQ, allow_download=True)
    assert env.pds.urls and set(env.pds.urls) <= {
        "https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/cylindrical/float_img/ldem_128_float.img"
    }


def test_cache_total_is_capped_with_oldest_tiles_evicted(env: Env) -> None:
    cap = 9_000_000
    env.store.max_bytes = cap
    a = s0.custom_site("c-a", 0.0, 40.0, strict=True)
    b = s0.custom_site("c-b", 0.0, 200.0, strict=True)
    env.store.download([a])
    first = {p.name for p in env.store.dir.glob("*.f32")}
    env.store.download([b])
    used = dem_cache.usage_bytes(env.store.dir)
    assert used <= cap
    left = {p.name for p in env.store.dir.glob("*.f32")}
    assert len(first - left) > 0  # the oldest tiles of site a went to make room for b
    plan_b = plan_site(0.0, 200.0)
    assert len(left) >= plan_b.n_tiles - 0 and used >= plan_b.n_tiles * TILE_BYTES


# -- unknown terrain -----------------------------------------------------------------------------
@needs_kernels
def test_site_without_terrain_has_unknown_horizon_but_valid_geometry(env: Env) -> None:
    pole = {"id": "c-np", "name": "North pole", "lat_deg": 89.9, "lon_deg_east": 10.0}
    r = ev(env, pole)  # no flag needed: nothing can be downloaded within the cap
    assert r.status_code == 200, r.text
    j = r.json()
    assert env.pds.urls == []
    assert j["terrain"]["state"] == "unknown" and j["terrain"]["reason"] == "exceeds_site_cap"
    assert j["terrain"]["resolution_m"] is None
    st = j["steps"]
    n = j["window"]["n_steps"]
    assert all(v is None for v in st["sun_horizon_deg"]) and all(
        v is None for v in st["earth_horizon_deg"]
    )
    assert all(v is None for v in st["margin_db"]) and all(v is None for v in st["rf_closes"])
    assert set(st["rf_state"]) == {None} and set(st["state"]) == {"unknown"}
    assert set(st["terrain_reason"]) == {"outside_coverage"}
    # geometry, ephemeris, DSN and free space stay valid
    assert all(
        isinstance(v, float) for v in st["sun_el_deg"] + st["earth_el_deg"] + st["earth_range_km"]
    )
    assert (
        all(isinstance(v, float) for v in st["free_space_loss_db"])
        and len(st["free_space_loss_db"]) == n
    )
    assert any(v is not None for v in st["dsn_visible"])
    assert all(v is None for v in st["lit"])  # lit needs the horizon: unknown, never "lit"


@needs_kernels
def test_catalogue_site_outside_the_polar_product_gets_downloaded_terrain(env: Env) -> None:
    """Apollo 11 is outside the 20 m polar product: its terrain comes from the global 237 m product, after the same consent."""
    body = {**BODY, "site_id": "apollo11", "include_steps": False}
    r = env.client.post("/api/raven/evaluate", json=body)
    assert r.status_code == 409 and r.json()["detail"] == "needs download"
    assert env.pds.urls == []  # nothing is fetched without the flag
    r2 = env.client.post("/api/raven/evaluate", json={**body, "allow_download": True})
    assert r2.status_code == 200, r2.text
    j = r2.json()
    assert j["terrain"]["state"] == "known"
    assert j["terrain"]["resolution_m"] == pytest.approx(236.901)
    # the catalogue identity and source are untouched
    assert j["site"]["id"] == "apollo11" and j["site"]["verified"] is True
    assert j["metrics"]["unknown_hours"] < 24  # the terrain is known now, not an all-unknown window


@needs_kernels
def test_scene_and_horizon_of_a_catalogue_site_outside_the_polar_product_use_downloaded_terrain(
    env: Env,
) -> None:
    """Apollo 11: 409 without the consent, then a 3D scene and a horizon from the global 237 m terrain."""
    scene = {"site": "apollo11", "t": "2027-04-16T00:00:00Z"}
    r = env.client.get("/api/raven/scene", params=scene)
    assert r.status_code == 409 and r.json()["detail"] == "needs download"
    assert env.pds.urls == []
    r2 = env.client.get("/api/raven/scene", params={**scene, "allow_download": "true"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["site"]["id"] == "apollo11"
    h = env.client.get("/api/raven/horizon", params={"site": "apollo11"})
    assert h.status_code == 200, h.text  # the tiles of the scene are cached now
    assert h.json()["site"]["id"] == "apollo11"
