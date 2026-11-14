# SPDX-License-Identifier: Apache-2.0
import asyncio
import os
import sys

import pytest

from backend.adapters.subprocess_sim import ExecSimulation
from backend.core.errors import InvalidOutput, PluginError, SimulationTimeout


def script(tmp_path, body):
    p = tmp_path / "s.py"
    p.write_text(body)
    return ExecSimulation([sys.executable, str(p)], root=tmp_path)


def pid_script(tmp_path):
    pidfile = tmp_path / "pid"
    body = f"import os,time; open({str(pidfile)!r},'w').write(str(os.getpid())); time.sleep(60)"
    return script(tmp_path, body), pidfile


@pytest.mark.parametrize("bad", [{"": 1.0}, {"a=b": 1.0}, {"a\nb": 1.0}, {"a\rb": 1.0}])
async def test_bad_input_keys_rejected(tmp_path, bad):
    sim = script(tmp_path, "print('y=1')")
    with pytest.raises(PluginError):
        await sim.run(bad, timeout_s=5)


@pytest.mark.parametrize("v", [float("nan"), float("inf"), float("-inf")])
async def test_non_finite_input_rejected(tmp_path, v):
    sim = script(tmp_path, "print('y=1')")
    with pytest.raises(PluginError):
        await sim.run({"x": v}, timeout_s=5)


async def test_timeout_process_really_dead(tmp_path):
    sim, pidfile = pid_script(tmp_path)
    with pytest.raises(SimulationTimeout):
        await sim.run({}, timeout_s=1.0)
    with pytest.raises(ProcessLookupError):
        os.kill(int(pidfile.read_text()), 0)


async def test_cancel_kills_child(tmp_path):
    sim, pidfile = pid_script(tmp_path)
    task = asyncio.create_task(sim.run({}, timeout_s=30))
    for _ in range(100):
        await asyncio.sleep(0.05)
        if pidfile.exists() and pidfile.read_text():
            break
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    with pytest.raises(ProcessLookupError):
        os.kill(int(pidfile.read_text()), 0)


async def test_huge_stdout_rejected(tmp_path):
    sim = script(tmp_path, "print('y=1'); print('z=' + '1' * 200000)")
    with pytest.raises(InvalidOutput):
        await sim.run({}, timeout_s=5)


@pytest.mark.parametrize("out", ["=1", "a=1\na=2"])
async def test_empty_or_duplicate_key_rejected(tmp_path, out):
    sim = script(tmp_path, f"print({out!r})")
    with pytest.raises(InvalidOutput):
        await sim.run({}, timeout_s=5)
