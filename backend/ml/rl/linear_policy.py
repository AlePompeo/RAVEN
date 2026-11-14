# SPDX-License-Identifier: Apache-2.0
"""Politica lineare, ricerca casuale aumentata (ARS) e export ONNX. Richiede numpy (+ onnx).

Alternativa a Stable-Baselines3 (extra [rl]) che non richiede torch: `a = clip(W . obs, -1, 1)`.
ARS: Mania, Guy, Recht (2018), "Simple random search provides a competitive approach to
reinforcement learning". Versione base (V1-t): perturbazioni simmetriche, top-b direzioni,
passo normalizzato dalla deviazione standard dei ritorni.
"""

import hashlib
import json
from collections.abc import Callable, Sequence
from typing import Any

import numpy as np
from numpy.typing import NDArray

from backend.ml.rl.env_adapter import SimulationEnv

Policy = Callable[[Sequence[float]], float]
TRAIN_SEED_BASE = 1000  # semi di addestramento: [1000, 1000 + n)
EVAL_SEED_BASE = 1_000_000  # semi di valutazione di base (training esclude questo intervallo)
ONNX_TOLERANCE = 1e-4  # |ONNX float32 - numpy float64| massimo sull'azione (in [-1, 1])
BASELINE_P_GAIN = 2.0  # P sull'errore normalizzato: regolatore scritto a mano, non ottimizzato


def zero_policy(_: Sequence[float]) -> float:
    return 0.0


def p_controller(obs: Sequence[float]) -> float:
    return max(-1.0, min(1.0, BASELINE_P_GAIN * obs[0]))


def linear(w: NDArray[np.float64]) -> Policy:
    wl = [float(x) for x in w]

    def pol(obs: Sequence[float]) -> float:
        return max(-1.0, min(1.0, sum(a * b for a, b in zip(wl, obs, strict=True))))

    return pol


def episode_return(env: SimulationEnv, policy: Policy, seed: int) -> float:
    obs, _ = env.reset(seed=seed)
    total, done = 0.0, False
    while not done:
        obs, r, term, trunc, _ = env.step([policy(obs)])
        total += r
        done = term or trunc
    return total


def mean_return(env: SimulationEnv, policy: Policy, seeds: Sequence[int]) -> float:
    return float(np.mean([episode_return(env, policy, s) for s in seeds]))


def eval_seeds(n: int) -> list[int]:
    return [EVAL_SEED_BASE + i for i in range(n)]


def ars_train(
    env: SimulationEnv,
    *,
    seed: int,
    iterations: int,
    directions: int,
    top: int | None = None,
    step_size: float = 0.1,
    noise_std: float = 0.3,
    episodes_per_eval: int = 3,
    init: NDArray[np.float64] | None = None,
    delta_scale: Sequence[float] | None = None,
) -> NDArray[np.float64]:
    """Addestra W (3,) in modo deterministico dato `seed`; episodi su semi di TRAINING.

    `init`: pesi iniziali (default zeri; un avvio a caldo da un baseline e' lecito se il baseline
    e' sintonizzato solo su semi di training). `delta_scale`: scala per componente delle
    perturbazioni (i guadagni di un regolatore ad alto guadagno stanno su scale diverse).
    """
    rng = np.random.default_rng(seed)
    dim = env.observation_space.shape[0]
    top = min(top or max(1, directions // 2), directions)
    w = np.zeros(dim) if init is None else np.asarray(init, dtype=np.float64).copy()
    if w.shape != (dim,) or not np.all(np.isfinite(w)):
        raise ValueError("init: vettore finito di dimensione corretta richiesto")
    scale = np.ones(dim) if delta_scale is None else np.asarray(delta_scale, dtype=np.float64)
    for _ in range(iterations):
        deltas = rng.standard_normal((directions, dim)) * scale
        # stessi semi di episodio per +/-: riduce la varianza della differenza
        eps = [TRAIN_SEED_BASE + int(s) for s in rng.integers(0, 5000, size=episodes_per_eval)]
        plus = np.array([mean_return(env, linear(w + noise_std * d), eps) for d in deltas])
        minus = np.array([mean_return(env, linear(w - noise_std * d), eps) for d in deltas])
        best = np.argsort(-np.maximum(plus, minus))[:top]
        sigma = float(np.std(np.concatenate([plus[best], minus[best]]))) or 1.0
        w = w + step_size / (top * sigma) * ((plus[best] - minus[best]) @ deltas[best])
    return w


def policy_to_onnx(w: NDArray[np.float64]) -> bytes:
    """Grafo ONNX: `action = Clip(obs @ W^T, -1, 1)`; ingresso `obs` [N, d], uscita `action` [N, 1]."""
    import onnx
    from onnx import TensorProto, helper, numpy_helper

    d = int(w.shape[0])
    nodes = [
        helper.make_node("MatMul", ["obs", "w"], ["pre"]),
        helper.make_node("Clip", ["pre", "lo", "hi"], ["action"]),
    ]
    inits = [
        numpy_helper.from_array(np.asarray(w, dtype=np.float32).reshape(d, 1), "w"),
        numpy_helper.from_array(np.array(-1.0, dtype=np.float32), "lo"),
        numpy_helper.from_array(np.array(1.0, dtype=np.float32), "hi"),
    ]
    graph = helper.make_graph(
        nodes,
        "linear_policy",
        [helper.make_tensor_value_info("obs", TensorProto.FLOAT, ["N", d])],
        [helper.make_tensor_value_info("action", TensorProto.FLOAT, ["N", 1])],
        inits,
    )
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    model.ir_version = 8
    onnx.checker.check_model(model)
    return bytes(model.SerializeToString())


def check_onnx_matches(w: NDArray[np.float64], blob: bytes, n: int = 200) -> float:
    """Verifica ONNX (float32) == politica numpy (float64) su `n` osservazioni casuali."""
    rng = np.random.default_rng(0)
    onnx_p, np_p = onnx_policy(blob), linear(w)
    diff = max(
        abs(onnx_p(o.tolist()) - np_p(o.tolist())) for o in rng.uniform(-1, 1, size=(n, len(w)))
    )
    if not diff <= ONNX_TOLERANCE:
        raise ValueError("export ONNX non coincide con la politica numpy")
    return float(diff)


def onnx_policy(blob: bytes) -> Policy:
    """Politica servita via onnxruntime (1 thread, CPU): e' quella valutata e promossa."""
    import onnxruntime as ort  # type: ignore[import-untyped,import-not-found,unused-ignore]

    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 1
    opts.inter_op_num_threads = 1
    sess = ort.InferenceSession(blob, sess_options=opts, providers=["CPUExecutionProvider"])

    def pol(obs: Sequence[float]) -> float:
        out = sess.run(None, {"obs": np.asarray([obs], dtype=np.float32)})[0]
        return float(out[0, 0])

    return pol


def config_sha256(env_kwargs: dict[str, Any], seeds: Sequence[int]) -> str:
    """Impronta della 'sorgente dati' RL: configurazione dell'ambiente + semi di valutazione."""
    blob = json.dumps({"env": env_kwargs, "eval_seeds": list(seeds)}, sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()
