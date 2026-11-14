# SPDX-License-Identifier: Apache-2.0
"""Rotte del Learning Assistant (contratto in docs/assistant.md).

POST /api/assistant/chat (SSE: meta, token, citations, warning, done | error),
GET /api/assistant/knowledge, /knowledge/{id}, /suggestions, /status. Errori generici verso il client.
"""

import logging
import os
import re
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from backend.api.routes import _CappedStreamingResponse
from backend.api.security import RateLimitMiddleware
from backend.assistant import local_llm
from backend.assistant.breaker import CircuitBreakers
from backend.assistant.cloud import GROQ_ID, MODEL_RE, groq_config
from backend.assistant.config import EXTRACTIVE_ID, Settings, load_settings
from backend.assistant.discovery import (
    OLLAMA_ID,
    OPENAI_ID,
    Candidate,
    Discovery,
    build_endpoints,
    is_local_host,
)
from backend.assistant.kb import KnowledgeBase
from backend.assistant.model import KnowledgeDoc
from backend.assistant.router import AUTO, ModelRouter
from backend.assistant.selection import RankingFile
from backend.assistant.service import AssistantService, ChatInput
from backend.core.errors import PluginError
from backend.core.registry import Registry
from backend.plugins.assistant_openai.plugin import DEFAULT_BASE_URL, OpenAICompatProvider

log = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parents[2]
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
PAGE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,63}$"
PageId = Annotated[str, StringConstraints(pattern=PAGE_PATTERN)]
Scalar = str | int | float


def _make_models(s: Settings) -> tuple[type[BaseModel], ...]:
    class Msg(BaseModel):
        model_config = ConfigDict(extra="forbid")
        role: Literal["user", "assistant"]  # "system" mai accettato dal client
        content: str = Field(min_length=1, max_length=s.max_message_chars)

    class PageContext(BaseModel):
        model_config = ConfigDict(extra="forbid")
        page_id: PageId
        simulation_id: PageId | None = None
        params: dict[Annotated[str, StringConstraints(max_length=40)], Scalar] | None = Field(
            default=None, max_length=16
        )

    class ChatBody(BaseModel):
        model_config = ConfigDict(extra="forbid")
        messages: list[Msg] = Field(min_length=1, max_length=s.max_messages)
        page_context: PageContext | None = None
        level: Literal["principiante", "intermedio", "tecnico"] | None = None
        lang: Literal["it", "en"] | None = None
        allow_external: bool = Field(default=False, strict=True)
        # Scelta manuale: DEVE coincidere con un candidato scoperto (altrimenti 422).
        provider: (
            Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9._-]{0,63}$")] | None
        ) = None
        model: Annotated[str, StringConstraints(pattern=MODEL_RE.pattern)] | None = None

    return Msg, PageContext, ChatBody


def _summary(d: KnowledgeDoc) -> dict[str, Any]:
    return {
        "id": d.id,
        "title": d.title,
        "kind": d.kind,
        "summary": d.summary,
        "applies_to": list(d.applies_to),
        "tags": list(d.tags),
    }


def build_assistant_router(s: Settings) -> APIRouter:
    _, _, ChatBody = _make_models(s)
    router = APIRouter()

    def svc(request: Request) -> AssistantService:
        service: AssistantService = request.app.state.assistant
        return service

    @router.post("/api/assistant/chat")
    async def chat(body: ChatBody, request: Request) -> StreamingResponse:  # type: ignore[valid-type]
        service = svc(request)
        limiter: RateLimitMiddleware = request.app.state.assistant_limiter
        pc = body.page_context  # type: ignore[attr-defined]
        override: Candidate | None = None
        req_provider, req_model = body.provider, body.model  # type: ignore[attr-defined]
        if req_model and not MODEL_RE.fullmatch(
            req_model
        ):  # policy: no model of a Chinese or Russian organisation, whatever the host
            raise HTTPException(422, "modello non disponibile")
        if req_provider or req_model:
            if req_provider:
                override = await service.router.resolve_override(req_provider, req_model)
            if override is None:
                raise HTTPException(422, "modello non disponibile")
            if not override.local and not body.allow_external:  # type: ignore[attr-defined]
                raise HTTPException(403, "external_consent_required")
        inp = ChatInput(
            messages=[m.model_dump() for m in body.messages],  # type: ignore[attr-defined]
            page_id=pc.page_id if pc else "",
            simulation_id=(pc.simulation_id or "") if pc else "",
            params=dict(pc.params or {}) if pc else {},
            level=body.level,  # type: ignore[attr-defined]
            lang=body.lang,  # type: ignore[attr-defined]
            client_key=limiter._key(request.scope),
            override=override,
            allow_external=body.allow_external,  # type: ignore[attr-defined]
        )
        max_s: float = request.app.state.chat_max_stream_s
        return _CappedStreamingResponse(
            service.chat_events(inp),
            max_s + 1.0,
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.get("/api/assistant/knowledge")
    async def knowledge(request: Request, kind: str = "", applies_to: str = "") -> dict[str, Any]:
        service = svc(request)
        service.kb.refresh_if_changed()
        docs = [
            d
            for d in service.kb.docs
            if (not kind or d.kind == kind) and (not applies_to or applies_to in d.applies_to)
        ]
        return {"count": len(docs), "docs": [_summary(d) for d in docs]}

    @router.get("/api/assistant/knowledge/{doc_id}")
    async def knowledge_doc(doc_id: str, request: Request) -> dict[str, Any]:
        service = svc(request)
        doc = service.kb.get(doc_id) if ID_RE.match(doc_id) else None
        if doc is None:
            raise HTTPException(404, "documento non trovato")
        out = doc.to_json()
        out["anchors"] = [
            {"anchor": c.anchor, "heading": c.heading}
            for c in service.kb.index.chunks
            if c.doc_id == doc_id and c.anchor
        ]
        return out

    @router.get("/api/assistant/suggestions")
    async def suggestions(request: Request, page: str = "", lang: str = "it") -> dict[str, Any]:
        if page and not re.match(PAGE_PATTERN, page):
            raise HTTPException(422, "page non valido")
        return {"page": page, "suggestions": svc(request).suggestions(page, lang)}

    @router.get("/api/assistant/status")
    async def status(request: Request) -> dict[str, Any]:
        service = svc(request)
        kb = service.kb
        routing = await service.router.status()
        selected = routing["selected"]
        return {
            "provider": selected["provider"],
            "mode": "extractive" if selected["provider"] == EXTRACTIVE_ID else "llm",
            **routing,
            "index": {"docs": len(kb.docs), "chunks": len(kb.index)},
            "last_build": kb.last_build,
            "knowledge_errors": len(kb.errors),
            "dev_reload": kb.reload,
            "cloud_available": groq_config(os.environ) is not None,
        }

    return router


def build_router(
    s: Settings,
    registry: Registry,
    env: Mapping[str, str] | None = None,
    *,
    discovery_transport: httpx.AsyncBaseTransport | None = None,
    llm_transport: httpx.AsyncBaseTransport | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> ModelRouter:
    env = os.environ if env is None else env
    manifests = {m.id: m for m in registry.manifests() if m.kind == "llm"}
    mode = s.provider

    def timeout_for(c: Candidate) -> float:
        if c.provider == local_llm.LOCAL_ID:
            return local_llm.LOCAL_TIMEOUT_S
        m = manifests.get(c.provider)
        return m.timeout_s if m else 30.0

    def make_provider(c: Candidate) -> Any:
        if c.provider == local_llm.LOCAL_ID:  # bundled model: started on first use, loopback only
            m_local = manifests.get(OPENAI_ID)
            if m_local is None:
                raise PluginError("provider OpenAI-compatibile non disponibile")
            return local_llm.LazyProvider(
                lambda url, model: OpenAICompatProvider(
                    m_local, endpoint=(url, model, ""), trust_env=False
                )
            )
        if c.base_url and c.model:  # candidato scoperto: endpoint esplicito, chiave solo in header
            m = manifests.get(OPENAI_ID)
            if m is None:
                raise PluginError("provider OpenAI-compatibile non disponibile")
            return OpenAICompatProvider(
                m,
                transport=llm_transport,
                endpoint=(c.base_url, c.model, c.api_key),
                trust_env=False,
                reasoning_effort="low"
                if c.provider == GROQ_ID and c.model.startswith("openai/gpt-oss")
                else None,
            )
        return registry.create("llm", c.provider)

    breakers = CircuitBreakers(s.breaker_failures, s.breaker_cooldown_s, clock)
    common: dict[str, Any] = {
        "make_provider": make_provider,
        "timeout_for": timeout_for,
        "breakers": breakers,
        "ranking": RankingFile(s.ranking_file),
        "prefs": s.preference,
        "min_score": s.min_score,
        "route_simple": s.route_simple,
    }
    if mode == EXTRACTIVE_ID:
        return ModelRouter(mode=mode, discovery=None, **common)
    if mode in (AUTO, OLLAMA_ID, GROQ_ID):
        endpoints, skipped = build_endpoints(s, env)
        if mode != AUTO:
            endpoints = [e for e in endpoints if e.provider == mode]
        discovery = Discovery(
            endpoints,
            ttl_s=s.discovery_ttl_s,
            timeout_s=s.discovery_timeout_s,
            clock=clock,
            transport=discovery_transport,
            skipped=skipped,
        )
        return ModelRouter(mode=mode, discovery=discovery, **common)
    if mode in manifests:  # provider registrato: configurazione solo da ambiente, come prima
        local, model = True, None
        if mode == OPENAI_ID:
            host = urlsplit(env.get("ASSISTANT_LLM_BASE_URL") or DEFAULT_BASE_URL).hostname or ""
            local = is_local_host(host, s.local_hosts)
            model = env.get("ASSISTANT_LLM_MODEL") or None
        fixed = Candidate(mode, model, local)
        return ModelRouter(mode=mode, discovery=None, fixed=fixed, **common)
    log.error("ASSISTANT_PROVIDER %r non disponibile: uso %s", mode, EXTRACTIVE_ID)
    return ModelRouter(mode=EXTRACTIVE_ID, discovery=None, **common)


def include_assistant_routes(app: FastAPI) -> None:
    s = load_settings()
    registry: Registry = app.state.registry
    kb = KnowledgeBase(REPO_ROOT, s.knowledge_dirs, reload=s.dev_reload)
    for err in kb.errors:
        log.warning("conoscenza: %s", err)
    limiter = RateLimitMiddleware(
        app,
        limit=s.llm_per_min_per_ip,
        window_s=60.0,
        trusted_proxy=os.environ.get("TRUSTED_PROXY") == "1",
    )
    app.state.assistant_limiter = limiter
    app.state.assistant = AssistantService(
        kb,
        router=build_router(s, registry),
        llm_allowed=lambda key: limiter._allow(key)[0],
        top_k=s.top_k,
        max_context_tokens=s.max_context_tokens,
        max_stream_s=float(getattr(app.state, "chat_max_stream_s", 120.0)),
        failover_budget_s=s.failover_budget_s,
    )
    app.include_router(build_assistant_router(s))
