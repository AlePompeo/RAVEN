# SPDX-License-Identifier: Apache-2.0
import json
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.adapters.cache_memory import MemoryCache
from backend.api.app import create_app
from backend.bootstrap import PLUGINS_DIR, make_loader
from backend.core.manifest import Manifest
from backend.core.registry import Registry

ROOT = Path(__file__).resolve().parents[3]


class ScriptedLLM:
    """LLM finto: emette i pezzi dati, poi eventualmente solleva (nessuna rete)."""

    def __init__(self, pieces: list[str], fail_after: bool = False, fail_first: bool = False):
        self.pieces, self.fail_after, self.fail_first = pieces, fail_after, fail_first
        self.calls: list[list[dict[str, str]]] = []

    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        self.calls.append(messages)
        if self.fail_first:
            raise RuntimeError("boom segreto-interno")
        for p in self.pieces:
            yield p
        if self.fail_after:
            raise RuntimeError("boom")


def parse_sse(text: str) -> list[tuple[str, dict[str, Any]]]:
    out = []
    for block in text.strip().split("\n\n"):
        lines = block.splitlines()
        ev = next(line[7:] for line in lines if line.startswith("event: "))
        data = next(line[6:] for line in lines if line.startswith("data: "))
        out.append((ev, json.loads(data)))
    return out


def answer_of(events: list[tuple[str, dict[str, Any]]]) -> str:
    return "".join(d["token"] for e, d in events if e == "token")


@pytest.fixture(autouse=True)
def _no_real_discovery(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nessuna sonda reale (nemmeno su 127.0.0.1:11434) nei test: la scoperta si prova con trasporti finti."""
    monkeypatch.setenv("ASSISTANT_OLLAMA_URL", "off")
    monkeypatch.delenv("ASSISTANT_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("ASSISTANT_PROVIDER", raising=False)


@pytest.fixture
def make_client(monkeypatch: pytest.MonkeyPatch) -> Callable[..., TestClient]:
    def _make(llm: ScriptedLLM | None = None, provider: str = "") -> TestClient:
        registry = Registry()
        errors = registry.discover(PLUGINS_DIR, make_loader())
        if llm is not None:
            m = Manifest("fake-llm", "llm", "0", "x", "Apache-2.0", "t", 5.0, PLUGINS_DIR)
            registry.register(m, lambda _m: llm)
        if provider:
            monkeypatch.setenv("ASSISTANT_PROVIDER", provider)
        return TestClient(create_app(registry, MemoryCache(), errors))

    return _make


def chat_body(q: str, **extra: Any) -> dict[str, Any]:
    return {"messages": [{"role": "user", "content": q}], **extra}
