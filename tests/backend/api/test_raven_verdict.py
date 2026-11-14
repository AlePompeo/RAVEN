# SPDX-License-Identifier: Apache-2.0
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.api import raven_llm as rl
from backend.bootstrap import build_app

SITES = [
    {
        "name": "Malapert Massif",
        "useful_hours": 120,
        "unknown_hours": 0,
        "margin_min_db": 4.0,
        "min_soc": 0.6,
        "sun_hours": 200,
    },
    {
        "name": "Haworth",
        "useful_hours": 96,
        "unknown_hours": 0,
        "margin_min_db": 9.0,
        "min_soc": 0.55,
        "sun_hours": 180,
    },
]


def _client(monkeypatch: pytest.MonkeyPatch, answer: Any) -> TestClient:
    async def fake(_request: Any, _messages: Any, _ext: bool, _max: int = 320) -> Any:
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(rl, "complete", fake)
    return TestClient(build_app())


def test_the_engine_decides_without_any_model() -> None:
    c = TestClient(build_app())
    r = c.post("/api/raven/report/verdict", json={"sites": SITES}).json()
    assert r["verdict"]["winner"] == "A" and r["verdict"]["decided_by"] == "useful_hours"
    assert (
        r["text_source"] == "template" and "Malapert Massif (A)" in r["text"] and r["model"] is None
    )
    radio = c.post("/api/raven/report/verdict", json={"sites": SITES, "priority": "radio"}).json()
    assert (
        radio["verdict"]["winner"] == "B"
    )  # the priority is part of the decision and is recorded with it


def test_a_valid_model_text_replaces_the_template_but_never_the_winner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    good = "Malapert Massif is the better choice: 120 useful hours against 96, while Haworth keeps the larger RF margin (9.0 dB against 4.0)."
    c = _client(monkeypatch, (good, "ollama:granite4:1b"))
    r = c.post("/api/raven/report/verdict", json={"sites": SITES, "use_model": True}).json()
    assert (
        r["text_source"] == "model"
        and r["text"] == good
        and r["model"] == "ollama:granite4:1b"
        and r["verdict"]["winner"] == "A"
    )


@pytest.mark.parametrize(
    "bad",
    [
        "Haworth is clearly better, with 96 useful hours against 120 for the other site, no doubt about it.",  # names the loser
        "Malapert Massif is the better choice with 130 useful hours against 96 for the other site, a wide gap.",  # an invented number
        "ok",
    ],
)
def test_a_model_text_that_contradicts_the_engine_or_invents_numbers_is_rejected(
    monkeypatch: pytest.MonkeyPatch, bad: str
) -> None:
    c = _client(monkeypatch, (bad, "ollama:x"))
    r = c.post("/api/raven/report/verdict", json={"sites": SITES, "use_model": True}).json()
    assert (
        r["text_source"] == "template"
        and r["model_note"] == "model_text_rejected"
        and r["verdict"]["winner"] == "A"
    )


def test_no_model_or_a_failing_model_leaves_the_template_with_a_generic_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    r = (
        _client(monkeypatch, None)
        .post("/api/raven/report/verdict", json={"sites": SITES, "use_model": True})
        .json()
    )
    assert r["text_source"] == "template" and r["model_note"] is None
    r2 = (
        _client(monkeypatch, TimeoutError("secret host detail"))
        .post("/api/raven/report/verdict", json={"sites": SITES, "use_model": True})
        .json()
    )
    assert (
        r2["text_source"] == "template"
        and r2["model_note"] == "TimeoutError"
        and "secret" not in str(r2)
    )


def test_unknown_values_never_decide_and_the_request_is_validated() -> None:
    c = TestClient(build_app())
    unknown = [{"name": "A site"}, {"name": "B site"}]
    assert (
        c.post("/api/raven/report/verdict", json={"sites": unknown}).json()["verdict"]["winner"]
        == "undetermined"
    )
    assert c.post("/api/raven/report/verdict", json={"sites": SITES[:1]}).status_code == 422
    assert (
        c.post("/api/raven/report/verdict", json={"sites": SITES, "priority": "cheap"}).status_code
        == 422
    )
    assert (
        c.post(
            "/api/raven/report/verdict", json={"sites": [{**SITES[0], "min_soc": 3}, SITES[1]]}
        ).status_code
        == 422
    )
    assert c.post("/api/raven/report/verdict", json={"sites": SITES, "extra": 1}).status_code == 422
