# SPDX-License-Identifier: Apache-2.0
"""GET/POST /api/grazing/scene: validazione, 422/503 generici, motore reale se kernel e tile esistono."""

import math
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

np = pytest.importorskip("numpy")
pytest.importorskip("scipy")

from backend.domain.grazing.dem import DEFAULT_DIR
from backend.domain.grazing.scene import fresnel_radius_m
from backend.ephemeris import kernels
from backend.ephemeris.engine import Engine
from scripts.raven_reference import build_reference_app as build_app

try:
    kernels.require_kernels()
    HAVE_KERNELS = True
except kernels.EphemerisUnavailable:  # pragma: no cover
    HAVE_KERNELS = False

needs_kernels = pytest.mark.skipif(not HAVE_KERNELS, reason="kernels missing (make ephemeris)")
HAVE_TILES = DEFAULT_DIR.is_dir() and any(DEFAULT_DIR.glob("*.f32"))
needs_tiles = pytest.mark.skipif(not HAVE_TILES, reason="LOLA tiles missing (make grazing-dem)")
T = "2027-04-07T00:00:00Z"


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    mp = pytest.MonkeyPatch()
    mp.setenv("GRAZING_DEM_ALLOW_DOWNLOAD", "0")
    mp.setenv("RATE_LIMIT_PER_MIN", "100000")
    try:
        yield TestClient(build_app())
    finally:
        mp.undo()


def test_fresnel_radius_matches_model_table() -> None:
    # docs/domain/grazinglink-model.md T6 (lambda 0.035690 m, d2 = 384 400 km)
    for d1, expect in ((10, 0.597), (100, 1.889), (1000, 5.974), (2000, 8.449), (10000, 18.891)):
        assert math.isclose(fresnel_radius_m(1, 0.03569, d1, 384_400_000.0), expect, abs_tol=2e-3)
    assert math.isclose(fresnel_radius_m(1, 0.03569, 1000, 1000), 4.224, abs_tol=2e-3)
    assert fresnel_radius_m(1, 0.03569, 0, 5) == 0.0


def test_scene_validation_and_no_echo(client: TestClient) -> None:
    for params in (
        {"site": "shackleton", "t": "not-a-date-at-all-123456"},
        {"site": "shackleton", "t": T, "rate": "123"},
        {"site": "shackleton", "t": T, "station": "dsn99"},
        {"site": "shackleton", "t": T, "mast": "nan"},
        {"site": "shackleton", "t": T, "gain": "99"},
        {"site": "shackleton", "t": T, "extra": "1"},
        {"t": T},
    ):
        r = client.get("/api/grazing/scene", params=params)
        assert r.status_code == 422, params
        assert "dsn99" not in r.text and "not-a-date" not in r.text


def test_scene_unknown_site_and_bad_rate_are_generic_422(client: TestClient) -> None:
    r = client.get("/api/grazing/scene", params={"site": "nowhere-zz", "t": T})
    assert r.status_code in (422, 503)
    assert "nowhere-zz" not in r.text


@needs_kernels
@needs_tiles
def test_scene_real_engine(client: TestClient) -> None:
    r = client.get("/api/grazing/scene", params={"site": "haworth", "t": T})
    assert r.status_code == 200
    d = r.json()
    matrix = np.asarray(d["sky"]["icrf_to_scene"])
    az = math.radians(d["earth"]["az_deg"])
    enu = Engine().icrf_to_enu("moon", d["site"]["lat_deg"], d["site"]["lon_deg_east"], T)
    expected = (
        np.array([[math.sin(az), math.cos(az), 0], [0, 0, 1], [math.cos(az), -math.sin(az), 0]])
        @ enu
    )
    np.testing.assert_allclose(matrix, expected, atol=1e-5)
    np.testing.assert_allclose(matrix @ matrix.T, np.eye(3), atol=1e-12)
    assert np.linalg.det(matrix) == pytest.approx(1.0, abs=1e-12)
    assert d["terrain"]["source"] == "lola" and not d["terrain"]["synthetic"]
    p = d["terrain"]["patch"]
    assert p["n"] == 96 and len(p["height_m"]) == 96 * 96
    assert p["native_resolution_m"] == 20.0 and p["spacing_m"] > 20.0
    assert d["terrain"]["product_id"] and "radius_resolved" in d["terrain"]
    prof = d["terrain"]["profile"]
    assert len(prof["e_m"]) == len(prof["u_m"]) == len(prof["arc_m"]) >= 100
    # same instant, same geometry and margin as the analysis engine
    a = client.post(
        "/api/grazing/analyze",
        json={"site_id": "haworth", "start_utc": T, "days": 0.05, "step_min": 60},
    ).json()
    assert abs(a["series"]["earth_el_deg"][0] - d["earth"]["el_deg"]) < 0.002
    assert abs(a["series"]["nu"][0] - d["ridge"]["nu"]) < 0.002
    assert abs(a["series"]["margin_chosen_rate_db"][0] - d["link"]["margin_db"]) < 0.006
    # Fresnel radius at the ridge from the formula
    rr = d["ridge"]
    exp = fresnel_radius_m(1, d["fresnel"]["wavelength_m"], rr["d1_m"], rr["d2_m"])
    assert abs(exp - d["fresnel"]["r1_at_ridge_m"]) < 0.002
    dd = d["diffraction"]
    assert abs(dd["diffraction_loss_db"] - (dd["knife_edge_db"] + dd["correction_db"])) < 0.002
    assert d["link"]["state"] in {"open", "transition", "blocked"}
    assert d["link"]["state_label"]
    if not dd["multipath_applicable"]:
        assert dd["multipath_reason"] and dd["multipath_gain_db"] is None
    assert d["antenna"]["mast_tag"] == "I" and d["antenna"]["hpbw_deg"] > 0
    assert client.get("/api/grazing/scene", params={"site": "haworth", "t": T}).json() == d


@needs_kernels
@needs_tiles
def test_scene_mast_and_rate_change_the_numbers(client: TestClient) -> None:
    base = {"site": "de-gerlache", "t": T}
    a = client.get("/api/grazing/scene", params=base).json()
    b = client.get("/api/grazing/scene", params={**base, "mast": 8, "rate": 1e6}).json()
    assert b["antenna"]["mast_height_m"] == 8.0
    assert b["link"]["rate_bps"] == 1e6
    assert b["link"]["margin_db"] < a["link"]["margin_db"]


@needs_kernels
@needs_tiles
def test_scene_out_of_coverage_is_generic_422(client: TestClient) -> None:
    r = client.get("/api/grazing/scene", params={"site": "apollo11", "t": T})
    assert r.status_code == 422
    assert "DEM" in r.json()["detail"]


@needs_kernels
@needs_tiles
def test_scene_user_profile_has_no_height_field(client: TestClient) -> None:
    prof = {
        "distance_m": [0.0, 100.0, 200.0, 300.0, 400.0, 500.0],
        "height_m": [0.0, 1.0, 5.0, 12.0, 4.0, 0.0],
    }
    r = client.post("/api/grazing/scene", json={"site": "apollo11", "t": T, "profile": prof})
    assert r.status_code == 200
    d = r.json()
    assert d["terrain"]["source"] == "user" and d["terrain"]["patch"] is None
    bad = client.post(
        "/api/grazing/scene",
        json={"site": "apollo11", "t": T, "profile": {"distance_m": [0, 1], "height_m": [0]}},
    )
    assert bad.status_code == 422


@needs_kernels
def test_custom_scene_uses_coordinates_and_checks_coverage(client: TestClient) -> None:
    custom = {"id": "custom-a", "lat_deg": 0, "lon_deg_east": 30}
    profile = {"distance_m": [0, 100, 200, 300, 400, 500], "height_m": [0, 1, 5, 12, 4, 0]}
    body = {"site": "custom-a", "t": T, "custom_site": custom, "profile": profile}
    result = client.post("/api/grazing/scene", json=body)
    assert result.status_code == 200, result.text
    assert result.json()["site"]["lon_deg_east"] == 30
    changed = {**body, "custom_site": {**custom, "lon_deg_east": 45}}
    result = client.post("/api/grazing/scene", json=changed)
    assert result.status_code == 200, result.text
    assert result.json()["site"]["lon_deg_east"] == 45
    assert client.post("/api/grazing/scene", json={**body, "profile": None}).status_code == 422
    assert client.post("/api/grazing/scene", json={**body, "site": "apollo11"}).status_code == 422
