# SPDX-License-Identifier: Apache-2.0
import ast
import re
from pathlib import Path

import pytest

from backend.adapters.cache_memory import MemoryCache
from backend.api.app import create_app
from backend.bootstrap import build_app
from backend.core.registry import Registry
from backend.envconf import ConfigError, env_positive_float, env_positive_int

ROOT = Path(__file__).resolve().parents[2]
BAD = ["0", "-3", "abc", "1.5"]


def test_helper_semantics(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("X_TEST", raising=False)
    assert env_positive_int("X_TEST", 7) == 7
    monkeypatch.setenv("X_TEST", "")
    assert env_positive_int("X_TEST", 7) == 7
    monkeypatch.setenv("X_TEST", "3")
    assert env_positive_int("X_TEST", 7) == 3
    assert env_positive_int("Y", 1, env={"Y": "9"}) == 9
    for bad in BAD:
        monkeypatch.setenv("X_TEST", bad)
        with pytest.raises(ConfigError, match="X_TEST"):
            env_positive_int("X_TEST", 7)
    for bad in ["0", "-1", "nan", "inf", "x"]:
        with pytest.raises(ConfigError, match="F_TEST"):
            env_positive_float("F_TEST", 1.0, env={"F_TEST": bad})
    assert env_positive_float("F_TEST", 2.5, env={}) == 2.5


@pytest.mark.parametrize(
    "name",
    [
        "RATE_LIMIT_PER_MIN",
        "MAX_BODY_BYTES",
        "TELEMETRY_MAX_SUBSCRIBERS",
        "CHAT_MAX_STREAM_SECONDS",
        "ESTIMATOR_MAX_SESSIONS",
        "PIPELINE_MAX_QUERIES",
        "ML_TRAIN_PER_HOUR",
        "ML_MAX_CANDIDATES",
        "SIM_MAX_CONCURRENT",
    ],
)
@pytest.mark.parametrize("bad", [*BAD, "-1"])
def test_every_numeric_env_fails_fast_at_startup(
    name: str, bad: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(name, bad)
    with pytest.raises(SystemExit, match=name):
        build_app()


def test_create_app_raises_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ESTIMATOR_MAX_SESSIONS", "0")
    with pytest.raises(ConfigError, match="ESTIMATOR_MAX_SESSIONS"):
        create_app(Registry(), MemoryCache())


def _literal(node: ast.expr) -> str | None:
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and re.fullmatch(r"[A-Z][A-Z0-9_]+", node.value)
    ):
        return node.value
    return None


def _env_names() -> set[str]:
    names: set[str] = set()
    for py in (ROOT / "backend").rglob("*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and node.args:
                name = _literal(node.args[0])
                if name is None:
                    continue
                f = node.func
                fname = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
                is_get = (
                    fname == "get"
                    and isinstance(f, ast.Attribute)
                    and ast.unparse(f.value) in ("os.environ", "env")
                )
                if fname == "getenv" or fname.startswith("env_positive_") or is_get:
                    names.add(name)
            elif isinstance(node, ast.Subscript) and ast.unparse(node.value) == "os.environ":
                name = _literal(node.slice)
                if name:
                    names.add(name)
    return names


def test_all_env_vars_documented_in_env_example() -> None:
    text = (ROOT / ".env.example").read_text(encoding="utf-8")
    documented = set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", text, flags=re.MULTILINE))
    names = _env_names()
    assert {"RATE_LIMIT_PER_MIN", "PIPELINE_MAX_QUERIES", "SIM_MAX_CONCURRENT"} <= names
    missing = sorted(names - documented)
    assert not missing, f"variabili lette in backend/ ma assenti da .env.example: {missing}"
