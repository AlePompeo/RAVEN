# SPDX-License-Identifier: Apache-2.0
from pathlib import Path

import pytest

from backend.bootstrap import make_loader
from backend.core.errors import PluginError
from backend.core.registry import Registry


def write(d: Path, entry: str, kind: str) -> None:
    d.mkdir(parents=True)
    (d / "manifest.toml").write_text(
        f'id="{d.name}"\nkind="{kind}"\nversion="0.1.0"\nentry="{entry}"\nlicense="Apache-2.0"\n'
    )


@pytest.mark.parametrize("kind", ["firmware", "estimator"])
def test_python_entry_supported(tmp_path: Path, kind: str) -> None:
    write(tmp_path / "ok", "python:backend.plugins.example_sim.plugin:ExampleSim", kind)
    reg = Registry()
    assert reg.discover(tmp_path, make_loader()) == []
    assert reg.create(kind, "ok") is not None


@pytest.mark.parametrize(
    "kind",
    ["data_source", "llm", "telemetry", "firmware", "estimator", "model", "trainer", "environment"],
)
def test_exec_entry_rejected(tmp_path: Path, kind: str) -> None:
    write(tmp_path / "x", "exec:bin/tool", kind)
    errors = Registry().discover(tmp_path, make_loader())
    assert len(errors) == 1
    assert "exec" in str(errors[0][1])
    assert isinstance(errors[0][1], PluginError)
