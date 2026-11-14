# SPDX-License-Identifier: Apache-2.0
"""Regola di selezione del modello (funzioni pure, testabili senza rete).

1. Si considerano solo i candidati che corrispondono a una voce di ASSISTANT_PREFERENCE.
2. Tra i SANI: prima quelli con punteggio MISURATO (file di classifica) >= soglia, dal punteggio
   piu' alto (a parita': ordine di preferenza, poi id); poi quelli senza misura, in ordine di
   preferenza. I candidati misurati SOTTO soglia sono esclusi (meglio l'estrattivo).
3. Ultimo anello sempre l'estrattivo (sempre disponibile).
"""

import fnmatch
import json
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path

from backend.assistant.discovery import EXTRACTIVE, Candidate

log = logging.getLogger(__name__)
RANKING_VERSION = 1
_DEFINITIONAL = (
    "che cos'e",
    "cos'e",
    "cosa e ",
    "cosa significa",
    "che cosa e",
    "what is",
    "what does",
    "define ",
    "definisci",
)


@dataclass(frozen=True)
class RankEntry:
    score: float
    meets_threshold: bool = False
    p50_s: float | None = None
    baseline: bool = False


@dataclass(frozen=True)
class Ranking:
    entries: dict[tuple[str, str | None], RankEntry] = field(default_factory=dict)

    def get(self, c: Candidate) -> RankEntry | None:
        e = self.entries.get(c.key)
        return None if e is None or e.baseline else e


@dataclass(frozen=True)
class Plan:
    chain: tuple[Candidate, ...]  # ordine di tentativo; l'ultimo e' sempre l'estrattivo
    reason: str  # ranking | preference | routed_simple | no_llm_available | forced | user_override
    selection: str = "auto"  # auto | forced
    unhealthy_ahead: tuple[Candidate, ...] = ()  # candidati migliori scartati perche' non sani


def _num(v: object) -> float | None:
    if isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v):
        return None
    return float(v)


def parse_ranking(data: object) -> Ranking:
    if not isinstance(data, dict) or data.get("version") != RANKING_VERSION:
        raise ValueError("versione della classifica non supportata")
    entries: dict[tuple[str, str | None], RankEntry] = {}
    for r in data.get("results") or []:
        if not isinstance(r, dict) or not isinstance(r.get("provider"), str):
            continue
        score = _num(r.get("score"))
        model = r.get("model")
        if score is None or not 0 <= score <= 1 or not (model is None or isinstance(model, str)):
            continue
        entries[(r["provider"], model)] = RankEntry(
            score=score,
            meets_threshold=r.get("meets_threshold") is True,
            p50_s=_num(r.get("latency_p50_s")),
            baseline=r.get("baseline") is True,
        )
    return Ranking(entries)


class RankingFile:
    """Legge il file di classifica ricaricandolo se cambia (mtime); file assente/rotto = nessuna misura."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._sig: tuple[int, int] | None = None
        self._ranking = Ranking()

    def get(self) -> Ranking:
        try:
            st = self.path.stat()
        except OSError:
            self._sig, self._ranking = None, Ranking()
            return self._ranking
        sig = (st.st_mtime_ns, st.st_size)
        if sig != self._sig:
            self._sig = sig
            try:
                if st.st_size > 1_000_000:
                    raise ValueError("file troppo grande")
                self._ranking = parse_ranking(json.loads(self.path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                log.warning("classifica dell'assistente ignorata (file non valido)")
                self._ranking = Ranking()
        return self._ranking


def pref_index(c: Candidate, prefs: tuple[str, ...]) -> int | None:
    for i, entry in enumerate(prefs):
        prov, _, glob = entry.partition(":")
        if prov != c.provider:
            continue
        if not glob or (c.model is not None and fnmatch.fnmatchcase(c.model, glob)):
            return i
    return None


def is_definitional(question: str) -> bool:
    q = question.lower().replace("è", "e").replace("’", "'").strip()
    return len(q) <= 120 and any(q.startswith(p) for p in _DEFINITIONAL)


def _ordered(
    cands: list[Candidate], prefs: tuple[str, ...], ranking: Ranking, min_score: float
) -> tuple[list[Candidate], list[Candidate]]:
    """(misurati sopra soglia ordinati per punteggio, non misurati in ordine di preferenza)."""
    scored: list[tuple[float, int, str, Candidate]] = []
    unscored: list[tuple[int, str, Candidate]] = []
    for c in cands:
        if c.provider == EXTRACTIVE.provider:
            continue
        idx = pref_index(c, prefs)
        if idx is None:
            continue
        entry = ranking.get(c)
        if entry is None:
            unscored.append((idx, c.id, c))
        elif entry.score >= min_score:
            scored.append((-entry.score, idx, c.id, c))
    return [t[3] for t in sorted(scored, key=lambda t: t[:3])], [
        t[2] for t in sorted(unscored, key=lambda t: t[:2])
    ]


def ideal_order(
    cands: list[Candidate], prefs: tuple[str, ...], ranking: Ranking, min_score: float
) -> list[Candidate]:
    a, b = _ordered(cands, prefs, ranking, min_score)
    return [*a, *b]


def plan_auto(
    cands: list[Candidate],
    prefs: tuple[str, ...],
    ranking: Ranking,
    min_score: float,
    healthy: set[tuple[str, str | None]],
    *,
    question: str = "",
    route_simple: bool = False,
) -> Plan:
    ideal = ideal_order(cands, prefs, ranking, min_score)
    ok = [c for c in ideal if c.key in healthy]
    scored, _ = _ordered([c for c in cands if c.key in healthy], prefs, ranking, min_score)
    reason = "ranking" if scored else ("preference" if ok else "no_llm_available")
    if route_simple and is_definitional(question):
        fast = [
            c for c in scored if (e := ranking.get(c)) and e.meets_threshold and e.p50_s is not None
        ]
        if fast:
            best = min(fast, key=lambda c: (ranking.entries[c.key].p50_s or 0.0, c.id))
            if best != ok[0]:
                ok = [best, *[c for c in ok if c != best]]
                reason = "routed_simple"
    ahead: list[Candidate] = []
    for c in ideal:
        if ok and c == ok[0]:
            break
        if c.key not in healthy:
            ahead.append(c)
    return Plan((*ok, EXTRACTIVE), reason, "auto", tuple(ahead))


def plan_forced(chosen: Candidate, reason: str = "forced") -> Plan:
    """Un solo candidato richiesto (id configurato o scelta dell'utente), poi l'estrattivo."""
    if chosen.provider == EXTRACTIVE.provider:
        return Plan((EXTRACTIVE,), reason, "forced")
    return Plan((chosen, EXTRACTIVE), reason, "forced")
