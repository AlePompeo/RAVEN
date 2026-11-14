# SPDX-License-Identifier: Apache-2.0
"""Scoperta dei candidati: solo trasporto simulato (nessuna rete, nessun Ollama reale)."""

import json

import httpx
import pytest

from backend.assistant.config import Settings, load_settings
from backend.assistant.discovery import (
    MAX_MODELS,
    MAX_RESPONSE_BYTES,
    Discovery,
    build_endpoints,
    is_local_host,
)


class Clock:
    def __init__(self) -> None:
        self.t = 100.0

    def __call__(self) -> float:
        return self.t


def settings(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    monkeypatch.setenv("ASSISTANT_OLLAMA_URL", "http://127.0.0.1:11434")  # il default reale
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return load_settings()


def tags(*names: str) -> bytes:
    return json.dumps({"models": [{"name": n} for n in names]}).encode()


def models(*ids: str) -> bytes:
    return json.dumps({"object": "list", "data": [{"id": i} for i in ids]}).encode()


def make(
    s: Settings, handler, env: dict[str, str] | None = None, clock: Clock | None = None, **kw
) -> tuple[Discovery, list[str]]:
    seen: list[str] = []

    def wrapped(req: httpx.Request) -> httpx.Response:
        seen.append(str(req.url))
        return handler(req)

    eps, skipped = build_endpoints(s, env or {})
    d = Discovery(
        eps,
        ttl_s=s.discovery_ttl_s,
        clock=clock or Clock(),
        transport=httpx.MockTransport(wrapped),
        skipped=skipped,
        **kw,
    )
    return d, seen


async def test_ollama_tags(monkeypatch: pytest.MonkeyPatch) -> None:
    s = settings(monkeypatch)
    d, seen = make(
        s, lambda r: httpx.Response(200, content=tags("phi4:4b", "nomic-embed-text:latest", "a:1"))
    )
    cands = await d.candidates()
    assert [c.id for c in cands] == ["ollama:a:1", "ollama:phi4:4b"]  # embedding escluso, ordinati
    assert all(c.local and c.base_url == "http://127.0.0.1:11434/v1" for c in cands)
    assert seen == ["http://127.0.0.1:11434/api/tags"]


async def test_openai_models_local_probed(monkeypatch: pytest.MonkeyPatch) -> None:
    s = settings(monkeypatch, ASSISTANT_OLLAMA_URL="off")
    env = {"ASSISTANT_LLM_BASE_URL": "http://192.168.1.5:8080/v1/"}
    d, seen = make(s, lambda r: httpx.Response(200, content=models("m-b", "m-a")), env)
    assert [c.id for c in await d.candidates()] == [
        "assistant-openai-compat:m-a",
        "assistant-openai-compat:m-b",
    ]
    assert seen == ["http://192.168.1.5:8080/v1/models"]


async def test_hosted_needs_key_and_model_and_is_never_contacted_otherwise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    s = settings(monkeypatch, ASSISTANT_OLLAMA_URL="off")
    for env in (
        {"ASSISTANT_LLM_BASE_URL": "https://api.example.com/v1", "ASSISTANT_LLM_MODEL": "m"},
        {"ASSISTANT_LLM_BASE_URL": "https://api.example.com/v1", "ASSISTANT_LLM_API_KEY": "k"},
    ):
        d, seen = make(s, lambda r: httpx.Response(200, content=models("x")), env)
        assert await d.candidates() == [] and seen == []
        assert d.errors() == {"assistant-openai-compat": "hosted_needs_key_and_model"}


async def test_hosted_with_key_and_model_is_candidate_without_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    s = settings(monkeypatch, ASSISTANT_OLLAMA_URL="off")
    env = {
        "ASSISTANT_LLM_BASE_URL": "https://api.example.com/v1",
        "ASSISTANT_LLM_MODEL": "big-1",
        "ASSISTANT_LLM_API_KEY": "sk-secret-1",
    }
    d, seen = make(s, lambda r: httpx.Response(500), env)
    (c,) = await d.candidates()
    assert seen == [] and c.id == "assistant-openai-compat:big-1" and not c.local
    assert "sk-secret-1" not in repr(c) and "api.example.com" not in repr(c)


async def test_ollama_disabled_and_openai_same_origin_deduplicated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    s = settings(monkeypatch, ASSISTANT_OLLAMA_URL="off")
    assert build_endpoints(s, {})[0] == []
    s = settings(monkeypatch, ASSISTANT_OLLAMA_URL="http://localhost:11434")
    eps, _ = build_endpoints(s, {"ASSISTANT_LLM_BASE_URL": "http://localhost:11434/v1"})
    assert [e.provider for e in eps] == ["ollama"]


@pytest.mark.parametrize(
    "url",
    ["ftp://x", "http://user:pw@127.0.0.1:11434", "http://", "http://h:99999", "http://h/?q=1"],
)
def test_invalid_urls_rejected(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    s = settings(monkeypatch, ASSISTANT_OLLAMA_URL=url)
    eps, skipped = build_endpoints(s, {})
    assert eps == [] and skipped == {"ollama": "invalid_url"}


@pytest.mark.parametrize(
    "handler,code",
    [
        (lambda r: httpx.Response(200, content=b"{not json"), "bad_json"),
        (lambda r: httpx.Response(200, content=b'{"models": 3}'), "bad_shape"),
        (lambda r: httpx.Response(200, content=b"[]"), "bad_shape"),
        (lambda r: httpx.Response(404), "http_404"),
        (lambda r: httpx.Response(500), "http_500"),
        (
            lambda r: httpx.Response(302, headers={"location": "http://evil.example/steal"}),
            "redirect_refused",
        ),
        (lambda r: httpx.Response(200, content=b" " * (MAX_RESPONSE_BYTES + 1)), "too_large"),
    ],
)
async def test_bad_endpoint_yields_no_candidates_and_a_code(
    monkeypatch: pytest.MonkeyPatch, handler, code: str
) -> None:
    d, seen = make(settings(monkeypatch), handler)
    assert await d.candidates() == []
    assert d.errors() == {"ollama": code}
    assert seen == ["http://127.0.0.1:11434/api/tags"]  # il redirect NON e' stato seguito


async def test_unreachable_and_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("secret-detail")

    d, _ = make(settings(monkeypatch), refuse)
    assert await d.candidates() == [] and d.errors() == {"ollama": "unreachable"}

    def slow(req: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("t")

    d, _ = make(settings(monkeypatch), slow)
    assert await d.candidates() == [] and d.errors() == {"ollama": "timeout"}


async def test_hostile_names_and_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    names = [f"m{i:03d}" for i in range(100)] + ["bad name", "x;rm -rf", "../etc", 7]
    body = json.dumps({"models": [{"name": n} for n in names] + ["junk", None]}).encode()
    d, _ = make(settings(monkeypatch), lambda r: httpx.Response(200, content=body))
    got = await d.candidates()
    assert len(got) == MAX_MODELS and got[0].model == "m000"


async def test_ttl_cache_and_reprobe_after_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    s = settings(monkeypatch, ASSISTANT_DISCOVERY_TTL_S="60")
    clock = Clock()
    state = {"ok": False}

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=tags("a")) if state["ok"] else httpx.Response(503)

    d, seen = make(s, handler, clock=clock)
    assert await d.candidates() == [] and len(seen) == 1
    clock.t += 5  # entro il TTL breve dei guasti (10 s): nessuna nuova sonda
    await d.candidates()
    assert len(seen) == 1
    state["ok"] = True
    clock.t += 6  # TTL dei guasti scaduto: ri-sonda e ora trova il modello
    assert [c.id for c in await d.candidates()] == ["ollama:a"] and len(seen) == 2
    clock.t += 59
    await d.candidates()
    assert len(seen) == 2  # ancora in cache (TTL 60 s)
    clock.t += 2
    await d.candidates()
    assert len(seen) == 3


async def test_mark_failed_forces_reprobe_but_not_a_storm(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = Clock()
    d, seen = make(
        settings(monkeypatch), lambda r: httpx.Response(200, content=tags("a")), clock=clock
    )
    await d.candidates()
    d.mark_failed("ollama")  # troppo presto: ignorato
    await d.candidates()
    assert len(seen) == 1
    clock.t += 6
    d.mark_failed("ollama")
    await d.candidates()
    assert len(seen) == 2


@pytest.mark.parametrize(
    "host,expected",
    [
        ("127.0.0.1", True),
        ("localhost", True),
        ("::1", True),
        ("10.1.2.3", True),
        ("192.168.0.9", True),
        ("169.254.1.1", True),
        ("8.8.8.8", False),
        ("api.openai.com", False),
        ("ollama", False),
    ],
)
def test_is_local_host(host: str, expected: bool) -> None:
    assert is_local_host(host) is expected


def test_local_hosts_env_extends_locality() -> None:
    assert is_local_host("ollama", ("ollama",))
