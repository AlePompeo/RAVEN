# SPDX-License-Identifier: Apache-2.0
from collections.abc import Mapping

from backend.core.manifest import Manifest


class ExampleSim:
    """Simulazione di esempio: y = x * x."""

    def __init__(self, manifest: Manifest) -> None:
        self.manifest = manifest

    async def run(self, inputs: Mapping[str, float], *, timeout_s: float) -> Mapping[str, float]:
        x = float(inputs["x"])
        return {"y": x * x}
