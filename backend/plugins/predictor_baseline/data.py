# SPDX-License-Identifier: Apache-2.0
"""Dati sintetici di telemetria per l'esempio di data science.

Origine e licenza: generati qui da una formula e da un generatore pseudo-casuale con seme; nessun
dato esterno. Licenza dei dati = licenza del progetto (Apache-2.0).

Modello fisico semplificato (NON un budget di collegamento reale): il margine cresce con la
potenza (10*log10 P) e cala con il quadrato della distanza (20*log10 d), piu' rumore gaussiano.
Il margine e' quindi non lineare nelle feature grezze, cosi' il baseline lineare e' battibile.
"""

import hashlib
import math

import numpy as np
from numpy.typing import NDArray

FEATURES = ("power_w", "distance_km")
TARGET = "link_margin_db"
OFFSET_DB = 40.0
NOISE_STD_DB = 0.5
POWER_RANGE_W = (1.0, 20.0)
DISTANCE_RANGE_KM = (500.0, 2000.0)
FIXED_TEST_SEED = 20261012
N_TEST = 500

Array = NDArray[np.float64]


def true_link_margin_db(power_w: float, distance_km: float) -> float:
    return OFFSET_DB + 10.0 * math.log10(power_w) - 20.0 * math.log10(distance_km / 1000.0)


def make_dataset(n: int, seed: int) -> tuple[Array, Array]:
    rng = np.random.default_rng(seed)
    power = rng.uniform(*POWER_RANGE_W, size=n)
    dist = rng.uniform(*DISTANCE_RANGE_KM, size=n)
    clean = OFFSET_DB + 10.0 * np.log10(power) - 20.0 * np.log10(dist / 1000.0)
    y = clean + rng.normal(0.0, NOISE_STD_DB, size=n)
    return np.column_stack([power, dist]), y


def fixed_test_set() -> tuple[Array, Array]:
    """Test set fisso: stesso seme sempre; i seed di training sono scelti dall'utente."""
    return make_dataset(N_TEST, FIXED_TEST_SEED)


def sha256_of(x: Array, y: Array) -> str:
    h = hashlib.sha256()
    h.update(np.ascontiguousarray(x, dtype="<f8").tobytes())
    h.update(np.ascontiguousarray(y, dtype="<f8").tobytes())
    return h.hexdigest()
