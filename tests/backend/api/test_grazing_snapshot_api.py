# SPDX-License-Identifier: Apache-2.0
"""GET /api/grazing/snapshot: validazione, nessun eco, motore reale se kernel e tile esistono."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("numpy")
pytest.importorskip("scipy")

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


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    mp = pytest.MonkeyPatch()
    mp.setenv("GRAZING_DEM_ALLOW_DOWNLOAD", "0")  # tests never touch the network
    mp.setenv("RATE_LIMIT_PER_MIN", "100000")
    try:
        yield TestClient(build_app())
    finally:
        mp.undo()


def test_snapshot_validation_and_no_echo(client: TestClient) -> None:
    for params in (
        {"t": "not-a-date-at-all-123456"},
        {"t": START, "rate_bps": "123"},
        {"t": START, "station": "dsn99"},
        {"t": START, "rate_bps": "nan"},
        {"t": START, "gain": 46},
        {"t": START, "gain": "nan"},
        {"t": START, "extra": "1"},
        {},
    ):
        r = client.get("/api/grazing/snapshot", params=params)
        assert r.status_code == 422, params
        assert "dsn99" not in r.text and "not-a-date" not in r.text


@needs_kernels
@needs_tiles
def test_snapshot_all_sites_real_engine(client: TestClient) -> None:
    r = client.get("/api/grazing/snapshot", params={"t": START})
    assert r.status_code == 200
    d = r.json()
    sites = {s["id"]: s for s in d["sites"]}
    assert sites["apollo11"]["state"] == "out_of_coverage"
    assert sites["apollo11"]["state_label"] == "fuori copertura DEM"
    assert sites["apollo11"]["margin_db"] is None  # never a guessed value
    covered = [s for s in sites.values() if s["dem_covered"]]
    # a covered site whose terrain tile is not cached is reported as unavailable, the others are computed
    computed = [s for s in covered if s["state"] != "unavailable"]
    assert computed and all(s["state"] in {"open", "transition", "blocked"} for s in computed)
    for sid in (
        "malapert-massif",
        "haworth",
        "mons-mouton",
        "nobile-rim",
        "de-gerlache",
        "shackleton",
    ):
        if sites[sid]["dem_covered"]:
            assert sites[sid]["state"] in {"open", "transition", "blocked"}, sid
    assert all(
        s["state_label"] == "dati DEM non disponibili"
        for s in covered
        if s["state"] == "unavailable"
    )
    assert all(s["terrain"]["source"] == "lola" for s in computed)
    assert -0.6 < d["fspl_delta_db"] < 0.6
    cx = {c["complex"]: c for c in d["dsn"]["complexes"]}
    assert set(cx) == {"Goldstone", "Canberra", "Madrid"}
    doc = d["dsn"]["source"]["document"]
    assert "810-005" in doc and "Table 5" in doc
    assert d["dsn"]["sees_moon"] == [c for c, v in cx.items() if v["sees_moon"]]
    # same geometry as the analysis engine at the same instant
    a = client.post(
        "/api/grazing/analyze",
        json={"site_id": "shackleton", "start_utc": START, "days": 0.05, "step_min": 60},
    ).json()
    assert abs(a["series"]["earth_el_deg"][0] - sites["shackleton"]["earth_el_deg"]) < 0.002
    assert client.get("/api/grazing/snapshot", params={"t": START}).json() == d  # cached


@needs_kernels
@needs_tiles
def test_snapshot_rate_changes_margin_not_geometry(client: TestClient) -> None:
    lo = client.get("/api/grazing/snapshot", params={"t": START, "rate_bps": 1e4}).json()
    hi = client.get("/api/grazing/snapshot", params={"t": START, "rate_bps": 1e6}).json()
    s_lo = {s["id"]: s for s in lo["sites"]}["malapert-massif"]
    s_hi = {s["id"]: s for s in hi["sites"]}["malapert-massif"]
    assert s_lo["earth_el_deg"] == s_hi["earth_el_deg"]
    assert s_lo["margin_db"] > s_hi["margin_db"]


@needs_kernels
@needs_tiles
def test_snapshot_gain_changes_margin_not_geometry(client: TestClient) -> None:
    lo = client.get("/api/grazing/snapshot", params={"t": START, "gain": 10}).json()
    hi = client.get("/api/grazing/snapshot", params={"t": START, "gain": 20}).json()
    s_lo = {s["id"]: s for s in lo["sites"]}["malapert-massif"]
    s_hi = {s["id"]: s for s in hi["sites"]}["malapert-massif"]
    assert s_lo["earth_el_deg"] == s_hi["earth_el_deg"]
    assert s_hi["margin_db"] - s_lo["margin_db"] == pytest.approx(10, abs=0.02)
