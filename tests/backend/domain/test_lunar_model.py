# SPDX-License-Identifier: Apache-2.0
import json
import math
from datetime import UTC, datetime
from pathlib import Path

import pytest

from backend.domain.lunar.model import (
    PARAMS,
    AnalysisWindow,
    EnergyParams,
    LinkParams,
    ParamError,
    defaults_table,
    load_sites,
)


def test_sites_load_and_validate() -> None:
    sites = load_sites()
    assert len(sites) == 51
    assert {s.id for s in sites} >= {"apollo11", "shackleton"}
    assert all(s.verified for s in sites)


def test_site_rejects_bad_data(tmp_path: Path) -> None:
    src = json.loads((Path(__file__).parents[3] / "backend/domain/data/sites.json").read_text())
    src["sites"][0]["lat_deg"] = 91
    p = tmp_path / "s.json"
    p.write_text(json.dumps(src))
    with pytest.raises(ValueError):
        load_sites(p)
    src["sites"][0]["lat_deg"] = 0
    src["sites"][1]["id"] = src["sites"][0]["id"]
    p.write_text(json.dumps(src))
    with pytest.raises(ValueError, match="duplicate"):
        load_sites(p)


def test_defaults_valid_and_labelled() -> None:
    LinkParams.from_overrides()
    EnergyParams.from_overrides()
    rows = defaults_table()
    assert {r["key"] for r in rows} >= set(PARAMS) | {"orientation"}
    for r in rows:
        assert r["status"] in {"V", "D", "I"}
        assert r["source"]
        if r["status"] == "I":
            assert r["source"] == "illustrative"
        if "min" in r:
            assert r["min"] <= r["value"] <= r["max"]


@pytest.mark.parametrize(
    "over",
    [
        {"frequency_ghz": -1},
        {"frequency_ghz": float("nan")},
        {"tx_power_w": float("inf")},
        {"tx_power_w": "20"},
        {"tx_power_w": True},
        {"nonsense": 1},
        {"ground_station_min_elevation_deg": 90},
    ],
)
def test_link_rejects_invalid(over: dict[str, object]) -> None:
    with pytest.raises(ParamError) as e:
        LinkParams.from_overrides(over)
    assert "invalid parameter" == str(e.value)


def test_energy_validation() -> None:
    with pytest.raises(ParamError):
        EnergyParams.from_overrides({"orientation": "sideways"})
    with pytest.raises(ParamError):
        EnergyParams.from_overrides({"orientation": 3})
    with pytest.raises(ParamError):
        EnergyParams.from_overrides({"min_soc": 1.5})
    e = EnergyParams.from_overrides({"orientation": "tilted", "tilt_deg": 30})
    assert e.to_dict()["tilt_deg"] == 30


def test_window() -> None:
    w = AnalysisWindow.build("2027-01-01T00:00:00Z", 1, 60)
    assert w.n_steps == 24 and w.dt_h == 1.0
    assert w.instants()[-1] == datetime(2027, 1, 1, 23, tzinfo=UTC)
    assert w.to_dict()["n_steps"] == 24
    for args in [
        ("2027-01-01", 1, 60),
        ("2027-01-01T00:00:00Z", 400, 60),
        ("2027-01-01T00:00:00Z", 1, 5),
        ("2027-01-01T00:00:00Z", math.nan, 60),
        ("2027-01-01T00:00:00+02:00", 1, 60),
    ]:
        with pytest.raises(ParamError):
            AnalysisWindow.build(*args)
