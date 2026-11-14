# SPDX-License-Identifier: Apache-2.0
"""Orchestrazione: recupero -> prompt -> provider (con fallback estrattivo) -> validazione -> SSE."""

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from backend.assistant.cloud import PUBLIC_KNOWLEDGE_ID
from backend.assistant.config import EXTRACTIVE_ID
from backend.assistant.discovery import EXTRACTIVE, Candidate
from backend.assistant.extractive import compose, stream_text
from backend.assistant.guard import CitationFilter, check_answer
from backend.assistant.index import Index, Retrieval
from backend.assistant.kb import KnowledgeBase
from backend.assistant.prompt import (
    build_messages,
    is_refusal,
    normalize_level,
    query_text,
)
from backend.assistant.router import ModelRouter
from backend.assistant.text import detect_lang

log = logging.getLogger(__name__)
MAX_ANSWER_CHARS = 8000
WARNING_TEXT = {
    "no_citation": "La risposta non cita il materiale del sito: verificare prima di fidarsi.",
    "invalid_citation_dropped": "Alcune citazioni non corrispondevano al materiale recuperato e sono state rimosse.",
    "numbers_not_in_context": "La risposta contiene numeri non presenti nel materiale recuperato.",
    "no_context_unlabelled": "Nessun materiale pertinente: la risposta non e' ancorata al sito.",
    "provider_fallback": "Il modello scelto non ha risposto: usato un'alternativa (vedi meta.fallback_from).",
    "provider_unhealthy": "Un modello preferito e' temporaneamente sospeso dopo errori ripetuti: usato un altro.",
    "all_candidates_failed": "Nessun modello LLM ha risposto: risposta estrattiva dal materiale del sito.",
    "llm_rate_limited": "Limite di chiamate LLM raggiunto: risposta estrattiva dal materiale del sito.",
    "possible_prompt_leak": "La risposta sembra riprodurre le istruzioni interne: ignorarla.",
    "llm_interrupted": "Il modello si e' interrotto a meta': la risposta puo' essere incompleta (non e' stato cambiato modello a meta' risposta).",
}
_QUESTIONS = {
    "it": {
        "formula": "Qual è la formula di «{t}» e come si usa, con unità e limiti?",
        "simulation": "Cosa fa «{t}» e quali parametri accetta?",
        "method": "Come funziona «{t}»?",
        "page": "Cosa posso fare nella sezione «{t}»?",
        "problem": "Qual è il problema da risolvere: {t}?",
        "decision": "Perché è stata scelta questa soluzione: {t}?",
        "concept": "Che cos'è «{t}»?",
        "glossary": "Che cos'è «{t}»?",
    },
    "en": {
        "formula": "What is the formula for «{t}», with units and limits?",
        "simulation": "What does «{t}» do and which parameters does it take?",
        "method": "How does «{t}» work?",
        "page": "What can I do in «{t}»?",
        "problem": "What problem is being solved: {t}?",
        "decision": "Why was this solution chosen: {t}?",
        "concept": "What is «{t}»?",
        "glossary": "What is «{t}»?",
    },
}
_KIND_RANK = {"problem": 0, "simulation": 1, "page": 2, "decision": 3, "formula": 4, "method": 5}


def sse(event: str, data: Mapping[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, allow_nan=False)}\n\n"


@dataclass
class ChatInput:
    messages: list[dict[str, str]]
    page_id: str = ""
    simulation_id: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    level: str | None = None
    lang: str | None = None
    client_key: str = "unknown"
    override: Candidate | None = None  # scelta manuale dell'utente (gia' validata)
    allow_external: bool = False


def classify_error(exc: BaseException) -> str:
    """Codice stabile e privo di dettagli per un errore del provider."""
    if isinstance(exc, TimeoutError):
        return "timeout"
    code = getattr(exc, "code", None)
    return code if isinstance(code, str) and code else "error"


class AssistantService:
    def __init__(
        self,
        kb: KnowledgeBase,
        make_provider: Callable[[str], Any] | None = None,
        *,
        provider_id: str = "auto",
        timeout_for: Callable[[str], float] | None = None,
        llm_allowed: Callable[[str], bool],
        top_k: int = 5,
        max_context_tokens: int = 1800,
        max_stream_s: float = 120.0,
        router: ModelRouter | None = None,
        failover_budget_s: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.kb = kb
        if router is None:
            assert make_provider is not None and timeout_for is not None
            router = ModelRouter.for_provider(provider_id, make_provider, timeout_for)
        self.router = router
        self._llm_allowed = llm_allowed
        self.top_k = top_k
        self.max_context_tokens = max_context_tokens
        self.max_stream_s = max_stream_s
        self.failover_budget_s = failover_budget_s
        self._clock = clock

    # ---------------------------------------------------------------- conoscenza
    def suggestions(self, page: str, lang: str = "it", limit: int = 6) -> list[dict[str, str]]:
        self.kb.refresh_if_changed()
        tpl = _QUESTIONS["en" if lang == "en" else "it"]
        docs = [
            d
            for d in self.kb.docs
            if d.origin != "contract" and (not page or page == d.id or page in d.applies_to)
        ]
        docs.sort(key=lambda d: (_KIND_RANK.get(d.kind, 9), d.origin != "manual", d.id))
        return [
            {"question": tpl.get(d.kind, tpl["concept"]).format(t=d.title), "doc_id": d.id}
            for d in docs[:limit]
        ]

    def retrieve(self, inp: ChatInput, *, public_only: bool = False) -> Retrieval:
        self.kb.refresh_if_changed()
        level = normalize_level(inp.level)
        index = (
            Index(
                [
                    d
                    for d in self.kb.docs
                    if d.id == PUBLIC_KNOWLEDGE_ID and d.path == "docs/knowledge/raven-si-guide.md"
                ]
            )
            if public_only
            else self.kb.index
        )
        return index.search(
            query_text(inp.messages),
            page_ids=[inp.page_id, inp.simulation_id],
            top_k=self.top_k,
            budget_tokens=self.max_context_tokens,
            level=level,
        )

    def _citation(self, doc_id: str, retrieval: Retrieval) -> dict[str, str]:
        doc = self.kb.get(doc_id)
        hit = next((h for h in retrieval.hits if h.chunk.doc_id == doc_id), None)
        anchor = next(
            (h.chunk.anchor for h in retrieval.hits if h.chunk.doc_id == doc_id and h.chunk.anchor),
            "",
        )
        base = f"/api/assistant/knowledge/{doc_id}"
        return {
            "id": doc_id,
            "title": doc.title if doc else doc_id,
            "kind": doc.kind if doc else "",
            "anchor": anchor if hit else "",
            "url_path": base + (f"#{anchor}" if anchor else ""),
        }

    def _followups(self, retrieval: Retrieval, lang: str) -> list[str]:
        tpl = _QUESTIONS["en" if lang == "en" else "it"]
        out: list[str] = []
        for did in retrieval.doc_ids:
            doc = self.kb.get(did)
            for rid in doc.related if doc else ():
                r = self.kb.get(rid)
                if r and rid not in retrieval.doc_ids:
                    q = tpl.get(r.kind, tpl["concept"]).format(t=r.title)
                    if q not in out:
                        out.append(q)
        return out[:3]

    # ---------------------------------------------------------------------- chat
    async def _llm_stream(
        self, provider: Any, messages: list[dict[str, str]], timeout_s: float
    ) -> AsyncIterator[str]:
        """Budget sul tempo di attesa del provider e tetto assoluto di durata (come /api/chat)."""
        it = provider.stream(messages).__aiter__()
        loop = asyncio.get_running_loop()
        begun = loop.time()
        remaining = timeout_s
        try:
            while True:
                if loop.time() - begun > self.max_stream_s:
                    raise TimeoutError("tetto di durata")
                started = loop.time()
                try:
                    tok = await asyncio.wait_for(
                        it.__anext__(), timeout=min(timeout_s, max(remaining, 0.0))
                    )
                except StopAsyncIteration:
                    return
                remaining -= loop.time() - started
                yield tok
        finally:
            aclose = getattr(it, "aclose", None)
            if aclose is not None:
                await aclose()

    async def chat_events(self, inp: ChatInput) -> AsyncIterator[str]:
        try:
            async for ev in self._chat(inp):
                yield ev
        except Exception:
            log.exception("assistente: errore interno")
            yield sse("error", {"detail": "assistente non disponibile"})

    async def _chat(self, inp: ChatInput) -> AsyncIterator[str]:
        last_user = next((m["content"] for m in reversed(inp.messages) if m["role"] == "user"), "")
        lang = inp.lang or detect_lang(last_user)
        level = normalize_level(inp.level)
        plan = await self.router.plan(last_user, inp.override)
        cloud_request = inp.allow_external and any(not c.local for c in plan.chain)
        retrieval = self.retrieve(inp, public_only=cloud_request)
        params = (
            {k: v for k, v in inp.params.items() if isinstance(v, (int, float))}
            if cloud_request
            else inp.params
        )
        page = {"page_id": inp.page_id, "simulation_id": inp.simulation_id, "params": params}
        messages = build_messages(inp.messages, retrieval, level=level, lang=lang, page=page)
        allowed_ids = set(retrieval.doc_ids)
        flt = CitationFilter(allowed_ids, self.kb.index.docs)
        pre_warnings: list[str] = []
        answer_parts: list[str] = []
        emitted = 0
        attempts = [
            c for c in plan.chain if c.provider != EXTRACTIVE_ID and (c.local or inp.allow_external)
        ]
        chosen: Candidate | None = None
        failed: list[Candidate] = []
        skipped: list[Candidate] = [
            c for c in plan.unhealthy_ahead if c.local or inp.allow_external
        ]
        stream: AsyncIterator[str] | None = None
        first: str | None = None
        rate_limited = False

        if attempts and not self._llm_allowed(inp.client_key):
            rate_limited = True
            pre_warnings.append("llm_rate_limited")
        elif attempts:
            deadline = self._clock() + self.failover_budget_s
            for cand in attempts:
                remaining = deadline - self._clock()
                if remaining <= 0:
                    break  # budget di tempo della richiesta esaurito: niente altri tentativi
                if not self.router.breakers.allow(cand.key):
                    skipped.append(cand)
                    continue
                try:
                    st = self._llm_stream(
                        self.router.make_provider(cand),
                        messages,
                        min(self.router.timeout_for(cand), remaining),
                    )
                    try:
                        first = await st.__anext__()
                    except StopAsyncIteration:
                        first = ""
                    stream, chosen = st, cand
                    break
                except Exception as e:  # noqa: BLE001 - qualunque guasto del provider -> failover
                    code = classify_error(e)
                    log.warning("modello %s fallito (%s)", cand.id, code)
                    self.router.record_failure(cand, code)
                    failed.append(cand)
        if chosen is None:
            stream = stream_text(compose(messages))
            first = None

        intended = (skipped + attempts)[:1]
        fallback_from = intended[0] if intended and chosen != intended[0] else None
        if rate_limited:
            fallback_from = None
        if fallback_from is not None:
            pre_warnings.append("provider_fallback")
        if skipped:
            pre_warnings.append("provider_unhealthy")
        if (attempts or skipped) and chosen is None and not rate_limited:
            pre_warnings.append("all_candidates_failed")
        if rate_limited:
            reason = "rate_limited"
        elif fallback_from is None:
            reason = plan.reason
        elif chosen is None:
            reason = "all_candidates_failed"
        else:
            reason = "provider_error" if failed else "provider_unhealthy"
        shown = chosen or EXTRACTIVE
        mode = "llm" if chosen else "extractive"

        yield sse(
            "meta",
            {
                "provider": shown.provider,
                "model": shown.model,
                "mode": mode,
                "selection": plan.selection,
                "fallback_from": fallback_from.id if fallback_from else None,
                "reason": reason,
                "external": not shown.local,
                "retrieved": retrieval.doc_ids,
                "level": level,
                "lang": lang,
            },
        )

        async def tokens_iter() -> AsyncIterator[str]:
            if first:
                yield first
            assert stream is not None
            async for t in stream:
                yield t

        interrupted = False
        try:
            async for tok in tokens_iter():
                emitted += len(tok)
                if emitted > MAX_ANSWER_CHARS:
                    interrupted = True
                    break
                answer_parts.append(tok)
                safe = flt.feed(tok)
                if safe:
                    yield sse("token", {"token": safe})
        except Exception as e:  # noqa: BLE001 - stream interrotto: nessun cambio di modello
            log.warning("stream del modello interrotto (%s)", classify_error(e))
            interrupted = True
            if chosen is not None:
                self.router.record_failure(chosen, classify_error(e))
        tail = flt.flush()
        if tail:
            yield sse("token", {"token": tail})
        aclose = getattr(stream, "aclose", None)
        if aclose is not None:
            await aclose()

        if chosen is not None and not interrupted:
            self.router.record_success(chosen)
        answer = "".join(answer_parts)
        refused = is_refusal(answer)
        warnings = list(pre_warnings)
        if interrupted:
            warnings.append("llm_interrupted")
        warnings += check_answer(
            answer,
            cited=flt.cited,
            dropped=flt.dropped,
            context_text="\n".join(h.chunk.text for h in retrieval.hits),
            question_text="\n".join(m["content"] for m in inp.messages)
            + "\n".join(str(v) for v in inp.params.values()),
            has_context=bool(retrieval.hits),
        )
        cites = [] if refused else [self._citation(i, retrieval) for i in flt.cited]
        yield sse("citations", {"citations": cites})
        if warnings:
            yield sse(
                "warning",
                {"codes": warnings, "messages": [WARNING_TEXT.get(w, w) for w in warnings]},
            )
        yield sse(
            "done",
            {
                "refused": refused,
                "followups": self._followups(retrieval, lang),
                "chars": len(answer),
            },
        )
