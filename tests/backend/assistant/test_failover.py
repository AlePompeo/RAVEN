# SPDX-License-Identifier: Apache-2.0
"""Failover per richiesta e circuit breaker: provider scriptati e orologio finto (nessuno sleep)."""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from backend.assistant.breaker import CircuitBreakers
from backend.assistant.config import DEFAULT_PREFERENCE, parse_preference
from backend.assistant.discovery import Candidate
from backend.assistant.kb import KnowledgeBase
from backend.assistant.router import ModelRouter
from backend.assistant.selection import RankEntry, Ranking
from backend.assistant.service import AssistantService, ChatInput
from backend.plugins.assistant_openai.plugin import LLMError

from .conftest import answer_of, parse_sse

ROOT = Path(__file__).resolve().parents[3]
Q = "Quali campi ha il contratto dati della telemetria, power_w e link_margin_db?"
CID = "telemetry-contract"
A = Candidate("ollama", "llama3.1:8b", True)
B = Candidate("ollama", "phi4:4b", True)
HOSTED = Candidate("assistant-openai-compat", "big", False)


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


class Script:
    """Provider finto: `plan` = eccezione prima del primo token / pezzi / eccezione dopo."""

    def __init__(
        self,
        pieces: list[str] | None = None,
        *,
        fail: Exception | None = None,
        fail_after: bool = False,
        clock: Clock | None = None,
        burn_s: float = 0.0,
    ) -> None:
        self.pieces = pieces if pieces is not None else [f"Risposta [{CID}] power_w."]
        self.fail, self.fail_after = fail, fail_after
        self.clock, self.burn_s = clock, burn_s
        self.calls = 0

    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        self.calls += 1
        if self.clock:
            self.clock.t += self.burn_s
        if self.fail and not self.fail_after:
            raise self.fail
        for p in self.pieces:
            yield p
        if self.fail and self.fail_after:
            raise self.fail


class FakeDiscovery:
    def __init__(self, cands: list[Candidate]) -> None:
        self.cands = cands
        self.failed: list[str] = []

    async def candidates(self) -> list[Candidate]:
        return list(self.cands)

    def errors(self) -> dict[str, str]:
        return {}

    def mark_failed(self, provider: str) -> None:
        self.failed.append(provider)


class Rank:
    def __init__(self, r: Ranking) -> None:
        self.r = r

    def get(self) -> Ranking:
        return self.r


def build(
    providers: dict[Candidate, Script],
    clock: Clock,
    *,
    ranking: Ranking | None = None,
    budget: float = 30.0,
    failures: int = 3,
    cooldown: float = 30.0,
) -> tuple[AssistantService, ModelRouter]:
    router = ModelRouter(
        mode="auto",
        discovery=FakeDiscovery(list(providers)),  # type: ignore[arg-type]
        make_provider=lambda c: providers[c],
        timeout_for=lambda c: 5.0,
        breakers=CircuitBreakers(failures, cooldown, clock),
        ranking=Rank(ranking or Ranking()),  # type: ignore[arg-type]
        prefs=parse_preference(DEFAULT_PREFERENCE),
    )
    svc = AssistantService(
        KnowledgeBase(ROOT),
        router=router,
        llm_allowed=lambda _k: True,
        failover_budget_s=budget,
        clock=clock,
    )
    return svc, router


async def ask(svc: AssistantService, **kw: Any) -> list[tuple[str, dict[str, Any]]]:
    inp = ChatInput(messages=[{"role": "user", "content": Q}], **kw)
    return parse_sse("".join([e async for e in svc.chat_events(inp)]))


def warn(ev: list[tuple[str, dict[str, Any]]]) -> list[str]:
    return next((d["codes"] for e, d in ev if e == "warning"), [])


async def test_auto_prefers_measured_best_and_reports_it() -> None:
    a, b = Script(), Script()
    r = Ranking({(A.provider, A.model): RankEntry(0.7), (B.provider, B.model): RankEntry(0.9)})
    svc, _ = build({A: a, B: b}, Clock(), ranking=r)
    meta = (await ask(svc))[0][1]
    assert (a.calls, b.calls) == (0, 1)
    assert meta | {"retrieved": 0, "level": 0, "lang": 0} == {
        "provider": "ollama",
        "model": "phi4:4b",
        "mode": "llm",
        "selection": "auto",
        "fallback_from": None,
        "reason": "ranking",
        "external": False,
        "retrieved": 0,
        "level": 0,
        "lang": 0,
    }


async def test_first_candidate_fails_before_token_next_one_answers() -> None:
    a, b = Script(fail=LLMError("x", "http_500")), Script()
    svc, router = build({A: a, B: b}, Clock())
    ev = await ask(svc)
    meta = ev[0][1]
    assert meta["model"] == "phi4:4b" and meta["fallback_from"] == A.id
    assert meta["reason"] == "provider_error" and meta["selection"] == "auto"
    assert "provider_fallback" in warn(ev) and CID in answer_of(ev)
    assert (a.calls, b.calls) == (1, 1)  # un solo tentativo ciascuno: nessuna tempesta di retry
    assert router.breakers.last_error(A.key) == "http_500"
    assert router.discovery.failed == ["ollama"]  # type: ignore[union-attr]


async def test_breaker_opens_skips_then_half_open_probe_recovers() -> None:
    clock = Clock()
    a, b = Script(fail=TimeoutError()), Script()
    svc, router = build({A: a, B: b}, clock, failures=3, cooldown=30.0)
    for _ in range(3):
        await ask(svc)
    assert a.calls == 3 and router.breakers.state(A.key) == "open"
    ev = await ask(svc)  # aperto: A non viene nemmeno contattato
    assert a.calls == 3 and ev[0][1]["model"] == "phi4:4b"
    assert ev[0][1]["fallback_from"] == A.id and ev[0][1]["reason"] == "provider_unhealthy"
    assert "provider_unhealthy" in warn(ev)
    assert router.breakers.last_error(A.key) == "timeout"
    clock.t += 31  # raffreddamento scaduto: una sola prova (mezzo aperto)
    a.fail = None
    ev = await ask(svc)
    assert a.calls == 4 and ev[0][1]["model"] == "llama3.1:8b" and ev[0][1]["fallback_from"] is None
    assert router.breakers.state(A.key) == "closed"


async def test_half_open_probe_failure_reopens() -> None:
    clock = Clock()
    a, b = Script(fail=LLMError("x", "http_429")), Script()
    svc, router = build({A: a, B: b}, clock, failures=5, cooldown=30.0)
    await ask(svc)  # 429: apre subito
    assert router.breakers.state(A.key) == "open"
    clock.t += 31
    await ask(svc)  # prova fallita
    assert a.calls == 2 and router.breakers.state(A.key) == "open"
    await ask(svc)
    assert a.calls == 2


async def test_all_candidates_fail_falls_to_extractive_with_warning() -> None:
    a, b = Script(fail=RuntimeError("segreto")), Script(fail=LLMError("x", "unreachable"))
    svc, _ = build({A: a, B: b}, Clock())
    ev = await ask(svc)
    meta = ev[0][1]
    assert meta["provider"] == "assistant-extractive" and meta["mode"] == "extractive"
    assert meta["model"] is None and meta["external"] is False
    assert meta["fallback_from"] == A.id and meta["reason"] == "all_candidates_failed"
    assert {"provider_fallback", "all_candidates_failed"} <= set(warn(ev))
    assert "power_w" in answer_of(ev) and "segreto" not in str(ev)


async def test_no_switch_after_first_token() -> None:
    a = Script([f"Parziale [{CID}] "], fail=RuntimeError("boom"), fail_after=True)
    b = Script()
    svc, router = build({A: a, B: b}, Clock())
    ev = await ask(svc)
    assert b.calls == 0 and ev[0][1]["model"] == A.model and ev[0][1]["fallback_from"] is None
    assert "llm_interrupted" in warn(ev) and "Parziale" in answer_of(ev)
    assert "provider_fallback" not in warn(ev) and ev[-1][0] == "done"
    assert router.breakers.last_error(A.key) == "error"


async def test_time_budget_stops_further_attempts() -> None:
    clock = Clock()
    a = Script(fail=TimeoutError(), clock=clock, burn_s=12.0)
    b = Script()
    svc, _ = build({A: a, B: b}, clock, budget=10.0)
    ev = await ask(svc)
    assert b.calls == 0 and ev[0][1]["provider"] == "assistant-extractive"
    assert "all_candidates_failed" in warn(ev)


async def test_failover_budget_only_limits_time_to_first_token() -> None:
    class SlowStream:
        async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
            yield f"Risposta [{CID}]"
            await asyncio.sleep(0.08)
            yield " completata."

    svc = AssistantService(
        KnowledgeBase(ROOT),
        make_provider=lambda _: SlowStream(),
        provider_id="test",
        timeout_for=lambda _: 1.0,
        llm_allowed=lambda _: True,
        failover_budget_s=0.04,
    )
    events = await ask(svc)
    assert answer_of(events).endswith("completata.")
    assert "llm_interrupted" not in warn(events)


async def test_external_flag_and_forced_override() -> None:
    h, a = Script(), Script()
    svc, _ = build({A: a, HOSTED: h}, Clock())
    ev = await ask(svc, override=HOSTED, allow_external=True)
    meta = ev[0][1]
    assert meta["external"] is True and meta["selection"] == "forced"
    assert meta["reason"] == "user_override" and (a.calls, h.calls) == (0, 1)


async def test_forced_override_failure_goes_to_extractive_not_to_other_models() -> None:
    a, b = Script(fail=RuntimeError("x")), Script()
    svc, _ = build({A: a, B: b}, Clock())
    ev = await ask(svc, override=A)
    assert b.calls == 0 and ev[0][1]["provider"] == "assistant-extractive"
    assert ev[0][1]["selection"] == "forced"


async def test_no_candidates_is_plain_extractive_without_noise() -> None:
    svc, _ = build({}, Clock())
    ev = await ask(svc)
    assert (
        ev[0][1]["provider"] == "assistant-extractive" and ev[0][1]["reason"] == "no_llm_available"
    )
    assert warn(ev) == [] and ev[0][1]["fallback_from"] is None


async def test_rate_limit_degrades_without_failover_noise() -> None:
    a = Script()
    svc, router = build({A: a}, Clock())
    svc._llm_allowed = lambda _k: False
    ev = await ask(svc)
    assert a.calls == 0 and warn(ev) == ["llm_rate_limited"]
    assert ev[0][1]["fallback_from"] is None and ev[0][1]["reason"] == "rate_limited"
    assert not router.breakers.is_open(A.key)


@pytest.mark.parametrize("n", [1, 2])
async def test_attempt_count_bounded_per_request(n: int) -> None:
    provs = {
        Candidate("ollama", f"m{i}", True): Script(fail=RuntimeError("x")) for i in range(n + 2)
    }
    svc, _ = build(provs, Clock())
    await ask(svc)
    assert all(p.calls == 1 for p in provs.values())
