# SPDX-License-Identifier: Apache-2.0
"""Addestramento e valutazione del predittore del margine di collegamento (richiede extra [ml])."""

import importlib.metadata
from typing import Any

import numpy as np
import onnxruntime as ort  # type: ignore[import-untyped,import-not-found,unused-ignore]
from numpy.typing import NDArray
from skl2onnx import to_onnx  # type: ignore[import-untyped,import-not-found,unused-ignore]
from sklearn.ensemble import GradientBoostingRegressor  # type: ignore[import-untyped,import-not-found,unused-ignore]
from sklearn.linear_model import LinearRegression  # type: ignore[import-untyped,import-not-found,unused-ignore]

from backend.core.ports import ModelRegistry
from backend.plugins.predictor_baseline import data

# Margine dichiarato: l'MSE del modello deve essere almeno il 25% sotto quello del miglior
# baseline (media o regressione lineare) sul test set fisso: skill = 1 - MSE_modello/MSE_baseline.
MIN_SKILL = 0.25
SKILL_KEY = "skill_vs_baseline"
LIBS = ("numpy", "scikit-learn", "skl2onnx", "onnxruntime")


def library_versions() -> dict[str, str]:
    return {name: importlib.metadata.version(name) for name in LIBS}


def make_session(blob: bytes) -> ort.InferenceSession:
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 1
    opts.inter_op_num_threads = 1
    return ort.InferenceSession(blob, sess_options=opts, providers=["CPUExecutionProvider"])


def onnx_predict(session: ort.InferenceSession, x: NDArray[np.float64]) -> NDArray[np.float64]:
    name = session.get_inputs()[0].name
    out = session.run(None, {name: np.asarray(x, dtype=np.float32)})[0]
    return np.asarray(out, dtype=np.float64).ravel()


def _rmse(pred: NDArray[np.float64], y: NDArray[np.float64]) -> float:
    return float(np.sqrt(np.mean((pred - y) ** 2)))


def evaluate(blob: bytes, x_train: Any, y_train: Any) -> dict[str, float]:
    """Metriche sul test set fisso, calcolate sul modello ONNX effettivamente servito."""
    x_test, y_test = data.fixed_test_set()
    model_rmse = _rmse(onnx_predict(make_session(blob), x_test), y_test)
    mean_rmse = _rmse(np.full_like(y_test, float(np.mean(y_train))), y_test)
    linear = LinearRegression().fit(x_train, y_train)
    linear_rmse = _rmse(linear.predict(x_test), y_test)
    base = min(mean_rmse, linear_rmse)
    return {
        "rmse_db": model_rmse,
        "baseline_mean_rmse_db": mean_rmse,
        "baseline_linear_rmse_db": linear_rmse,
        "baseline_rmse_db": base,
        SKILL_KEY: 1.0 - (model_rmse / base) ** 2,
    }


def _promoted_skill(registry: ModelRegistry) -> float | None:
    v = registry.promoted_version()
    if v is None:
        return None
    _, card = registry.load(v)
    skill = card["metrics"].get(SKILL_KEY)
    return float(skill) if skill is not None else None


def train_candidate(
    registry: ModelRegistry,
    *,
    seed: int,
    n_train: int = 2000,
    n_estimators: int = 200,
    max_depth: int = 3,
) -> tuple[str, dict[str, float]]:
    """Addestra, esporta in ONNX e salva un CANDIDATO. Non promuove mai.

    La soglia nella card e' max(MIN_SKILL, skill del modello attualmente promosso): un candidato
    peggiore del promosso (regressione) non supera il cancello di promozione del registro.
    """
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("seed: intero >= 0 richiesto")
    if seed == data.FIXED_TEST_SEED:  # riprodurrebbe i campioni del test set fisso
        raise ValueError("seed riservato al test set fisso")
    x, y = data.make_dataset(n_train, seed)
    model = GradientBoostingRegressor(
        n_estimators=n_estimators, max_depth=max_depth, random_state=seed
    ).fit(x, y)
    blob = to_onnx(model, x[:1].astype(np.float32)).SerializeToString()
    metrics = evaluate(blob, x, y)
    # Dominio di addestramento: il servizio rifiuta ingressi oltre [min*0.9, max*1.1].
    for i, name in enumerate(data.FEATURES):
        metrics[f"train_{name}_min"] = float(x[:, i].min())
        metrics[f"train_{name}_max"] = float(x[:, i].max())
    promoted = _promoted_skill(registry)
    threshold = max(MIN_SKILL, promoted) if promoted is not None else MIN_SKILL
    version = registry.save(
        blob,
        {
            "seed": seed,
            "dataset_sha256": data.sha256_of(x, y),
            "library_versions": library_versions(),
            "metrics": metrics,
            "threshold": {SKILL_KEY: threshold},
            "format": "onnx",
        },
    )
    return version, metrics
