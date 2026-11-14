# SPDX-License-Identifier: Apache-2.0
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from backend.adapters.subprocess_sim import ExecSimulation, resolve_inside
from backend.core.errors import InvalidOutput, PluginError, SimulationTimeout

ROOT = Path(__file__).resolve().parents[3]


def test_resolve_inside_rejects_traversal(tmp_path):
    with pytest.raises(PluginError):
        resolve_inside(tmp_path, "../evil")
    with pytest.raises(PluginError):
        resolve_inside(tmp_path, "/bin/sh")


@pytest.fixture(scope="session")
def fspl_bin(tmp_path_factory):
    if not shutil.which("gcc"):
        pytest.skip("gcc assente")
    out = tmp_path_factory.mktemp("fspl") / "fspl"
    src = ROOT / "backend/plugins/fspl_c/fspl.c"
    subprocess.run(["gcc", "-O2", "-o", str(out), str(src), "-lm"], check=True)
    return out


async def test_fspl_c_matches_formula(fspl_bin):
    sim = ExecSimulation([str(fspl_bin)], root=fspl_bin.parent)
    out = await sim.run({"distance_km": 384400.0, "freq_ghz": 2.2}, timeout_s=5)
    assert out["fspl_db"] == pytest.approx(210.99, abs=0.02)


def script(tmp_path, body):
    p = tmp_path / "s.py"
    p.write_text(body)
    return ExecSimulation([sys.executable, str(p)], root=tmp_path)


async def test_timeout_kills_process(tmp_path):
    sim = script(tmp_path, "import time; time.sleep(60)")
    with pytest.raises(SimulationTimeout):
        await sim.run({}, timeout_s=0.5)


@pytest.mark.parametrize("line", ["y=nan", "y=inf", "y=abc", "senza_uguale"])
async def test_invalid_output_rejected(tmp_path, line):
    sim = script(tmp_path, f"print({line!r})")
    with pytest.raises(InvalidOutput):
        await sim.run({}, timeout_s=5)


async def test_nonzero_exit_is_error(tmp_path):
    sim = script(tmp_path, "import sys; sys.exit(3)")
    with pytest.raises(PluginError):
        await sim.run({}, timeout_s=5)
