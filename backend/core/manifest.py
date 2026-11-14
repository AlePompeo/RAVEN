# SPDX-License-Identifier: Apache-2.0
import math
import tomllib
from dataclasses import dataclass
from pathlib import Path

from backend.core.errors import ManifestError

KINDS = {
    "data_source",
    "simulation",
    "llm",
    "telemetry",
    "firmware",
    "estimator",
    "model",
    "trainer",
    "environment",
}
REQUIRED = ("id", "kind", "version", "entry", "license")


@dataclass(frozen=True)
class Manifest:
    id: str
    kind: str
    version: str
    entry: str
    license: str
    terms_url: str
    timeout_s: float
    root: Path


def load_manifest(path: Path) -> Manifest:
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError, UnicodeDecodeError) as e:
        raise ManifestError(f"{path}: {e}") from e
    missing = [k for k in REQUIRED if k not in data]
    if missing:
        raise ManifestError(f"{path}: campi mancanti {missing}")
    for k in REQUIRED:
        if not isinstance(data[k], str) or not data[k].strip():
            raise ManifestError(f"{path}: {k} deve essere una stringa non vuota")
    try:
        timeout_s = float(data.get("timeout_s", 30.0))
    except (TypeError, ValueError) as e:
        raise ManifestError(f"{path}: timeout_s non valido: {e}") from e
    if not math.isfinite(timeout_s) or timeout_s <= 0:
        raise ManifestError(f"{path}: timeout_s deve essere finito e > 0")
    if data["kind"] not in KINDS:
        raise ManifestError(f"{path}: kind non valido {data['kind']!r}")
    if data["kind"] in ("data_source", "llm") and not data.get("terms_url"):
        raise ManifestError(f"{path}: terms_url obbligatorio per {data['kind']}")
    return Manifest(
        data["id"],
        data["kind"],
        data["version"],
        data["entry"],
        data["license"],
        data.get("terms_url", ""),
        timeout_s,
        path.parent,
    )
