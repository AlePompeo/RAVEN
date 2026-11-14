# SPDX-License-Identifier: Apache-2.0
"""Addestramento di una politica ARS sul servo e salvataggio di un CANDIDATO nel registro.

Gate di promozione (ogni metrica in `threshold` deve essere >= alla sua soglia):

* baseline = migliore controllore di una griglia P/PD (`evaluation.PD_GRID`) sintonizzato sui semi
  di TRAINING; vede errore e velocita', cioe' la stessa informazione della politica;
* guadagno = (R_politica - R_baseline) / |R_baseline| su `n_eval >= 300` episodi APPAIATI (stessi
  semi per politica e baseline); IC bootstrap appaiato al 95% (2000 ricampioni, seme fisso);
* soglie: `gain_ci_low >= 0.15` (impianto nominale) e `gain_ci_low_perturbed >= 0.15` (tau e rate
  +-20%, semi distinti). Si usa il limite INFERIORE dell'IC, non la media.

Rischio "maledizione del vincitore": rivalutare piu' candidati su un insieme di valutazione FISSO
seleziona il candidato che per caso ci va meglio e sovrastima il guadagno. Per questo ogni
candidato ha un blocco di semi di valutazione NUOVO, derivato dal seme registrato
(`eval_seed_base(seed)`, salvato nella card come metrica `eval_seed_base`). Non elimina il rischio
se si provano molti semi e si tiene il migliore: serve comunque un test finale indipendente.

Esito misurato su questo impianto: un PD sintonizzato e' quasi ottimo; ARS (avviato a caldo dal PD)
lo eguaglia (guadagno ~ 0) e NON supera la soglia 0.15: il candidato di esempio e' correttamente
non promuovibile. Resta come prova del cancello, non come dimostrazione di superiorita' dell'RL.
"""

import importlib.metadata
from collections.abc import Mapping
from typing import Any

import numpy as np

from backend.core.ports import ModelRegistry
from backend.ml.rl import evaluation as ev
from backend.ml.rl import linear_policy as lp
from backend.ml.rl.env_adapter import SimulationEnv, profile_kwargs

MIN_GAIN = 0.15
CI_KEY = "gain_ci_low"
CI_PERT_KEY = "gain_ci_low_perturbed"
MIN_EVAL = 300
LIBS = ("numpy", "onnx", "onnxruntime")
DEFAULT_PROFILE = "servo_realistic"
_EVAL_SALT = 0xE7A1


def library_versions() -> dict[str, str]:
    return {name: importlib.metadata.version(name) for name in LIBS}


def eval_seed_base(seed: int) -> int:
    """Inizio del blocco di semi di valutazione di questo candidato (>= EVAL_SEED_BASE)."""
    off = int(np.random.default_rng([seed, _EVAL_SALT]).integers(0, 2**31 - 1))
    return lp.EVAL_SEED_BASE + off


def evaluate(
    blob: bytes,
    *,
    baseline: lp.Policy,
    seed_base: int,
    n_eval: int = MIN_EVAL,
    env_kwargs: Mapping[str, Any] | None = None,
) -> dict[str, float]:
    """Metriche del modello ONNX servito contro `baseline`, appaiate sugli stessi semi."""
    if n_eval < MIN_EVAL:
        raise ValueError(f"n_eval >= {MIN_EVAL} richiesto")
    policy = lp.onnx_policy(blob)
    nominal = list(range(seed_base, seed_base + n_eval))
    pert = [s + ev.PERTURBED_OFFSET for s in nominal]
    kw = dict(env_kwargs or {})
    nom_env = SimulationEnv(**kw)
    r_pol = ev.episode_returns(lambda s: nom_env, policy, nominal)
    r_base = ev.episode_returns(lambda s: nom_env, baseline, nominal)
    r_p2 = ev.episode_returns(lambda s: nom_env, lp.p_controller, nominal)
    rp_pol = ev.episode_returns(lambda s: ev.perturbed_env(s, kw), policy, pert)
    rp_base = ev.episode_returns(lambda s: ev.perturbed_env(s, kw), baseline, pert)
    mean, low = ev.bootstrap_gain(r_pol, r_base)
    pmean, plow = ev.bootstrap_gain(rp_pol, rp_base)
    return {
        "mean_return": float(r_pol.mean()),
        "baseline_return": float(r_base.mean()),
        "gain_mean": mean,
        CI_KEY: low,
        "mean_return_perturbed": float(rp_pol.mean()),
        "baseline_return_perturbed": float(rp_base.mean()),
        "gain_mean_perturbed": pmean,
        CI_PERT_KEY: plow,
        "gain_mean_vs_untuned_p": ev.gain(r_pol, r_p2),
        "n_eval": float(n_eval),
        "eval_seed_base": float(seed_base),
    }


def _promoted_ci(registry: ModelRegistry) -> float | None:
    v = registry.promoted_version()
    if v is None:
        return None
    _, card = registry.load(v)
    g = card["metrics"].get(CI_KEY)
    return float(g) if g is not None else None


def train_candidate(
    registry: ModelRegistry,
    *,
    seed: int,
    iterations: int = 40,
    directions: int = 16,
    n_eval: int = MIN_EVAL,
    profile: str = DEFAULT_PROFILE,
) -> tuple[str, dict[str, float]]:
    """Sintonizza il baseline sui semi di training, addestra ARS (avvio a caldo dal PD, 20 episodi
    di training per valutazione), esporta in ONNX e salva un CANDIDATO. Non promuove mai.
    Tempo misurato: ~3-4 s su CPU."""
    env_kwargs = profile_kwargs(profile)
    env = SimulationEnv(**env_kwargs)
    baseline, kp, kd = ev.tune_pd(env, ev.tuning_seeds())
    w = lp.ars_train(
        env,
        seed=seed,
        iterations=iterations,
        directions=directions,
        step_size=0.5,
        noise_std=0.5,
        episodes_per_eval=ev.N_TUNING,
        init=np.array([kp, kd, 0.0]),
        delta_scale=(10.0, 1.0, 1.0),
    )
    if not np.all(np.isfinite(w)):
        raise ValueError("pesi non finiti")
    blob = lp.policy_to_onnx(w)
    diff = lp.check_onnx_matches(w, blob)
    base = eval_seed_base(seed)
    metrics = evaluate(
        blob, baseline=baseline, seed_base=base, n_eval=n_eval, env_kwargs=env_kwargs
    )
    metrics.update(baseline_kp=kp, baseline_kd=kd, onnx_vs_numpy_max_abs_diff=diff)
    for name in ("deadband_deg", "stiction_dps", "backlash_deg"):  # profilo registrato nella card
        metrics[f"profile_{name}"] = float(env_kwargs.get(name, 0.0))
    promoted = _promoted_ci(registry)
    threshold = {
        CI_KEY: max(MIN_GAIN, promoted) if promoted is not None else MIN_GAIN,
        CI_PERT_KEY: MIN_GAIN,
    }
    nominal = list(range(base, base + n_eval))
    seeds = nominal + [s + ev.PERTURBED_OFFSET for s in nominal]
    version = registry.save(
        blob,
        {
            "seed": seed,
            "dataset_sha256": lp.config_sha256({"profile": profile, **env_kwargs}, seeds),
            "library_versions": library_versions(),
            "metrics": metrics,
            "threshold": threshold,
            "format": "onnx",
        },
    )
    return version, metrics
