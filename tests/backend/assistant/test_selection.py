# SPDX-License-Identifier: Apache-2.0
"""Regola di selezione, classifica e circuit breaker (orologio finto: nessuno sleep)."""

import json
from pathlib import Path

import pytest

from backend.assistant.breaker import CircuitBreakers
from backend.assistant.config import DEFAULT_PREFERENCE, parse_preference
from backend.assistant.discovery import EXTRACTIVE, Candidate
from backend.assistant.selection import (
    RankEntry,
    Ranking,
    RankingFile,
    is_definitional,
    parse_ranking,
    plan_auto,
    plan_forced,
    pref_index,
)

PREFS = parse_preference(DEFAULT_PREFERENCE)


def c(model: str, provider: str = "ollama", local: bool = True) -> Candidate:
    return Candidate(provider, model, local)


LLAMA, QWEN, GEMMA, ODD = c("llama3.1:8b"), c("phi4:4b"), c("gemma3:4b"), c("zzz:1")
ALL = [QWEN, LLAMA, GEMMA, ODD]
HEALTHY = {x.key for x in ALL}


def ids(plan) -> list[str]:
    return [x.id for x in plan.chain]


def rank(**scores: float) -> Ranking:
    return Ranking({("ollama", k.replace("_", ":")): RankEntry(v) for k, v in scores.items()})


def test_preference_order_without_ranking() -> None:
    p = plan_auto(ALL, PREFS, Ranking(), 0.6, HEALTHY)
    assert ids(p) == [
        "ollama:llama3.1:8b",
        "ollama:phi4:4b",
        "ollama:gemma3:4b",
        "ollama:zzz:1",
        "assistant-extractive",
    ]
    assert p.reason == "preference" and p.selection == "auto"


def test_measured_ranking_beats_preference() -> None:
    r = Ranking(
        {
            ("ollama", "phi4:4b"): RankEntry(0.9),
            ("ollama", "llama3.1:8b"): RankEntry(0.7),
        }
    )
    p = plan_auto(ALL, PREFS, r, 0.6, HEALTHY)
    # misurati per punteggio, poi i non misurati in ordine di preferenza
    assert ids(p)[:4] == [
        "ollama:phi4:4b",
        "ollama:llama3.1:8b",
        "ollama:gemma3:4b",
        "ollama:zzz:1",
    ]
    assert p.reason == "ranking"


def test_tie_broken_by_preference_then_id() -> None:
    r = Ranking({("ollama", "phi4:4b"): RankEntry(0.8), ("ollama", "llama3.1:8b"): RankEntry(0.8)})
    assert ids(plan_auto(ALL, PREFS, r, 0.6, HEALTHY))[0] == "ollama:llama3.1:8b"


def test_unhealthy_skipped_and_reported() -> None:
    r = Ranking({("ollama", "phi4:4b"): RankEntry(0.9), ("ollama", "llama3.1:8b"): RankEntry(0.7)})
    p = plan_auto(ALL, PREFS, r, 0.6, HEALTHY - {QWEN.key})
    assert ids(p)[0] == "ollama:llama3.1:8b" and "ollama:phi4:4b" not in ids(p)
    assert [x.id for x in p.unhealthy_ahead] == ["ollama:phi4:4b"]


def test_below_threshold_excluded_and_nothing_available_is_extractive() -> None:
    r = Ranking({(x.provider, x.model): RankEntry(0.2) for x in ALL})
    p = plan_auto(ALL, PREFS, r, 0.6, HEALTHY)
    assert ids(p) == ["assistant-extractive"] and p.reason == "no_llm_available"
    assert ids(plan_auto([], PREFS, Ranking(), 0.6, set())) == ["assistant-extractive"]
    assert ids(plan_auto(ALL, PREFS, Ranking(), 0.6, set())) == ["assistant-extractive"]


def test_baseline_entry_is_ignored() -> None:
    r = Ranking({("ollama", "phi4:4b"): RankEntry(1.0, baseline=True)})
    assert r.get(QWEN) is None


def test_preference_acts_as_allowlist() -> None:
    prefs = parse_preference("ollama:phi4*")
    assert ids(plan_auto(ALL, prefs, Ranking(), 0.6, HEALTHY)) == [
        "ollama:phi4:4b",
        "assistant-extractive",
    ]


def test_pref_index_glob_and_provider_only() -> None:
    prefs = ("ollama:phi4*", "assistant-openai-compat", "assistant-extractive")
    assert pref_index(QWEN, prefs) == 0 and pref_index(LLAMA, prefs) is None
    assert pref_index(c("gpt-x", "assistant-openai-compat", False), prefs) == 1


def test_forced_plan() -> None:
    p = plan_forced(QWEN, "user_override")
    assert ids(p) == ["ollama:phi4:4b", "assistant-extractive"] and p.selection == "forced"
    assert ids(plan_forced(EXTRACTIVE, "configured")) == ["assistant-extractive"]


def test_simple_routing_needs_flag_threshold_and_definitional_question() -> None:
    fast = c("tiny:1b")
    r = Ranking(
        {
            ("ollama", "phi4:4b"): RankEntry(0.9, True, 4.0),
            ("ollama", "tiny:1b"): RankEntry(0.7, True, 0.5),
            ("ollama", "slow:70b"): RankEntry(0.65, False, 0.1),  # sotto soglia del bench
        }
    )
    cands = [QWEN, fast, c("slow:70b")]
    healthy = {x.key for x in cands}
    base = plan_auto(cands, PREFS, r, 0.6, healthy, question="Che cos'è l'EIRP?")
    assert ids(base)[0] == "ollama:phi4:4b"  # opzione spenta: ignorata
    on = plan_auto(cands, PREFS, r, 0.6, healthy, question="Che cos'è l'EIRP?", route_simple=True)
    assert ids(on)[0] == "ollama:tiny:1b" and on.reason == "routed_simple"
    hard = plan_auto(
        cands, PREFS, r, 0.6, healthy, question="Deriva la formula FSPL", route_simple=True
    )
    assert ids(hard)[0] == "ollama:phi4:4b"


@pytest.mark.parametrize(
    "q,expected",
    [("Che cos'è l'EIRP?", True), ("What is Eb/N0?", True), ("Come si deriva FSPL?", False)],
)
def test_is_definitional(q: str, expected: bool) -> None:
    assert is_definitional(q) is expected


def test_ranking_file_parse_reload_and_garbage(tmp_path: Path) -> None:
    f = tmp_path / "r.json"
    rf = RankingFile(f)
    assert rf.get().entries == {}  # assente
    good = {
        "version": 1,
        "results": [
            {"provider": "ollama", "model": "a", "score": 0.8, "meets_threshold": True},
            {"provider": "ollama", "model": "b", "score": "x"},  # scartato
            {"provider": "ollama", "model": "c", "score": 7},  # fuori scala
            {"provider": "ollama", "model": "d", "score": float("nan")},
            "junk",
        ],
    }
    f.write_text(json.dumps(good))
    assert list(rf.get().entries) == [("ollama", "a")]
    f.write_text("{broken")
    assert rf.get().entries == {}
    f.write_text(json.dumps({"version": 99, "results": []}))
    assert rf.get().entries == {}
    with pytest.raises(ValueError):
        parse_ranking([])


# ------------------------------------------------------------------ circuit breaker
class Clock:
    t = 0.0

    def __call__(self) -> float:
        return self.t


def test_breaker_opens_after_consecutive_failures_and_half_open_probe() -> None:
    clk = Clock()
    b = CircuitBreakers(3, 30.0, clk)
    k = ("ollama", "m")
    b.failure(k, "timeout")
    b.failure(k, "error")
    assert b.allow(k) and not b.is_open(k)
    b.success(k)  # azzera i consecutivi
    b.failure(k, "timeout")
    b.failure(k, "timeout")
    assert b.state(k) == "closed"
    b.failure(k, "timeout")
    assert b.state(k) == "open" and not b.allow(k) and b.last_error(k) == "timeout"
    clk.t += 29
    assert not b.allow(k)
    clk.t += 2
    assert b.state(k) == "half_open"
    assert b.allow(k)  # una sola prova
    assert not b.allow(k)
    b.failure(k, "error")  # prova fallita: riapre per un nuovo raffreddamento
    assert b.is_open(k) and not b.allow(k)
    clk.t += 31
    assert b.allow(k)
    b.success(k)
    assert b.state(k) == "closed" and b.allow(k) and b.last_error(k) is None


def test_breaker_429_opens_immediately_and_keys_are_independent() -> None:
    b = CircuitBreakers(5, 10.0, Clock())
    b.failure("a", "http_429")
    assert b.is_open("a") and not b.is_open("b")


def test_stuck_probe_expires() -> None:
    clk = Clock()
    b = CircuitBreakers(1, 10.0, clk)
    b.failure("a", "error")
    clk.t += 11
    assert b.allow("a") and not b.allow("a")
    clk.t += 11  # la prova non ha mai riportato l'esito (richiesta annullata)
    assert b.allow("a")
