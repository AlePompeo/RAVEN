# SPDX-License-Identifier: Apache-2.0
import logging

import pytest

from .conftest import ScriptedLLM, answer_of, chat_body, parse_sse

Q = "Quali campi ha il contratto dati della telemetria, power_w e link_margin_db?"
CID = "telemetry-contract"


def test_extractive_sse_sequence_and_citations(make_client) -> None:
    r = make_client().post("/api/assistant/chat", json=chat_body(Q))
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    ev = parse_sse(r.text)
    names = [e for e, _ in ev]
    assert names[0] == "meta" and names[-1] == "done"
    assert "token" in names and names.index("citations") > max(
        i for i, n in enumerate(names) if n == "token"
    )
    meta = ev[0][1]
    assert meta["provider"] == "assistant-extractive" and meta["mode"] == "extractive"
    assert CID in meta["retrieved"]
    cites = next(d for e, d in ev if e == "citations")["citations"]
    assert cites and cites[0]["id"] == CID
    assert set(cites[0]) == {"id", "title", "kind", "anchor", "url_path"}
    assert "power_w" in answer_of(ev) and f"[{CID}]" in answer_of(ev)
    assert "warning" not in names and ev[-1][1]["refused"] is False


def test_out_of_kb_is_refused_with_empty_citations(make_client) -> None:
    ev = parse_sse(
        make_client()
        .post("/api/assistant/chat", json=chat_body("Chi ha vinto i mondiali 1982?"))
        .text
    )
    assert "non è presente nel materiale del sito" in answer_of(ev)
    assert next(d for e, d in ev if e == "citations")["citations"] == []
    assert ev[-1][1]["refused"] is True


@pytest.mark.parametrize(
    "body",
    [
        {"messages": []},
        {"messages": [{"role": "user", "content": "x"}] * 21},
        {"messages": [{"role": "user", "content": "x" * 2001}]},
        {"messages": [{"role": "system", "content": "x"}]},
        {"messages": [{"role": "user", "content": "x"}], "level": "dio"},
        {"messages": [{"role": "user", "content": "x"}], "extra": 1},
        {"messages": [{"role": "user", "content": "x"}], "page_context": {"page_id": "a b<"}},
        {
            "messages": [{"role": "user", "content": "x"}],
            "page_context": {"page_id": "ok", "params": {"a": {"b": 1}}},
        },
    ],
)
def test_bad_input_rejected(make_client, body) -> None:
    assert make_client().post("/api/assistant/chat", json=body).status_code == 422


def test_body_cap_and_global_rate_limit(make_client, monkeypatch) -> None:
    monkeypatch.setenv("MAX_BODY_BYTES", "2000")
    c = make_client()
    assert c.post("/api/assistant/chat", content=b"x" * 5000).status_code == 413
    monkeypatch.setenv("MAX_BODY_BYTES", "65536")
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "3")
    c = make_client()
    codes = [c.get("/api/assistant/status").status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]


def test_page_context_fallback_answers_this_page(make_client) -> None:
    body = chat_body("Cosa fa questa simulazione?", page_context={"page_id": "fspl-c"})
    ev = parse_sse(make_client().post("/api/assistant/chat", json=body).text)
    assert "plugin-fspl-c" in ev[0][1]["retrieved"]


def test_llm_ok_invalid_citation_dropped_and_warned(make_client) -> None:
    llm = ScriptedLLM(["Il contratto ha power_w ", f"[{CID}] e ", "[invented-doc] fine."])
    c = make_client(llm, "fake-llm")
    ev = parse_sse(c.post("/api/assistant/chat", json=chat_body(Q)).text)
    assert ev[0][1]["mode"] == "llm" and ev[0][1]["provider"] == "fake-llm"
    text = answer_of(ev)
    assert "invented-doc" not in text and "[fonte non valida]" in text
    warn = next(d for e, d in ev if e == "warning")
    assert "invalid_citation_dropped" in warn["codes"]
    assert [x["id"] for x in next(d for e, d in ev if e == "citations")["citations"]] == [CID]
    system = llm.calls[0][0]["content"]
    assert system.startswith("Sei il") and Q not in system
    assert [m["role"] for m in llm.calls[0]] == ["system", "user"]


def test_llm_uncited_answer_gets_warning(make_client) -> None:
    ev = parse_sse(
        make_client(ScriptedLLM(["Il campo è power_w."]), "fake-llm")
        .post("/api/assistant/chat", json=chat_body(Q))
        .text
    )
    assert "no_citation" in next(d for e, d in ev if e == "warning")["codes"]


def test_provider_failure_falls_back_to_extractive(make_client, caplog) -> None:
    caplog.set_level(logging.ERROR)
    c = make_client(ScriptedLLM([], fail_first=True), "fake-llm")
    ev = parse_sse(c.post("/api/assistant/chat", json=chat_body(Q)).text)
    assert ev[0][1]["mode"] == "extractive" and ev[0][1]["provider"] == "assistant-extractive"
    assert "provider_fallback" in next(d for e, d in ev if e == "warning")["codes"]
    assert "power_w" in answer_of(ev)
    assert "segreto-interno" not in "".join(str(x) for x in ev)


def test_provider_failure_mid_stream_flags_interruption(make_client) -> None:
    c = make_client(ScriptedLLM([f"Parziale [{CID}] "], fail_after=True), "fake-llm")
    ev = parse_sse(c.post("/api/assistant/chat", json=chat_body(Q)).text)
    assert "llm_interrupted" in next(d for e, d in ev if e == "warning")["codes"]
    assert ev[-1][0] == "done"


def test_per_ip_llm_cap_degrades_to_extractive(make_client, monkeypatch) -> None:
    monkeypatch.setenv("ASSISTANT_LLM_PER_MIN_PER_IP", "1")
    c = make_client(ScriptedLLM([f"ok [{CID}]"]), "fake-llm")
    first = parse_sse(c.post("/api/assistant/chat", json=chat_body(Q)).text)
    second = parse_sse(c.post("/api/assistant/chat", json=chat_body(Q)).text)
    assert first[0][1]["mode"] == "llm" and second[0][1]["mode"] == "extractive"
    assert "llm_rate_limited" in next(d for e, d in second if e == "warning")["codes"]


def test_unconfigured_openai_provider_falls_back_and_never_leaks_key(
    make_client, monkeypatch, caplog
) -> None:
    secret = "sk-TOPSECRET-999"
    monkeypatch.setenv("ASSISTANT_LLM_API_KEY", secret)
    monkeypatch.setenv("ASSISTANT_LLM_BASE_URL", "http://127.0.0.1:9/v1")  # porta chiusa
    monkeypatch.setenv("ASSISTANT_LLM_MODEL", "m")
    caplog.set_level(logging.DEBUG)
    c = make_client(provider="assistant-openai-compat")
    r = c.post("/api/assistant/chat", json=chat_body(Q))
    assert "provider_fallback" in r.text
    everything = r.text + str(dict(r.headers)) + caplog.text
    everything += c.get("/api/assistant/status").text + c.get("/api/plugins").text
    assert secret not in everything


def test_unknown_provider_uses_extractive(make_client) -> None:
    st = make_client(provider="does-not-exist").get("/api/assistant/status").json()
    assert st["provider"] == "assistant-extractive" and st["mode"] == "extractive"


def test_knowledge_endpoints(make_client) -> None:
    c = make_client()
    idx = c.get("/api/assistant/knowledge").json()
    assert idx["count"] == len(idx["docs"]) > 0
    assert set(idx["docs"][0]) == {"id", "title", "kind", "summary", "applies_to", "tags"}
    only = c.get("/api/assistant/knowledge", params={"kind": "simulation"}).json()["docs"]
    assert only and all(d["kind"] == "simulation" for d in only)
    doc = c.get(f"/api/assistant/knowledge/{CID}").json()
    assert doc["id"] == CID and "power_w" in doc["body"] and "anchors" in doc
    for bad in ("nope", "..%2f..%2fetc", "A" * 100, "x y"):
        assert c.get(f"/api/assistant/knowledge/{bad}").status_code == 404


def test_suggestions_and_status(make_client) -> None:
    c = make_client()
    s = c.get("/api/assistant/suggestions", params={"page": "fspl-c"}).json()
    assert s["suggestions"] and all({"question", "doc_id"} <= set(x) for x in s["suggestions"])
    assert c.get("/api/assistant/suggestions", params={"page": "<x>"}).status_code == 422
    st = c.get("/api/assistant/status").json()
    assert st["index"]["docs"] > 0 and st["index"]["chunks"] >= st["index"]["docs"]
    assert st["last_build"].endswith("Z")
    assert "key" not in str(st).lower()
