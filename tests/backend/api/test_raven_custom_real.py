# SPDX-License-Identifier: Apache-2.0
"""The real engine: a custom point on a catalogue site gives the catalogue result (stated tolerances)."""

from pathlib import Path
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient

pytest.importorskip("scipy")

from backend.api.raven_custom import TerrainService
from backend.bootstrap import build_app
from backend.domain.grazing.dem import dem_dir
from backend.domain.raven import s0_context as s0
from backend.domain.raven.custom_terrain import TerrainStore
from scripts import raven_golden as rg

needs_real = pytest.mark.skipif(
    not (rg.have_kernels() and rg.have_tiles()), reason="kernels or LOLA tiles missing"
)


def arr(j: dict[str, Any], k: str) -> Any:
    return np.array([np.nan if v is None else v for v in j["steps"][k]], dtype=float)


@needs_real
@pytest.mark.parametrize("sid", ["malapert-massif", "shackleton"])
def test_custom_point_on_a_catalogue_site_matches_the_catalogue(
    sid: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same coordinates, own tile plan (radial step 20 m instead of 10 m near, far range 100 km
    instead of 200 km, far step 240 m instead of 120 m). Stated tolerances: Sun horizon 2 deg, Earth
    horizon 0.6 deg, margins 1e-6 dB (same RF profile), `lit` identical, useful fraction within 0.02."""
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "100000")
    app = build_app()
    app.state.raven.terrain = TerrainService(
        TerrainStore(
            tmp_path / "custom", fallback=dem_dir()
        )  # the cached catalogue tiles: no download
    )
    c = TestClient(app)
    s = s0.load_catalog()[sid]
    body = {"start_utc": "2027-04-07T00:00:00Z", "days": 14, "step_min": 60}
    a = c.post("/api/raven/evaluate", json={**body, "site_id": sid}).json()
    cs = {"id": "c-x", "name": "X", "lat_deg": s.lat_deg, "lon_deg_east": s.lon_deg_east}
    r = c.post("/api/raven/evaluate", json={**body, "site_id": "c-x", "custom_site": cs})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["terrain"]["resolution_m"] == 20.0 and b["terrain"]["horizon_range_km"] < 200.0
    assert not np.isnan(arr(b, "sun_horizon_deg")).any()
    assert np.nanmax(np.abs(arr(a, "sun_horizon_deg") - arr(b, "sun_horizon_deg"))) < 2.0
    assert np.nanmax(np.abs(arr(a, "earth_horizon_deg") - arr(b, "earth_horizon_deg"))) < 0.6
    assert a["steps"]["lit"] == b["steps"]["lit"]
    np.testing.assert_allclose(
        arr(a, "margin_db"), arr(b, "margin_db"), atol=1e-6, rtol=0, equal_nan=True
    )
    assert abs(a["metrics"]["useful_fraction"] - b["metrics"]["useful_fraction"]) < 0.02
