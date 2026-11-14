# SPDX-License-Identifier: Apache-2.0
"""Configurazione da ambiente (variabili numeriche con envconf: un valore errato ferma l'avvio)."""

import os
import re
from dataclasses import dataclass
from pathlib import Path

from backend.envconf import ConfigError, env_positive_float, env_positive_int

DEFAULT_PROVIDER = "auto"
EXTRACTIVE_ID = "assistant-extractive"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_RANKING_FILE = "build/assistant-ranking.json"
# Ordine di preferenza di default: modelli aperti locali citati in docs/assistant.md (Llama 3.1 ha
# l'italiano tra le lingue supportate), poi qualunque altro modello Ollama, poi l'endpoint
# compatibile OpenAI configurato dall'operatore (anche ospitato), infine l'estrattivo.
DEFAULT_PREFERENCE = (
    "groq,ollama:llama3.1*,ollama:granite4*,ollama:phi4*,ollama:gemma3*,ollama,assistant-openai-compat,"
    "raven-local,assistant-extractive"
)


@dataclass(frozen=True)
class Settings:
    provider: str
    knowledge_dirs: tuple[Path, ...]
    dev_reload: bool
    max_context_tokens: int
    top_k: int
    max_messages: int
    max_message_chars: int
    llm_per_min_per_ip: int
    preference: tuple[str, ...] = ()
    ranking_file: Path = Path(DEFAULT_RANKING_FILE)
    ollama_url: str = DEFAULT_OLLAMA_URL
    local_hosts: tuple[str, ...] = ()
    discovery_ttl_s: float = 60.0
    discovery_timeout_s: float = 2.0
    breaker_failures: int = 3
    breaker_cooldown_s: float = 30.0
    failover_budget_s: float = 30.0
    min_score: float = 0.6
    route_simple: bool = False


def load_settings() -> Settings:
    dirs = tuple(
        Path(p) for p in (os.environ.get("ASSISTANT_KNOWLEDGE_DIRS") or "").split(":") if p.strip()
    )
    return Settings(
        provider=os.environ.get("ASSISTANT_PROVIDER") or DEFAULT_PROVIDER,
        knowledge_dirs=dirs,
        dev_reload=os.environ.get("ASSISTANT_DEV_RELOAD") == "1",
        max_context_tokens=env_positive_int("ASSISTANT_MAX_CONTEXT_TOKENS", 1800),
        top_k=env_positive_int("ASSISTANT_TOP_K", 5),
        max_messages=env_positive_int("ASSISTANT_MAX_MESSAGES", 20),
        max_message_chars=env_positive_int("ASSISTANT_MAX_MESSAGE_CHARS", 2000),
        llm_per_min_per_ip=env_positive_int("ASSISTANT_LLM_PER_MIN_PER_IP", 20),
        preference=parse_preference(os.environ.get("ASSISTANT_PREFERENCE") or DEFAULT_PREFERENCE),
        ranking_file=Path(os.environ.get("ASSISTANT_RANKING_FILE") or DEFAULT_RANKING_FILE),
        ollama_url=os.environ.get("ASSISTANT_OLLAMA_URL") or DEFAULT_OLLAMA_URL,
        local_hosts=tuple(
            h.strip().lower()
            for h in (os.environ.get("ASSISTANT_LOCAL_HOSTS") or "").split(",")
            if h.strip()
        ),
        discovery_ttl_s=env_positive_float("ASSISTANT_DISCOVERY_TTL_S", 60.0),
        discovery_timeout_s=env_positive_float("ASSISTANT_DISCOVERY_TIMEOUT_S", 2.0),
        breaker_failures=env_positive_int("ASSISTANT_BREAKER_FAILURES", 3),
        breaker_cooldown_s=env_positive_float("ASSISTANT_BREAKER_COOLDOWN_S", 30.0),
        failover_budget_s=env_positive_float("ASSISTANT_FAILOVER_BUDGET_S", 30.0),
        min_score=_unit_float("ASSISTANT_MIN_SCORE", 0.6),
        route_simple=os.environ.get("ASSISTANT_ROUTE_SIMPLE") == "1",
    )


def _unit_float(name: str, default: float) -> float:
    value = env_positive_float(name, default)
    if value > 1:
        raise ConfigError(f"{name} deve essere un numero in (0, 1]")
    return value


def parse_preference(raw: str) -> tuple[str, ...]:
    """'provider[:glob],...' -> voci normalizzate; il provider estrattivo e' sempre ultimo."""
    out: list[str] = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        prov, _, glob = item.partition(":")
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", prov) or (
            glob and not re.fullmatch(r"[A-Za-z0-9._:/*?\[\]-]{1,128}", glob)
        ):
            raise ConfigError(
                "ASSISTANT_PREFERENCE: voce non valida (usare provider[:modello-glob])"
            )
        if prov != EXTRACTIVE_ID:
            out.append(f"{prov}:{glob}" if glob else prov)
    return (*out, EXTRACTIVE_ID)
