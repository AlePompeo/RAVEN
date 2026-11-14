# SPDX-License-Identifier: Apache-2.0
"""Contratto HTTP dell'auto mode con endpoint finti (httpx.MockTransport): nessuna rete reale."""

import json
import logging
import os
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.api.assistant_routes import build_router
from backend.assistant.config import load_settings
from backend.assistant.service import AssistantService

from .conftest import answer_of, chat_body, parse_sse

Q = "Quali campi ha il contratto dati della telemetria, power_w e link_margin_db?"
CID = "telemetry-contract"
KEY = "sk-HOSTED-SECRET-777"
HOSTED_URL = "https://api.hosted-example.test/v1"


class Net:
    """Server finto: Ollama (tags + chat) e, opzionalmente, un endpoint ospitato."""

    def __init__(self, models: tuple[str, ...] = ("llama3.1:8b", "phi4:4b")) -> None:
        self.models = models
        self.requests: list[tuple[str, str, str | None]] = []  # metodo, host+path, modello
        self.chat_status = 200

    def __call__(self, req: httpx.Request) -> httpx.Response:
        model = json.loads(req.content)["model"] if req.content else None
        self.requests.append((req.method, req.url.host + req.url.path, model))
        if req.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": m} for m in self.models]})
        if req.url.path.endswith("/chat/completions"):
            if self.chat_status != 200:
                return httpx.Response(self.chat_status)
            deltas = [f"Risposta di {model} ", f"[{CID}] power_w."]
            body = "".join(
                f"data: {json.dumps({'choices': [{'delta': {'content': d}}]})}\n\n" for d in deltas
            )
            return httpx.Response(200, content=(body + "data: [DONE]\n\n").encode())
        return httpx.Response(404)

    def hosts(self) -> set[str]:
        return {r[1].split("/")[0] for r in self.requests}


@pytest.fixture
def auto_client(
    make_client: Callable[..., TestClient], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Callable[..., tuple[TestClient, Net]]:
    def _make(net: Net | None = None, env: dict[str, str] | None = None) -> tuple[TestClient, Net]:
        net = net or Net()
        monkeypatch.setenv("ASSISTANT_OLLAMA_URL", "http://127.0.0.1:11434")
        monkeypatch.setenv("ASSISTANT_RANKING_FILE", str(tmp_path / "rank.json"))
        for k, v in (env or {}).items():
            monkeypatch.setenv(k, v)
        client = make_client()
        old: AssistantService = client.app.state.assistant  # type: ignore[attr-defined]
        router = build_router(
            load_settings(),
            client.app.state.registry,  # type: ignore[attr-defined]
            env=os.environ,
            discovery_transport=httpx.MockTransport(net),
            llm_transport=httpx.MockTransport(net),
        )
        client.app.state.assistant = AssistantService(  # type: ignore[attr-defined]
            old.kb, router=router, llm_allowed=lambda _k: True
        )
        return client, net

    return _make


def write_ranking(tmp_path: Path, **scores: float) -> None:
    results = [
        {"provider": "ollama", "model": m.replace("_", ":"), "score": v, "meets_threshold": True}
        for m, v in scores.items()
    ]
    (tmp_path / "rank.json").write_text(json.dumps({"version": 1, "results": results}))


def test_default_is_auto_and_without_any_model_is_extractive(
    make_client: Callable[..., TestClient],
) -> None:
    c = make_client()
    st = c.get("/api/assistant/status").json()
    assert st["selection_mode"] == "auto" and st["selected"] == {
        "provider": "assistant-extractive",
        "model": None,
    }
    assert [x["provider"] for x in st["candidates"]] == ["assistant-extractive"]
    assert st["provider"] == "assistant-extractive" and st["mode"] == "extractive"
    ev = parse_sse(c.post("/api/assistant/chat", json=chat_body(Q)).text)
    assert ev[0][1]["selection"] == "auto" and ev[0][1]["model"] is None


def test_status_lists_candidates_with_rank_score_health(auto_client, tmp_path: Path) -> None:
    write_ranking(tmp_path, **{"phi4_4b": 0.91, "llama3.1_8b": 0.75})
    c, _ = auto_client()
    st = c.get("/api/assistant/status").json()
    assert st["selected"] == {"provider": "ollama", "model": "phi4:4b"}
    by = {(x["provider"], x["model"]): x for x in st["candidates"]}
    assert set(next(iter(by.values()))) == {
        "provider",
        "model",
        "local",
        "healthy",
        "rank",
        "score",
        "last_error_code",
    }
    q, ll = by[("ollama", "phi4:4b")], by[("ollama", "llama3.1:8b")]
    assert (q["rank"], q["score"], q["local"], q["healthy"]) == (1, 0.91, True, True)
    assert (ll["rank"], ll["score"]) == (2, 0.75)
    assert by[("assistant-extractive", None)]["rank"] == 3
    assert by[("assistant-extractive", None)]["score"] is None
    assert st["external"] is False


def test_chat_auto_uses_best_model_and_override_selects_other(auto_client, tmp_path: Path) -> None:
    write_ranking(tmp_path, phi4_4b=0.91)
    c, net = auto_client()
    ev = parse_sse(c.post("/api/assistant/chat", json=chat_body(Q)).text)
    assert ev[0][1]["model"] == "phi4:4b" and ev[0][1]["reason"] == "ranking"
    assert "Risposta di phi4:4b" in answer_of(ev)
    ev = parse_sse(
        c.post(
            "/api/assistant/chat", json=chat_body(Q, provider="ollama", model="llama3.1:8b")
        ).text
    )
    assert ev[0][1]["model"] == "llama3.1:8b" and ev[0][1]["selection"] == "forced"
    ev = parse_sse(
        c.post("/api/assistant/chat", json=chat_body(Q, provider="assistant-extractive")).text
    )
    assert ev[0][1]["mode"] == "extractive" and ev[0][1]["selection"] == "forced"
    assert net.hosts() == {"127.0.0.1"}


@pytest.mark.parametrize(
    "extra",
    [
        {"provider": "ollama", "model": "ghost:1"},
        {"provider": "nope"},
        {"model": "phi4:4b"},  # modello senza provider
        {"provider": "ollama", "model": "../../etc/passwd"},
        {"provider": "OLLAMA"},
        {"provider": "assistant-extractive", "model": "phi4:4b"},
    ],
)
def test_override_must_match_a_discovered_candidate(auto_client, extra: dict[str, str]) -> None:
    c, _ = auto_client()
    assert c.post("/api/assistant/chat", json=chat_body(Q, **extra)).status_code == 422


def test_provider_only_override_picks_best_model_of_that_provider(auto_client) -> None:
    c, _ = auto_client()
    ev = parse_sse(c.post("/api/assistant/chat", json=chat_body(Q, provider="ollama")).text)
    assert ev[0][1]["model"] == "llama3.1:8b"  # primo per preferenza


def test_runtime_failure_falls_back_and_status_shows_error(auto_client) -> None:
    net = Net(("phi4:4b",))
    net.chat_status = 429
    c, _ = auto_client(net)
    ev = parse_sse(c.post("/api/assistant/chat", json=chat_body(Q)).text)
    assert ev[0][1]["provider"] == "assistant-extractive"
    assert ev[0][1]["fallback_from"] == "ollama:phi4:4b"
    assert {"provider_fallback", "all_candidates_failed"} <= set(
        next(d for e, d in ev if e == "warning")["codes"]
    )
    st = c.get("/api/assistant/status").json()
    cand = next(x for x in st["candidates"] if x["model"] == "phi4:4b")
    assert cand["healthy"] is False and cand["last_error_code"] == "http_429"
    assert st["selected"]["provider"] == "assistant-extractive"


def test_forced_extractive_never_touches_the_network(auto_client) -> None:
    c, net = auto_client(env={"ASSISTANT_PROVIDER": "assistant-extractive"})
    st = c.get("/api/assistant/status").json()
    assert st["selection_mode"] == "forced" and len(st["candidates"]) == 1
    c.post("/api/assistant/chat", json=chat_body(Q))
    assert net.requests == []
    assert c.post("/api/assistant/chat", json=chat_body(Q, provider="ollama")).status_code == 422


def test_forced_ollama_provider(auto_client) -> None:
    c, _ = auto_client(env={"ASSISTANT_PROVIDER": "ollama"})
    ev = parse_sse(c.post("/api/assistant/chat", json=chat_body(Q)).text)
    assert ev[0][1]["provider"] == "ollama" and ev[0][1]["selection"] == "forced"
    assert c.get("/api/assistant/status").json()["selection_mode"] == "forced"


def test_hosted_needs_key_and_is_flagged_external_without_leaking(
    auto_client, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    # senza chiave: mai contattato
    c, net = auto_client(
        Net(()),
        {"ASSISTANT_LLM_BASE_URL": HOSTED_URL, "ASSISTANT_LLM_MODEL": "big-1"},
    )
    st = c.get("/api/assistant/status").json()
    assert [x["provider"] for x in st["candidates"]] == ["assistant-extractive"]
    assert st["discovery_errors"]["assistant-openai-compat"] == "hosted_needs_key_and_model"
    c.post("/api/assistant/chat", json=chat_body(Q))
    assert "api.hosted-example.test" not in net.hosts()


def test_hosted_with_key_external_flag_and_no_secrets_anywhere(
    auto_client, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    net = Net(())
    c, _ = auto_client(
        net,
        {
            "ASSISTANT_LLM_BASE_URL": HOSTED_URL,
            "ASSISTANT_LLM_MODEL": "big-1",
            "ASSISTANT_LLM_API_KEY": KEY,
        },
    )
    st = c.get("/api/assistant/status").json()
    assert st["selected"]["provider"] == "assistant-openai-compat" and st["external"] is True
    r = c.post("/api/assistant/chat", json=chat_body(Q, allow_external=True))
    ev = parse_sse(r.text)
    assert ev[0][1]["external"] is True and ev[0][1]["model"] == "big-1"
    everything = r.text + json.dumps(st) + caplog.text + str(dict(r.headers))
    everything += c.get("/api/plugins").text
    assert KEY not in everything  # (il logger di httpx scrive host e percorso, mai credenziali)
    for public in (r.text, json.dumps(st), c.get("/api/plugins").text):
        assert "hosted-example" not in public and "/v1" not in public
    assert "api.hosted-example.test" in net.hosts()  # contattato davvero, solo perche' configurato
    assert "127.0.0.1" in net.hosts()  # la sonda locale su Ollama predefinito


@pytest.mark.parametrize(
    "enabled,key,model",
    [("0", KEY, "openai/gpt-oss-20b"), ("1", "", "openai/gpt-oss-20b"), ("1", KEY, "bad model")],
)
def test_groq_unavailable_configuration_never_contacts_cloud(
    auto_client, enabled: str, key: str, model: str
) -> None:
    net = Net(())
    c, _ = auto_client(
        net,
        {
            "RAVEN_SI_CLOUD_ENABLED": enabled,
            "GROQ_API_KEY": key,
            "GROQ_MODEL": model,
        },
    )
    assert c.get("/api/assistant/status").json()["cloud_available"] is False
    c.post("/api/assistant/chat", json=chat_body("Explain the Mission Planner"))
    assert "api.groq.com" not in net.hosts()


def test_groq_requires_consent_and_receives_public_guide_not_private_knowledge(auto_client) -> None:
    class CloudNet(Net):
        body: dict | None = None
        authorization: str | None = None

        def __call__(self, req: httpx.Request) -> httpx.Response:
            if req.url.host == "api.groq.com":
                self.body = json.loads(req.content)
                self.authorization = req.headers.get("authorization")
            return super().__call__(req)

    net = CloudNet(())
    c, _ = auto_client(
        net,
        {
            "RAVEN_SI_CLOUD_ENABLED": "1",
            "GROQ_API_KEY": KEY,
            "GROQ_MODEL": "openai/gpt-oss-20b",
        },
    )
    assert c.get("/api/assistant/status").json()["cloud_available"] is True
    body = chat_body(
        "Explain the Mission Planner",
        provider="groq",
        page_context={
            "page_id": "planner",
            "params": {"private_note": "DO_NOT_SEND", "power_w": 12},
        },
    )
    assert c.post("/api/assistant/chat", json=body).status_code == 403
    assert net.body is None
    response = c.post("/api/assistant/chat", json={**body, "allow_external": True})
    assert response.status_code == 200
    assert parse_sse(response.text)[0][1]["external"] is True
    assert net.body is not None
    prompt = json.dumps(net.body["messages"])
    assert "raven-si-guide" in prompt
    assert "DO_NOT_SEND" not in prompt and "telemetry-contract" not in prompt
    assert net.authorization == f"Bearer {KEY}"
    assert net.body["reasoning_effort"] == "low"
    assert KEY not in response.text
