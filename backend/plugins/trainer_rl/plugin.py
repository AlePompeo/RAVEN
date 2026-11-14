# SPDX-License-Identifier: Apache-2.0
"""Trainer RL (ARS lineare) per il servo. Gira solo nel subprocess del TrainerRunner.

Salva un CANDIDATO nel registro; la promozione resta un atto umano separato (spec 13.1).
"""

from collections.abc import Mapping
from typing import Any

from backend.core.manifest import Manifest
from backend.ml.registry import FileModelRegistry, default_registry_dir

# nome -> (minimo, massimo): tetti che limitano tempo e memoria di un job
BOUNDS: dict[str, tuple[int, int]] = {
    "seed": (0, 2**31 - 1),
    "iterations": (1, 200),
    "directions": (2, 64),
    "n_eval": (300, 1000),
}
DEFAULTS = {"seed": 0, "iterations": 40, "directions": 16, "n_eval": 300}


def _int(config: Mapping[str, Any], name: str) -> int:
    v = config.get(name, DEFAULTS[name])
    lo, hi = BOUNDS[name]
    if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
        raise ValueError(f"{name}: intero in [{lo}, {hi}] richiesto")
    return v


class RLTrainer:
    def __init__(self, manifest: Manifest | None) -> None:
        self._manifest = manifest

    def fit(self, dataset_ref: str, config: Mapping[str, Any]) -> Mapping[str, Any]:
        if set(config) - set(BOUNDS) - {"profile"}:
            raise ValueError("parametri sconosciuti")
        args: dict[str, Any] = {name: _int(config, name) for name in BOUNDS}
        from backend.ml.rl.env_adapter import PROFILES
        from backend.ml.rl.training import DEFAULT_PROFILE, train_candidate

        profile = config.get("profile", DEFAULT_PROFILE)
        if not isinstance(profile, str) or profile not in PROFILES:
            raise ValueError("profile: nome di profilo noto richiesto")
        version, metrics = train_candidate(
            FileModelRegistry(default_registry_dir()), profile=profile, **args
        )
        return {"metrics": metrics, "model_version": version}
