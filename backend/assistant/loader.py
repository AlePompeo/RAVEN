# SPDX-License-Identifier: Apache-2.0
"""Caricamento e validazione della base di conoscenza.

Radici scandite: `docs/knowledge/**`, `backend/plugins/*/knowledge/**` (documenti scritti a mano,
file `*.md` con front-matter YAML; i file che iniziano con `_` sono modelli e si saltano) piu'
voci GENERATE dai manifest dei plugin e da `contracts/*.schema.json`.
Un documento non valido non ferma gli altri: l'errore e' raccolto e riportato in `/status`.
"""

import json
import re
import tomllib
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from backend.assistant.model import (
    KINDS,
    LANGS,
    LEVELS,
    KnowledgeDoc,
    Source,
    Variable,
)
from backend.core.errors import ManifestError
from backend.core.manifest import load_manifest

MAX_DOC_BYTES = 256 * 1024
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
LINK_RE = re.compile(r"\]\(kb:([a-z0-9][a-z0-9._-]*)\)")
REPO_PREFIXES = ("docs/", "backend/", "contracts/", "frontend/", "tests/", "e2e/", "scripts/")

# suffisso del nome del campo -> unita' leggibile (convenzione dei contratti: unita' nel nome)
UNIT_SUFFIXES: dict[str, str] = {
    "deg": "gradi (deg)",
    "rad": "radianti (rad)",
    "w": "watt (W)",
    "kw": "chilowatt (kW)",
    "db": "decibel (dB)",
    "dbm": "dBm",
    "km": "chilometri (km)",
    "m": "metri (m)",
    "s": "secondi (s)",
    "ms": "millisecondi (ms)",
    "hz": "hertz (Hz)",
    "mhz": "megahertz (MHz)",
    "ghz": "gigahertz (GHz)",
    "dps": "gradi al secondo (deg/s)",
    "g": "accelerazione in g",
    "ut": "microtesla (uT)",
    "v": "volt (V)",
    "c": "gradi Celsius (C)",
    "k": "kelvin (K)",
}


def unit_from_name(name: str) -> str:
    """Unita' dedotta dal suffisso `_xxx` del nome; stringa vuota se non c'e' (es. t_utc)."""
    if "_" not in name:
        return ""
    return UNIT_SUFFIXES.get(name.rsplit("_", 1)[1].lower(), "")


class KnowledgeError(ValueError):
    pass


def _str(d: dict[str, Any], key: str, default: str = "") -> str:
    v = d.get(key, default)
    if v is None:
        return default
    if not isinstance(v, str | int | float):  # date di YAML -> isoformat sotto
        v = v.isoformat() if hasattr(v, "isoformat") else v
    return str(v).strip()


def _strs(d: dict[str, Any], key: str) -> tuple[str, ...]:
    v = d.get(key) or []
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, list):
        raise KnowledgeError(f"{key} deve essere una lista")
    if not all(isinstance(x, str | int | float) for x in v):
        raise KnowledgeError(
            f"{key}: ogni elemento deve essere testo (usare le virgolette se contiene ': ')"
        )
    return tuple(str(x).strip() for x in v if str(x).strip())


def split_front_matter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        raise KnowledgeError("front-matter YAML mancante (il file deve iniziare con ---)")
    m = re.match(r"^---[ \t]*\n(.*?)\n---[ \t]*(?:\n|$)(.*)$", text, flags=re.DOTALL)
    if not m:
        raise KnowledgeError("front-matter non chiuso")
    try:
        meta = yaml.safe_load(m.group(1))
    except yaml.YAMLError as e:
        raise KnowledgeError(f"YAML non valido: {type(e).__name__}") from None
    if not isinstance(meta, dict):
        raise KnowledgeError("il front-matter deve essere una mappa")
    return meta, m.group(2).strip()


def parse_doc(text: str, path: str = "") -> KnowledgeDoc:
    meta, body = split_front_matter(text)
    sources: list[Source] = []
    for s in meta.get("sources") or []:
        if not isinstance(s, dict) or not s.get("ref"):
            raise KnowledgeError("sources[] richiede ref e supports")
        sources.append(Source(str(s["ref"]).strip(), str(s.get("supports", "")).strip()))
    variables: list[Variable] = []
    for v in meta.get("variables") or []:
        if not isinstance(v, dict):
            raise KnowledgeError("variables[] deve contenere mappe")
        variables.append(
            Variable(
                str(v.get("symbol", "")).strip(),
                str(v.get("name", "")).strip(),
                str(v.get("unit", "")).strip(),
                str(v.get("range", "") or "").strip(),
            )
        )
    we = meta.get("worked_example") or {}
    if not isinstance(we, dict):
        raise KnowledgeError("worked_example deve essere una mappa")
    return KnowledgeDoc(
        id=_str(meta, "id"),
        title=_str(meta, "title"),
        kind=_str(meta, "kind"),
        summary=_str(meta, "summary"),
        body=body,
        tags=_strs(meta, "tags"),
        sources=tuple(sources),
        applies_to=_strs(meta, "applies_to"),
        related=_strs(meta, "related"),
        level=_str(meta, "level", "intermedio"),
        lang=_str(meta, "lang", "it"),
        last_verified=_str(meta, "last_verified"),
        path=path,
        expression=_str(meta, "expression"),
        variables=tuple(variables),
        assumptions=_strs(meta, "assumptions"),
        limits=_strs(meta, "limits"),
        worked_example=we,
        derivation=_strs(meta, "derivation"),
    )


def validate(docs: Iterable[KnowledgeDoc], repo_root: Path | None = None) -> list[str]:
    """Errori di coerenza (lista vuota = valido). Gli id duplicati sono errori."""
    docs = list(docs)
    errors: list[str] = []
    ids: dict[str, KnowledgeDoc] = {}
    for d in docs:
        where = d.path or d.id
        if d.id in ids:
            errors.append(f"{where}: id duplicato {d.id!r} (gia' in {ids[d.id].path or d.id})")
        ids[d.id] = d
        if not ID_RE.match(d.id):
            errors.append(f"{where}: id non valido {d.id!r}")
        if d.kind not in KINDS:
            errors.append(f"{where}: kind non valido {d.kind!r}")
        if d.level not in LEVELS:
            errors.append(f"{where}: level non valido {d.level!r}")
        if d.lang not in LANGS:
            errors.append(f"{where}: lang non valido {d.lang!r}")
        if not d.title:
            errors.append(f"{where}: title mancante")
        if not d.summary:
            errors.append(f"{where}: summary mancante")
        if d.origin == "manual":
            if not d.sources:
                errors.append(f"{where}: almeno una fonte (sources) richiesta")
            if not d.last_verified:
                errors.append(f"{where}: last_verified mancante")
        if d.kind == "formula":
            if not d.expression:
                errors.append(f"{where}: formula senza expression")
            if not d.variables:
                errors.append(f"{where}: formula senza variables")
            if not d.worked_example.get("inputs") or not d.worked_example.get("outputs"):
                errors.append(f"{where}: formula senza worked_example (inputs e outputs)")
            if not d.assumptions:
                errors.append(f"{where}: formula senza assumptions")
            if not d.limits:
                errors.append(f"{where}: formula senza limits")
        for v in d.variables:
            if not v.symbol or not v.name:
                errors.append(f"{where}: variabile senza symbol/name")
            if not v.unit:
                errors.append(
                    f"{where}: variabile {v.symbol!r} senza unit (usare '-' se adimensionale)"
                )
    for d in docs:
        where = d.path or d.id
        refs = list(d.related) + LINK_RE.findall(d.body)
        for r in refs:
            if r not in ids:
                errors.append(f"{where}: link a id inesistente {r!r}")
        if repo_root is not None:
            for s in d.sources:
                if s.ref.startswith(REPO_PREFIXES):
                    p = s.ref.split("#", 1)[0]
                    if not (repo_root / p).exists():
                        errors.append(f"{where}: fonte non trovata nel repository: {s.ref}")
    return errors


def _resolve(schema: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    ref = node.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/"):
        cur: Any = schema
        for part in ref[2:].split("/"):
            cur = cur.get(part, {}) if isinstance(cur, dict) else {}
        return cur if isinstance(cur, dict) else {}
    return node


def _walk(
    schema: dict[str, Any], node: dict[str, Any], prefix: str, req: bool, out: list[str]
) -> None:
    node = _resolve(schema, node)
    props = node.get("properties")
    if isinstance(props, dict):
        required = set(node.get("required", []))
        for name, sub in props.items():
            _walk(schema, sub, f"{prefix}{name}.", name in required, out)
        return
    field = prefix[:-1]
    leaf = field.rsplit(".", 1)[-1]
    unit = unit_from_name(leaf)
    typ = node.get("type", "oggetto")
    desc = str(node.get("description", "")).strip()
    parts = [f"- `{field}`: tipo {typ}", "obbligatorio" if req else "opzionale"]
    parts.append(f"unita' {unit}" if unit else "senza unita' (adimensionale o testo)")
    if desc:
        parts.append(desc)
    out.append(", ".join(parts))


def contract_docs(contracts_dir: Path) -> list[KnowledgeDoc]:
    docs: list[KnowledgeDoc] = []
    for f in sorted(contracts_dir.glob("*.schema.json")):
        try:
            schema = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(schema, dict):
            continue
        name = f.name[: -len(".schema.json")]
        lines: list[str] = []
        _walk(schema, schema, "", True, lines)
        title = str(schema.get("title", name))
        desc = str(schema.get("description", "")).strip()
        body = (
            f"## Campi del contratto {name}\n\n"
            "Le unita' sono nel nome del campo (suffisso `_deg`, `_w`, `_db`, ...).\n\n"
            + "\n".join(lines)
        )
        docs.append(
            KnowledgeDoc(
                id=f"contract-{name.replace('_', '-')}",
                title=f"Contratto dati {title} ({f.name})",
                kind="concept",
                summary=desc or f"Schema JSON {f.name}",
                body=body,
                tags=("contract", "contratto", "schema", name, title.lower()),
                sources=(Source(f"contracts/{f.name}", "schema JSON (fonte unica dei tipi)"),),
                applies_to=(name,),
                origin="contract",
                path=f"contracts/{f.name}",
            )
        )
    return docs


def manifest_docs(plugins_dir: Path, repo_root: Path) -> list[KnowledgeDoc]:
    docs: list[KnowledgeDoc] = []
    for mf in sorted(plugins_dir.glob("*/manifest.toml")):
        try:
            m = load_manifest(mf)
            raw = tomllib.loads(mf.read_text(encoding="utf-8"))
        except (ManifestError, OSError, ValueError):
            continue
        desc = str(raw.get("description", "")).strip()
        rel = mf.relative_to(repo_root).as_posix() if mf.is_relative_to(repo_root) else mf.name
        lines = [
            f"- id: `{m.id}`",
            f"- kind: {m.kind}",
            f"- versione: {m.version}",
            f"- licenza: {m.license}",
            f"- timeout: {m.timeout_s:g} s",
        ]
        if m.terms_url:
            lines.append(f"- condizioni d'uso (terms_url): {m.terms_url}")
        if desc:
            lines.append(f"- descrizione: {desc}")
        docs.append(
            KnowledgeDoc(
                id=f"plugin-{m.id}",
                title=f"Plugin {m.id} ({m.kind})",
                kind="simulation" if m.kind == "simulation" else "concept",
                summary=desc
                or f"Plugin {m.kind} {m.id}, versione {m.version}, licenza {m.license}.",
                body="## Manifest del plugin\n\n" + "\n".join(lines),
                tags=("plugin", m.kind, m.id),
                sources=(Source(rel, "manifest.toml del plugin"),),
                applies_to=(m.id,),
                origin="manifest",
                path=rel,
            )
        )
    return docs


def knowledge_files(repo_root: Path, extra_roots: Iterable[Path] = ()) -> list[Path]:
    roots = [
        repo_root / "docs" / "knowledge",
        *sorted((repo_root / "backend/plugins").glob("*/knowledge")),
    ]
    roots += list(extra_roots)
    files: list[Path] = []
    for r in roots:
        if r.is_dir():
            files += [
                p
                for p in sorted(r.rglob("*.md"))
                if not p.name.startswith("_") and p.name.lower() != "readme.md"
            ]
    return files


def load_all(
    repo_root: Path, extra_roots: Iterable[Path] = ()
) -> tuple[list[KnowledgeDoc], list[str]]:
    """Documenti (manuali con precedenza sulle voci generate) ed errori di caricamento/validazione."""
    errors: list[str] = []
    manual: list[KnowledgeDoc] = []
    for p in knowledge_files(repo_root, extra_roots):
        rel = p.relative_to(repo_root).as_posix() if p.is_relative_to(repo_root) else str(p)
        try:
            if p.stat().st_size > MAX_DOC_BYTES:
                raise KnowledgeError("file troppo grande")
            manual.append(parse_doc(p.read_text(encoding="utf-8"), rel))
        except (KnowledgeError, OSError, UnicodeDecodeError) as e:
            errors.append(f"{rel}: {e}")
    generated = manifest_docs(repo_root / "backend/plugins", repo_root) + contract_docs(
        repo_root / "contracts"
    )
    taken = {d.id for d in manual}
    docs = manual + [g for g in generated if g.id not in taken]
    # Le fonti citate (test, frontend, altri documenti) esistono solo in un checkout completo: in un'immagine
    # di runtime (senza `tests/`) non si controllano, per non segnalare come errori file volutamente assenti.
    full_checkout = (repo_root / "tests").is_dir()
    errors += validate(docs, repo_root if full_checkout else None)
    return docs, errors
