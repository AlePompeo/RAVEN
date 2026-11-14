# SPDX-License-Identifier: Apache-2.0
"""Plugin `environment`: servo di riferimento (Python puro, nessun extra)."""

from typing import Any

from backend.core.manifest import Manifest
from backend.ml.rl.env_adapter import SimulationEnv


class ServoEnvironment(SimulationEnv):
    def __init__(self, manifest: Manifest | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._manifest = manifest
