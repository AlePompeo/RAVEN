# SPDX-License-Identifier: Apache-2.0
"""Code at-least-once (spec 14): MemoryQueue (asyncio) e DurableQueue (SQLite, stdlib).

Semantica comune: `get` concede un lease di `visibility_timeout_s`; senza ack il messaggio viene
riconsegnato. `attempt` conta i tentativi che *consumano* il budget del messaggio (dopo
`max_attempts` consegne va in dead-letter con un motivo); `lease` identifica la singola consegna:
`ack`/`nack` con un lease non piu' valido (scaduto e riconsegnato) ritornano False, quindi nessun
doppio ack. `nack(count_attempt=False, delay_s=...)` rilascia il messaggio senza consumare un
tentativo e lo rende visibile dopo il ritardo: serve per guasti d'infrastruttura (non e' colpa del
messaggio) con backoff.

DurableQueue: le chiamate SQLite sono bloccanti e girano in un thread (`asyncio.to_thread` o
l'executor indicato); il loop resta libero.
"""

import asyncio
import functools
import json
import sqlite3
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import Executor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.core.ports import QueueItem

POLICIES = ("block", "drop_with_counter")
POLL_SLICE_S = 0.05
DEAD_LETTER_LIMIT = 1000
DB_SUFFIXES = (".db", ".sqlite", ".sqlite3")
MAX_PAYLOAD_BYTES = 64 * 1024  # tetto per messaggio (JSON compatto, UTF-8)


class QueueConfigError(ValueError):
    pass


class PayloadTooLarge(ValueError):
    """Messaggio oltre `max_payload_bytes`: rifiutato prima di entrare in coda."""


def epoch_monotonic_clock() -> Callable[[], float]:
    """Orologio dei lease della coda durevole: epoca all'apertura + tempo monotono.

    Immune ai salti dell'orologio di sistema (NTP, cambio manuale) dentro il processo, ma resta
    confrontabile con altri processi/riavvii sullo stesso file (stessa epoca, errore = sincronia
    dell'orologio di sistema al momento dell'apertura)."""
    offset = time.time() - time.monotonic()
    return lambda: time.monotonic() + offset


def _check_config(
    capacity: int, policy: str, max_attempts: int, visibility_timeout_s: float
) -> None:
    if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity <= 0:
        raise QueueConfigError("capacity deve essere un intero > 0")
    if policy not in POLICIES:
        raise QueueConfigError(f"policy deve essere una di {POLICIES}")
    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or max_attempts <= 0:
        raise QueueConfigError("max_attempts deve essere un intero > 0")
    if not visibility_timeout_s > 0 or visibility_timeout_s == float("inf"):
        raise QueueConfigError("visibility_timeout_s deve essere finito e > 0")


def _dump(payload: Mapping[str, Any], max_bytes: int = MAX_PAYLOAD_BYTES) -> str:
    if not isinstance(payload, Mapping):
        raise TypeError("payload deve essere una mappa")
    text = json.dumps(payload, allow_nan=False, separators=(",", ":"), sort_keys=True)
    if len(text.encode("utf-8")) > max_bytes:
        raise PayloadTooLarge(f"payload oltre il limite di {max_bytes} byte")
    return text


def _check_delay(delay_s: float) -> float:
    if not isinstance(delay_s, int | float) or not 0 <= delay_s < float("inf"):
        raise ValueError("delay_s deve essere finito e >= 0")
    return float(delay_s)


@dataclass
class _Entry:
    id: int
    payload: Mapping[str, Any]
    attempts: int = 0
    deliveries: int = 0
    deadline: float = 0.0
    not_before: float = 0.0


class MemoryQueue:
    def __init__(
        self,
        *,
        capacity: int = 1000,
        policy: str = "block",
        max_attempts: int = 3,
        visibility_timeout_s: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
        put_timeout_s: float | None = None,
        dead_letter_limit: int = DEAD_LETTER_LIMIT,
        max_payload_bytes: int = MAX_PAYLOAD_BYTES,
    ) -> None:
        _check_config(capacity, policy, max_attempts, visibility_timeout_s)
        self._max_payload = max_payload_bytes
        self._capacity, self._policy, self._max = capacity, policy, max_attempts
        self._vis, self._clock, self._put_timeout = visibility_timeout_s, clock, put_timeout_s
        self._ready: deque[_Entry] = deque()
        self._inflight: dict[int, _Entry] = {}
        self._dead: deque[dict[str, Any]] = deque(maxlen=dead_letter_limit)
        self._cond = asyncio.Condition()
        self._next_id = 1
        self._counters = {"enqueued": 0, "acked": 0, "dropped": 0, "put_timeouts": 0, "dead": 0}

    def _full(self) -> bool:
        return len(self._ready) + len(self._inflight) >= self._capacity

    def _bury(self, e: _Entry, reason: str) -> None:
        self._counters["dead"] += 1
        self._dead.append(
            {"id": e.id, "payload": dict(e.payload), "reason": reason, "attempts": e.attempts}
        )

    def _reclaim(self) -> None:
        now = self._clock()
        expired = sorted(
            (e for e in self._inflight.values() if e.deadline <= now), key=lambda e: e.id
        )
        for e in reversed(expired):
            del self._inflight[e.id]
            if e.attempts >= self._max:
                self._bury(e, "visibility_timeout_max_attempts")
            else:
                self._ready.appendleft(e)

    def _pop_due(self) -> _Entry | None:
        now = self._clock()
        for idx, e in enumerate(self._ready):
            if e.not_before <= now:
                del self._ready[idx]
                return e
        return None

    async def put(self, payload: Mapping[str, Any]) -> bool:
        _dump(payload, self._max_payload)  # stessa validazione della coda durevole
        async with self._cond:
            if self._full():
                if self._policy == "drop_with_counter":
                    self._counters["dropped"] += 1
                    return False
                try:
                    await asyncio.wait_for(
                        self._cond.wait_for(lambda: not self._full()), self._put_timeout
                    )
                except TimeoutError:
                    self._counters["put_timeouts"] += 1
                    return False
            self._ready.append(_Entry(self._next_id, dict(payload)))
            self._next_id += 1
            self._counters["enqueued"] += 1
            self._cond.notify_all()
            return True

    async def get(self, timeout_s: float | None = None) -> QueueItem | None:
        loop = asyncio.get_running_loop()
        end = None if timeout_s is None else loop.time() + timeout_s
        async with self._cond:
            while True:
                self._reclaim()
                e = self._pop_due()
                if e is not None:
                    e.attempts += 1
                    e.deliveries += 1
                    e.deadline = self._clock() + self._vis
                    self._inflight[e.id] = e
                    return QueueItem(e.id, e.payload, e.attempts, e.deliveries)
                remaining = None if end is None else end - loop.time()
                if remaining is not None and remaining <= 0:
                    return None
                wait = POLL_SLICE_S if remaining is None else min(POLL_SLICE_S, remaining)
                try:
                    await asyncio.wait_for(self._cond.wait(), wait)
                except TimeoutError:
                    pass

    def _lease(self, item: QueueItem) -> _Entry | None:
        e = self._inflight.get(item.id)
        return e if e is not None and e.deliveries == item.lease else None

    async def ack(self, item: QueueItem) -> bool:
        async with self._cond:
            e = self._lease(item)
            if e is None:
                return False
            del self._inflight[e.id]
            self._counters["acked"] += 1
            self._cond.notify_all()
            return True

    async def nack(
        self,
        item: QueueItem,
        reason: str,
        *,
        requeue: bool = True,
        delay_s: float = 0.0,
        count_attempt: bool = True,
    ) -> bool:
        delay = _check_delay(delay_s)
        async with self._cond:
            e = self._lease(item)
            if e is None:
                return False
            del self._inflight[e.id]
            if requeue and not count_attempt:
                e.attempts -= 1  # guasto d'infrastruttura: il messaggio non ha colpa
                e.not_before = self._clock() + delay
                self._ready.appendleft(e)
            elif requeue and e.attempts < self._max:
                e.not_before = self._clock() + delay
                self._ready.appendleft(e)
            else:
                self._bury(e, reason if not requeue else f"max_attempts:{reason}")
            self._cond.notify_all()
            return True

    def dead_letters(self) -> Sequence[Mapping[str, Any]]:
        return list(self._dead)

    def stats(self) -> Mapping[str, int]:
        c = self._counters
        return {
            "depth": len(self._ready) + len(self._inflight),
            "ready": len(self._ready),
            "inflight": len(self._inflight),
            "dead_letter": c["dead"],
            "dropped": c["dropped"],
            "put_timeouts": c["put_timeouts"],
            "enqueued": c["enqueued"],
            "acked": c["acked"],
        }

    def close(self) -> None:
        """Nulla da rilasciare (simmetria con DurableQueue)."""


def validate_db_path(path: str | Path, base_dir: Path | None = None) -> Path:
    """Valida il percorso del file della coda: niente URI/memoria, estensione, dir esistente."""
    raw = str(path)
    if not raw or "\x00" in raw or raw == ":memory:" or raw.startswith("file:"):
        raise QueueConfigError("percorso della coda non valido")
    p = Path(raw)
    resolved = p.parent.resolve() / p.name  # risolve symlink e ".." nella directory
    if p.name in ("", ".", "..") or resolved.suffix not in DB_SUFFIXES:
        raise QueueConfigError(f"il file della coda deve avere estensione {DB_SUFFIXES}")
    if not resolved.parent.is_dir():
        raise QueueConfigError("la directory del file della coda non esiste")
    if resolved.is_dir() or resolved.is_symlink():
        raise QueueConfigError("il file della coda non puo' essere una directory o un symlink")
    if base_dir is not None and not resolved.parent.is_relative_to(base_dir.resolve()):
        raise QueueConfigError("il file della coda e' fuori dalla directory consentita")
    return resolved


_SCHEMA = """
CREATE TABLE IF NOT EXISTS items(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  payload TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  deliveries INTEGER NOT NULL DEFAULT 0,
  state TEXT NOT NULL CHECK(state IN ('ready','inflight','dead')),
  visible_at REAL NOT NULL DEFAULT 0,
  reason TEXT,
  enqueued_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_items_state ON items(state, id);
"""


class DurableQueue:
    """Coda su SQLite (WAL). Durevolezza: sopravvive al crash del processo; `synchronous=NORMAL`
    non protegge dall'interruzione di corrente dell'ultimo commit (limite dichiarato)."""

    def __init__(
        self,
        path: str | Path,
        *,
        capacity: int = 10_000,
        policy: str = "block",
        max_attempts: int = 3,
        visibility_timeout_s: float = 30.0,
        clock: Callable[[], float] | None = None,
        put_timeout_s: float | None = None,
        poll_s: float = 0.01,
        base_dir: Path | None = None,
        require_base_dir: bool = False,
        dead_letter_limit: int = DEAD_LETTER_LIMIT,
        executor: Executor | None = None,
        max_payload_bytes: int = MAX_PAYLOAD_BYTES,
    ) -> None:
        _check_config(capacity, policy, max_attempts, visibility_timeout_s)
        if require_base_dir and base_dir is None:
            raise QueueConfigError("base_dir obbligatoria: il file della coda va confinato")
        self._max_payload = max_payload_bytes
        self._path = validate_db_path(path, base_dir)
        self._capacity, self._policy, self._max = capacity, policy, max_attempts
        self._vis, self._put_timeout = visibility_timeout_s, put_timeout_s
        self._clock = clock or epoch_monotonic_clock()
        self._poll, self._dl_limit, self._executor = poll_s, dead_letter_limit, executor
        self._lock = threading.RLock()
        self._counters = {"dropped": 0, "put_timeouts": 0, "enqueued": 0, "acked": 0}
        self._con: sqlite3.Connection | None = sqlite3.connect(
            self._path, isolation_level=None, check_same_thread=False, timeout=5.0
        )
        with self._lock:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA synchronous=NORMAL")
            self._db.execute("PRAGMA busy_timeout=5000")
            self._db.executescript(_SCHEMA)
            cols = {r[1] for r in self._db.execute("PRAGMA table_info(items)")}
            if "deliveries" not in cols:  # file creato da una versione precedente
                self._db.execute(
                    "ALTER TABLE items ADD COLUMN deliveries INTEGER NOT NULL DEFAULT 0"
                )

    @property
    def _db(self) -> sqlite3.Connection:
        if self._con is None:
            raise RuntimeError("coda chiusa")
        return self._con

    def close(self) -> None:
        with self._lock:
            if self._con is not None:
                self._con.close()
                self._con = None

    async def _off(self, fn: Callable[..., Any], *args: Any) -> Any:
        """SQLite e' bloccante: lo si esegue in un thread, il loop resta libero."""
        if self._con is None:
            raise RuntimeError("coda chiusa")
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, functools.partial(fn, *args))

    def _trim_dead(self) -> None:
        self._db.execute(
            "DELETE FROM items WHERE state='dead' AND id NOT IN "
            "(SELECT id FROM items WHERE state='dead' ORDER BY id DESC LIMIT ?)",
            (self._dl_limit,),
        )

    def _try_put(self, text: str) -> bool:
        with self._lock:
            db = self._db
            db.execute("BEGIN IMMEDIATE")
            try:
                (n,) = db.execute("SELECT COUNT(*) FROM items WHERE state!='dead'").fetchone()
                if n >= self._capacity:
                    db.execute("ROLLBACK")
                    return False
                db.execute(
                    "INSERT INTO items(payload, state, enqueued_at) VALUES (?, 'ready', ?)",
                    (text, self._clock()),
                )
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise
            self._counters["enqueued"] += 1
            return True

    async def put(self, payload: Mapping[str, Any]) -> bool:
        text = _dump(payload, self._max_payload)
        end = None if self._put_timeout is None else time.monotonic() + self._put_timeout
        while True:
            if await self._off(self._try_put, text):
                return True
            if self._policy == "drop_with_counter":
                self._counters["dropped"] += 1
                return False
            if end is not None and time.monotonic() >= end:
                self._counters["put_timeouts"] += 1
                return False
            await asyncio.sleep(self._poll)

    def _try_get(self) -> QueueItem | None:
        with self._lock:
            db = self._db
            db.execute("BEGIN IMMEDIATE")
            try:
                now = self._clock()
                buried = db.execute(
                    "UPDATE items SET state='dead', reason='visibility_timeout_max_attempts' "
                    "WHERE state='inflight' AND visible_at<=? AND attempts>=?",
                    (now, self._max),
                ).rowcount
                if buried:
                    self._trim_dead()
                row = db.execute(
                    "SELECT id, payload, attempts, deliveries FROM items "
                    "WHERE state IN ('ready','inflight') AND visible_at<=? "
                    "ORDER BY id LIMIT 1",
                    (now,),
                ).fetchone()
                item = None
                if row is not None:
                    rid, text, attempts, deliveries = row
                    db.execute(
                        "UPDATE items SET state='inflight', attempts=?, deliveries=?, "
                        "visible_at=? WHERE id=?",
                        (attempts + 1, deliveries + 1, now + self._vis, rid),
                    )
                    item = QueueItem(rid, json.loads(text), attempts + 1, deliveries + 1)
                db.execute("COMMIT")
                return item
            except BaseException:
                db.execute("ROLLBACK")
                raise

    async def get(self, timeout_s: float | None = None) -> QueueItem | None:
        end = None if timeout_s is None else time.monotonic() + timeout_s
        while True:
            item: QueueItem | None = await self._off(self._try_get)
            if item is not None:
                return item
            if end is not None and time.monotonic() >= end:
                return None
            await asyncio.sleep(self._poll)

    def _ack(self, item: QueueItem) -> bool:
        with self._lock:
            cur = self._db.execute(
                "DELETE FROM items WHERE id=? AND state='inflight' AND deliveries=?",
                (item.id, item.lease),
            )
            if cur.rowcount == 1:
                self._counters["acked"] += 1
                return True
            return False

    async def ack(self, item: QueueItem) -> bool:
        return bool(await self._off(self._ack, item))

    def _nack(
        self, item: QueueItem, reason: str, requeue: bool, delay_s: float, count_attempt: bool
    ) -> bool:
        with self._lock:
            db = self._db
            db.execute("BEGIN IMMEDIATE")
            try:
                row = db.execute(
                    "SELECT attempts FROM items WHERE id=? AND state='inflight' AND deliveries=?",
                    (item.id, item.lease),
                ).fetchone()
                if row is None:
                    db.execute("ROLLBACK")
                    return False
                attempts = row[0]
                visible_at = self._clock() + delay_s
                if requeue and not count_attempt:
                    db.execute(
                        "UPDATE items SET state='ready', attempts=?, visible_at=? WHERE id=?",
                        (attempts - 1, visible_at, item.id),
                    )
                elif requeue and attempts < self._max:
                    db.execute(
                        "UPDATE items SET state='ready', visible_at=? WHERE id=?",
                        (visible_at, item.id),
                    )
                else:
                    why = reason if not requeue else f"max_attempts:{reason}"
                    db.execute("UPDATE items SET state='dead', reason=? WHERE id=?", (why, item.id))
                    self._trim_dead()
                db.execute("COMMIT")
                return True
            except BaseException:
                db.execute("ROLLBACK")
                raise

    async def nack(
        self,
        item: QueueItem,
        reason: str,
        *,
        requeue: bool = True,
        delay_s: float = 0.0,
        count_attempt: bool = True,
    ) -> bool:
        delay = _check_delay(delay_s)
        return bool(await self._off(self._nack, item, reason, requeue, delay, count_attempt))

    def dead_letters(self) -> Sequence[Mapping[str, Any]]:
        with self._lock:
            rows = self._db.execute(
                "SELECT id, payload, reason, attempts FROM items WHERE state='dead' ORDER BY id"
            ).fetchall()
        return [
            {"id": i, "payload": json.loads(p), "reason": r, "attempts": a} for i, p, r, a in rows
        ]

    def stats(self) -> Mapping[str, int]:
        with self._lock:
            counts = dict(self._db.execute("SELECT state, COUNT(*) FROM items GROUP BY state"))
        ready, inflight = counts.get("ready", 0), counts.get("inflight", 0)
        return {
            "depth": ready + inflight,
            "ready": ready,
            "inflight": inflight,
            "dead_letter": counts.get("dead", 0),
            "dropped": self._counters["dropped"],
            "put_timeouts": self._counters["put_timeouts"],
            "enqueued": self._counters["enqueued"],
            "acked": self._counters["acked"],
        }
