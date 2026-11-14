# SPDX-License-Identifier: Apache-2.0
"""Lettura uniforme delle variabili d'ambiente numeriche.

Semantica unica: non impostata o vuota -> default documentato; valore non valido o <= 0
-> ConfigError che nomina la variabile (l'avvio si ferma con un messaggio chiaro).
"""

import math
import os
from collections.abc import Mapping


class ConfigError(ValueError):
    pass


def _raw(name: str, env: Mapping[str, str] | None) -> str | None:
    raw = (os.environ if env is None else env).get(name)
    return None if raw is None or raw == "" else raw


def env_positive_int(name: str, default: int, env: Mapping[str, str] | None = None) -> int:
    raw = _raw(name, env)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"{name} deve essere un intero > 0 (valore non valido)") from None
    if value <= 0:
        raise ConfigError(f"{name} deve essere un intero > 0")
    return value


def env_positive_float(name: str, default: float, env: Mapping[str, str] | None = None) -> float:
    raw = _raw(name, env)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        raise ConfigError(f"{name} deve essere un numero finito > 0 (valore non valido)") from None
    if not math.isfinite(value) or value <= 0:
        raise ConfigError(f"{name} deve essere un numero finito > 0")
    return value
