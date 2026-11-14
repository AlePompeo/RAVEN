# SPDX-License-Identifier: Apache-2.0
"""Scheduler in-process (asyncio) per i job della pipeline: ingestione, compattazione, retention.

Garanzie: timeout per job (il job viene cancellato), nessuna sovrapposizione (se il giro
precedente e' ancora attivo il nuovo e' saltato e contato), isolamento dei guasti (un'eccezione
non ferma ne' lo scheduler ne' gli altri job; si conserva solo il nome del tipo di errore).
Nessun persistente: dopo un riavvio i job ripartono subito (i job devono essere idempotenti).
"""

import asyncio
import logging
import math
import re
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_:-]{0,63}$")


class SchedulerConfigError(ValueError):
    pass


@dataclass
class _Job:
    name: str
    fn: Callable[[], Awaitable[None]]
    interval_s: float
    timeout_s: float
    next_due: float
    running: bool = False
    runs: int = 0
    ok: int = 0
    failed: int = 0
    timeouts: int = 0
    skipped: int = 0
    last_status: str | None = None
    last_duration_s: float | None = None
    last_error: str | None = None
    last_finished_at: float | None = None


def _positive_finite(value: float, what: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not math.isfinite(value)
        or value <= 0
    ):
        raise SchedulerConfigError(f"{what} deve essere un numero finito > 0")
    return float(value)


class AsyncScheduler:
    def __init__(self, *, clock: Callable[[], float] = time.monotonic, tick_s: float = 0.5) -> None:
        self._clock = clock
        self._tick = _positive_finite(tick_s, "tick_s")
        self._jobs: dict[str, _Job] = {}
        self._tasks: set[asyncio.Task[str]] = set()
        self._loop_task: asyncio.Task[None] | None = None

    def add_job(
        self, name: str, fn: Callable[[], Awaitable[None]], *, interval_s: float, timeout_s: float
    ) -> None:
        if not isinstance(name, str) or not NAME_RE.fullmatch(name):
            raise SchedulerConfigError("nome del job non valido")
        if name in self._jobs:
            raise SchedulerConfigError(f"job duplicato: {name}")
        interval = _positive_finite(interval_s, "interval_s")
        timeout = _positive_finite(timeout_s, "timeout_s")
        self._jobs[name] = _Job(name, fn, interval, timeout, next_due=self._clock())

    async def run_now(self, name: str) -> str:
        """Esegue il job una volta. Ritorna ok | failed | timeout | skipped."""
        job = self._jobs[name]
        if job.running:
            job.skipped += 1
            return "skipped"
        job.running = True
        job.runs += 1
        started = self._clock()
        status = "ok"
        error: str | None = None
        try:
            cm = asyncio.timeout(job.timeout_s)
            try:
                async with cm:
                    await job.fn()
            except TimeoutError:
                if cm.expired():
                    status = "timeout"
                else:
                    status, error = "failed", "TimeoutError"
            except Exception as e:
                status, error = "failed", type(e).__name__
                log.exception("job %s fallito", name)
        finally:
            job.running = False
            job.last_duration_s = max(0.0, self._clock() - started)
            job.last_finished_at = self._clock()
        if status == "ok":
            job.ok += 1
        elif status == "timeout":
            job.timeouts += 1
            error = "timeout"
            log.warning("job %s oltre il timeout di %.1fs", name, job.timeout_s)
        else:
            job.failed += 1
        job.last_status, job.last_error = status, error
        return status

    def run_due(self) -> list[asyncio.Task[str]]:
        """Avvia (senza attendere) i job scaduti secondo l'orologio iniettato."""
        now = self._clock()
        launched: list[asyncio.Task[str]] = []
        for job in self._jobs.values():
            if job.next_due > now:
                continue
            job.next_due = now + job.interval_s
            if job.running:
                job.skipped += 1
                continue
            task = asyncio.create_task(self.run_now(job.name), name=f"job:{job.name}")
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
            launched.append(task)
        return launched

    async def _loop(self) -> None:
        while True:
            self.run_due()
            await asyncio.sleep(self._tick)

    async def start(self) -> None:
        if self._loop_task is None or self._loop_task.done():
            self._loop_task = asyncio.create_task(self._loop(), name="scheduler-loop")

    async def stop(self) -> None:
        pending: list[asyncio.Task[Any]] = list(self._tasks)
        if self._loop_task is not None:
            pending.append(self._loop_task)
            self._loop_task = None
        for t in pending:
            t.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

    def status(self) -> Mapping[str, Mapping[str, Any]]:
        now = self._clock()
        return {
            n: {
                "interval_s": j.interval_s,
                "timeout_s": j.timeout_s,
                "running": j.running,
                "runs": j.runs,
                "ok": j.ok,
                "failed": j.failed,
                "timeouts": j.timeouts,
                "skipped": j.skipped,
                "last_status": j.last_status,
                "last_duration_s": j.last_duration_s,
                "last_error": j.last_error,
                "next_due_in_s": max(0.0, j.next_due - now),
            }
            for n, j in self._jobs.items()
        }
