# SPDX-License-Identifier: Apache-2.0
"""Instradamento dei modelli: scoperta + classifica + salute -> piano di tentativi per richiesta.

Modalita' (ASSISTANT_PROVIDER): `auto` (default) sceglie tra i candidati scoperti; un id forza
quel provider (`assistant-extractive`: nessuna rete; `ollama`: solo i modelli Ollama; un provider
registrato come plugin, es. `assistant-openai-compat`: configurazione solo da ambiente, come prima).
"""

from collections.abc import Callable
from typing import Any

from backend.assistant import local_llm
from backend.assistant.breaker import CircuitBreakers
from backend.assistant.config import EXTRACTIVE_ID
from backend.assistant.discovery import EXTRACTIVE, Candidate, Discovery
from backend.assistant.selection import (
    Plan,
    Ranking,
    RankingFile,
    ideal_order,
    plan_auto,
    plan_forced,
)

AUTO = "auto"


class ModelRouter:
    def __init__(
        self,
        *,
        mode: str,
        discovery: Discovery | None,
        make_provider: Callable[[Candidate], Any],
        timeout_for: Callable[[Candidate], float],
        breakers: CircuitBreakers,
        ranking: RankingFile | None = None,
        prefs: tuple[str, ...] = (EXTRACTIVE_ID,),
        min_score: float = 0.6,
        route_simple: bool = False,
        fixed: Candidate | None = None,
    ) -> None:
        self.mode = mode
        self.discovery = discovery
        self.make_provider = make_provider
        self.timeout_for = timeout_for
        self.breakers = breakers
        self._ranking = ranking
        self.prefs, self.min_score, self.route_simple = prefs, min_score, route_simple
        self._fixed = fixed  # provider registrato come plugin (modalita' forzata "legacy")

    @classmethod
    def for_provider(
        cls,
        provider_id: str,
        make_provider: Callable[[str], Any],
        timeout_for: Callable[[str], float],
        *,
        local: bool = True,
        model: str | None = None,
    ) -> "ModelRouter":
        """Router forzato su un provider noto per id (nessuna scoperta)."""
        fixed = None if provider_id == EXTRACTIVE_ID else Candidate(provider_id, model, local)
        return cls(
            mode=provider_id,
            discovery=None,
            make_provider=lambda c: make_provider(c.provider),
            timeout_for=lambda c: timeout_for(c.provider),
            breakers=CircuitBreakers(),
            fixed=fixed,
        )

    # ------------------------------------------------------------------ stato
    @property
    def selection_mode(self) -> str:
        return AUTO if self.mode == AUTO else "forced"

    def ranking(self) -> Ranking:
        return self._ranking.get() if self._ranking else Ranking()

    async def discovered(self) -> list[Candidate]:
        if self._fixed is not None:
            return [self._fixed]
        if self.discovery is None:
            return []
        cands = await self.discovery.candidates()
        if self.mode != AUTO:  # forzato su un provider scoperto (es. "ollama")
            return [c for c in cands if c.provider == self.mode]
        if (
            local_llm.usable()
        ):  # il modello incluso (se installato e se la memoria basta): parte solo quando serve
            name = str(local_llm.manifest().get("name") or "local")
            cands = [*cands, Candidate(local_llm.LOCAL_ID, name, True)]
        return cands

    async def candidates(self) -> list[Candidate]:
        """Candidati scoperti + estrattivo (sempre ultimo)."""
        if self.mode == EXTRACTIVE_ID:
            return [EXTRACTIVE]
        return [*await self.discovered(), EXTRACTIVE]

    def _healthy(self, cands: list[Candidate]) -> set[tuple[str, str | None]]:
        return {c.key for c in cands if not self.breakers.is_open(c.key)}

    def _ideal(self, cands: list[Candidate]) -> list[Candidate]:
        if self._fixed is not None or self.mode != AUTO:
            return [c for c in cands if c.provider != EXTRACTIVE_ID]
        return ideal_order(cands, self.prefs, self.ranking(), self.min_score)

    # ------------------------------------------------------------------ piano
    async def plan(self, question: str = "", override: Candidate | None = None) -> Plan:
        if override is not None:
            return plan_forced(override, "user_override")
        if self.mode == EXTRACTIVE_ID:
            return Plan((EXTRACTIVE,), "forced", "forced")
        cands = await self.discovered()
        if self.mode != AUTO:  # un provider forzato: i suoi modelli in ordine, poi estrattivo
            healthy = self._healthy(cands)
            ideal = self._ideal(cands)
            ok = [c for c in ideal if c.key in healthy]
            ahead = tuple(c for c in ideal if c.key not in healthy)
            return Plan((*ok, EXTRACTIVE), "forced", "forced", ahead)
        return plan_auto(
            cands,
            self.prefs,
            self.ranking(),
            self.min_score,
            self._healthy(cands),
            question=question,
            route_simple=self.route_simple,
        )

    async def resolve_override(self, provider: str, model: str | None) -> Candidate | None:
        """Il candidato scelto dall'utente deve essere uno di quelli scoperti (altrimenti None)."""
        cands = await self.candidates()
        if model:
            return next((c for c in cands if c.provider == provider and c.model == model), None)
        same = [c for c in cands if c.provider == provider]
        if not same:
            return None
        ideal = [c for c in self._ideal(cands) if c.provider == provider]
        return (ideal or same)[0]

    # --------------------------------------------------------------- esiti
    def record_success(self, c: Candidate) -> None:
        self.breakers.success(c.key)

    def record_failure(self, c: Candidate, code: str) -> None:
        self.breakers.failure(c.key, code)
        if self.discovery is not None:
            self.discovery.mark_failed(c.provider)

    # --------------------------------------------------------------- status
    async def status(self) -> dict[str, Any]:
        cands = await self.candidates()
        ranking = self.ranking()
        ideal = [*self._ideal(cands), EXTRACTIVE]
        rank = {c.key: i + 1 for i, c in enumerate(ideal)}
        plan = await self.plan("")
        sel = plan.chain[0]
        errors = self.discovery.errors() if self.discovery else {}
        out = []
        for c in cands:
            entry = ranking.get(c)
            out.append(
                {
                    "provider": c.provider,
                    "model": c.model,
                    "local": c.local,
                    "healthy": not self.breakers.is_open(c.key),
                    "rank": rank.get(c.key),
                    "score": entry.score if entry else None,
                    "last_error_code": self.breakers.last_error(c.key),
                }
            )
        return {
            "selection_mode": self.selection_mode,
            "selected": {"provider": sel.provider, "model": sel.model},
            "external": not sel.local,
            "candidates": out,
            "discovery_errors": dict(sorted(errors.items())),
        }
