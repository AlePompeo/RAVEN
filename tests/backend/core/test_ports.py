# SPDX-License-Identifier: Apache-2.0
from backend.core.errors import InvalidOutput, PluginError, SimulationTimeout
from backend.core.ports import Simulation


class Fake:
    async def run(self, inputs, *, timeout_s):
        return {"y": 1.0}


def test_errors_share_base():
    assert issubclass(SimulationTimeout, PluginError)
    assert issubclass(InvalidOutput, PluginError)


def test_simulation_protocol_is_structural():
    assert isinstance(Fake(), Simulation)
