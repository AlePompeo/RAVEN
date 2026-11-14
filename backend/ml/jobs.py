# SPDX-License-Identifier: Apache-2.0
"""Modelli dei job di addestramento: macchina a stati e archivio con storico limitato."""

import re
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

JOB_ID_RE = re.compile(r"[0-9a-f]{32}")
SCHEMA_VERSION = "1.0.0"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL = frozenset({JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED})
_ALLOWED: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.QUEUED: frozenset({JobStatus.RUNNING, JobStatus.CANCELLED, JobStatus.FAILED}),
    JobStatus.RUNNING: frozenset({JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED}),
    JobStatus.DONE: frozenset(),
    JobStatus.FAILED: frozenset(),
    JobStatus.CANCELLED: frozenset(),
}


class UnknownTrainer(Exception):
    pass


class TooManyJobs(Exception):
    pass


class InvalidTransition(Exception):
    pass


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Job:
    id: str
    trainer: str
    config: dict[str, Any] = field(repr=False)
    status: JobStatus = JobStatus.QUEUED
    created_utc: str = field(default_factory=utc_now)
    started_utc: str | None = None
    finished_utc: str | None = None
    error: str | None = (
        None  # codice generico: timeout|failed|invalid_output|output_too_large|cancelled
    )
    metrics: dict[str, float] | None = None
    model_version: str | None = None

    def transition(self, new: JobStatus) -> None:
        if new not in _ALLOWED[self.status]:
            raise InvalidTransition(f"{self.status} -> {new}")
        self.status = new
        if new == JobStatus.RUNNING:
            self.started_utc = utc_now()
        elif new in TERMINAL:
            self.finished_utc = utc_now()

    @property
    def terminal(self) -> bool:
        return self.status in TERMINAL

    def public(self) -> dict[str, Any]:
        """Vista per il client: nessuna config, nessun dettaglio interno."""
        return {
            "schema_version": SCHEMA_VERSION,
            "id": self.id,
            "trainer": self.trainer,
            "status": self.status.value,
            "created_utc": self.created_utc,
            "started_utc": self.started_utc,
            "finished_utc": self.finished_utc,
            "error": self.error,
            "metrics": self.metrics,
            "model_version": self.model_version,
        }


class JobStore:
    """Archivio: al piu' `max_active` job non terminali e `max_history` terminali (FIFO)."""

    def __init__(self, *, max_active: int, max_history: int) -> None:
        self._max_active = max_active
        self._max_history = max_history
        self._jobs: OrderedDict[str, Job] = OrderedDict()

    def add(self, job: Job) -> None:
        if sum(1 for j in self._jobs.values() if not j.terminal) >= self._max_active:
            raise TooManyJobs
        self._jobs[job.id] = job

    def get(self, job_id: str) -> Job | None:
        if not isinstance(job_id, str) or JOB_ID_RE.fullmatch(job_id) is None:
            return None
        return self._jobs.get(job_id)

    def prune(self) -> None:
        finished = [j.id for j in self._jobs.values() if j.terminal]
        for job_id in finished[: max(0, len(finished) - self._max_history)]:
            del self._jobs[job_id]

    def counts(self) -> dict[JobStatus, int]:
        out = dict.fromkeys(JobStatus, 0)
        for j in self._jobs.values():
            out[j.status] += 1
        return out
