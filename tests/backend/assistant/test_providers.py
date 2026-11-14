# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path

import httpx
import pytest

from backend.assistant.extractive import compose
from backend.assistant.index import Index
from backend.assistant.loader import parse_doc
from backend.assistant.prompt import REFUSAL_EN, REFUSAL_IT, build_messages
from backend.core.errors import PluginError
from backend.core.manifest import load_manifest
from backend.plugins.assistant_extractive.plugin import ExtractiveProvider
from backend.plugins.assistant_openai.plugin import (
    MAX_TOTAL_CHARS,
    OpenAICompatProvider,
)

from .test_retrieval import FORMULA

ROOT = Path(__file__).resolve().parents[3]
SECRET = "sk-super-secret-123"


def _msgs(q: str, level: str = "intermedio", lang: str = "it"):
    idx = Index([parse_doc(FORMULA)])
    return build_messages([{"role": "user", "content": q}], idx.search(q), level=level, lang=lang)


def test_extractive_formula_answer_has_symbols_units_example_and_citation() -> None:
    out = compose(_msgs("Qual è la formula della perdita nello spazio libero?"))
    assert "[fspl-test]" in out and "92.45" in out
    assert "d = distanza [km]" in out and "f = frequenza [GHz]" in out
    assert "Ipotesi" in out and "Limiti" in out and "Esempio svolto" in out


def test_extractive_refuses_without_context_in_both_languages() -> None:
    assert compose(_msgs("capitale della Francia?")) == REFUSAL_IT
    assert compose(_msgs("capital of France?", lang="en")) == REFUSAL_EN


async def test_extractive_plugin_streams_same_text() -> None:
    m = load_manifest(ROOT / "backend/plugins/assistant_extractive/manifest.toml")
    msgs = _msgs("formula perdita spazio libero")
    got = "".join([p async for p in ExtractiveProvider(m).stream(msgs)])
    assert got == compose(msgs)


def _sse(*deltas: str, done: bool = True) -> bytes:
    lines = [f"data: {json.dumps({'choices': [{'delta': {'content': d}}]})}\n\n" for d in deltas]
    if done:
        lines.append("data: [DONE]\n\n")
    return "".join(lines).encode()


def _provider(handler) -> OpenAICompatProvider:
    m = load_manifest(ROOT / "backend/plugins/assistant_openai/manifest.toml")
    return OpenAICompatProvider(m, transport=httpx.MockTransport(handler))


async def _collect(p: OpenAICompatProvider) -> str:
    return "".join([t async for t in p.stream([{"role": "user", "content": "ciao"}])])


async def test_openai_streams_and_sends_key_only_in_header(monkeypatch) -> None:
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = str(req.url)
        seen["auth"] = req.headers.get("authorization")
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, content=_sse("Ci", "ao"))

    monkeypatch.setenv("ASSISTANT_LLM_MODEL", "m1")
    monkeypatch.setenv("ASSISTANT_LLM_API_KEY", SECRET)
    monkeypatch.setenv("ASSISTANT_LLM_BASE_URL", "http://example.invalid/v1/")
    assert await _collect(_provider(handler)) == "Ciao"
    assert seen["url"] == "http://example.invalid/v1/chat/completions"
    assert seen["auth"] == f"Bearer {SECRET}"
    assert SECRET not in json.dumps(seen["body"]) and "tools" not in seen["body"]


async def test_openai_errors_are_generic_and_do_not_leak_key(monkeypatch) -> None:
    monkeypatch.setenv("ASSISTANT_LLM_MODEL", "m1")
    monkeypatch.setenv("ASSISTANT_LLM_API_KEY", SECRET)

    def bad(req: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text=f"bad key {SECRET}")

    with pytest.raises(PluginError) as e:
        await _collect(_provider(bad))
    assert SECRET not in str(e.value)

    def boom(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"cannot connect {SECRET}")

    with pytest.raises(PluginError) as e2:
        await _collect(_provider(boom))
    assert SECRET not in str(e2.value) and "ConnectError" in str(e2.value)


async def test_openai_rejects_bad_config_and_garbage(monkeypatch) -> None:
    ok = lambda r: httpx.Response(200, content=_sse("x"))
    monkeypatch.delenv("ASSISTANT_LLM_MODEL", raising=False)
    with pytest.raises(PluginError, match="MODEL"):
        await _collect(_provider(ok))
    monkeypatch.setenv("ASSISTANT_LLM_MODEL", "m")
    for bad in ("ftp://x/v1", "http://user:pw@host/v1", "nonsense"):
        monkeypatch.setenv("ASSISTANT_LLM_BASE_URL", bad)
        with pytest.raises(PluginError, match="BASE_URL"):
            await _collect(_provider(ok))
    monkeypatch.setenv("ASSISTANT_LLM_BASE_URL", "http://h/v1")
    garbage = lambda r: httpx.Response(200, content=b"data: {not json}\n\n")
    with pytest.raises(PluginError):
        await _collect(_provider(garbage))


async def test_openai_caps_total_size(monkeypatch) -> None:
    monkeypatch.setenv("ASSISTANT_LLM_MODEL", "m")
    big = _sse("x" * 5000, "x" * 5000, "x" * 5000, "x" * 5000, "x" * 5000, done=False)
    assert 5000 * 5 > MAX_TOTAL_CHARS
    with pytest.raises(PluginError, match="troppo lunga"):
        await _collect(_provider(lambda r: httpx.Response(200, content=big)))
