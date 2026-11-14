# SPDX-License-Identifier: Apache-2.0
import pytest

from backend.assistant.config import DEFAULT_PREFERENCE, load_settings, parse_preference
from backend.envconf import ConfigError


def test_defaults_are_auto_with_extractive_last(monkeypatch: pytest.MonkeyPatch) -> None:
    for v in ("ASSISTANT_PROVIDER", "ASSISTANT_PREFERENCE", "ASSISTANT_DISCOVERY_TTL_S"):
        monkeypatch.delenv(v, raising=False)
    s = load_settings()
    assert s.provider == "auto" and s.preference[-1] == "assistant-extractive"
    assert s.discovery_ttl_s == 60.0 and s.route_simple is False
    assert s.ranking_file.as_posix() == "build/assistant-ranking.json"
    assert parse_preference(DEFAULT_PREFERENCE) == s.preference


def test_preference_is_normalised_and_extractive_forced_last() -> None:
    assert parse_preference("assistant-extractive, ollama:phi4* ,x") == (
        "ollama:phi4*",
        "x",
        "assistant-extractive",
    )


@pytest.mark.parametrize("raw", ["Ollama", "ollama:", "a b", "ollama:q;rm", "../x"])
def test_bad_preference_rejected(raw: str) -> None:
    if raw == "ollama:":  # glob vuoto = solo provider
        assert parse_preference(raw) == ("ollama", "assistant-extractive")
        return
    with pytest.raises(ConfigError, match="ASSISTANT_PREFERENCE"):
        parse_preference(raw)


@pytest.mark.parametrize(
    "name,value",
    [
        ("ASSISTANT_DISCOVERY_TTL_S", "0"),
        ("ASSISTANT_DISCOVERY_TTL_S", "abc"),
        ("ASSISTANT_DISCOVERY_TIMEOUT_S", "-1"),
        ("ASSISTANT_BREAKER_FAILURES", "1.5"),
        ("ASSISTANT_BREAKER_COOLDOWN_S", "nan"),
        ("ASSISTANT_FAILOVER_BUDGET_S", "0"),
        ("ASSISTANT_MIN_SCORE", "1.5"),
    ],
)
def test_numeric_env_validated(monkeypatch: pytest.MonkeyPatch, name: str, value: str) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ConfigError, match=name):
        load_settings()
