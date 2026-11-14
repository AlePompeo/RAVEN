# SPDX-License-Identifier: Apache-2.0
"""Punto d'ingresso del subprocess di addestramento: `python -I -c <boot> <root> backend.ml.worker
<manifest.toml>`. Legge `{"trainer", "config"}` da stdin e stampa una riga JSON di risultato.

Nessun dettaglio d'errore va su stdout: il runner non lo mostra comunque; stderr e' solo log.
"""

import importlib
import json
import sys
from pathlib import Path
from typing import Any

from backend.core.manifest import load_manifest

PLUGIN_PACKAGE = "backend.plugins."
MAX_SPEC_BYTES = 16 * 1024


def run(manifest_path: Path, raw_spec: bytes) -> dict[str, Any]:
    spec = json.loads(raw_spec)
    config = spec["config"]
    if not isinstance(config, dict):
        raise TypeError("config deve essere un oggetto")
    manifest = load_manifest(manifest_path)
    if manifest.kind != "trainer":
        raise ValueError("il manifest non e' di tipo trainer")
    scheme, _, rest = manifest.entry.partition(":")
    module_name, _, cls_name = rest.partition(":")
    if scheme != "python" or not module_name.startswith(PLUGIN_PACKAGE) or not cls_name:
        raise ValueError("entry del trainer non ammesso")
    trainer = getattr(importlib.import_module(module_name), cls_name)(manifest)
    result = trainer.fit("", config)
    return {"metrics": result["metrics"], "model_version": result.get("model_version")}


def main(argv: list[str]) -> int:
    if len(argv) < 2:  # via boot: argv = [-c, root, modulo, manifest]
        return 2
    raw = sys.stdin.buffer.read(MAX_SPEC_BYTES + 1)
    if len(raw) > MAX_SPEC_BYTES:
        return 2
    out = run(Path(argv[-1]), raw)
    sys.stdout.write(json.dumps(out, allow_nan=False) + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
