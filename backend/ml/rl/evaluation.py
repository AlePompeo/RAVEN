# SPDX-License-Identifier: Apache-2.0
"""Valutazione appaiata: baseline PD sintonizzato, impianto perturbato, bootstrap del guadagno.

Cosa e' "tenuto fuori" (e cosa no): i semi di valutazione producono setpoint e rumore del sensore
DIVERSI da quelli di training, ma sullo stesso impianto nominale e con la stessa distribuzione.
L'insieme perturbato cambia anche la fisica (tau e rate +-20%): e' una misura di robustezza a una
perturbazione dichiarata, non di generalizzazione a un impianto reale.
"""

import itertools
import random
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import numpy as np
from numpy.typing import NDArray

from backend.ml.rl import linear_policy as lp
from backend.ml.rl.env_adapter import SimulationEnv

# Griglia P/PD (kp sull'errore normalizzato, kd sulla velocita' normalizzata; kd=0 e' un P).
# Il bordo superiore (150) non e' mai il migliore sui semi di training (verificato in test).
PD_GRID: tuple[tuple[float, float], ...] = tuple(
    itertools.product(
        (2.0, 4.0, 8.0, 15.0, 30.0, 45.0, 60.0, 90.0, 150.0),
        (-6.0, -4.0, -3.0, -2.0, -1.5, -1.0, -0.5, 0.0),
    )
)
N_TUNING = 20  # semi di training usati per sintonizzare il baseline
PERTURBATION = 0.2  # +-20% su tau e rate
NOMINAL_TAU_S = 0.3
NOMINAL_RATE_DPS = 90.0
PERTURBED_OFFSET = 1_000_000  # blocco di semi perturbati = blocco nominale + offset
BOOT_SEED = 20261013
BOOT_RESAMPLES = 2000

Policy = Callable[[Sequence[float]], float]


def tuning_seeds() -> list[int]:
    return [lp.TRAIN_SEED_BASE + i for i in range(N_TUNING)]


def pd_policy(kp: float, kd: float) -> Policy:
    def pol(obs: Sequence[float]) -> float:
        return max(-1.0, min(1.0, kp * obs[0] + kd * obs[1]))

    return pol


def tune_pd(env: SimulationEnv, seeds: Sequence[int]) -> tuple[Policy, float, float]:
    """Migliore (kp, kd) della griglia sui semi di TRAINING: mai su quelli di valutazione."""
    best = max(PD_GRID, key=lambda g: lp.mean_return(env, pd_policy(*g), seeds))
    return pd_policy(*best), best[0], best[1]


def perturbed_env(seed: int, base: Mapping[str, Any] | None = None) -> SimulationEnv:
    """Impianto con tau, rate e (se non nulli in `base`) deadband/stiction/backlash scalati
    ognuno uniformemente in +-20%, deterministico dal seme. Parametri nulli restano nulli."""
    rng = random.Random(f"perturb-{seed}")
    f = PERTURBATION

    def scale(x: float) -> float:
        return x * (1.0 + rng.uniform(-f, f))

    kw = dict(base or {})
    tau, rate = scale(NOMINAL_TAU_S), scale(NOMINAL_RATE_DPS)
    for name in ("deadband_deg", "stiction_dps", "backlash_deg"):
        if kw.get(name):
            kw[name] = scale(kw[name])
    return SimulationEnv(tau_s=tau, rate_dps=rate, **kw)


def episode_returns(
    env_for_seed: Callable[[int], SimulationEnv], policy: Policy, seeds: Sequence[int]
) -> NDArray[np.float64]:
    return np.array([lp.episode_return(env_for_seed(s), policy, s) for s in seeds])


def gain(policy_returns: NDArray[np.float64], base_returns: NDArray[np.float64]) -> float:
    base = float(np.mean(base_returns))
    if abs(base) < 1e-9:
        raise ValueError("ritorno del baseline nullo")
    return (float(np.mean(policy_returns)) - base) / abs(base)


def bootstrap_gain(
    policy_returns: NDArray[np.float64],
    base_returns: NDArray[np.float64],
    *,
    seed: int = BOOT_SEED,
    resamples: int = BOOT_RESAMPLES,
) -> tuple[float, float]:
    """(guadagno medio, limite inferiore IC 95%) con bootstrap APPAIATO (stessi indici)."""
    pol = np.asarray(policy_returns, dtype=np.float64)
    base = np.asarray(base_returns, dtype=np.float64)
    if pol.shape != base.shape or pol.ndim != 1 or pol.size < 2:
        raise ValueError("serie appaiate della stessa lunghezza (>= 2) richieste")
    mean = gain(pol, base)
    idx = np.random.default_rng(seed).integers(0, pol.size, size=(resamples, pol.size))
    mb = base[idx].mean(axis=1)
    if np.any(np.abs(mb) < 1e-9):
        raise ValueError("ritorno del baseline nullo")
    g = (pol[idx].mean(axis=1) - mb) / np.abs(mb)
    return mean, float(np.percentile(g, 2.5))
