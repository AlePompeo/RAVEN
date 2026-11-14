# SPDX-License-Identifier: Apache-2.0
import base64
import json
import threading
import time
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.api import raven_discover as rd
from backend.bootstrap import build_app
from scripts import raven_golden as rg

BRIEF = {"start_utc": "2027-04-07T00:00:00Z", "days": 14, "k": 4, "min_distance_km": 25}


def _fake_factory(gate: threading.Event | None = None) -> Any:
    """A 'core' that is a deterministic function of the overlay features, so that the job is fast and its answer is known."""

    def factory(_app: Any, feat: Any, _brief: Any, tick: Any) -> Any:
        names = {n: i for i, n in enumerate(feat.names)}

        def evaluate(i: int, overrides: dict | None = None) -> dict[str, float] | None:
            if overrides is None:
                tick()
            if gate is not None:
                gate.wait(5)
            x = feat.x[i]
            if x[names["rho"]] < 0.02:
                return None  # the very pole: pretend there is no terrain
            both, sun, earth = (
                x[names["both"]] / 100,
                x[names["sun"]] / 100,
                x[names["earth"]] / 100,
            )
            sun *= (
                (overrides or {}).get("energy", {}).get("array_area_m2", 1.0)
            )  # a bigger array, more of the window with power
            return {
                "useful_fraction": 0.9 * both,
                "sun_fraction": sun,
                "rf_fraction": earth,
                "useful_hours": 100 * both,
                "unknown_hours": 0.0,
            }

        return evaluate

    return factory


def _wait(c: TestClient, job_id: str, limit: float = 60.0) -> dict[str, Any]:
    t0 = time.time()
    while time.time() - t0 < limit:
        j = c.get(f"/api/raven/discover/{job_id}").json()
        if j["state"] != "running":
            return j  # type: ignore[no-any-return]
        time.sleep(0.2)
    raise AssertionError("the job did not finish")


def test_a_brief_without_a_window_is_rejected_and_extra_fields_too() -> None:
    c = TestClient(build_app())
    r = c.post("/api/raven/discover", json={"brief": {"k": 3}})
    assert r.status_code == 422 and r.json()["missing"] == ["start_utc", "days"]
    assert c.post("/api/raven/discover", json={"brief": BRIEF, "extra": 1}).status_code == 422
    assert c.post("/api/raven/discover", json={"brief": BRIEF, "budget": 5}).status_code == 422
    assert c.get("/api/raven/discover/nope").status_code == 404


def test_a_search_runs_as_a_job_and_returns_core_values_with_honest_intervals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rd, "make_evaluator", _fake_factory())
    c = TestClient(build_app())
    r = c.post(
        "/api/raven/discover",
        json={
            "brief": {**BRIEF, "min_sun_percent": 40, "min_rf_percent": 70},
            "budget": 40,
            "deadline_s": 60,
        },
    )
    assert r.status_code == 202
    j = _wait(c, r.json()["job_id"])
    assert j["state"] == "done" and j["evaluated"] <= 40
    res = j["result"]
    json.dumps(res, allow_nan=False)  # strict JSON: no NaN or infinity anywhere
    assert 1 <= len(res["proposals"]) <= 4 and res["tag"] == "I" and res["limits"]
    values = [p["core"]["useful_fraction"] for p in res["proposals"]]
    assert values == sorted(values, reverse=True) or any(
        p["meets_objectives"] is False for p in res["proposals"]
    )
    assert all(p["terrain"] == "LOLA 240 m" and p["rank"] >= 1 for p in res["proposals"])
    sui = res["suitability"]
    raster = np.frombuffer(base64.b64decode(sui["data_b64"]), dtype=np.uint8)
    assert raster.size == sui["size"] ** 2 and (raster > 0).sum() > 10_000 and sui["tag"] == "I"
    assert res["not_comparable"] >= 0 and "conformal" in res["interval"]


def test_only_one_search_at_a_time(monkeypatch: pytest.MonkeyPatch) -> None:
    gate = threading.Event()
    monkeypatch.setattr(rd, "make_evaluator", _fake_factory(gate))
    c = TestClient(build_app())
    first = c.post("/api/raven/discover", json={"brief": BRIEF, "budget": 16, "deadline_s": 30})
    assert first.status_code == 202
    second = c.post("/api/raven/discover", json={"brief": BRIEF, "budget": 16})
    assert second.status_code == 409 and second.headers["retry-after"]
    gate.set()
    assert _wait(c, first.json()["job_id"])["state"] == "done"
    assert (
        c.post(
            "/api/raven/discover", json={"brief": BRIEF, "budget": 16, "deadline_s": 30}
        ).status_code
        == 202
    )


def test_a_failing_evaluator_gives_a_failed_job_with_a_generic_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*_a: Any) -> Any:
        raise RuntimeError("secret detail")

    monkeypatch.setattr(rd, "make_evaluator", boom)
    c = TestClient(build_app())
    j = _wait(
        c, c.post("/api/raven/discover", json={"brief": BRIEF, "budget": 16}).json()["job_id"]
    )
    assert j["state"] == "failed" and j["error"] == "RuntimeError" and "secret" not in json.dumps(j)


@pytest.mark.skipif(
    not (rg.have_kernels() and rg.have_tiles()), reason="kernels or LOLA tiles missing"
)
def test_the_real_core_evaluates_polar_cells_on_the_same_product() -> None:
    c = TestClient(build_app())
    r = c.post(
        "/api/raven/discover",
        json={"brief": {**BRIEF, "days": 3, "k": 2}, "budget": 14, "deadline_s": 120},
    )
    j = _wait(c, r.json()["job_id"], 150)
    assert j["state"] == "done", j
    res = j["result"]
    assert res["evaluated"] + res["not_comparable"] <= 14
    for p in res["proposals"]:
        assert 0.0 <= p["core"]["useful_fraction"] <= 1.0 and p["terrain"] == "LOLA 240 m"


def test_the_probability_of_meeting_the_objectives_comes_with_an_interval_and_drivers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rd, "make_evaluator", _fake_factory())
    c = TestClient(build_app())
    body = {
        "brief": {**BRIEF, "min_sun_percent": 45, "min_rf_percent": 50},
        "budget": 40,
        "deadline_s": 60,
        "uncertainty_samples": 16,
    }
    j = _wait(c, c.post("/api/raven/discover", json=body).json()["job_id"])
    assert j["state"] == "done"
    res = j["result"]
    json.dumps(res, allow_nan=False)
    ps = [p["uncertainty"] for p in res["proposals"]]
    assert all(
        u and u["samples"] == 16 and 0.0 <= u["p_low"] <= u["p_meet"] <= u["p_high"] <= 1.0
        for u in ps
    )
    order = [u["p_meet"] for u in ps]
    assert order == sorted(order, reverse=True)  # ranked by the probability first
    assert any(
        u["drivers"] and u["drivers"][0]["parameter"] == "array_area_m2"
        for u in ps
        if 0 < u["p_meet"] < 1
    ) or all(u["p_meet"] in (0.0, 1.0) for u in ps)
    assert res["parameter_spreads"] and "Wilson" in res["uncertainty_note"]


def test_without_objectives_or_with_zero_samples_there_is_no_probability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rd, "make_evaluator", _fake_factory())
    c = TestClient(build_app())
    j = _wait(
        c,
        c.post("/api/raven/discover", json={"brief": BRIEF, "budget": 24, "deadline_s": 30}).json()[
            "job_id"
        ],
    )
    assert (
        all(p["uncertainty"] is None for p in j["result"]["proposals"])
        and j["result"]["parameter_spreads"] == []
    )
    j2 = _wait(
        c,
        c.post(
            "/api/raven/discover",
            json={
                "brief": {**BRIEF, "min_sun_percent": 40},
                "budget": 24,
                "uncertainty_samples": 0,
            },
        ).json()["job_id"],
    )
    assert all(p["uncertainty"] is None for p in j2["result"]["proposals"])


def _catalogue_factory(_app: Any, feat: Any, _brief: Any, tick: Any) -> Any:
    """A 'core' for named sites: deterministic in the latitude and longitude of the site; a few sites without terrain."""

    def evaluate(i: int, overrides: dict | None = None) -> dict[str, float] | None:
        if overrides is None:
            tick()
        lat, lon = float(feat.lat[i]), float(feat.lon[i])
        if i % 9 == 0:
            return None  # no terrain in the cache
        sun = min(1.0, max(0.0, (lat + 90.0) / 90.0))
        rf = min(1.0, max(0.0, 0.5 + 0.5 * np.cos(np.radians(lon))))
        return {
            "useful_fraction": 0.8 * sun * rf,
            "sun_fraction": sun,
            "rf_fraction": rf,
            "useful_hours": 10.0,
            "unknown_hours": 0.0,
        }

    return evaluate


def test_the_catalogue_region_evaluates_the_named_sites_and_reports_the_pareto_front(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(rd, "make_evaluator", _catalogue_factory)
    c = TestClient(build_app())
    body = {
        "brief": {**BRIEF, "k": 5},
        "budget": 60,
        "deadline_s": 60,
        "region": "catalogue",
        "order": ["sun_fraction"],
    }
    j = _wait(c, c.post("/api/raven/discover", json=body).json()["job_id"])
    assert j["state"] == "done", j
    res = j["result"]
    json.dumps(res, allow_nan=False)
    assert (
        res["region"] == "catalogue"
        and res["suitability"] is None
        and res["evaluated"] + res["not_comparable"] <= 51
    )
    assert res["not_comparable"] >= 5 and all(p["name"] for p in res["proposals"])
    suns = [p["core"]["sun_fraction"] for p in res["proposals"]]
    assert (
        suns == sorted(suns, reverse=True) and res["order"][0] == "sun_fraction"
    )  # the user's order decides first
    assert res["pareto"] and any(p["on_front"] for p in res["proposals"])
    # nothing on the front is dominated by another front member on the three components
    pts = [
        (f["core"]["useful_fraction"], f["core"]["sun_fraction"], f["core"]["rf_fraction"])
        for f in res["pareto"]
    ]
    for a in pts:
        assert not any(
            b != a
            and all(x >= y for x, y in zip(b, a, strict=True))
            and any(x > y for x, y in zip(b, a, strict=True))
            for b in pts
        )


def test_an_unknown_order_or_region_is_refused() -> None:
    c = TestClient(build_app())
    assert (
        c.post("/api/raven/discover", json={"brief": BRIEF, "order": ["margin"]}).status_code == 422
    )
    assert c.post("/api/raven/discover", json={"brief": BRIEF, "region": "mars"}).status_code == 422
