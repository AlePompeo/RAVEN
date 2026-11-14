# SPDX-License-Identifier: Apache-2.0
"""Trainer dell'esempio predictor_baseline. Gira solo nel subprocess del TrainerRunner.

Salva un CANDIDATO nel registro; la promozione resta un atto umano separato (spec 13.1).
"""

from collections.abc import Mapping
from typing import Any

from backend.core.manifest import Manifest
from backend.ml.registry import FileModelRegistry, default_registry_dir

# nome -> (minimo, massimo): tetti che limitano tempo e memoria di un job
BOUNDS: dict[str, tuple[int, int]] = {
    "seed": (0, 2**31 - 1),
    "n_train": (20, 20_000),
    "n_estimators": (1, 500),
    "max_depth": (1, 6),
}


def _int(config: Mapping[str, Any], name: str, default: int) -> int:
    v = config.get(name, default)
    lo, hi = BOUNDS[name]
    if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
        raise ValueError(f"{name}: intero in [{lo}, {hi}] richiesto")
    return v


class BaselineTrainer:
    def __init__(self, manifest: Manifest | None) -> None:
        self._manifest = manifest

    def fit(self, dataset_ref: str, config: Mapping[str, Any]) -> Mapping[str, Any]:
        unknown = set(config) - set(BOUNDS)
        if unknown:
            raise ValueError("parametri sconosciuti")
        seed = _int(config, "seed", 0)
        n_train = _int(config, "n_train", 2000)
        n_estimators = _int(config, "n_estimators", 200)
        max_depth = _int(config, "max_depth", 3)
        from backend.plugins.predictor_baseline.training import train_candidate

        version, metrics = train_candidate(
            FileModelRegistry(default_registry_dir()),
            seed=seed,
            n_train=n_train,
            n_estimators=n_estimators,
            max_depth=max_depth,
        )
        return {"metrics": metrics, "model_version": version}
