# SPDX-License-Identifier: Apache-2.0
"""Verifica che `backend/core` sia identico a un riferimento git (branch di hackathon).

Uso: python scripts/check_core_unchanged.py <riferimento> [--repo DIR]
Exit 0 = invariato; 1 = diverso (stampa i file); 2 = errore (riferimento inesistente, non e' un repo).
Regola di flusso: nei branch di hackathon il core non si modifica; i miglioramenti generici si fanno
nel branch base e poi si fa merge.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

CORE_PATH = "backend/core"
_REF_RE = re.compile(r"^[A-Za-z0-9._/-]{1,200}$")


def check(ref: str, repo: Path) -> tuple[int, list[str]]:
    """Ritorna (exit_code, file_diversi)."""
    if not _REF_RE.fullmatch(ref) or ref.startswith("-"):
        return 2, [f"riferimento non valido: {ref!r}"]
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "diff", "--name-only", ref, "--", CORE_PATH],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 2, [f"git non eseguibile: {type(exc).__name__}"]
    if proc.returncode != 0:
        return 2, [proc.stderr.strip()[:200] or "git diff fallito"]
    changed = [line for line in proc.stdout.splitlines() if line.strip()]
    return (1, changed) if changed else (0, [])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ref", help="branch/commit di riferimento (la base generica)")
    parser.add_argument("--repo", default=".", help="cartella del repository")
    args = parser.parse_args(argv)
    code, files = check(args.ref, Path(args.repo))
    if code == 0:
        print(f"{CORE_PATH}: invariato rispetto a {args.ref}")
    elif code == 1:
        print(f"{CORE_PATH}: MODIFICATO rispetto a {args.ref}:", *files, sep="\n  ")
    else:
        print("errore:", *files, file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
