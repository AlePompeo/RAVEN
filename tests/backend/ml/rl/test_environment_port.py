# SPDX-License-Identifier: Apache-2.0
import subprocess
import sys

from backend.core.ports import BoxSpace, Environment


class Fake:
    observation_space = BoxSpace(low=(-1.0,), high=(1.0,), shape=(1,))
    action_space = BoxSpace(low=(-1.0,), high=(1.0,), shape=(1,))

    def reset(self, seed=None):
        return (0.0,), {}

    def step(self, action):
        return (0.0,), 0.0, False, False, {}


def test_environment_is_a_protocol() -> None:
    assert isinstance(Fake(), Environment)
    assert not isinstance(object(), Environment)


def test_boxspace_is_plain_dataclass() -> None:
    b = BoxSpace(low=(-1.0, -2.0), high=(1.0, 2.0), shape=(2,))
    assert b.shape == (2,)


def test_core_does_not_import_gymnasium() -> None:
    code = (
        "import sys; sys.modules['gymnasium']=None; sys.modules['numpy']=None; "
        "import backend.core.ports"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
