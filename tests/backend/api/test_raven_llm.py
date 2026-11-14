# SPDX-License-Identifier: Apache-2.0
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.api import raven_llm as rl
from backend.api.raven_brief import parse_rules
from backend.bootstrap import build_app

TEXT = "una missione di tre settimane da giugno 2027, almeno il 60% di sole, 4 siti vicino al polo sud, con buona comunicazione radio"


def test_grounding_keeps_only_what_the_text_supports() -> None:
    t = "21 giorni da aprile 2027, 100 kbit/s, 60% di sole, 4 siti, collegamento radio"
    assert rl.grounded("days", 21, t) and rl.grounded("days", 3 * 7, "tre settimane, 21 giorni")
    assert (
        rl.grounded("rate_bps", 100_000, t)
        and rl.grounded("min_sun_percent", 60, t)
        and rl.grounded("k", 4, t)
    )
    assert not rl.grounded(
        "min_sun_percent", 75, t
    )  # a number that is not in the text is an invention
    assert (
        not rl.grounded("k", 5, t)
        and not rl.grounded("days", True, t)
        and not rl.grounded("days", "21", t)
    )
    assert rl.grounded("start_utc", "2027-04-01", t) and not rl.grounded(
        "start_utc", "2028-04-01", t
    )
    assert rl.grounded("priority", "radio", t) and not rl.grounded("priority", 3, t)
    # an enumerated value needs a word of the text that stands for it: "balanced" or a lander class nobody mentioned is an invention
    assert not rl.grounded("priority", "balanced", t) and not rl.grounded("priority", "earth", t)
    assert not rl.grounded("mission_class", "medium_lander", t)
    assert rl.grounded("mission_class", "rover", "una missione con un rover") and rl.grounded(
        "priority", "balanced", "un compromesso bilanciato"
    )


def test_merge_never_overrides_the_rules_and_rejects_ungrounded_or_invalid_values() -> None:
    rules = parse_rules(TEXT)
    assert (
        rules.brief.priority is None and rules.brief.k == 4
    )  # the rules found the sites, not the priority
    proposed: dict[str, Any] = {
        "priority": "radio",
        "k": 9,
        "days": 21,
        "min_rf_percent": 150,
        "min_sun_percent": 90,
        "bogus": 1,
        "start_utc": None,
        "max_slope_deg": 8,
    }
    merged, filled, rejected = rl.merge(rules, proposed, TEXT)
    b = merged.brief
    assert b.priority == "radio" and b.k == 4  # filled the gap, did not override the rules' 4
    assert b.min_sun_percent == 60  # the rules' value stays (the model's 90 is ignored)
    assert (
        "days" in filled or b.days == 21
    )  # "tre settimane" is 21 days; the number 21 is not written, so it is either rules or rejected
    assert set(rejected) >= {"min_rf_percent", "max_slope_deg"} and "bogus" not in filled


def _app_with(monkeypatch: pytest.MonkeyPatch, answer: Any) -> TestClient:
    async def fake(_request: Any, _text: str, _found: dict[str, Any], _ext: bool) -> Any:
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(rl, "ask", fake)
    return TestClient(build_app())


def test_the_route_uses_the_model_only_when_asked_and_reports_what_it_filled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = _app_with(monkeypatch, ({"priority": "radio", "k": 7}, "ollama:granite4:1b"))
    off = c.post("/api/raven/brief/parse", json={"text": TEXT}).json()
    assert off["level"] == "rules" and off["model"] is None and off["brief"]["priority"] is None
    on = c.post("/api/raven/brief/parse", json={"text": TEXT, "use_model": True}).json()
    assert (
        on["level"] == "rules+model"
        and on["model"] == "ollama:granite4:1b"
        and on["filled_by_model"] == ["priority"]
    )
    assert (
        on["brief"]["priority"] == "radio" and on["brief"]["k"] == 4
    )  # the invented 7 is not in the text
    assert "priority" not in on["unresolved"]


def test_a_failing_model_leaves_the_rules_result_with_a_generic_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = _app_with(monkeypatch, TimeoutError("secret detail of the host"))
    r = c.post("/api/raven/brief/parse", json={"text": TEXT, "use_model": True}).json()
    assert (
        r["level"] == "rules"
        and r["model_error"] == "TimeoutError"
        and "secret" not in str(r)
        and r["brief"]["k"] == 4
    )


def test_no_model_available_says_so_and_a_complete_prompt_does_not_call_the_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = _app_with(monkeypatch, None)
    r = c.post("/api/raven/brief/parse", json={"text": TEXT, "use_model": True}).json()
    assert r["level"] == "rules" and r["model"] is None and r["model_available"] is False
    full = "dammi 3 siti per 14 giorni da aprile 2027 con priorità al sole"
    calls: list[int] = []

    async def counting(*_a: Any) -> Any:
        calls.append(1)
        return None

    monkeypatch.setattr(rl, "ask", counting)
    c.post("/api/raven/brief/parse", json={"text": full, "use_model": True})
    assert calls == []  # nothing left unresolved: no model call, no tokens


def test_the_online_path_needs_a_configured_service_and_refuses_a_denied_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    monkeypatch.setenv("RAVEN_SI_CLOUD_ENABLED", "1")
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.setenv("GROQ_MODEL", "qwen/qwen3-32b")
    assert asyncio.run(rl.pick(TestClient(build_app()).app, True)) is None  # type: ignore[arg-type]
    monkeypatch.delenv("GROQ_API_KEY")
    monkeypatch.setenv("GROQ_MODEL", "openai/gpt-oss-20b")
    assert asyncio.run(rl.pick(TestClient(build_app()).app, True)) is None  # type: ignore[arg-type]  # no key: nothing to call


def test_the_rules_understand_the_verbs_of_priority_and_the_model_cannot_invent_one() -> None:
    for text, want in (
        ("14 giorni da aprile 2027, 4 siti, privilegiando la comunicazione", "radio"),
        ("14 days from April 2027, 4 sites, favouring the Sun", "sun"),
        ("14 giorni da aprile 2027, 4 siti, preferisco la Terra", "earth"),
        ("14 days from April 2027, 4 sites, prioritize radio", "radio"),
    ):
        assert parse_rules(text).brief.priority == want, text
    rules = parse_rules("dammi 4 siti per 14 giorni da aprile 2027")
    merged, filled, rejected = rl.merge(
        rules,
        {"priority": "balanced", "mission_class": "medium_lander"},
        "dammi 4 siti per 14 giorni da aprile 2027",
    )
    assert merged.brief.priority is None and merged.brief.mission_class is None and not filled
    assert set(rejected) == {"priority", "mission_class"}
