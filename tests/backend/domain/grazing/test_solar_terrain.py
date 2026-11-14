# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from backend.domain.grazing import horizon as hz
from backend.domain.grazing import solar_terrain as solar
from backend.domain.grazing.dem import DemOutOfCoverage, DemUnavailable, LolaDem
from backend.domain.grazing.terrain import profile_from_user

H = 1.0  # synthetic constant horizon (deg)


def _mask(complete: np.ndarray | None = None) -> hz.HorizonMask:
    n = 360
    return hz.HorizonMask(
        -89.0,
        0.0,
        2.0,
        0.0,
        np.full(n, H),
        np.full(n, 5000.0),
        np.ones(n, dtype=bool) if complete is None else complete,
        0.0,
        hz.MaskConfig(n_azimuths=n),
        [{"id": "x", "sha256": "0", "label_sha256": "0", "scale_m": 20.0, "tiles_missing": 0}],
    )


def _timeline(site_ids: list[str], az: list[Any], el: list[Any]) -> dict[str, Any]:
    return {
        "window": {"n_steps": len(az)},
        "series_time_unix": list(range(len(az))),
        "assumptions": {"lunar_frame": "MOON_ME_DE440_ME421", "ephemeris": {}},
        "sites": [
            {
                "site": {"id": sid, "lat_deg": -89.0, "lon_deg_east": 0.0},
                "series": {"sun_az_deg": az, "sun_el_deg": el},
            }
            for sid in site_ids
        ],
    }


def test_mask_states_limbs_and_disc_fraction() -> None:
    r = 0.27
    els = [H + 0.5, H + 0.1, H, H - 0.1, H - 0.5, None]
    tl = _timeline(["t"], [10.0, 10.0, 10.0, 10.0, 10.0, None], els)
    row = solar.solar_terrain(tl, semidiameter_deg=r, mask_for=lambda _s, _h: _mask())["sites"][0]
    assert row["state"] == [
        "upper_above_profile",
        "upper_above_profile",
        "upper_above_profile",
        "upper_above_profile",
        "upper_below_profile",
        "invalid_geometry",
    ]
    assert row["upper_limb_visible"] == [True, True, True, True, False, None]
    assert row["centre_visible"] == [True, True, True, False, False, None]
    assert row["lower_limb_visible"] == [True, False, False, False, False, None]
    assert row["centre_above_profile"] == row["centre_visible"]
    assert row["lower_above_profile"] == row["lower_limb_visible"]
    f = row["disc_fraction"]
    assert f[0] == pytest.approx(1.0) and f[2] == pytest.approx(0.5, abs=2e-3)
    assert f[4] == 0.0 and f[5] is None
    assert row["horizon_deg"][:5] == [pytest.approx(H)] * 5 and row["horizon_deg"][5] is None
    assert row["mask"]["n_azimuths"] == 360 and row["mask_state"] == "ok"


def test_missing_dem_and_coverage_are_unknown_not_sunlit() -> None:
    def mask_for(site: dict[str, Any], _h: float) -> hz.HorizonMask:
        if site["id"] == "out":
            raise DemOutOfCoverage("outside")
        if site["id"] == "missing":
            raise DemUnavailable("missing")
        comp = np.ones(360, dtype=bool)
        comp[:20] = False
        return _mask(comp)

    tl = _timeline(["out", "missing", "partial"], [5.0, 200.0], [H + 2.0, H + 2.0])
    out, missing, partial = solar.solar_terrain(tl, mask_for=mask_for)["sites"]
    assert out["state"] == ["outside_coverage"] * 2 and out["disc_fraction"] == [None, None]
    assert missing["state"] == ["missing_dem"] * 2 and missing["mask"] is None
    # Sun over an incomplete part of the mask: unknown, never sunlit; complete part: known
    assert partial["state"] == ["missing_dem", "upper_above_profile"]
    assert partial["disc_fraction"][0] is None and partial["horizon_deg"][0] is None
    assert partial["disc_fraction"][1] == pytest.approx(1.0)


def test_assumptions_declare_observer_and_limits() -> None:
    tl = _timeline(["t"], [10.0], [2.0])
    a = solar.solar_terrain(tl, observer_height_m=0.0, mask_for=lambda _s, _h: _mask())[
        "assumptions"
    ]
    assert a["observer_height_m"] == 0.0 and a["observer_height_status"] == "I"
    assert a["method"] == "horizon_mask" and a["dem_policy"] == "cached tiles only; no downloads"
    assert "200 km" in a["coverage_limits"]["beyond"]
    assert [p["id"] for p in a["dem_products"]] == ["ldem_85s_20m_float", "ldem_75s_240m_float"]


def test_circular_horizon_reports_each_direction_and_missing_data(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    profile = profile_from_user([0.0, 1000.0, 2000.0], [0.0, 0.0, 100.0])

    def profile_at(_dem: Any, _lat: float, _lon: float, az: float, _length: float) -> Any:
        if az == 5:
            raise DemUnavailable("missing")
        return profile

    monkeypatch.setattr(solar, "profile_from_dem", profile_at)
    site = {"id": "test", "lat_deg": -89.0, "lon_deg_east": 0.0}
    dem = LolaDem(tmp_path, allow_download=False)
    ground = solar.circular_horizon(site, dem, 0.0)
    raised = solar.circular_horizon(site, dem, 2.0)
    assert len(ground["samples"]) == 72
    assert [s["azimuth_deg"] for s in ground["samples"]] == list(range(0, 360, 5))
    assert ground["samples"][1] == {
        "azimuth_deg": 5,
        "elevation_deg": None,
        "distance_m": None,
        "state": "missing_dem",
    }
    assert raised["samples"][0]["elevation_deg"] < ground["samples"][0]["elevation_deg"]
