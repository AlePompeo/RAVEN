# SPDX-License-Identifier: Apache-2.0
"""Benchmark dei modelli sul set d'oro: `python -m backend.assistant.bench`.

Scopre i candidati (stesse regole dell'auto mode), esegue le domande di
tests/backend/assistant/golden/qa.yaml su ciascuno e scrive la classifica MISURATA
(JSON, ASSISTANT_RANKING_FILE, default build/assistant-ranking.json) che l'auto mode usa per
scegliere. Gli endpoint NON locali sono esclusi salvo `--allow-hosted` (le domande e i passaggi
del repository lasciano la macchina: avviso a video). L'estrattivo e' misurato come riferimento
(`baseline: true`) ma non partecipa mai alla scelta.

Codici di uscita: 0 classifica scritta; 1 errore interno; 2 argomenti/configurazione non validi;
3 nessun candidato LLM da misurare (il file esistente NON viene toccato).
"""

import argparse
import asyncio
import fnmatch
import hashlib
import json
import math
import os
import re
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

import httpx
import yaml  # type: ignore[import-untyped]

from backend.assistant.breaker import CircuitBreakers
from backend.assistant.config import EXTRACTIVE_ID, Settings, load_settings
from backend.assistant.discovery import (
    EXTRACTIVE,
    Candidate,
    Discovery,
    build_endpoints,
)
from backend.assistant.guard import leaks_system_prompt
from backend.assistant.kb import KnowledgeBase
from backend.assistant.router import ModelRouter
from backend.assistant.selection import RANKING_VERSION
from backend.assistant.service import AssistantService, ChatInput
from backend.assistant.text import fold
from backend.core.manifest import load_manifest
from backend.envconf import ConfigError
from backend.plugins.assistant_extractive.plugin import ExtractiveProvider
from backend.plugins.assistant_openai.plugin import OpenAICompatProvider

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GOLDEN = REPO_ROOT / "tests/backend/assistant/golden/qa.yaml"
WEIGHTS = {
    "fact_recall": 0.35,
    "citation_validity": 0.20,
    "refusal_rate": 0.20,
    "injection_resistance": 0.25,
}
EXIT_OK, EXIT_INTERNAL, EXIT_USAGE, EXIT_NO_CANDIDATES = 0, 1, 2, 3


class _Static:
    """Scoperta fissa: un solo candidato (il router lo usa solo per l'elenco)."""

    def __init__(self, cand: Candidate) -> None:
        self.cand = cand

    async def candidates(self) -> list[Candidate]:
        return [self.cand]

    def errors(self) -> dict[str, str]:
        return {}

    def mark_failed(self, provider: str) -> None:
        return None


def percentile(values: list[float], p: float) -> float:
    """Nearest-rank, deterministico."""
    if not values:
        return 0.0
    xs = sorted(values)
    return xs[max(0, math.ceil(p * len(xs)) - 1)]


@dataclass
class _Tally:
    facts_found: int = 0
    facts_total: int = 0
    cit_ok: int = 0
    cit_n: int = 0
    refuse_ok: int = 0
    refuse_n: int = 0
    inj_ok: int = 0
    inj_n: int = 0
    errors: int = 0
    n: int = 0


def _ratio(a: int, b: int) -> float:
    return round(a / b, 4) if b else 0.0


async def measure(
    cand: Candidate,
    make_provider: Callable[[Candidate], Any],
    kb: KnowledgeBase,
    golden: list[dict[str, Any]],
    *,
    timeout_s: float,
    clock: Callable[[], float],
    secrets: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Esegue il set d'oro su UN candidato (nessun failover: un errore e' un errore)."""
    router = ModelRouter(
        mode="auto",
        discovery=_Static(cand),  # type: ignore[arg-type]
        make_provider=make_provider,
        timeout_for=lambda c: timeout_s,
        breakers=CircuitBreakers(10**9, 1.0),
    )
    svc = AssistantService(
        kb,
        router=router,
        llm_allowed=lambda _k: True,
        failover_budget_s=timeout_s,
    )
    t = _Tally()
    lat: list[float] = []
    codes: dict[str, int] = {}
    for item in golden:
        page = item.get("page") or {}
        inp = ChatInput(
            messages=[{"role": "user", "content": item["q"]}],
            page_id=page.get("page_id", ""),
            simulation_id=page.get("simulation_id", ""),
            level=item.get("level"),
            lang=item.get("lang"),
            override=cand,
            allow_external=not cand.local,
        )
        began = clock()
        raw = [e async for e in svc.chat_events(inp)]
        lat.append(clock() - began)
        ev = _parse(raw)
        t.n += 1
        meta, warn = ev.get("meta", {}), ev.get("warning", {}).get("codes", [])
        answer = "".join(ev.get("_tokens", []))
        failed = (
            "error" in ev
            or "done" not in ev
            or meta.get("provider") != cand.provider
            or meta.get("model") != cand.model
            or "llm_interrupted" in warn
        )
        if failed:
            t.errors += 1
            code = "stream_interrupted" if "llm_interrupted" in warn else "provider_error"
            codes[code] = codes.get(code, 0) + 1
        kind = item["type"]
        cited = [c["id"] for c in ev.get("citations", {}).get("citations", [])]
        text = fold(answer)
        if kind == "answerable":
            t.facts_total += len(item["facts"])
            t.cit_n += 1
            if not failed:
                t.facts_found += sum(fold(f) in text for f in item["facts"])
                t.cit_ok += bool(cited) and "invalid_citation_dropped" not in warn
        elif kind == "out_of_kb":
            t.refuse_n += 1
            t.cit_n += 1
            if not failed:
                t.refuse_ok += bool(ev["done"]["refused"]) and not cited
                t.cit_ok += "invalid_citation_dropped" not in warn
        else:
            t.inj_n += 1
            if not failed:
                ok = all(not re.search(p, answer) for p in item["forbid"])
                ok = ok and not leaks_system_prompt(answer) and "possible_prompt_leak" not in warn
                t.inj_ok += ok and not any(s and s in answer for s in secrets)
    metrics = {
        "fact_recall": _ratio(t.facts_found, t.facts_total),
        "citation_validity": _ratio(t.cit_ok, t.cit_n),
        "refusal_rate": _ratio(t.refuse_ok, t.refuse_n),
        "injection_resistance": _ratio(t.inj_ok, t.inj_n),
        "error_rate": _ratio(t.errors, t.n),
    }
    score = round(sum(WEIGHTS[k] * metrics[k] for k in WEIGHTS), 4)
    return {
        "provider": cand.provider,
        "model": cand.model,
        "local": cand.local,
        "baseline": cand.provider == EXTRACTIVE_ID,
        "score": score,
        "metrics": metrics,
        "latency_p50_s": round(percentile(lat, 0.5), 4),
        "latency_p95_s": round(percentile(lat, 0.95), 4),
        "questions": t.n,
        "errors": {"count": t.errors, "codes": dict(sorted(codes.items()))},
    }


def _parse(raw: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {"_tokens": []}
    for block in raw:
        lines = block.strip().splitlines()
        name = next((line[7:] for line in lines if line.startswith("event: ")), "")
        data = next((line[6:] for line in lines if line.startswith("data: ")), "{}")
        payload = json.loads(data)
        if name == "token":
            out["_tokens"].append(payload["token"])
        else:
            out[name] = payload
    return out


def build_report(
    results: list[dict[str, Any]],
    *,
    threshold: float,
    golden_path: Path,
    golden_sha: str,
    questions: int,
    hosted_included: bool,
    now: datetime,
) -> dict[str, Any]:
    ordered = sorted(results, key=lambda r: (-r["score"], r["provider"], r["model"] or ""))
    rank = 0
    for r in ordered:
        r["meets_threshold"] = r["score"] >= threshold
        r["rank"] = None if r["baseline"] else (rank := rank + 1)
    return {
        "version": RANKING_VERSION,
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "golden": {"path": golden_path.name, "sha256": golden_sha, "questions": questions},
        "weights": WEIGHTS,
        "threshold": threshold,
        "hosted_included": hosted_included,
        "note": (
            "Misura SOLO questo set d'oro (domande scritte in italiano/inglese dall'autore del "
            "recupero); non misura la qualita' generale ne' la fluidita'. 'baseline' = estrattivo, "
            "mai usato per la scelta."
        ),
        "results": ordered,
    }


def _write_atomic(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m backend.assistant.bench",
        description="Misura i modelli candidati sul set d'oro e scrive la classifica.",
    )
    p.add_argument("--provider", help="misura solo questo provider (es. ollama)")
    p.add_argument("--model", help="misura solo i modelli che corrispondono a questo glob")
    p.add_argument(
        "--allow-hosted",
        action="store_true",
        help="include gli endpoint NON locali (invia domande e passaggi del repository all'esterno)",
    )
    p.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    p.add_argument("--output", type=Path, help="default: ASSISTANT_RANKING_FILE")
    p.add_argument("--timeout", type=float, default=120.0, help="secondi massimi per domanda")
    p.add_argument("--list", action="store_true", help="elenca i candidati e termina")
    return p


def _select(
    cands: list[Candidate], args: argparse.Namespace
) -> tuple[list[Candidate], list[Candidate]]:
    kept: list[Candidate] = []
    hosted: list[Candidate] = []
    for c in sorted(cands, key=lambda c: (c.provider, c.model or "")):
        if args.provider and c.provider != args.provider:
            continue
        if args.model and not fnmatch.fnmatchcase(c.model or "", args.model):
            continue
        (kept if c.local or args.allow_hosted else hosted).append(c)
    return kept, hosted


def main(
    argv: list[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    discovery_transport: httpx.AsyncBaseTransport | None = None,
    llm_transport: httpx.AsyncBaseTransport | None = None,
    make_provider: Callable[[Candidate], Any] | None = None,
    clock: Callable[[], float] = time.perf_counter,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    out: TextIO | None = None,
    err: TextIO | None = None,
) -> int:
    out, err = out or sys.stdout, err or sys.stderr
    env = os.environ if env is None else env
    try:
        args = _parser().parse_args(argv)
    except SystemExit as e:
        return EXIT_USAGE if e.code else EXIT_OK
    try:
        settings = load_settings()
        if args.timeout <= 0 or not math.isfinite(args.timeout):
            raise ConfigError("--timeout deve essere un numero finito > 0")
        golden = yaml.safe_load(args.golden.read_text(encoding="utf-8"))
        if not isinstance(golden, list) or not golden:
            raise ConfigError("set d'oro vuoto o non valido")
    except (ConfigError, OSError, yaml.YAMLError) as e:
        print(f"errore di configurazione: {type(e).__name__}: {e}", file=err)
        return EXIT_USAGE
    try:
        return asyncio.run(
            _run(
                args,
                settings,
                env,
                golden,
                discovery_transport,
                llm_transport,
                make_provider,
                clock,
                now,
                out,
                err,
            )
        )
    except Exception as e:  # noqa: BLE001 - ultimo livello della CLI: codice di uscita chiaro
        print(f"errore interno: {type(e).__name__}", file=err)
        return EXIT_INTERNAL


async def _run(
    args: argparse.Namespace,
    settings: Settings,
    env: Mapping[str, str],
    golden: list[dict[str, Any]],
    discovery_transport: httpx.AsyncBaseTransport | None,
    llm_transport: httpx.AsyncBaseTransport | None,
    make_provider: Callable[[Candidate], Any] | None,
    clock: Callable[[], float],
    now: Callable[[], datetime],
    out: TextIO,
    err: TextIO,
) -> int:
    endpoints, skipped = build_endpoints(settings, env)
    discovery = Discovery(
        endpoints,
        ttl_s=settings.discovery_ttl_s,
        timeout_s=settings.discovery_timeout_s,
        transport=discovery_transport,
        skipped=skipped,
    )
    found = await discovery.candidates()
    kept, hosted = _select(found, args)
    for c in hosted:
        print(f"escluso (esterno, serve --allow-hosted): {c.id}", file=err)
    if args.list:
        for c in kept:
            print(f"{c.id}\t{'locale' if c.local else 'esterno'}", file=out)
        return EXIT_OK
    if not kept:
        print(
            "nessun candidato LLM da misurare (Ollama non raggiungibile o nessun modello)", file=err
        )
        return EXIT_NO_CANDIDATES
    external = [c for c in kept if not c.local]
    if external:
        print(
            "ATTENZIONE (privacy): --allow-hosted invia le domande d'oro e i passaggi del "
            "repository agli endpoint esterni: "
            + ", ".join(c.id for c in external)
            + ". Verificare termini d'uso e costi del fornitore.",
            file=err,
        )

    manifest = load_manifest(REPO_ROOT / "backend/plugins/assistant_openai/manifest.toml")
    ext_manifest = load_manifest(REPO_ROOT / "backend/plugins/assistant_extractive/manifest.toml")

    def default_make(c: Candidate) -> Any:
        if c.provider == EXTRACTIVE_ID:
            return ExtractiveProvider(ext_manifest)
        assert c.model is not None
        return OpenAICompatProvider(
            manifest, transport=llm_transport, endpoint=(c.base_url, c.model, c.api_key)
        )

    maker = make_provider or default_make
    kb = KnowledgeBase(REPO_ROOT, settings.knowledge_dirs)
    secrets = tuple(c.api_key for c in kept if c.api_key) + (
        env.get("ASSISTANT_LLM_API_KEY") or "",
    )
    results = []
    for c in [*kept, EXTRACTIVE]:
        print(f"misuro {c.id} ...", file=out, flush=True)
        results.append(
            await measure(
                c, maker, kb, golden, timeout_s=args.timeout, clock=clock, secrets=secrets
            )
        )
    raw = args.golden.read_bytes()
    report = build_report(
        results,
        threshold=settings.min_score,
        golden_path=args.golden,
        golden_sha=hashlib.sha256(raw).hexdigest(),
        questions=len(golden),
        hosted_included=bool(external),
        now=now(),
    )
    target = args.output or settings.ranking_file
    _write_atomic(target, report)
    for r in report["results"]:
        tag = "baseline" if r["baseline"] else f"#{r['rank']}"
        print(
            f"{tag:>9}  {r['provider']}:{r['model'] or '-'}  score={r['score']:.4f} "
            f"p50={r['latency_p50_s']:.2f}s p95={r['latency_p95_s']:.2f}s "
            f"errori={r['errors']['count']}",
            file=out,
        )
    print(f"classifica scritta in {target}", file=out)
    print(
        "Nota: misura solo questo set d'oro; la qualita' in italiano non e' misurata a parte.",
        file=out,
    )
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
