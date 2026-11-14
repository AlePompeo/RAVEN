# SPDX-License-Identifier: Apache-2.0
"""Gate licenze: allowlist su dipendenze Python (pip-licenses) e Node (node_modules).

Uso:
    pip-licenses --format=json > /tmp/py.json
    python scripts/license_check.py --python-json /tmp/py.json \
        --node-modules frontend/node_modules --lockfile frontend/package-lock.json \
        --out frontend/public/licenses.json

Esito: 0 se nessuna violazione, 1 altrimenti. Nessuna dipendenza aggiuntiva.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

OK, REVIEW, FORBIDDEN = 0, 1, 2

_FORBIDDEN = re.compile(r"(^|[^a-z])(a|l)?gpl|general public license|affero", re.IGNORECASE)
_ALLOWED = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"mit(-0)?( license)?",
        r"expat( license)?",
        r"bsd.*",
        # grafie non SPDX (es. protobuf: "3-Clause BSD License"); il rilevamento di GPL/GNU
        # in _FORBIDDEN viene sempre prima, quindi gli alias non possono nascondere copyleft
        r"[234]-clause bsd( license)?",
        r"apache([- ]software)?([- ]license)?[- ]?(v?2(\.0)?)?( license)?",
        r"isc( license.*)?",
        r"0bsd",
        # Zlib: licenza permissiva; CC0-1.0: dedica al pubblico dominio
        r"zlib( license)?",
        r"cc0-1\.0",
        r"python-2\.0",
        r"psf(-2\.0)?( license.*)?",
        r"python software foundation( license)?",
    )
]


def _normalise(token: str) -> str:
    t = token.strip().strip("*").strip()
    return re.sub(r"(\+|-or-later|-only)$", "", t, flags=re.IGNORECASE)


def _classify_name(name: str) -> int:
    t = _normalise(name)
    if not t or t.upper() in {"UNKNOWN", "UNLICENSED", "NONE"}:
        return REVIEW
    if _FORBIDDEN.search(t):
        return FORBIDDEN
    if any(p.fullmatch(t) for p in _ALLOWED):
        return OK
    return REVIEW  # incluso MPL-2.0: da rivedere esplicitamente


def _split_top(expr: str, op: str) -> list[str]:
    parts: list[str] = []
    depth, start = 0, 0
    pat = f" {op} "
    i = 0
    while i < len(expr):
        c = expr[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        elif depth == 0 and expr[i : i + len(pat)].upper() == pat:
            parts.append(expr[start:i])
            start = i + len(pat)
            i = start - 1
        i += 1
    parts.append(expr[start:])
    return parts


def _strip_outer(expr: str) -> str:
    expr = expr.strip()
    while expr.startswith("(") and expr.endswith(")"):
        depth = 0
        for i, c in enumerate(expr):
            depth += (c == "(") - (c == ")")
            if depth == 0 and i < len(expr) - 1:
                return expr
        expr = expr[1:-1].strip()
    return expr


def _severity(expr: str) -> int:
    expr = _strip_outer(re.sub(r"\s+", " ", expr))
    # pip-licenses unisce più classifier con ';' (devono valere tutte)
    if ";" in expr:
        return max(_severity(p) for p in expr.split(";") if p.strip())
    ors = _split_top(expr, "OR")
    if len(ors) > 1:
        return min(_severity(p) for p in ors)  # a scelta di chi usa: la migliore
    ands = _split_top(expr, "AND")
    if len(ands) > 1:
        return max(_severity(p) for p in ands)
    return _classify_name(expr)


def _is_reviewed(key: str, reviewed: set[str]) -> bool:
    """`key` e' `eco:nome@versione`; vale anche la forma senza ecosistema `nome@versione`."""
    bare = key.split(":", 1)[1] if ":" in key.split("@", 1)[0] else key
    return key in reviewed or bare in reviewed


def check(licenses: dict[str, str], reviewed: set[str] | None = None) -> list[str]:
    """Restituisce le violazioni (lista vuota = OK) per {pacchetto: licenza}.

    `reviewed`: chiavi `eco:nome@versione` (o `nome@versione`) rivisti a mano. Escludono
    solo l'esito "da rivedere", mai "vietata".
    """
    out: list[str] = []
    for name, lic in sorted(licenses.items()):
        sev = _severity(lic or "")
        if sev == FORBIDDEN:
            out.append(f"{name}: licenza vietata ({lic})")
        elif sev == REVIEW and not _is_reviewed(name, reviewed or set()):
            out.append(f"{name}: licenza da rivedere ({lic or 'assente'})")
    return out


def load_reviewed(path: Path) -> set[str]:
    """File con una chiave per riga (`pip:nome@versione  # motivo`); `#` = commento."""
    keys: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        key = line.split("#", 1)[0].strip()
        if key:
            keys.add(key)
    return keys


def _license_field(pkg: dict[str, Any]) -> str:
    lic = pkg.get("license")
    if lic is None and isinstance(pkg.get("licenses"), list):
        lic = " OR ".join(
            str(x.get("type", x)) if isinstance(x, dict) else str(x) for x in pkg["licenses"]
        )
    if isinstance(lic, dict):
        lic = lic.get("type")
    return str(lic) if lic else "UNKNOWN"


def collect_node(node_modules: Path, lockfile: Path | None = None) -> list[dict[str, str]]:
    """Legge node_modules/*/package.json (e @scope/*). Con lockfile esclude i pacchetti dev."""
    dev: set[str] = set()
    if lockfile is not None:
        packages = json.loads(lockfile.read_text(encoding="utf-8")).get("packages", {})
        dev = {k.removeprefix("node_modules/") for k, v in packages.items() if v.get("dev")}
    result: list[dict[str, str]] = []
    if not node_modules.is_dir():
        return result
    dirs: list[Path] = []
    for d in sorted(node_modules.iterdir()):
        if d.name.startswith("."):
            continue
        dirs.extend(sorted(d.iterdir()) if d.name.startswith("@") and d.is_dir() else [d])
    for d in dirs:
        pj = d / "package.json"
        if not pj.is_file():
            continue
        pkg = json.loads(pj.read_text(encoding="utf-8"))
        name = str(pkg.get("name") or d.name)
        if name in dev:
            continue
        result.append(
            {"name": name, "version": str(pkg.get("version", "")), "license": _license_field(pkg)}
        )
    return result


def collect_python(path: Path) -> list[dict[str, str]]:
    rows = json.loads(path.read_text(encoding="utf-8"))
    return [
        {"name": r["Name"], "version": r.get("Version", ""), "license": r.get("License", "")}
        for r in rows
    ]


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--python-json", type=Path, help="output di `pip-licenses --format=json`")
    ap.add_argument("--node-modules", type=Path, help="cartella frontend/node_modules")
    ap.add_argument("--lockfile", type=Path, help="package-lock.json: esclude le dipendenze dev")
    ap.add_argument("--out", type=Path, help="scrive [{name,version,license}] (es. licenses.json)")
    ap.add_argument("--reviewed", default="", help="eco:nome@versione rivisti (virgola)")
    ap.add_argument("--reviewed-file", type=Path, help="file di revisioni (una chiave per riga)")
    args = ap.parse_args(argv)

    entries: list[dict[str, str]] = []
    keyed: dict[str, str] = {}
    if args.python_json:
        py = collect_python(args.python_json)
        entries += py
        keyed.update({f"pip:{e['name']}@{e['version']}": e["license"] for e in py})
    if args.node_modules:
        nd = collect_node(args.node_modules, args.lockfile)
        entries += nd
        keyed.update({f"npm:{e['name']}@{e['version']}": e["license"] for e in nd})
    reviewed = {n.strip() for n in args.reviewed.split(",") if n.strip()}
    if args.reviewed_file:
        reviewed |= load_reviewed(args.reviewed_file)
    violations = check(keyed, reviewed)
    if args.out:
        args.out.write_text(
            json.dumps(sorted(entries, key=lambda e: (e["name"], e["version"])), indent=2) + "\n",
            encoding="utf-8",
        )
    for v in violations:
        print(v, file=sys.stderr)
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
