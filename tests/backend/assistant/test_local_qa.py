# SPDX-License-Identifier: Apache-2.0
"""The bundled model as a candidate of the RAVEN SI Q&A: offered only when installed and the memory allows, lazy start, graceful fallback."""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from backend.assistant import local_llm as ll
from backend.assistant.breaker import CircuitBreakers
from backend.assistant.config import DEFAULT_PREFERENCE, parse_preference
from backend.assistant.discovery import EXTRACTIVE, Candidate, Discovery
from backend.assistant.router import AUTO, ModelRouter


def _router(mode: str = AUTO, extra: list[Candidate] | None = None) -> ModelRouter:
    disc = Discovery([])
    if extra:

        async def fake() -> list[Candidate]:
            return list(extra)

        disc.candidates = fake  # type: ignore[method-assign]
    return ModelRouter(
        mode=mode,
        discovery=disc,
        make_provider=lambda c: None,
        timeout_for=lambda c: 30.0,
        breakers=CircuitBreakers(),
        prefs=parse_preference(DEFAULT_PREFERENCE),
    )


@pytest.fixture
def installed_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ll, "usable", lambda: True)
    monkeypatch.setattr(ll, "manifest", lambda: {"name": "ministral-test"})


def test_the_local_model_is_a_candidate_only_when_usable(
    monkeypatch: pytest.MonkeyPatch, installed_model: None
) -> None:
    got = asyncio.run(_router().candidates())
    assert [(c.provider, c.model, c.local) for c in got] == [
        (ll.LOCAL_ID, "ministral-test", True),
        (EXTRACTIVE.provider, EXTRACTIVE.model, EXTRACTIVE.local),
    ]
    monkeypatch.setattr(ll, "usable", lambda: False)  # not installed, or not enough memory
    assert [c.provider for c in asyncio.run(_router().candidates())] == [EXTRACTIVE.provider]
    monkeypatch.setattr(ll, "usable", lambda: True)
    assert [c.provider for c in asyncio.run(_router("ollama").candidates())] == [
        EXTRACTIVE.provider
    ]  # a forced provider never gets the bundled model added


def test_the_user_own_model_is_tried_before_the_bundled_one(installed_model: None) -> None:
    mine = Candidate("ollama", "granite4:1b", True)
    plan = asyncio.run(_router(extra=[mine]).plan("come funziona?"))
    assert [c.provider for c in plan.chain] == ["ollama", ll.LOCAL_ID, EXTRACTIVE.provider]
    alone = asyncio.run(_router().plan("come funziona?"))
    assert [c.provider for c in alone.chain] == [ll.LOCAL_ID, EXTRACTIVE.provider]


class _Fake:
    def __init__(self, url: str, model: str) -> None:
        self.url, self.model = url, model

    async def stream(self, _messages: list[dict[str, str]]) -> AsyncIterator[str]:
        for piece in ("Ciao ", self.model):
            yield piece


def test_the_lazy_provider_starts_the_server_then_streams(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[int] = []

    async def ensure() -> tuple[str, str]:
        started.append(1)
        return "http://127.0.0.1:1/v1", "m"

    monkeypatch.setattr(ll.MANAGER, "ensure", ensure)
    prov = ll.LazyProvider(lambda url, model: _Fake(url, model))

    async def run() -> str:
        return "".join([p async for p in prov.stream([{"role": "user", "content": "x"}])])

    assert asyncio.run(run()) == "Ciao m" and started == [1]


def test_an_unavailable_server_raises_a_stable_code_so_the_assistant_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def ensure() -> None:
        return None

    monkeypatch.setattr(ll.MANAGER, "ensure", ensure)
    prov = ll.LazyProvider(lambda url, model: _Fake(url, model))

    async def run() -> Any:
        return [p async for p in prov.stream([])]

    with pytest.raises(ll.LocalUnavailable) as e:
        asyncio.run(run())
    assert e.value.code == "unavailable"
