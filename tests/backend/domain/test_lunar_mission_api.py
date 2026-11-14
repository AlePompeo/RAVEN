# SPDX-License-Identifier: Apache-2.0
"""/api/lunar/mission: validation, unknown propagation and two real sites (Malapert, Haworth)."""

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
    "site_id": "malapert-massif",
    "start_utc": "2027-01-01T00:00:00Z",
    "days": 30,
    "step_min": 60,
}


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(build_app())


def _tiles_cached() -> bool:
    from backend.domain.grazing import horizon as hz
    from backend.domain.grazing.dem import DemUnavailable
    from backend.domain.lunar.model import load_sites

    sites = {s.id: s for s in load_sites()}
    try:
        for sid in ("malapert-massif", "haworth"):
            m = hz.compute_mask(sites[sid].lat_deg, sites[sid].lon_deg_east, 2.0)
            if not m.complete.all():
                return False
    except DemUnavailable:
        return False
    return True


def test_mission_rejects_invalid_requests_generically(client: TestClient) -> None:
    for bad in (
        {**BODY, "days": 91},
        {**BODY, "step_min": 5},
        {**BODY, "days": 90, "step_min": 10},  # 12960 steps > 1500
        {**BODY, "station": "dsn70"},
        {**BODY, "rate_bps": 12345},
        {**BODY, "observer_height_m": -1},
        {**BODY, "energy_overrides": {"tx_power_w": 3}},
        {**BODY, "rf_overrides": {"station": "dsn18"}},
        {**BODY, "site_id": "nope"},
        {**BODY, "extra": 1},
    ):
        r = client.post("/api/lunar/mission", json=bad)
        assert r.status_code == 422, bad
        assert "nope" not in r.text and "12345" not in r.text


@needs_kernels
def test_missing_dem_and_uncovered_site_are_unknown(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    monkeypatch.setenv("GRAZING_DEM_DIR", str(tmp_path))
    for sid in ("malapert-massif", "apollo11"):
        r = client.post("/api/lunar/mission", json={**BODY, "site_id": sid, "days": 1})
        assert r.status_code == 200, r.text
        j = r.json()
        assert set(j["series"]["state"]) == {"unknown"}
        assert all(v is None for v in j["series"]["useful"] + j["series"]["soc"])
        assert j["metrics"]["useful_hours"] == 0 and j["metrics"]["min_soc"] is None
        assert j["inputs_state"]["shadow"] in ("missing_dem", "outside_coverage")


@needs_kernels
@pytest.mark.skipif(not _tiles_cached(), reason="LOLA tiles not cached (prefetch)")
def test_real_sites_malapert_lit_haworth_dark(client: TestClient) -> None:
    mal = client.post("/api/lunar/mission", json=BODY).json()
    haw = client.post("/api/lunar/mission", json={**BODY, "site_id": "haworth"}).json()
    for j in (mal, haw):
        assert j["metrics"]["unknown_steps"] == 0
        assert len(j["series"]["state"]) == 720
        assert j["inputs_state"] == {"shadow": "ok", "rf": "ok", "dsn": "geometric_34m"}
        assert j["parameters"]["observer_height"]["status"] == "I"
        assert any("dominant obstacle" in x for x in j["declared_limits"])
    # Haworth crater floor: the horizon mask hides the Sun for the whole window
    assert all(f == 0.0 for f in haw["series"]["disc_fraction"])
    assert haw["metrics"]["sun_hours"] == 0.0 and haw["metrics"]["useful_hours"] == 0.0
    assert haw["metrics"]["time_to_first_blackout_h"] is not None
    assert haw["series"]["state"][-1] == "dark"
    # Malapert summit: sunlit part of the time and some useful hours
    assert mal["metrics"]["sun_hours"] > 0 and mal["metrics"]["useful_hours"] > 0
    assert any(f and f > 0 for f in mal["series"]["disc_fraction"])
    # dsn18: DSN visibility unknown -> no step is counted as useful or known
    j18 = client.post("/api/lunar/mission", json={**BODY, "days": 2, "station": "dsn18"}).json()
    assert j18["inputs_state"]["dsn"] == "unknown_18m_hypothesis"
    assert set(j18["series"]["state"]) == {"unknown"} and j18["metrics"]["useful_hours"] == 0
