# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.raven_report import build_report_router
from backend.domain.raven import economics as e


def test_launch_co2_matches_the_browser_mirror_values() -> None:
    # same stoichiometry and tank capacities as frontend/src/pages/planner/estimates/missionClass.ts
    assert e.launch_co2_t("falcon9") == {"min": 412, "typical": 466, "max": 497}


def test_unknown_stays_unknown_never_zero() -> None:
    r = e.estimate("rover")
    assert r["cost"]["min"] is None and r["cost"]["typical"] is None and r["cost"]["max"] is None
    assert r["co2e"]["launch"] is None and r["co2e"]["total"] is None
    large = e.estimate("large_lander")["co2e"]["production"]
    assert large["min"] is not None and large["max"] is None  # no upper mass: no upper bound


def test_total_needs_both_parts_for_each_bound() -> None:
    t = e.estimate("small_lander")["co2e"]
    assert t["total"]["min"] == t["launch"]["min"] + t["production"]["min"]
    assert t["total"]["max"] == t["launch"]["max"] + t["production"]["max"]
    assert (
        e.estimate("medium_lander")["co2e"]["total"]["typical"] is None
    )  # no typical mass for the class


def test_every_estimate_carries_tag_source_limits() -> None:
    for c in e.CLASS_IDS:
        r = e.estimate(c)
        assert (
            r["limits"]
            and r["unknown"]
            and r["cost"]["tag"] == "D"
            and r["co2e"]["production"]["tag"] == "I"
        )
        assert len(r["context"]) == 4


def test_unknown_class_rejected() -> None:
    with pytest.raises(ValueError):
        e.estimate("moon_base")


def test_route() -> None:
    app = FastAPI()
    app.include_router(build_report_router())
    c = TestClient(app)
    assert c.get("/api/raven/report/estimate").json()["mission_class"] == "small_lander"
    assert c.get("/api/raven/report/estimate?mission_class=large_lander").status_code == 200
    assert c.get("/api/raven/report/estimate?mission_class=x").status_code == 422
