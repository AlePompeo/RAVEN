# SPDX-License-Identifier: Apache-2.0
"""Shim Gymnasium opzionale (extra [rl]). Importare questo modulo senza gymnasium solleva
ImportError con messaggio chiaro; il resto del plugin non lo importa mai."""

from typing import Any

try:
    import gymnasium as gym
    import numpy as np
except ImportError as e:  # pragma: no cover - dipende dall'ambiente
    raise ImportError("gymnasium/numpy non installati: usare l'extra [rl]") from e

from backend.ml.rl.env_adapter import SimulationEnv


class ServoGymEnv(gym.Env[Any, Any]):
    """`SimulationEnv` esposto come `gymnasium.Env` (spazi Box float32)."""

    metadata: dict[str, Any] = {"render_modes": []}  # noqa: RUF012

    def __init__(self, **kwargs: Any) -> None:
        self._env = SimulationEnv(**kwargs)
        o, a = self._env.observation_space, self._env.action_space
        self.observation_space = gym.spaces.Box(
            low=np.array(o.low, dtype=np.float32), high=np.array(o.high, dtype=np.float32)
        )
        self.action_space = gym.spaces.Box(
            low=np.array(a.low, dtype=np.float32), high=np.array(a.high, dtype=np.float32)
        )

    def reset(
        self, *, seed: int | None = None, options: dict[str, Any] | None = None
    ) -> tuple[Any, dict[str, Any]]:
        super().reset(seed=seed)
        obs, info = self._env.reset(seed=seed)
        return np.array(obs, dtype=np.float32), info

    def step(self, action: Any) -> tuple[Any, float, bool, bool, dict[str, Any]]:
        obs, r, term, trunc, info = self._env.step(
            np.asarray(action, dtype=np.float64).ravel().tolist()
        )
        return np.array(obs, dtype=np.float32), r, term, trunc, info
