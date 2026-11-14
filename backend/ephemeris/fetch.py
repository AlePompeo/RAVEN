# SPDX-License-Identifier: Apache-2.0
"""`python -m backend.ephemeris.fetch`: scarica e verifica i kernel NAIF in EPHEMERIS_DIR.

Con `--write-lock` (solo per aggiornare i kernel) ricalcola dimensione e SHA-256 dei file gia'
presenti nella cartella e riscrive `kernels.lock.json`: rivedere sempre il diff prima del commit.
"""

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime

from backend.ephemeris import kernels as k


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write-lock", action="store_true", help="rigenera il lock dai file presenti")
    ap.add_argument("--check", action="store_true", help="solo verifica, nessun download")
    args = ap.parse_args(argv)
    directory = k.ephemeris_dir()
    specs = k.load_lock()
    if args.write_lock:
        today = datetime.now(UTC).date().isoformat()
        raw = json.loads(k.LOCK_PATH.read_text(encoding="utf-8"))
        for entry, s in zip(raw["kernels"], specs, strict=True):
            p = directory / s.name
            entry.update(size=p.stat().st_size, sha256=k.sha256_file(p), retrieved=today)
        k.LOCK_PATH.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
        print(f"lock riscritto da {directory}")
        return 0
    if args.check:
        bad = k.problems(directory, specs)
        print("\n".join(bad) if bad else f"kernel OK in {directory}")
        return 1 if bad else 0
    try:
        # the kernels are independent files: fetch them in parallel and say how many are done
        todo = [s for s in specs if k.problems(directory, [s])]
        for s in specs:
            if s not in todo:
                print(f"gia presente: {directory / s.name} ({s.size} B)", flush=True)
        with ThreadPoolExecutor(max_workers=max(1, min(4, len(todo)))) as pool:
            futures = {pool.submit(k.fetch_all, directory, [s]): s for s in todo}
            for i, fut in enumerate(as_completed(futures), 1):
                s = futures[fut]
                fut.result()
                print(f"scaricato: {directory / s.name} ({s.size} B)", flush=True)
                print(f"PROGRESS {i} {len(todo)}", flush=True)
    except (k.KernelIntegrityError, OSError) as e:
        print(f"errore: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
