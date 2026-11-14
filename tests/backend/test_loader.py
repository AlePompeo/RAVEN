# SPDX-License-Identifier: Apache-2.0
import shutil
import subprocess
from pathlib import Path

import pytest

from backend.bootstrap import make_loader
from backend.core.errors import PluginError
from backend.core.registry import Registry

ROOT = Path(__file__).resolve().parents[2]


def write(d: Path, entry: str, kind: str = "simulation") -> None:
    d.mkdir(parents=True)
    (d / "manifest.toml").write_text(
        f'id="{d.name}"\nkind="{kind}"\nversion="0.1.0"\nentry="{entry}"\nlicense="Apache-2.0"\n'
    )


def test_exec_traversal_collected(tmp_path: Path) -> None:
    write(tmp_path / "evil", "exec:../../bin/sh")
    errors = Registry().discover(tmp_path, make_loader())
    assert len(errors) == 1
    assert isinstance(errors[0][1], PluginError)


def test_exec_missing_binary_collected(tmp_path: Path) -> None:
    write(tmp_path / "nobin", "exec:bin/missing")
    errors = Registry().discover(tmp_path, make_loader())
    assert len(errors) == 1
    assert "bin/missing" in str(errors[0][1])


def test_missing_module_collected(tmp_path: Path) -> None:
    write(tmp_path / "ghost", "python:backend.plugins.no_such.module:X")
    assert len(Registry().discover(tmp_path, make_loader())) == 1


def test_missing_class_collected(tmp_path: Path) -> None:
    write(tmp_path / "noclass", "python:backend.plugins.example_sim.plugin:Nope")
    assert len(Registry().discover(tmp_path, make_loader())) == 1


@pytest.mark.parametrize("entry", ["python:os:system", "python:backend.core.registry:Registry"])
def test_python_outside_plugins_rejected(tmp_path: Path, entry: str) -> None:
    write(tmp_path / "bad", entry)
    errors = Registry().discover(tmp_path, make_loader())
    assert len(errors) == 1
    assert isinstance(errors[0][1], PluginError)


def test_malformed_entry_collected(tmp_path: Path) -> None:
    write(tmp_path / "weird", "ftp:whatever")
    write(tmp_path / "short", "python:backend.plugins.x")
    assert len(Registry().discover(tmp_path, make_loader())) == 2


async def test_exec_plugin_runs(tmp_path: Path) -> None:
    write(tmp_path / "echo", "exec:run.sh")
    script = tmp_path / "echo" / "run.sh"
    script.write_text("#!/bin/sh\ncat >/dev/null\necho y=3\n")
    script.chmod(0o755)
    r = Registry()
    assert r.discover(tmp_path, make_loader()) == []
    assert (await r.create("simulation", "echo").run({}, timeout_s=5))["y"] == 3.0


@pytest.fixture(scope="module")
def built_c() -> None:
    if shutil.which("gcc") is None or shutil.which("make") is None:
        pytest.skip("gcc/make assenti")
    subprocess.run(["make", "-C", str(ROOT), "build-c"], check=True, capture_output=True)


@pytest.mark.usefixtures("built_c")
async def test_real_plugins_dir() -> None:
    r = Registry()
    errors = r.discover(ROOT / "backend" / "plugins", make_loader())
    # un plugin che richiede un extra opzionale non installato (es. imufusion) non e' un errore
    real = [p.name for p, e in errors if "No module named" not in str(e)]
    assert real == []
    sim = r.create("simulation", "example-sim")
    assert (await sim.run({"x": 2.0}, timeout_s=1))["y"] == 4.0
