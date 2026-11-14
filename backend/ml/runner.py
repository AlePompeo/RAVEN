# SPDX-License-Identifier: Apache-2.0
"""TrainerRunner: esegue i trainer in un SUBPROCESS (mai nel processo web, spec 13.1).

Garanzie: nessuna shell (argv come lista), ambiente minimo (nessun segreto ereditato), nuova
sessione/gruppo di processi uccisi in blocco, timeout, tetto di memoria (RLIMIT_AS dove
disponibile), tetto sull'output, metriche non finite rifiutate, concorrenza e storico limitati.
Gli errori esposti ai client sono codici generici: stderr del figlio non esce mai dal server.

Protocollo con il figlio: JSON `{"trainer", "config"}` su stdin; l'ULTIMA riga non vuota di stdout
e' `{"metrics": {nome: float finito}, "model_version": "vNNNN" | null}`.
"""

import asyncio
import contextlib
import json
import logging
import math
import os
import re
import secrets
import signal
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from backend.core.registry import Registry
from backend.ml.jobs import (
    Job,
    JobStatus,
    JobStore,
    TooManyJobs,
    UnknownTrainer,
)
from backend.ml.registry import VERSION_RE, default_registry_dir

log = logging.getLogger(__name__)

DEFAULT_MEMORY_LIMIT = 4 * 1024**3
DEFAULT_MAX_STDOUT = 64 * 1024
MAX_STDERR_KEPT = 4096
MAX_SPEC_BYTES = 16 * 1024
MAX_METRICS = 64
MAX_TIMEOUT_S = 3600.0
_METRIC_KEY = re.compile(r"[a-z][a-z0-9_]{0,63}")
_BOOT = (
    "import runpy, sys; sys.path.insert(0, sys.argv[1]); "
    "runpy.run_module(sys.argv[2], run_name='__main__')"
)
_BASE_ENV = {"OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}


@dataclass(frozen=True)
class TrainerCommand:
    argv: tuple[str, ...]
    timeout_s: float
    cwd: Path | None = None


class _OutputTooLarge(Exception):
    pass


class _InvalidOutput(Exception):
    pass


def registry_resolver(
    registry: Registry, project_root: Path | None = None
) -> Callable[[str], TrainerCommand | None]:
    """Risolve un id di trainer (plugin `kind = "trainer"`) nel comando del worker."""
    root = project_root or Path(__file__).resolve().parents[2]

    def resolve(trainer_id: str) -> TrainerCommand | None:
        for m in registry.manifests():
            if m.kind == "trainer" and m.id == trainer_id:
                argv = (
                    sys.executable,
                    "-I",
                    "-c",
                    _BOOT,
                    str(root),
                    "backend.ml.worker",
                    str(m.root / "manifest.toml"),
                )
                return TrainerCommand(argv=argv, timeout_s=min(m.timeout_s, MAX_TIMEOUT_S))
        return None

    return resolve


_LIMIT_BOOT = (
    "import os, sys\n"
    "limit = int(sys.argv[1])\n"
    "parent = int(sys.argv[2])\n"
    "if limit > 0:\n"
    "    try:\n"
    "        import resource\n"
    "        resource.setrlimit(resource.RLIMIT_AS, (limit, limit))\n"
    "    except ImportError:\n"
    "        pass\n"
    "if sys.platform.startswith('linux'):\n"
    "    try:\n"
    "        import ctypes, signal\n"
    "        ctypes.CDLL(None).prctl(1, int(signal.SIGKILL))\n"  # PR_SET_PDEATHSIG
    "    except Exception:\n"
    "        pass\n"
    "    if os.getppid() != parent:\n"  # il genitore e' morto prima di prctl
    "        os._exit(1)\n"
    "os.execv(sys.argv[3], sys.argv[3:])\n"
)


def wrap_with_limits(
    argv: Sequence[str], memory_limit_bytes: int, parent_pid: int | None = None
) -> tuple[str, ...]:
    """Antepone un boot `-I -c` che applica RLIMIT_AS e PR_SET_PDEATHSIG e poi fa exec(argv).

    Nessun hook tra fork ed exec nel processo del server (non e' sicuro con i thread).
    Le limitazioni sopravvivono a execve. Fuori da POSIX l'argv resta invariato.
    """
    if os.name != "posix":  # pragma: no cover
        return tuple(argv)
    parent = os.getpid() if parent_pid is None else parent_pid
    limit = str(max(0, memory_limit_bytes))
    return (sys.executable, "-I", "-c", _LIMIT_BOOT, limit, str(parent), *argv)


def parse_result(raw: bytes) -> tuple[dict[str, float], str | None]:
    """Valida l'ultima riga di stdout. Solleva _InvalidOutput."""

    def bad_constant(_: str) -> float:
        raise ValueError("NaN/Infinity non ammessi")

    lines = [ln for ln in raw.decode("utf-8", errors="replace").splitlines() if ln.strip()]
    if not lines:
        raise _InvalidOutput
    try:
        obj = json.loads(lines[-1], parse_constant=bad_constant)
    except (ValueError, RecursionError):
        raise _InvalidOutput from None
    if not isinstance(obj, dict):
        raise _InvalidOutput
    metrics = obj.get("metrics")
    if not isinstance(metrics, dict) or not 0 < len(metrics) <= MAX_METRICS:
        raise _InvalidOutput
    clean: dict[str, float] = {}
    for k, v in metrics.items():
        if (
            not isinstance(k, str)
            or _METRIC_KEY.fullmatch(k) is None
            or isinstance(v, bool)
            or not isinstance(v, int | float)
        ):
            raise _InvalidOutput
        try:
            f = float(v)
        except (OverflowError, ValueError):
            raise _InvalidOutput from None
        if not math.isfinite(f):
            raise _InvalidOutput
        clean[k] = f
    version = obj.get("model_version")
    if version is not None and (
        not isinstance(version, str) or VERSION_RE.fullmatch(version) is None
    ):
        raise _InvalidOutput
    return clean, version


class TrainerRunner:
    def __init__(
        self,
        resolve: Callable[[str], TrainerCommand | None],
        *,
        max_concurrent: int = 2,
        max_active: int = 4,
        max_history: int = 100,
        memory_limit_bytes: int = DEFAULT_MEMORY_LIMIT,
        max_stdout_bytes: int = DEFAULT_MAX_STDOUT,
        extra_env: Mapping[str, str] | None = None,
        on_process_exit: Callable[[int], None] | None = None,
    ) -> None:
        if max_concurrent < 1 or max_active < max_concurrent or max_history < 0:
            raise ValueError("limiti non validi")
        self._resolve = resolve
        self._memory_limit = memory_limit_bytes
        self._max_stdout = max_stdout_bytes
        self._env = {**_BASE_ENV, **(extra_env or {})}
        self._store = JobStore(max_active=max_active, max_history=max_history)
        self._max_concurrent = max_concurrent
        self._sem: asyncio.Semaphore | None = None  # creato nel loop corrente
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._procs: dict[str, asyncio.subprocess.Process] = {}
        self._on_exit = on_process_exit
        self._closed = False

    # -- API -------------------------------------------------------------------------------
    def submit(self, trainer_id: str, config: Mapping[str, Any]) -> Job:
        """Accoda un job. Deve essere chiamato dentro l'event loop."""
        if self._closed:
            raise TooManyJobs
        command = self._resolve(trainer_id)
        if command is None:
            raise UnknownTrainer
        spec = json.dumps({"trainer": trainer_id, "config": dict(config)}, allow_nan=False)
        if len(spec.encode("utf-8")) > MAX_SPEC_BYTES:
            raise ValueError("configurazione troppo grande")
        job = Job(id=secrets.token_hex(16), trainer=trainer_id, config=dict(config))
        self._store.add(job)  # TooManyJobs se troppi job attivi
        if self._sem is None:
            self._sem = asyncio.Semaphore(self._max_concurrent)
        self._tasks[job.id] = asyncio.create_task(self._run(job, command, spec.encode("utf-8")))
        return job

    def get(self, job_id: str) -> Job | None:
        return self._store.get(job_id)

    def counts(self) -> dict[JobStatus, int]:
        return self._store.counts()

    async def cancel(self, job_id: str) -> Job | None:
        job = self._store.get(job_id)
        if job is None:
            return None
        task = self._tasks.get(job_id)
        if not job.terminal and task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            if not job.terminal:  # task annullato prima della prima esecuzione
                job.error = "cancelled"
                job.transition(JobStatus.CANCELLED)
                self._tasks.pop(job.id, None)
                self._store.prune()
        return job

    async def shutdown(self) -> None:
        self._closed = True
        tasks = list(self._tasks.values())
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for job_id in list(self._tasks):
            job = self._store.get(job_id)
            if job is not None and not job.terminal:
                job.error = "cancelled"
                job.transition(JobStatus.CANCELLED)
        self._tasks.clear()

    # -- esecuzione ------------------------------------------------------------------------
    async def _run(self, job: Job, command: TrainerCommand, spec: bytes) -> None:
        assert self._sem is not None
        try:
            try:
                async with self._sem:
                    job.transition(JobStatus.RUNNING)
                    await self._execute(job, command, spec)
            except asyncio.CancelledError:
                job.error = "cancelled"
                job.transition(JobStatus.CANCELLED)
        except Exception:
            log.exception("job %s: errore interno del runner", job.id)
            if not job.terminal:
                job.error = "failed"
                job.transition(JobStatus.FAILED)
        finally:
            self._tasks.pop(job.id, None)
            self._store.prune()

    async def _execute(self, job: Job, command: TrainerCommand, spec: bytes) -> None:
        kwargs: dict[str, Any] = {}
        if os.name == "posix":
            kwargs["start_new_session"] = True
        proc = await asyncio.create_subprocess_exec(
            *wrap_with_limits(command.argv, self._memory_limit),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=command.cwd,
            env=self._env,
            **kwargs,
        )
        self._procs[job.id] = proc
        stdout = b""
        stderr = b""
        outcome: str | None = None
        try:
            try:
                stdout, stderr = await asyncio.wait_for(
                    self._communicate(proc, spec), command.timeout_s
                )
            except TimeoutError:
                outcome = "timeout"
            except _OutputTooLarge:
                outcome = "output_too_large"
        finally:
            await self._kill(proc)  # il processo e' morto prima di ogni cambio di stato
            self._procs.pop(job.id, None)
            if self._on_exit is not None:
                try:
                    self._on_exit(proc.pid)
                except Exception:
                    log.exception("job %s: pulizia dopo il processo fallita", job.id)
        if outcome is None and proc.returncode != 0:
            log.warning("job %s: trainer terminato con codice %s", job.id, proc.returncode)
            if stderr:
                log.debug("job %s stderr (troncato): %r", job.id, stderr)
            outcome = "failed"
        if outcome is None:
            try:
                job.metrics, job.model_version = parse_result(stdout)
            except _InvalidOutput:
                outcome = "invalid_output"
        if outcome is not None:
            job.error = outcome
            job.transition(JobStatus.FAILED)
        else:
            job.transition(JobStatus.DONE)

    async def _communicate(
        self, proc: asyncio.subprocess.Process, spec: bytes
    ) -> tuple[bytes, bytes]:
        assert proc.stdin and proc.stdout and proc.stderr

        async def feed() -> None:
            try:
                proc.stdin.write(spec)  # type: ignore[union-attr]
                await proc.stdin.drain()  # type: ignore[union-attr]
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                with contextlib.suppress(Exception):
                    proc.stdin.close()  # type: ignore[union-attr]

        async def read_out() -> bytes:
            buf = bytearray()
            while chunk := await proc.stdout.read(8192):  # type: ignore[union-attr]
                buf += chunk
                if len(buf) > self._max_stdout:
                    raise _OutputTooLarge
            return bytes(buf)

        async def read_err() -> bytes:
            buf = bytearray()
            while chunk := await proc.stderr.read(8192):  # type: ignore[union-attr]
                if len(buf) < MAX_STDERR_KEPT:
                    buf += chunk[: MAX_STDERR_KEPT - len(buf)]
            return bytes(buf)

        async def leader_exit() -> None:
            await proc.wait()
            self._killpg(proc)  # un nipote puo' tenere aperte le pipe: via tutto il gruppo

        tasks = [asyncio.ensure_future(c) for c in (feed(), read_out(), read_err(), leader_exit())]
        try:
            results = await asyncio.gather(*tasks)
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        return cast(bytes, results[1]), cast(bytes, results[2])

    @staticmethod
    def _killpg(proc: asyncio.subprocess.Process) -> None:
        """SIGKILL all'intero gruppo (start_new_session: pgid == pid), anche a leader gia' uscito."""
        with contextlib.suppress(ProcessLookupError, PermissionError):
            if os.name == "posix":
                os.killpg(proc.pid, signal.SIGKILL)
            elif proc.returncode is None:  # pragma: no cover
                proc.kill()

    @classmethod
    async def _kill(cls, proc: asyncio.subprocess.Process) -> None:
        if proc.returncode is None:  # leader gia' reaped: leader_exit ha gia' ucciso il gruppo
            cls._killpg(proc)
        with contextlib.suppress(Exception):
            await asyncio.shield(proc.wait())


def default_runner(registry: Registry) -> TrainerRunner:
    """Runner di produzione: trainer dal registry dei plugin, registro modelli da env."""
    directory = default_registry_dir()

    def cleanup(pid: int) -> None:  # directory .tmp-<pid>-* lasciate da un trainer ucciso
        from backend.ml.registry import FileModelRegistry

        FileModelRegistry(directory).cleanup_tmp(pid=pid)

    return TrainerRunner(
        registry_resolver(registry),
        extra_env={"MODEL_REGISTRY_DIR": str(directory)},
        on_process_exit=cleanup,
    )
