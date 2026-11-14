# SPDX-License-Identifier: Apache-2.0
"""Benchmark CLI con provider scriptati e un 'Ollama' finto: nessuna rete, nessun LLM reale."""

import io
import itertools
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from backend.assistant import bench
from backend.assistant.config import DEFAULT_PREFERENCE, parse_preference
from backend.assistant.discovery import Candidate
from backend.assistant.extractive import compose
from backend.assistant.selection import RankingFile, plan_auto

NOW = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)
EXT_MANIFEST = bench.REPO_ROOT / "backend/plugins/assistant_extractive/manifest.toml"


class ComposeLLM:
    """Si comporta come l'estrattivo (risposta perfetta sul set d'oro)."""

    def __init__(self) -> None:
        self.calls = 0

    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        self.calls += 1
        yield compose(messages)


class VagueLLM:
    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        yield "Dipende, non saprei dire."


class BrokenLLM:
    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        raise RuntimeError("segreto-interno")
        yield ""


class Fake:
    def __init__(self, tags: tuple[str, ...]) -> None:
        self.tags = tags

    def __call__(self, req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"models": [{"name": n} for n in self.tags]})


def run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    providers: dict[str, Any],
    tags: tuple[str, ...] = ("good:1", "vague:1", "broken:1"),
    env: dict[str, str] | None = None,
    out_name: str = "rank.json",
) -> tuple[int, str, str, Path, dict[str, Any]]:
    monkeypatch.setenv("ASSISTANT_OLLAMA_URL", "http://127.0.0.1:11434")
    env = env or {}
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    out, err = io.StringIO(), io.StringIO()
    ticks = itertools.count()
    path = tmp_path / out_name

    def make(c: Candidate) -> Any:
        if c.model is None:
            return bench.ExtractiveProvider(bench.load_manifest(EXT_MANIFEST))
        return providers[c.model]

    code = bench.main(
        [*argv, "--output", str(path)],
        env=env,
        discovery_transport=httpx.MockTransport(Fake(tags)),
        make_provider=make,
        clock=lambda: next(ticks) * 0.01,
        now=lambda: NOW,
        out=out,
        err=err,
    )
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        data = {}
    return code, out.getvalue(), err.getvalue(), path, data


def providers() -> dict[str, Any]:
    return {"good:1": ComposeLLM(), "vague:1": VagueLLM(), "broken:1": BrokenLLM()}


def test_ranking_order_scores_and_file_shape(tmp_path, monkeypatch) -> None:
    code, out, err, _, data = run(tmp_path, monkeypatch, [], providers())
    assert code == 0, err
    names = [(r["model"], r["rank"], r["baseline"]) for r in data["results"]]
    assert [n[0] for n in names if not n[2]] == ["good:1", "vague:1", "broken:1"]
    assert [n[1] for n in names if not n[2]] == [1, 2, 3]
    by = {r["model"]: r for r in data["results"]}
    good, vague, broken = by["good:1"], by["vague:1"], by["broken:1"]
    assert good["score"] > 0.95 and good["errors"]["count"] == 0
    assert vague["score"] < good["score"] and vague["metrics"]["refusal_rate"] == 0.0
    assert broken["metrics"]["error_rate"] == 1.0 and broken["score"] == 0.0
    assert broken["errors"]["codes"] == {"provider_error": data["golden"]["questions"]}
    base = by[None]
    assert base["provider"] == "assistant-extractive" and base["rank"] is None and base["baseline"]
    assert data["version"] == 1 and data["weights"] == bench.WEIGHTS
    assert sum(data["weights"].values()) == pytest.approx(1.0)
    assert data["golden"]["questions"] >= 30 and len(data["golden"]["sha256"]) == 64
    assert {"latency_p50_s", "latency_p95_s", "metrics", "meets_threshold", "local"} <= set(good)
    assert "segreto-interno" not in json.dumps(data) + out + err


def test_deterministic_output_bytes(tmp_path, monkeypatch) -> None:
    a = run(tmp_path, monkeypatch, [], providers(), out_name="a.json")[3].read_bytes()
    b = run(tmp_path, monkeypatch, [], providers(), out_name="b.json")[3].read_bytes()
    assert a == b


def test_selection_uses_the_written_ranking(tmp_path, monkeypatch) -> None:
    path = run(tmp_path, monkeypatch, [], providers())[3]
    cands = [Candidate("ollama", m, True) for m in ("broken:1", "vague:1", "good:1")]
    plan = plan_auto(
        cands,
        parse_preference(DEFAULT_PREFERENCE),
        RankingFile(path).get(),
        0.6,
        {c.key for c in cands},
    )
    models = [c.model for c in plan.chain]
    assert models[0] == "good:1" and "broken:1" not in models  # sotto soglia: escluso


def test_provider_and_model_filters(tmp_path, monkeypatch) -> None:
    data = run(tmp_path, monkeypatch, ["--model", "good*"], providers())[4]
    assert {r["model"] for r in data["results"] if not r["baseline"]} == {"good:1"}
    assert run(tmp_path, monkeypatch, ["--provider", "nope"], providers())[0] == 3


def test_hosted_excluded_without_flag_and_warned_with_flag(tmp_path, monkeypatch) -> None:
    env = {
        "ASSISTANT_LLM_BASE_URL": "https://api.hosted-example.test/v1",
        "ASSISTANT_LLM_MODEL": "cloud:1",
        "ASSISTANT_LLM_API_KEY": "sk-BENCH-SECRET",
    }
    calls = providers() | {"cloud:1": ComposeLLM()}
    code, out, err, _, data = run(tmp_path, monkeypatch, [], calls, env=env)
    assert code == 0 and "cloud:1" not in {r["model"] for r in data["results"]}
    assert "escluso (esterno" in err and data["hosted_included"] is False
    assert calls["cloud:1"].calls == 0
    code, out, err, _, data = run(tmp_path, monkeypatch, ["--allow-hosted"], calls, env=env)
    cloud = next(r for r in data["results"] if r["model"] == "cloud:1")
    assert cloud["local"] is False and data["hosted_included"] is True
    assert "ATTENZIONE (privacy)" in err and calls["cloud:1"].calls > 0
    assert "sk-BENCH-SECRET" not in out + err + json.dumps(data)


def test_exit_codes(tmp_path, monkeypatch) -> None:
    existing = tmp_path / "prev.txt"
    existing.write_text("PRECEDENTE")
    code, _, err, _, _ = run(tmp_path, monkeypatch, [], providers(), tags=(), out_name="prev.txt")
    assert code == 3 and "nessun candidato" in err
    assert existing.read_text() == "PRECEDENTE"  # non sovrascritto
    assert run(tmp_path, monkeypatch, ["--bogus"], providers())[0] == 2
    assert run(tmp_path, monkeypatch, ["--timeout", "0"], providers())[0] == 2
    missing = ["--golden", str(tmp_path / "missing.yaml")]
    assert run(tmp_path, monkeypatch, missing, providers())[0] == 2
    assert run(tmp_path, monkeypatch, ["--help"], providers())[0] == 0
    monkeypatch.setenv("ASSISTANT_MIN_SCORE", "7")
    assert run(tmp_path, monkeypatch, [], providers())[0] == 2


def test_list_mode_writes_nothing(tmp_path, monkeypatch) -> None:
    code, out, _, path, _ = run(tmp_path, monkeypatch, ["--list"], providers())
    assert code == 0 and not path.exists()
    assert out.splitlines() == [
        "ollama:broken:1\tlocale",
        "ollama:good:1\tlocale",
        "ollama:vague:1\tlocale",
    ]


def test_percentile_nearest_rank() -> None:
    assert bench.percentile([], 0.5) == 0.0
    xs = [0.1 * i for i in range(1, 11)]
    assert bench.percentile(xs, 0.5) == pytest.approx(0.5)
    assert bench.percentile(xs, 0.95) == pytest.approx(1.0)
