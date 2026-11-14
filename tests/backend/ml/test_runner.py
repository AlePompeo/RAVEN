# SPDX-License-Identifier: Apache-2.0
import asyncio
import os
import sys
import textwrap
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from backend.ml.jobs import Job, JobStatus, TooManyJobs, UnknownTrainer
from backend.ml.runner import TrainerCommand, TrainerRunner

Resolver = Callable[[str], TrainerCommand | None]

OK_SCRIPT = """
import json, sys
spec = json.load(sys.stdin)
print(json.dumps({"metrics": {"echo": float(spec["config"].get("v", 1))},
                  "model_version": "v0001"}))
"""
HANG_SCRIPT = """
import os, sys, time
open(sys.argv[1], "w").write(str(os.getpid()))
time.sleep(600)
"""


def make_resolver(tmp_path: Path, scripts: dict[str, str], timeout_s: float = 20.0) -> Resolver:
    cmds: dict[str, TrainerCommand] = {}
    for name, body in scripts.items():
        p = tmp_path / f"{name}.py"
        p.write_text(textwrap.dedent(body))
        argv = (sys.executable, "-I", str(p), str(tmp_path / f"{name}.pid"))
        cmds[name] = TrainerCommand(argv=argv, timeout_s=timeout_s)
    return cmds.get


async def wait_terminal(runner: TrainerRunner, job: Job, timeout: float = 20.0) -> Job:
    async def loop() -> Job:
        while True:
            j = runner.get(job.id)
            assert j is not None
            if j.status in (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED):
                return j
            await asyncio.sleep(0.02)

    return await asyncio.wait_for(loop(), timeout)


async def wait_status(runner: TrainerRunner, job: Job, status: JobStatus) -> None:
    async def loop() -> None:
        while runner.get(job.id) is None or runner.get(job.id).status != status:  # type: ignore[union-attr]
            await asyncio.sleep(0.02)

    await asyncio.wait_for(loop(), 20)


def alive(pid_file: Path) -> bool:
    deadline = time.monotonic() + 10  # il figlio scrive il pid file poco dopo l'avvio
    while not (pid_file.exists() and pid_file.read_text().strip()):
        assert time.monotonic() < deadline, "pid file mai scritto"
        time.sleep(0.02)
    pid = int(pid_file.read_text())
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


async def wait_pid_file(p: Path) -> None:
    async def loop() -> None:
        while not (p.exists() and p.read_text()):
            await asyncio.sleep(0.02)

    await asyncio.wait_for(loop(), 20)


@pytest.fixture
async def runners():
    made: list[TrainerRunner] = []

    def make(resolver: Resolver, **kw) -> TrainerRunner:
        r = TrainerRunner(resolver, **kw)
        made.append(r)
        return r

    yield make
    for r in made:
        await r.shutdown()


async def test_success_path(tmp_path, runners) -> None:
    r = runners(make_resolver(tmp_path, {"ok": OK_SCRIPT}))
    job = r.submit("ok", {"v": 3})
    assert job.status in (JobStatus.QUEUED, JobStatus.RUNNING)
    done = await wait_terminal(r, job)
    assert done.status == JobStatus.DONE
    assert done.metrics == {"echo": 3.0}
    assert done.model_version == "v0001"
    assert done.error is None
    assert done.started_utc and done.finished_utc


async def test_unknown_trainer(tmp_path, runners) -> None:
    r = runners(make_resolver(tmp_path, {}))
    with pytest.raises(UnknownTrainer):
        r.submit("nope", {})


async def test_hanging_trainer_is_killed_on_timeout(tmp_path, runners) -> None:
    r = runners(make_resolver(tmp_path, {"hang": HANG_SCRIPT}, timeout_s=0.7))
    job = r.submit("hang", {})
    done = await wait_terminal(r, job)
    assert done.status == JobStatus.FAILED
    assert done.error == "timeout"
    assert not alive(tmp_path / "hang.pid")


async def test_cancel_running_job(tmp_path, runners) -> None:
    r = runners(make_resolver(tmp_path, {"hang": HANG_SCRIPT}))
    job = r.submit("hang", {})
    await wait_pid_file(tmp_path / "hang.pid")
    await wait_status(r, job, JobStatus.RUNNING)
    cancelled = await r.cancel(job.id)
    assert cancelled is not None and cancelled.status == JobStatus.CANCELLED
    assert cancelled.error == "cancelled"
    assert not alive(tmp_path / "hang.pid")


async def test_cancel_queued_job_never_starts(tmp_path, runners) -> None:
    r = runners(make_resolver(tmp_path, {"hang": HANG_SCRIPT, "ok": OK_SCRIPT}), max_concurrent=1)
    first = r.submit("hang", {})
    await wait_status(r, first, JobStatus.RUNNING)
    second = r.submit("ok", {})
    assert r.get(second.id).status == JobStatus.QUEUED  # type: ignore[union-attr]
    c = await r.cancel(second.id)
    assert c is not None and c.status == JobStatus.CANCELLED and c.started_utc is None
    await r.cancel(first.id)


async def test_cancel_finished_job_is_noop_and_unknown_is_none(tmp_path, runners) -> None:
    r = runners(make_resolver(tmp_path, {"ok": OK_SCRIPT}))
    job = await wait_terminal(r, r.submit("ok", {}))
    again = await r.cancel(job.id)
    assert again is not None and again.status == JobStatus.DONE
    assert await r.cancel("0" * 32) is None
    assert await r.cancel("../etc") is None


async def test_failure_does_not_leak_internals(tmp_path, runners) -> None:
    script = """
    import sys
    sys.stderr.write("Traceback secret-path /srv/key=hunter2\\n")
    raise RuntimeError("hunter2 internal detail")
    """
    r = runners(make_resolver(tmp_path, {"boom": script}))
    done = await wait_terminal(r, r.submit("boom", {}))
    assert done.status == JobStatus.FAILED
    assert done.error == "failed"
    dumped = repr(done.public())
    assert "hunter2" not in dumped and "Traceback" not in dumped and "/srv" not in dumped


@pytest.mark.parametrize(
    "payload",
    [
        '{"metrics": {"x": NaN}}',
        '{"metrics": {"x": Infinity}}',
        '{"metrics": {"x": -Infinity}}',
        '{"metrics": {"x": "high"}}',
        '{"metrics": {"x": true}}',
        '{"metrics": {}}',
        '{"metrics": [1, 2]}',
        '{"metrics": {"Bad Name": 1.0}}',
        '{"metrics": {"x": 1e999}}',
        '{"metrics": {"x": 1' + "0" * 400 + "}}",
        '{"nothing": 1}',
        '{"metrics": {"x": 1.0}, "model_version": "../../etc"}',
        "not json at all",
        "",
    ],
)
async def test_invalid_output_rejected(tmp_path, runners, payload: str) -> None:
    script = f"import sys\nsys.stdin.read()\nprint({payload!r})\n"
    r = runners(make_resolver(tmp_path, {"bad": script}))
    done = await wait_terminal(r, r.submit("bad", {}))
    assert done.status == JobStatus.FAILED
    assert done.error == "invalid_output"
    assert done.metrics is None


async def test_nonzero_exit_with_valid_output_still_fails(tmp_path, runners) -> None:
    script = 'import sys\nprint(\'{"metrics": {"x": 1.0}}\')\nsys.exit(3)\n'
    r = runners(make_resolver(tmp_path, {"x": script}))
    done = await wait_terminal(r, r.submit("x", {}))
    assert done.status == JobStatus.FAILED and done.error == "failed"


async def test_stdout_is_capped_and_process_killed(tmp_path, runners) -> None:
    script = """
    import os, sys
    open(sys.argv[1], "w").write(str(os.getpid()))
    while True:
        sys.stdout.write("x" * 65536)
        sys.stdout.flush()
    """
    r = runners(make_resolver(tmp_path, {"flood": script}), max_stdout_bytes=4096)
    done = await wait_terminal(r, r.submit("flood", {}))
    assert done.status == JobStatus.FAILED
    assert done.error == "output_too_large"
    assert not alive(tmp_path / "flood.pid")


@pytest.mark.skipif(sys.platform == "win32", reason="RLIMIT_AS non disponibile")
async def test_memory_limit_enforced(tmp_path, runners) -> None:
    script = """
    import sys
    sys.stdin.read()
    blob = bytearray(1024 * 1024 * 1024)
    print('{"metrics": {"x": 1.0}}')
    """
    r = runners(make_resolver(tmp_path, {"mem": script}), memory_limit_bytes=512 * 1024 * 1024)
    done = await wait_terminal(r, r.submit("mem", {}))
    assert done.status == JobStatus.FAILED and done.error == "failed"


async def test_environment_is_not_inherited(tmp_path, runners, monkeypatch) -> None:
    monkeypatch.setenv("SUPER_SECRET_TOKEN", "s3cr3t")
    script = """
    import json, os, sys
    sys.stdin.read()
    leaked = float("SUPER_SECRET_TOKEN" in os.environ)
    print(json.dumps({"metrics": {"leaked": leaked, "extra": float(os.environ.get("MY_VAR", 0))}}))
    """
    r = runners(make_resolver(tmp_path, {"env": script}), extra_env={"MY_VAR": "7"})
    done = await wait_terminal(r, r.submit("env", {}))
    assert done.metrics == {"leaked": 0.0, "extra": 7.0}


async def test_concurrency_is_bounded_and_active_jobs_capped(tmp_path, runners) -> None:
    r = runners(make_resolver(tmp_path, {"hang": HANG_SCRIPT}), max_concurrent=1, max_active=2)
    a = r.submit("hang", {})
    b = r.submit("hang", {})
    await wait_status(r, a, JobStatus.RUNNING)
    await asyncio.sleep(0.2)
    assert r.get(b.id).status == JobStatus.QUEUED  # type: ignore[union-attr]
    assert r.counts()[JobStatus.RUNNING] == 1
    with pytest.raises(TooManyJobs):
        r.submit("hang", {})
    await r.cancel(a.id)
    await r.cancel(b.id)
    r.submit("hang", {})  # di nuovo spazio


async def test_history_is_bounded(tmp_path, runners) -> None:
    r = runners(make_resolver(tmp_path, {"ok": OK_SCRIPT}), max_history=3, max_active=10)
    jobs = []
    for _ in range(6):
        jobs.append(await wait_terminal(r, r.submit("ok", {})))
    assert r.get(jobs[0].id) is None
    assert r.get(jobs[-1].id) is not None
    assert sum(r.counts().values()) <= 3


async def test_running_jobs_never_evicted_by_history(tmp_path, runners) -> None:
    r = runners(
        make_resolver(tmp_path, {"hang": HANG_SCRIPT, "ok": OK_SCRIPT}),
        max_history=1,
        max_active=10,
        max_concurrent=5,
    )
    h = r.submit("hang", {})
    await wait_status(r, h, JobStatus.RUNNING)
    for _ in range(4):
        await wait_terminal(r, r.submit("ok", {}))
    assert r.get(h.id) is not None
    await r.cancel(h.id)


async def test_shutdown_kills_running_jobs(tmp_path, runners) -> None:
    r = runners(make_resolver(tmp_path, {"hang": HANG_SCRIPT}))
    j = r.submit("hang", {})
    await wait_pid_file(tmp_path / "hang.pid")
    await wait_status(r, j, JobStatus.RUNNING)
    await r.shutdown()
    assert not alive(tmp_path / "hang.pid")


GRANDCHILD_SCRIPT = """
import json, os, subprocess, sys, time
sys.stdin.read()
gc = os.path.join(os.path.dirname(sys.argv[1]), "grandchild.pid")
code = "import os,sys,time;open(sys.argv[1],'w').write(str(os.getpid()));time.sleep(600)"
subprocess.Popen([sys.executable, "-I", "-c", code, gc])  # eredita stdout/stderr
while not (os.path.exists(gc) and open(gc).read()):
    time.sleep(0.01)
print(json.dumps({"metrics": {"x": 1.0}}))
"""


async def test_grandchild_holding_pipes_is_killed_after_leader_exits(tmp_path, runners) -> None:
    r = runners(make_resolver(tmp_path, {"gc": GRANDCHILD_SCRIPT}, timeout_s=30))
    start = time.monotonic()
    done = await wait_terminal(r, r.submit("gc", {}))
    assert done.status == JobStatus.DONE, done.error
    assert time.monotonic() - start < 15  # senza killpg le pipe restano aperte fino al timeout
    gc = tmp_path / "grandchild.pid"
    deadline = time.monotonic() + 10
    while alive(gc) and time.monotonic() < deadline:
        await asyncio.sleep(0.05)
    assert not alive(gc)


async def test_hook_runs_after_process_is_killed(tmp_path, runners) -> None:
    from backend.ml.registry import FileModelRegistry

    script = """
    import os, sys, time
    d = os.path.dirname(sys.argv[1])
    os.mkdir(os.path.join(d, ".tmp-%d-x" % os.getpid()))
    open(sys.argv[1], "w").write(str(os.getpid()))
    time.sleep(600)
    """
    reg = FileModelRegistry(tmp_path)
    r = runners(
        make_resolver(tmp_path, {"orphan": script}, timeout_s=0.8),
        on_process_exit=lambda pid: reg.cleanup_tmp(pid=pid),
    )
    done = await wait_terminal(r, r.submit("orphan", {}))
    assert done.error == "timeout"
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".tmp-")]


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="PR_SET_PDEATHSIG e' Linux")
def test_child_dies_when_parent_dies(tmp_path) -> None:
    import subprocess

    from backend.ml.runner import wrap_with_limits

    root = Path(__file__).resolve().parents[3]
    pidfile = tmp_path / "child.pid"
    parent = f"""
import os, subprocess, sys, time
sys.path.insert(0, {str(root)!r})
from backend.ml.runner import wrap_with_limits
child = [sys.executable, "-I", "-c",
         "import os,sys,time;open(sys.argv[1],'w').write(str(os.getpid()));time.sleep(600)",
         {str(pidfile)!r}]
subprocess.Popen(wrap_with_limits(child, 0))
while not os.path.exists({str(pidfile)!r}) or not open({str(pidfile)!r}).read():
    time.sleep(0.01)
os._exit(0)
"""
    assert wrap_with_limits  # esportato
    subprocess.run([sys.executable, "-I", "-c", parent], timeout=30, check=True)
    pid = int(pidfile.read_text())
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.05)
    os.kill(pid, 9)
    raise AssertionError("il figlio e' sopravvissuto alla morte del genitore")


def test_wrapper_applies_memory_limit_without_preexec(tmp_path) -> None:
    import inspect

    from backend.ml import runner as runner_mod

    assert "preexec" not in inspect.getsource(runner_mod)  # fork+preexec non e' thread-safe


async def test_no_killpg_after_leader_reaped(tmp_path, runners, monkeypatch) -> None:
    """Dopo l'uscita del leader, killpg avviene una volta sola (leader_exit), non in _kill."""
    calls: list[int] = []
    real = os.killpg
    monkeypatch.setattr(os, "killpg", lambda pid, sig: (calls.append(pid), real(pid, sig))[1])
    r = runners(make_resolver(tmp_path, {"ok": OK_SCRIPT}))
    done = await wait_terminal(r, r.submit("ok", {}))
    assert done.status == JobStatus.DONE
    assert len(calls) == 1


HANG_WITH_GRANDCHILD = """
import os, subprocess, sys, time
gc = os.path.join(os.path.dirname(sys.argv[1]), "grandchild.pid")
code = "import os,sys,time;open(sys.argv[1],'w').write(str(os.getpid()));time.sleep(600)"
subprocess.Popen([sys.executable, "-I", "-c", code, gc])
open(sys.argv[1], "w").write(str(os.getpid()))
time.sleep(600)
"""


@pytest.mark.parametrize("how", ["timeout", "cancel"])
async def test_running_leader_and_group_killed(tmp_path, runners, how: str) -> None:
    r = runners(
        make_resolver(
            tmp_path, {"g": HANG_WITH_GRANDCHILD}, timeout_s=1.5 if how == "timeout" else 30
        )
    )
    job = r.submit("g", {})
    await wait_pid_file(tmp_path / "g.pid")
    await wait_pid_file(tmp_path / "grandchild.pid")
    if how == "cancel":
        await r.cancel(job.id)
        assert r.get(job.id).status == JobStatus.CANCELLED  # type: ignore[union-attr]
    else:
        done = await wait_terminal(r, job)
        assert done.error == "timeout"
    assert not alive(tmp_path / "g.pid")
    deadline = time.monotonic() + 10
    while alive(tmp_path / "grandchild.pid") and time.monotonic() < deadline:
        await asyncio.sleep(0.05)
    assert not alive(tmp_path / "grandchild.pid")


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="PR_SET_PDEATHSIG e' Linux")
def test_boot_exits_if_parent_already_dead(tmp_path) -> None:
    import subprocess

    from backend.ml.runner import wrap_with_limits

    marker = tmp_path / "ran"
    child = [sys.executable, "-I", "-c", "import sys;open(sys.argv[1],'w').write('x')", str(marker)]
    res = subprocess.run(
        wrap_with_limits(child, 0, parent_pid=2**22 + 12345), check=False, timeout=30
    )
    assert res.returncode != 0 and not marker.exists()
    ok = subprocess.run(wrap_with_limits(child, 0), check=False, timeout=30)
    assert ok.returncode == 0 and marker.exists()


async def test_oversized_spec_rejected(tmp_path, runners) -> None:
    r = runners(make_resolver(tmp_path, {"ok": OK_SCRIPT}))
    with pytest.raises(ValueError):
        r.submit("ok", {"k": "x" * 100_000})
