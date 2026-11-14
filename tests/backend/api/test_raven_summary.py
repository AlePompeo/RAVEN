# SPDX-License-Identifier: Apache-2.0
"""The final account of a search: the engine names the best site, a model only explains it, and its text is kept only if it matches the facts."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.api import raven_discover as rd
from backend.api import raven_llm
from backend.bootstrap import build_app
from backend.domain.raven.discovery import summary as sm
from tests.backend.api.test_raven_discover import BRIEF, _fake_factory, _wait

RESULT: dict[str, Any] = {
    "brief": {"days": 14, "priority": "sun"},
    "proposals": [
        {
            "rank": 1,
            "lat_deg": -89.54,
            "lon_deg_east": 12.3,
            "name": "Haworth",
            "core": {"useful_fraction": 0.62, "sun_fraction": 0.71, "rf_fraction": 0.80},
            "meets_objectives": True,
            "on_front": True,
            "terrain": "LOLA 240 m",
            "uncertainty": {"p_meet": 0.83, "p_low": 0.7, "p_high": 0.92},
        },
        {
            "rank": 2,
            "lat_deg": -88.1,
            "lon_deg_east": 40.0,
            "name": None,
            "core": {"useful_fraction": 0.55, "sun_fraction": 0.6, "rf_fraction": None},
            "meets_objectives": False,
            "on_front": False,
            "terrain": "LOLA 240 m",
            "uncertainty": None,
        },
    ],
    "pareto": [{}],
    "evaluated": 54,
    "not_comparable": 3,
    "order": ["useful_fraction"],
    "region": "polar",
}


def test_facts_come_only_from_the_result_and_unknown_stays_unknown() -> None:
    f = sm.facts(RESULT)
    assert f is not None
    assert f["best"]["label"] == "Haworth" and f["second"]["label"] == "site 2"
    assert f["best"]["useful_percent"] == 62 and f["second"]["radio_percent"] is None
    assert f["n_front"] == 1 and f["n_meet"] == 1 and f["evaluated"] == 54
    assert sm.facts({"proposals": []}) is None


def test_template_text_names_the_best_site_in_both_languages_and_passes_its_own_check() -> None:
    f = sm.facts(RESULT)
    assert f is not None
    for lang, word in (("en", "best site"), ("it", "sito migliore")):
        text = sm.template_text(f, lang)
        assert "Haworth" in text and word in text and "62 %" in text and "83 %" in text
        assert sm.check_text(text, f)


def test_check_rejects_a_text_that_invents_a_number_or_forgets_the_site() -> None:
    f = sm.facts(RESULT)
    assert f is not None
    good = "Haworth is the best site: useful time 62 % and Sun 71 %, with a probability of 83 % of meeting the objectives."
    assert sm.check_text(good, f)
    assert not sm.check_text(good.replace("62", "75"), f)  # a number that is not in the facts
    assert not sm.check_text(good.replace("Haworth", "The first"), f)  # the best site is not named
    assert not sm.check_text("Haworth.", f)  # too short to be an account


def _done_job(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, str]:
    monkeypatch.setattr(rd, "make_evaluator", _fake_factory())
    c = TestClient(build_app())
    r = c.post("/api/raven/discover", json={"brief": BRIEF, "budget": 24, "deadline_s": 60})
    job_id = r.json()["job_id"]
    assert _wait(c, job_id)["state"] == "done"
    return c, job_id


def test_the_endpoint_answers_with_the_template_when_no_model_is_asked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c, job_id = _done_job(monkeypatch)
    r = c.post(f"/api/raven/discover/{job_id}/summary", json={"use_model": False, "lang": "it"})
    body = r.json()
    assert r.status_code == 200 and body["text_source"] == "template" and body["model"] is None
    assert body["facts"]["best"]["label"] in body["text"] and "sito migliore" in body["text"]
    assert c.post("/api/raven/discover/nope/summary", json={}).status_code == 404
    assert c.post(f"/api/raven/discover/{job_id}/summary", json={"x": 1}).status_code == 422


def test_a_model_text_is_used_only_if_it_matches_the_facts(monkeypatch: pytest.MonkeyPatch) -> None:
    c, job_id = _done_job(monkeypatch)
    f = c.post(f"/api/raven/discover/{job_id}/summary", json={"use_model": False}).json()["facts"]
    best = f["best"]
    good = f"{best['label']} is the best site for this window, with useful time {best['useful_percent']} % and these estimates rest on illustrative assumptions."
    seen: list[str] = []

    async def fake(
        _req: Any, messages: list[dict[str, str]], allow_external: bool, max_tokens: int = 0
    ) -> tuple[str, str]:
        seen.append(messages[-1]["content"])
        assert allow_external is False
        return good, "assistant-openai-compat:fake"

    monkeypatch.setattr(raven_llm, "complete", fake)
    ok = c.post(f"/api/raven/discover/{job_id}/summary", json={"use_model": True}).json()
    assert ok["text_source"] == "model" and ok["text"] == good and ok["model"].endswith("fake")
    assert "facts" in seen[0]  # the model gets the facts, not the client's words

    async def liar(*_a: Any, **_k: Any) -> tuple[str, str]:
        return (
            f"{best['label']} is the best site with useful time 99 % and everything is certain, no doubts at all remain here.",
            "m",
        )

    monkeypatch.setattr(raven_llm, "complete", liar)
    bad = c.post(f"/api/raven/discover/{job_id}/summary", json={"use_model": True}).json()
    assert bad["text_source"] == "template" and bad["model_note"] == "model_text_rejected"

    async def down(*_a: Any, **_k: Any) -> None:
        return None

    monkeypatch.setattr(raven_llm, "complete", down)
    none = c.post(f"/api/raven/discover/{job_id}/summary", json={"use_model": True}).json()
    assert none["text_source"] == "template" and none["model_note"] == "no_model"


def test_llm_status_reports_without_starting_anything() -> None:
    body = TestClient(build_app()).get("/api/raven/llm/status").json()
    assert (
        set(body) >= {"installed", "running", "free_mb", "min_free_mb", "enough_memory"}
        and body["running"] is False
    )
