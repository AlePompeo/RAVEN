# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.raven_report import build_report_router
from backend.assistant.discovery import Candidate, Discovery
from backend.core.manifest import Manifest
from backend.domain.raven.report_budget import COST_ITEMS
from backend.domain.raven.report_carbon import PHASES
from backend.plugins.assistant_openai.plugin import OpenAICompatProvider


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("ASSISTANT_OLLAMA_URL", "http://127.0.0.1:11434")
    monkeypatch.delenv("ASSISTANT_LLM_BASE_URL", raising=False)
    app = FastAPI()
    app.include_router(build_report_router())
    manifest = Manifest("assistant-openai-compat", "llm", "1", "", "", "", 10, Path("."))
    app.state.registry = SimpleNamespace(manifests=lambda: [manifest])
    app.state.assistant_limiter = SimpleNamespace(
        _key=lambda scope: "test", _allow=lambda k: (True, 0)
    )
    return TestClient(app)


def test_complete_partial_zero_and_funding_budget(client: TestClient) -> None:
    body = {
        "costs": dict.fromkeys(COST_ITEMS, 100),
        "contingency_percent": 20,
        "funding": 1000,
        "currency": "EUR",
        "price_base_year": 2026,
        "basis": "User preliminary estimate; taxes included; no inflation.",
    }
    response = client.post("/api/raven/report/budget", json=body)
    assert response.status_code == 200
    data = response.json()
    assert data["known_subtotal"] == 900
    assert data["total_lifecycle_cost"] == 1080
    assert data["funding_gap"] == 80
    assert data["within_declared_funding"] is False
    assert data["economic_feasibility"] is None
    body["costs"]["disposal"] = None
    data = client.post("/api/raven/report/budget", json=body).json()
    assert data["known_subtotal"] == 800
    assert data["total_lifecycle_cost"] is None
    assert data["missing_cost_items"] == ["disposal"]
    body["costs"] = dict.fromkeys(COST_ITEMS, 0)
    body["contingency_percent"] = 0
    data = client.post("/api/raven/report/budget", json=body).json()
    assert data["total_lifecycle_cost"] == 0
    assert data["within_declared_funding"] is True
    assert (
        client.post("/api/raven/report/budget", json={"costs": {}}).json()["known_subtotal"] is None
    )


@pytest.mark.parametrize(
    "patch",
    [
        {"costs": {"unknown": 10}},
        {"costs": {"disposal": -1}},
        {"costs": {"disposal": True}},
        {"costs": {"disposal": "100"}},
        {"contingency_percent": 101},
        {"currency": "EUR", "costs": {"disposal": 10}},
        {"currency": "XXX"},
    ],
)
def test_invalid_or_unattributed_estimates_rejected(client: TestClient, patch: dict) -> None:
    assert client.post("/api/raven/report/budget", json={"costs": {}, **patch}).status_code == 422


@pytest.mark.parametrize("cloud_status", [200, 429])
def test_cloud_narrative_requires_consent_and_excludes_nontechnical_data(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, cloud_status: int
) -> None:
    monkeypatch.setenv("RAVEN_SI_CLOUD_ENABLED", "1")
    monkeypatch.setenv("GROQ_API_KEY", "test-only-key")
    monkeypatch.setenv("GROQ_MODEL", "openai/gpt-oss-20b")
    requests: list[dict] = []

    def serve(req: httpx.Request) -> httpx.Response:
        assert str(req.url) == "https://api.groq.com/openai/v1/chat/completions"
        assert req.headers["authorization"] == "Bearer test-only-key"
        body = json.loads(req.content)
        requests.append(body)
        assert body["response_format"] == {"type": "json_object"}
        assert body["reasoning_effort"] == "low" and body["max_tokens"] == 3072
        data = json.loads(json.loads(body["messages"][1]["content"])["data"])
        assert data["scenarios"] == [
            {
                "metrics": {"useful_hours": 0, "min_soc": None},
                "parameters_used": {"energy": {"battery_capacity_wh": 120}},
            }
        ]
        assert "PRIVATE" not in json.dumps(body)
        if cloud_status == 429:
            return httpx.Response(429)
        sections = json.dumps(
            dict.fromkeys(
                ("0", "A", "B", "C", "D", "E", "F"), "Proposed work; inputs require review."
            )
        )
        event = json.dumps({"choices": [{"delta": {"content": sections}}]})
        return httpx.Response(200, text=f"data: {event}\n\ndata: [DONE]\n\n")

    original_init = OpenAICompatProvider.__init__

    def mocked_init(self, *args, **kwargs):
        original_init(self, *args, transport=httpx.MockTransport(serve), **kwargs)

    async def no_local(self):
        return []

    monkeypatch.setattr(OpenAICompatProvider, "__init__", mocked_init)
    monkeypatch.setattr(Discovery, "candidates", no_local)
    context = json.dumps(
        {
            "planning": {"owner": "PRIVATE", "costs": {"launch": 500}, "legal": "PRIVATE"},
            "scenarios": [
                {
                    "name": "PRIVATE",
                    "metrics": {"useful_hours": 0, "min_soc": None, "PRIVATE": 8},
                    "parameters_used": {"energy": {"battery_capacity_wh": 120, "PRIVATE": 40}},
                    "notes": "PRIVATE",
                }
            ],
        }
    )
    body = {"lang": "en", "context": context}
    assert client.post("/api/raven/report/narrative", json=body).status_code == 503
    assert not requests
    response = client.post("/api/raven/report/narrative", json={**body, "allow_external": True})
    assert response.status_code == cloud_status
    if cloud_status == 200:
        assert response.json()["local"] is False
        assert response.json()["provider"] == "groq"
        assert response.json()["data_scope"] == "anonymous_technical_profile"
    assert len(requests) == 1


def test_carbon_phase_coverage_and_paper_production_estimate(client: TestClient) -> None:
    body = {
        "phases": dict.fromkeys(PHASES, 10.1),
        "basis": "Declared phase LCA estimates, each counted once.",
        "boundary": "Whole mission, manufacturing through disposal.",
        "compact_pages": 10,
        "reference_pages": 30,
    }
    response = client.post("/api/raven/report/carbon", json=body)
    assert response.status_code == 200
    data = response.json()
    assert data["mission"]["total_kg_co2e"] == 70.7
    assert data["mission"]["independently_verified"] is False
    paper = data["document"]
    assert paper["paper_factor_id"] == "19_506_5164_15_1"
    assert paper["sheet_mass_kg"] == pytest.approx(0.0049896)
    assert paper["paper_production_kg_co2e_per_sheet"] == pytest.approx(0.00671140068984)
    assert paper["compaction_avoided_kg_co2e"] == pytest.approx(0.1342280137968)
    assert paper["not_printing_avoided_kg_co2e"] == pytest.approx(0.0671140068984)
    body["phases"]["F"] = None
    mission = client.post("/api/raven/report/carbon", json=body).json()["mission"]
    assert mission["known_subtotal_kg_co2e"] == 60.6
    assert mission["total_kg_co2e"] is None
    assert mission["missing_phases"] == ["F"]
    body["phases"] = dict.fromkeys(PHASES, 0)
    assert (
        client.post("/api/raven/report/carbon", json=body).json()["mission"]["total_kg_co2e"] == 0
    )
    empty = client.post("/api/raven/report/carbon", json={"phases": {}}).json()
    assert empty["mission"]["known_subtotal_kg_co2e"] is None
    assert empty["mission"]["total_kg_co2e"] is None
    assert empty["document"]["not_printing_avoided_kg_co2e"] is None
    body["reference_pages"] = 1
    assert (
        client.post("/api/raven/report/carbon", json=body).json()["document"][
            "compaction_avoided_kg_co2e"
        ]
        < 0
    )


@pytest.mark.parametrize(
    "patch",
    [
        {"phases": {"G": 1}},
        {"phases": {"E": -1}},
        {"phases": {"E": True}},
        {"phases": {"E": "10"}},
        {"phases": {"E": 10}},
        {"compact_pages": 0},
        {"compact_pages": 1.5},
        {"reference_pages": True},
    ],
)
def test_invalid_or_unattributed_carbon_inputs_rejected(client: TestClient, patch: dict) -> None:
    assert client.post("/api/raven/report/carbon", json={"phases": {}, **patch}).status_code == 422


def test_si_only_discovers_loopback_and_never_uses_remote_service(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ASSISTANT_OLLAMA_URL", "http://10.0.0.2:11434")
    monkeypatch.setenv("ASSISTANT_LLM_BASE_URL", "https://remote.example/v1")
    monkeypatch.setenv("ASSISTANT_LLM_MODEL", "remote-model")
    monkeypatch.setenv("ASSISTANT_LLM_API_KEY", "not-a-real-key")

    async def no_candidates(self: Discovery) -> list[Candidate]:
        assert self.endpoints == []
        return []

    monkeypatch.setattr(Discovery, "candidates", no_candidates)
    response = client.post("/api/raven/report/narrative", json={"lang": "en", "context": "{}"})
    assert response.status_code == 503
    assert response.json()["detail"] == "si_unavailable"


def test_local_si_proposals_are_bounded_and_attributed(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = Candidate("ollama", "local-model", True, "http://127.0.0.1:11434/v1")

    async def candidates(self: Discovery) -> list[Candidate]:
        return [candidate]

    async def stream(self: OpenAICompatProvider, messages: list[dict[str, str]]):
        assert "Do not invent prices" in messages[0]["content"]
        yield json.dumps(dict.fromkeys(("0", "A", "B", "C", "D", "E", "F"), "Proposed work."))

    monkeypatch.setattr(Discovery, "candidates", candidates)
    monkeypatch.setattr(OpenAICompatProvider, "stream", stream)
    response = client.post("/api/raven/report/narrative", json={"lang": "en", "context": "{}"})
    assert response.status_code == 200
    data = response.json()
    assert data["model"] == "local-model"
    assert data["local"] is True
    assert data["status"] == "unreviewed_si_proposal"
    assert len(data["context_sha256"]) == 64

    async def bad_stream(self: OpenAICompatProvider, messages: list[dict[str, str]]):
        yield "A hallucinated approval, not valid structured JSON."

    monkeypatch.setattr(OpenAICompatProvider, "stream", bad_stream)
    assert (
        client.post("/api/raven/report/narrative", json={"lang": "it", "context": "{}"}).status_code
        == 502
    )
