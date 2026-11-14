# SPDX-License-Identifier: Apache-2.0
"""MLP minimo in PyTorch (CPU) per il margine di collegamento, export ONNX (extra [dl]).

Stessi dati sintetici dell'esempio `predictor_baseline` (origine: generati da seme, licenza
Apache-2.0). Il modello include la standardizzazione degli ingressi (statistiche del training come
buffer; anche l'uscita e' de-standardizzata nel grafo): l'ONNX accetta le feature grezze `[N, 2]` = (power_w, distance_km).
Importare questo modulo senza torch solleva ImportError: il plugin di servizio NON lo importa.
"""

import importlib.metadata
import io
import math
import warnings

import numpy as np
import torch
from numpy.typing import NDArray

from backend.core.ports import ModelRegistry
from backend.plugins.predictor_baseline import data  # solo numpy: nessuna dipendenza da sklearn

MIN_SKILL = 0.25  # stesso margine dichiarato del baseline: 1 - MSE_modello / MSE_baseline
SKILL_KEY = "skill_vs_baseline"
LIBS = ("numpy", "torch", "onnx", "onnxruntime")
ONNX_TOLERANCE = 1e-4  # |ONNX - PyTorch| massimo ammesso (float32; misurato ~1e-6)
INPUT_NAME, OUTPUT_NAME = "features", "link_margin_db"


class Net(torch.nn.Module):
    mean: torch.Tensor
    std: torch.Tensor

    def __init__(
        self,
        mean: NDArray[np.float64],
        std: NDArray[np.float64],
        y_mean: float,
        y_std: float,
    ) -> None:
        super().__init__()
        self.y_mean = y_mean  # costanti Python: finiscono nel grafo ONNX come costanti
        self.y_std = y_std
        self.register_buffer("mean", torch.tensor(mean, dtype=torch.float32))
        self.register_buffer("std", torch.tensor(std, dtype=torch.float32))
        self.body = torch.nn.Sequential(
            torch.nn.Linear(2, 16), torch.nn.Tanh(), torch.nn.Linear(16, 16),
            torch.nn.Tanh(), torch.nn.Linear(16, 1),
        )  # fmt: skip

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.body((x - self.mean) / self.std) * self.y_std + self.y_mean  # type: ignore[no-any-return]


def library_versions() -> dict[str, str]:
    return {name: importlib.metadata.version(name) for name in LIBS}


def check_train_seed(seed: int) -> None:
    """Il test set fisso e' `make_dataset(N_TEST, FIXED_TEST_SEED)`: usare quel seme per il
    training riprodurrebbe gli stessi campioni (perdita di dati nel test)."""
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("seed: intero >= 0 richiesto")
    if seed == data.FIXED_TEST_SEED:
        raise ValueError("seed riservato al test set fisso")


def fit(seed: int, n_train: int = 2000, epochs: int = 400) -> tuple[Net, NDArray[np.float64]]:
    """Addestra full-batch con Adam; deterministico a parita' di seme su CPU (1 thread)."""
    check_train_seed(seed)
    torch.manual_seed(seed)
    x, y = data.make_dataset(n_train, seed)
    net = Net(x.mean(axis=0), x.std(axis=0), float(y.mean()), float(y.std()))
    xt = torch.tensor(x, dtype=torch.float32)
    yt = torch.tensor(y, dtype=torch.float32).unsqueeze(1)
    opt = torch.optim.Adam(net.parameters(), lr=0.02)
    for _ in range(epochs):
        opt.zero_grad()
        loss = torch.mean((net(xt) - yt) ** 2)
        loss.backward()  # type: ignore[no-untyped-call]
        opt.step()
    if not math.isfinite(float(loss.detach())):
        raise ValueError("addestramento divergente")
    return net.eval(), y


def export_onnx(net: Net) -> bytes:
    buf = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        torch.onnx.export(
            net,
            (torch.zeros(1, 2),),
            buf,  # type: ignore[arg-type]
            input_names=[INPUT_NAME],
            output_names=[OUTPUT_NAME],
            dynamic_axes={INPUT_NAME: {0: "N"}},
            dynamo=True,
        )
    return buf.getvalue()


def torch_predict(net: Net, x: NDArray[np.float64]) -> NDArray[np.float64]:
    with torch.no_grad():
        out = net(torch.tensor(x, dtype=torch.float32))
    return np.asarray(out.numpy(), dtype=np.float64).ravel()


def _rmse(pred: NDArray[np.float64], y: NDArray[np.float64]) -> float:
    return float(np.sqrt(np.mean((pred - y) ** 2)))


def evaluate(
    blob: bytes, x_train: NDArray[np.float64], y_train: NDArray[np.float64]
) -> dict[str, float]:
    """Metriche sul test set FISSO, calcolate sull'ONNX servito (via onnxruntime)."""
    from backend.plugins.predictor_nn.serving import make_session, onnx_predict

    x_test, y_test = data.fixed_test_set()
    model_rmse = _rmse(onnx_predict(make_session(blob), x_test), y_test)
    mean_rmse = _rmse(np.full_like(y_test, float(np.mean(y_train))), y_test)
    design = np.column_stack([x_train, np.ones(len(x_train))])
    coef, *_ = np.linalg.lstsq(design, y_train, rcond=None)
    linear_rmse = _rmse(np.column_stack([x_test, np.ones(len(x_test))]) @ coef, y_test)
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
    s = card["metrics"].get(SKILL_KEY)
    return float(s) if s is not None else None


def train_candidate(
    registry: ModelRegistry, *, seed: int, n_train: int = 2000, epochs: int = 400
) -> tuple[str, dict[str, float]]:
    """Addestra, esporta in ONNX, verifica ONNX == PyTorch e salva un CANDIDATO (mai promosso)."""
    from backend.plugins.predictor_nn.serving import make_session, onnx_predict

    net, y = fit(seed, n_train, epochs)  # fit rifiuta il seme del test set fisso
    x, _ = data.make_dataset(n_train, seed)
    blob = export_onnx(net)
    x_test, _ = data.fixed_test_set()
    diff = float(
        np.max(np.abs(onnx_predict(make_session(blob), x_test) - torch_predict(net, x_test)))
    )
    if not diff <= ONNX_TOLERANCE:
        raise ValueError("export ONNX non coincide con PyTorch")
    metrics = evaluate(blob, x, y)
    metrics["onnx_vs_torch_max_abs_diff"] = diff
    # Dominio di addestramento: il servizio rifiuta ingressi oltre [min, max] + margine 10%.
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
