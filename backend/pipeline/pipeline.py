# SPDX-License-Identifier: Apache-2.0
"""Colla della pipeline: coda -> processor -> raw + clean (+ curated). At-least-once, idempotente.

Un `drain_once` legge un batch, valida/normalizza ogni messaggio (isolato: un messaggio che fallisce
non tocca i vicini), scrive `raw` (tutto cio' che arriva da una sorgente valida, scarti compresi) e
`clean` (deduplicato) e solo dopo conferma (ack) ogni messaggio.

Dedup transazionale: la chiave viene ammessa provvisoriamente, confermata (`commit`) solo dopo la
scrittura Parquet durevole del suo file e rilasciata su QUALUNQUE altra uscita (eccezione, scrittura
parziale su piu' giorni, BaseException). Il retry di un record non scritto non e' quindi mai un falso
duplicato; quello di un record gia' scritto lo e' (ed e' corretto). Un crash fra scrittura e ack
produce una riconsegna: `clean` resta corretto grazie alla chiave, `raw` puo' contenere il record due
volte (e' il registro di cio' che e' arrivato, non e' deduplicato).
"""

import asyncio
import functools
import hashlib
import json
import logging
import math
import random
import threading
from collections import OrderedDict
from collections.abc import Callable, Mapping
from concurrent.futures import Executor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from backend.core.ports import IngestSource, Processor, Queue, QueueItem
from backend.pipeline.metrics import (
    PipelineMetrics,
    check_clean_rows,
    check_curated_rows,
    check_raw_rows,
)
from backend.pipeline.processors import SOURCE_RE, Deduplicator, try_parse_time
from backend.pipeline.queues import PayloadTooLarge
from backend.pipeline.reserved import CANARY_SOURCE
from backend.pipeline.store import LayerBusy, LockOrderError, ParquetStore

log = logging.getLogger(__name__)
INVALID_SOURCE = "_invalid"

_ACK = "ack"
_DEAD = "dead"  # scarto definitivo (record non valido)
_POISON = "poison"  # il messaggio stesso non e' elaborabile: retry che consuma un tentativo
_INFRA = "infra"  # guasto d'infrastruttura (disco...): retry con backoff, tetto per messaggio
_INFRA_TYPES = (OSError, LayerBusy, MemoryError, LockOrderError)


@dataclass(frozen=True)
class DrainResult:
    processed: int = 0
    clean_rows: int = 0
    duplicates: int = 0
    rejected: int = 0
    requeued: int = 0

    @property
    def progressed(self) -> bool:
        """Almeno un messaggio e' stato chiuso (ack o dead-letter): ha senso rileggere subito."""
        return self.processed > self.requeued

    def __add__(self, other: "DrainResult") -> "DrainResult":
        return DrainResult(
            self.processed + other.processed,
            self.clean_rows + other.clean_rows,
            self.duplicates + other.duplicates,
            self.rejected + other.rejected,
            self.requeued + other.requeued,
        )


@dataclass
class _Outcome:
    kind: str
    reason: str = ""


Entry = tuple[int, dict[str, Any]]


def _poison(exc: BaseException) -> "_Outcome":
    """Una riga che lo store non riesce a scrivere (non e' un guasto di infrastruttura)."""
    return _Outcome(_DEAD, f"store_rejected:{type(exc).__name__}")


def _source_of(payload: Mapping[str, Any]) -> str | None:
    s = payload.get("source_id")
    return s if isinstance(s, str) and SOURCE_RE.fullmatch(s) else None


def _day(dt: datetime) -> str:
    return dt.astimezone(UTC).date().isoformat()


def _sanitise(obj: Any) -> Any:
    """Rende il record serializzabile in JSON stretto: float non finiti -> testo ("nan", "inf")."""
    if isinstance(obj, float) and not math.isfinite(obj):
        return str(obj)
    if isinstance(obj, Mapping):
        return {str(k): _sanitise(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_sanitise(v) for v in obj]
    return obj


class BatchInterrupted(BaseException):
    """Il batch e' stato fermato (cancellazione): nessun'altra scrittura deve partire."""


_CACHE_MAX = 100_000
_PROBE_SIZE = 5


def _ikey(item: QueueItem) -> tuple[int, str]:
    """Identita' di un messaggio per l'idempotenza interna: id di coda + hash del payload."""
    try:
        text = json.dumps(item.payload, sort_keys=True, allow_nan=False, default=str)
    except (TypeError, ValueError):
        text = ""
    return item.id, hashlib.blake2b(text.encode(), digest_size=8).hexdigest()


class Pipeline:
    def __init__(
        self,
        *,
        queue: Queue,
        processor: Processor,
        store: ParquetStore,
        metrics: PipelineMetrics,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        batch_size: int = 500,
        dedup: Deduplicator | None = None,
        executor: Executor | None = None,
        backoff_base_s: float = 1.0,
        backoff_cap_s: float = 60.0,
        rng: Callable[[], float] = random.random,
        max_infra_retries: int = 20,
        poison_breaker: int = 50,
        breaker_backoff_s: float = 30.0,
        shutdown_wait_s: float = 30.0,
    ) -> None:
        if not 0 < shutdown_wait_s < float("inf"):
            raise ValueError("shutdown_wait_s deve essere finito e > 0")
        self._shutdown_wait_s = shutdown_wait_s
        self._probe_unhealthy = False
        if max_infra_retries < 1:
            raise ValueError("max_infra_retries deve essere >= 1")
        if poison_breaker < 1:
            raise ValueError("poison_breaker deve essere >= 1")
        if breaker_backoff_s <= 0:
            raise ValueError("breaker_backoff_s deve essere > 0")
        self._max_infra_retries = max_infra_retries
        if batch_size < 1:
            raise ValueError("batch_size deve essere >= 1")
        if not 0 < backoff_base_s <= backoff_cap_s:
            raise ValueError("backoff: 0 < base <= cap")
        self.queue, self.processor, self.store = queue, processor, store
        self.metrics, self._clock, self._batch = metrics, clock, batch_size
        self.dedup = dedup or Deduplicator(loader=store.clean_keys)
        self._dirty: set[tuple[str, str]] = set()
        self._dirty_lock = threading.Lock()
        self._lock = asyncio.Lock()
        # un thread di batch gia' avviato non e' interrompibile: la cancellazione del job non deve
        # far partire un secondo batch in parallelo sullo stesso stato di dedup
        self._batch_lock = threading.Lock()
        self._executor = executor
        self._backoff = (backoff_base_s, backoff_cap_s, rng)
        self._infra_failures = 0
        self._gate_until: datetime | None = None
        # idempotenza interna (per riconsegne e bisezioni): cosa e' gia' su disco per un messaggio
        self._done_raw: OrderedDict[tuple[int, str], str] = OrderedDict()
        self._done_clean: OrderedDict[tuple[int, str], None] = OrderedDict()
        self._batch_stop = threading.Event()
        # circuit breaker sui veleni consecutivi (regressione dello store)
        self._breaker_n = poison_breaker
        self._breaker_base = breaker_backoff_s
        self._breaker_cap = max(600.0, breaker_backoff_s)
        self._consec_poison = 0
        self._breaker_until: datetime | None = None
        self._breaker_level = 0
        self._breaker_opened = 0

    async def _run(self, fn: Callable[..., Any], *args: Any) -> Any:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, functools.partial(fn, *args))

    def backoff_remaining_s(self) -> float:
        if self._gate_until is None:
            return 0.0
        return max(0.0, (self._gate_until - self._clock()).total_seconds())

    def _item_delay(self, attempt: int) -> float:
        """Ritardo per-messaggio (senza fermare gli altri) dopo un bug interno."""
        base, cap, rng = self._backoff
        return float(min(cap, base * 2 ** max(0, attempt - 1)) * (0.5 + 0.5 * rng()))

    def _register_infra_failure(self) -> float:
        base, cap, rng = self._backoff
        self._infra_failures += 1
        delay = float(min(cap, base * 2 ** (self._infra_failures - 1)) * (0.5 + 0.5 * rng()))
        self._gate_until = self._clock() + timedelta(seconds=delay)
        return delay

    # ---- circuit breaker ----

    def _breaker_state(self) -> str:
        if self._breaker_until is None:
            return "ok"
        return "breaker_open" if self._clock() < self._breaker_until else "half_open"

    def status(self) -> dict[str, Any]:
        """Stato del drain: ok | breaker_open | half_open (+ contatori per metriche/allarmi)."""
        until = self._breaker_until
        return {
            "state": self._breaker_state(),
            "breaker_opened": self._breaker_opened,
            "consecutive_store_rejected": self._consec_poison,
            "poison_breaker": self._breaker_n,
            "breaker_until_utc": until.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            if until
            else None,
            "backoff_remaining_s": self.backoff_remaining_s(),
        }

    def _trip_breaker(self) -> float:
        self._breaker_level += 1
        _, _, rng = self._backoff
        delay = float(
            min(self._breaker_cap, self._breaker_base * 2 ** (self._breaker_level - 1))
            * (0.5 + 0.5 * rng())
        )
        self._breaker_until = self._clock() + timedelta(seconds=delay)
        self._breaker_opened += 1
        log.error(
            "ALLARME: circuit breaker aperto dopo %d scarti consecutivi 'store_rejected' senza "
            "nessuna scrittura riuscita (regressione dello store?): drain in pausa %.0f s",
            self._consec_poison,
            delay,
        )
        return delay

    async def _release(self, items: list[QueueItem], delay_s: float = 0.0) -> None:
        for item in items:
            await self.queue.nack(item, "interrupted", count_attempt=False, delay_s=delay_s)

    def _canary_ok(self) -> bool:
        """Sonda di salute: una scrittura nota-buona sullo STESSO percorso dello store (layer clean,
        sorgente riservata, subito cancellata e mai visibile ai lettori). Falsa se lo store rifiuta
        o fallisce; vera se i veleni visti prima sono quindi davvero messaggi cattivi."""
        now = self._clock()
        row = {
            "source_id": CANARY_SOURCE,
            "site_id": "canary",
            "t_utc": now,
            "schema_version": "1.0.0",
            "power_w": 0.0,
            "link_margin_db": None,
            "sun_az_deg": None,
            "sun_el_deg": None,
            "earth_az_deg": None,
            "earth_el_deg": None,
            "received_utc": now,
            "raw_file_id": "canary",
        }
        try:
            self.store.write("clean", CANARY_SOURCE, [row])
            return True
        except Exception:  # noqa: BLE001
            return False
        finally:
            try:
                self.store.discard_canary()
            except OSError:
                log.warning("pulizia del canarino di salute fallita")

    async def _await_thread(self, fut: "asyncio.Future[Any]") -> Any:
        """Dopo una cancellazione: attende il thread del batch (che si ferma alla prossima verifica
        cooperativa) anche se arrivano altre cancel(); al massimo `shutdown_wait_s`, poi ALLARME.
        Ritorna il risultato del thread, oppure None se e' fallito/interrotto/ancora in corso."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._shutdown_wait_s
        while not fut.done():
            remaining = deadline - loop.time()
            if remaining <= 0:
                log.error(
                    "ALLARME: il thread del batch non si e' fermato entro %.1f s dalla cancellazione: "
                    "rilascio comunque i messaggi (possibile scrittura tardiva, idempotente)",
                    self._shutdown_wait_s,
                )
                return None
            try:
                await asyncio.wait_for(asyncio.shield(fut), remaining)
            except asyncio.CancelledError:
                continue  # un'altra cancel(): si continua ad attendere il thread
            except TimeoutError:
                continue
            except BaseException:  # noqa: BLE001  il thread e' terminato con un errore
                break
        if fut.cancelled() or fut.exception() is not None:
            return None
        return fut.result()

    async def drain_once(self) -> DrainResult:
        async with self._lock:  # un solo batch alla volta: il Deduplicator non e' thread-safe
            if self.backoff_remaining_s() > 0:  # guasto recente: non girare a vuoto
                return DrainResult()
            state = self._breaker_state()
            if state == "breaker_open":
                return DrainResult()
            limit = self._batch
            self._probe_unhealthy = False
            if state == "half_open":
                if self.queue.stats()["ready"] == 0:
                    return (
                        DrainResult()
                    )  # niente da fare: il canarino non serve (e non lo si ripete)
                if await self._run(self._canary_ok):
                    # lo store scrive: i messaggi cattivi lo sono davvero, si riparte con tetto N per
                    # intervallo e backoff base (il livello non cresce con una testa lunga di veleni)
                    self._breaker_until, self._consec_poison = None, 0
                    self._breaker_level = 0
                else:
                    self._probe_unhealthy = True
                    limit = _PROBE_SIZE
            items: list[QueueItem] = []
            while len(items) < limit:
                item = await self.queue.get(timeout_s=0)
                if item is None:
                    break
                items.append(item)
            if not items:
                return DrainResult()
            stop = threading.Event()
            self._batch_stop = stop
            loop = asyncio.get_running_loop()
            fut = loop.run_in_executor(
                self._executor, functools.partial(self._process_batch_safe, items, stop)
            )
            try:
                outcomes, stats = await asyncio.shield(fut)
            except asyncio.CancelledError:
                # il thread non si uccide: gli si dice di fermarsi prima della prossima scrittura e
                # lo si attende (anche a fronte di altre cancel); se ha gia' finito si applicano i
                # suoi esiti, altrimenti si rilascia
                stop.set()
                done = await self._await_thread(fut)
                if done is None:
                    await self._release(items)
                else:
                    await self._apply(items, *done)
                raise
            except (
                BaseException
            ):  # interruzione vera (KeyboardInterrupt...): niente tentativi persi
                stop.set()
                await self._release(items)
                raise
            return await self._apply(items, outcomes, stats)

    # ---- scrittura isolata ----

    def _write_isolated(
        self,
        layer: str,
        source: str,
        entries: list[Entry],
        stop: threading.Event,
        on_written: Callable[[int, dict[str, Any], str], None],
    ) -> tuple[list[Entry], dict[int, _Outcome]]:
        """Scrive un gruppo (stessa sorgente e giorno). Se una riga non e' conforme (StoreError) il
        gruppo viene riscritto riga per riga: solo la riga velenosa fallisce, i vicini passano.
        Ritorna (voci scritte, esiti di fallimento per indice).
        Controlla `stop` prima di OGNI scrittura (cancellazione cooperativa) e chiama `on_written`
        SUBITO dopo ogni scrittura durevole (file o riga), cosi' un'interruzione a meta' non perde
        traccia di cio' che e' gia' su disco."""
        if stop.is_set():
            raise BatchInterrupted
        try:
            (fid,) = self.store.write(layer, source, [r for _, r in entries])
        except _INFRA_TYPES:
            # disco pieno, EIO, EMFILE, memoria, lock occupato...: non e' colpa dei messaggi
            log.exception("scrittura %s fallita (infrastruttura)", layer)
            return [], {i: _Outcome(_INFRA, "store_error") for i, _ in entries}
        except Exception as e:  # noqa: BLE001
            if len(entries) == 1:  # riga singola: e' lei il veleno, dead-letter subito
                log.warning("riga rifiutata da %s: %s", layer, type(e).__name__)
                return [], {entries[0][0]: _poison(e)}
            log.warning(
                "gruppo rifiutato da %s/%s (%s): isolo riga per riga",
                layer,
                source,
                type(e).__name__,
            )
            ok: list[Entry] = []
            failed: dict[int, _Outcome] = {}
            for idx, row in entries:
                if stop.is_set():
                    raise BatchInterrupted from None
                try:
                    (rid,) = self.store.write(layer, source, [row])
                except _INFRA_TYPES:
                    log.exception("scrittura %s fallita (infrastruttura)", layer)
                    failed[idx] = _Outcome(_INFRA, "store_error")
                except Exception as e2:  # noqa: BLE001
                    failed[idx] = _poison(e2)
                else:
                    ok.append((idx, row))
                    on_written(idx, row, rid)
            return ok, failed
        for idx, row in entries:
            on_written(idx, row, fid)
        return entries, {}

    # ---- parte bloccante del batch ----

    def _process_batch_safe(
        self, items: list[QueueItem], stop: threading.Event
    ) -> tuple[list[_Outcome], dict[str, int]]:
        """Come `_process_batch`, ma un'eccezione inattesa (bug) non fa fallire tutto il batch:
        lo si biseca fino a isolare il messaggio colpevole (tentativo consumato, ritardo, solo il
        tipo dell'errore nel log/motivo, mai il payload). Le BaseException non sono catturate.
        Le scritture gia' fatte in un tentativo sono ricordate (`_done_raw`/`_done_clean`): le
        riesecuzioni non le ripetono e le metriche non le contano due volte."""
        try:
            return self._process_batch(items, stop)
        except Exception as e:  # noqa: BLE001
            log.error("errore interno nel batch (%s): bisezione", type(e).__name__)
            if len(items) == 1:
                return (
                    [_Outcome(_POISON, f"internal_error:{type(e).__name__}")],
                    {"clean_rows": 0, "duplicates": 0},
                )
            mid = len(items) // 2
            o1, s1 = self._process_batch_safe(items[:mid], stop)
            o2, s2 = self._process_batch_safe(items[mid:], stop)
            return o1 + o2, {k: s1[k] + s2[k] for k in s1}

    def _process_batch(
        self, items: list[QueueItem], stop: threading.Event
    ) -> tuple[list[_Outcome], dict[str, int]]:
        """Parte bloccante (CPU/disco). Le chiavi di dedup si confermano solo dopo la scrittura
        durevole; qualunque altra uscita (anche BaseException) le rilascia."""
        with self._batch_lock:
            try:
                return self._process_batch_inner(items, stop)
            finally:
                self.dedup.rollback_pending()

    @staticmethod
    def _remember(cache: "OrderedDict[tuple[int, str], Any]", key: tuple[int, str], v: Any) -> None:
        cache[key] = v
        cache.move_to_end(key)
        while len(cache) > _CACHE_MAX:
            cache.popitem(last=False)

    def _process_batch_inner(
        self, items: list[QueueItem], stop: threading.Event
    ) -> tuple[list[_Outcome], dict[str, int]]:
        now = self._clock()
        keys = [_ikey(item) for item in items]
        outcomes: dict[int, _Outcome] = {}
        rows_of: dict[int, list[dict[str, Any]]] = {}
        stats = {"clean_rows": 0, "duplicates": 0}

        # 1. validazione/normalizzazione, isolata per messaggio
        for i, item in enumerate(items):
            if stop.is_set():
                raise BatchInterrupted
            if keys[i] in self._done_clean:  # gia' scritto da un tentativo precedente
                outcomes[i] = _Outcome(_ACK)
                continue
            try:
                rows = self.processor.process(item.payload)
            except ValueError as e:  # record non valido: niente retry
                outcomes[i] = _Outcome(_DEAD, str(getattr(e, "reason", "invalid_record")))
                continue
            except Exception:
                log.exception("processor fallito")
                outcomes[i] = _Outcome(_POISON, "processor_error")
                continue
            if rows:
                rows_of[i] = [dict(r) for r in rows]
            else:
                outcomes[i] = _Outcome(_ACK)

        # 2. raw per (sorgente, giorno di ricezione); stessa funzione di parsing del processor
        raw_groups: dict[tuple[str, str], list[Entry]] = {}
        raw_id_of: dict[int, str] = {}
        for i, item in enumerate(items):
            src = _source_of(item.payload)
            if src is None or (i in outcomes and outcomes[i].kind == _ACK):
                continue
            if keys[i] in self._done_raw:  # raw gia' scritto (riconsegna/bisezione): idempotente
                raw_id_of[i] = self._done_raw[keys[i]]
                continue
            rcv = (
                rows_of[i][0]["received_utc"]
                if i in rows_of
                else try_parse_time(item.payload.get("received_utc")) or now
            )
            raw_groups.setdefault((src, _day(rcv)), []).append(
                (
                    i,
                    {
                        "received_utc": rcv,
                        "payload_json": json.dumps(item.payload, allow_nan=False),
                    },
                )
            )

        def on_raw(idx: int, _row: dict[str, Any], fid: str) -> None:
            raw_id_of[idx] = fid
            self._remember(self._done_raw, keys[idx], fid)
            self.metrics.add("raw", _source_of(items[idx].payload) or INVALID_SOURCE, in_=1, out=1)

        for (src, _d), entries in raw_groups.items():
            ok, failed = self._write_isolated("raw", src, entries, stop, on_raw)
            outcomes.update(failed)
            if ok:
                self.metrics.record_checks("raw", check_raw_rows([r for _, r in ok]))

        # 3. dedup provvisorio -> scrittura clean per (sorgente, giorno del dato) -> commit
        new_entries: dict[tuple[str, str], list[Entry]] = {}
        pending_dups: list[Entry] = []
        late: dict[int, bool] = {}
        for i, rows in rows_of.items():
            if i in outcomes:  # scartato/fallito (p.es. raw non scritto)
                continue
            src = rows[0]["source_id"]
            admitted: list[dict[str, Any]] = []
            staged: list[tuple[tuple[str, str], Entry]] = []
            try:
                for row in rows:
                    row["raw_file_id"] = raw_id_of[i]
                    adm = self.dedup.admit(row)
                    if adm.is_new:
                        admitted.append(row)
                        late[id(row)] = adm.out_of_order
                        staged.append(((src, _day(row["t_utc"])), (i, row)))
                    elif adm.pending:
                        pending_dups.append((i, row))
                    else:
                        stats["duplicates"] += 1
                        self.metrics.add("clean", src, in_=1, dropped=1)
            except Exception:
                log.exception("dedup fallito")
                outcomes[i] = _Outcome(_INFRA, "dedup_error")
                for row in admitted:  # rilascia solo le chiavi provvisorie di questo messaggio
                    self.dedup.forget(row)
                continue
            for key, entry in staged:
                new_entries.setdefault(key, []).append(entry)

        committed: dict[int, int] = {}

        def on_clean(idx: int, row: dict[str, Any], _fid: str) -> None:
            self.dedup.commit(row)  # durevole: la chiave resta anche se il batch viene interrotto
            src = row["source_id"]
            committed[idx] = committed.get(idx, 0) + 1
            if committed[idx] == len(rows_of[idx]):  # messaggio interamente su disco
                self._remember(self._done_clean, keys[idx], None)
            with self._dirty_lock:
                self._dirty.add((src, _day(row["t_utc"])))
            self.metrics.seen(src, data_t=row["t_utc"])
            if late.get(id(row)):
                self.metrics.count(src, "out_of_order")
            self.metrics.add("clean", src, in_=1, out=1)
            stats["clean_rows"] += 1

        for (src, _d), entries in new_entries.items():
            ok, failed = self._write_isolated("clean", src, entries, stop, on_clean)
            for idx, out in failed.items():
                outcomes[idx] = out
            for idx, row in entries:
                if idx in failed:
                    self.dedup.forget(row)  # rilasciata: il retry non e' un falso duplicato
            if ok:
                self.metrics.record_checks("clean", check_clean_rows([r for _, r in ok], now))

        # 4. duplicati di chiavi pendenti: ack solo se l'originale e' durevole, altrimenti retry
        for i, row in pending_dups:
            if self.dedup.is_committed(row):
                stats["duplicates"] += 1
                self.metrics.add("clean", row["source_id"], in_=1, dropped=1)
            elif i not in outcomes:
                outcomes[i] = _Outcome(_INFRA, "original_not_durable")

        result: list[_Outcome] = []
        for i, item in enumerate(items):
            out = outcomes.get(i) or _Outcome(_ACK)
            result.append(out)
            src = _source_of(item.payload)
            if src and i in rows_of and out.kind == _ACK:
                self.metrics.seen(src)
        return result, stats

    # ---- esito verso la coda ----

    async def _apply(
        self, items: list[QueueItem], outcomes: list[_Outcome], stats: dict[str, int]
    ) -> DrainResult:
        rejected = requeued = 0
        infra = any(o.kind == _INFRA for o in outcomes)
        delay = self._register_infra_failure() if infra else 0.0
        if not infra:
            self._infra_failures, self._gate_until = 0, None
        # prova che lo store funziona: i veleni di questo batch sono veleni veri, il breaker si chiude
        healthy = stats["clean_rows"] > 0 or stats["duplicates"] > 0
        if healthy:
            self._consec_poison = 0
            self._breaker_until, self._breaker_level = None, 0
        tripped_now = False
        for item, out in zip(items, outcomes, strict=True):
            src = _source_of(item.payload) or INVALID_SOURCE
            if out.kind == _ACK:
                await self.queue.ack(item)  # False = lease perso: riconsegnato, idempotente
            elif out.kind == _DEAD:
                if out.reason.startswith("store_rejected") and not healthy:
                    if self._probe_unhealthy or self._consec_poison >= self._breaker_n:
                        # breaker gia' scattato: non si svuota lo stream in dead-letter, si rilascia
                        if not tripped_now:
                            self._trip_breaker()
                            tripped_now = True
                        requeued += 1
                        await self.queue.nack(
                            item, "breaker_open", count_attempt=False, delay_s=self._breaker_wait()
                        )
                        continue
                    self._consec_poison += 1
                    rejected += 1
                    self.metrics.add("clean", src, in_=1, dead_letter=1)
                    await self.queue.nack(item, out.reason, requeue=False)
                    if self._consec_poison >= self._breaker_n and not tripped_now:
                        self._trip_breaker()
                        tripped_now = True
                    continue
                rejected += 1
                self.metrics.add("clean", src, in_=1, dead_letter=1)
                await self.queue.nack(item, out.reason, requeue=False)
            else:
                requeued += 1
                if out.kind == _INFRA:  # non e' colpa del messaggio: niente tentativo, con ritardo
                    self.metrics.count(src, "store_errors")
                    if item.lease >= self._max_infra_retries:
                        requeued -= 1
                        rejected += 1
                        log.error(
                            "ALLARME: messaggio in dead-letter dopo %d consegne per guasto "
                            "persistente dell'infrastruttura (sorgente %s)",
                            item.lease,
                            src,
                        )
                        self.metrics.count(src, "infra_retry_exhausted")
                        self.metrics.add("clean", src, dead_letter=1)
                        await self.queue.nack(item, "infra_retry_exhausted", requeue=False)
                    else:
                        await self.queue.nack(item, out.reason, count_attempt=False, delay_s=delay)
                elif out.reason.startswith("internal_error"):
                    await self.queue.nack(item, out.reason, delay_s=self._item_delay(item.attempt))
                else:
                    await self.queue.nack(item, out.reason)
        return DrainResult(
            processed=len(items),
            clean_rows=stats["clean_rows"],
            duplicates=stats["duplicates"],
            rejected=rejected,
            requeued=requeued,
        )

    def _breaker_wait(self) -> float:
        if self._breaker_until is None:
            return 0.0
        return max(0.0, (self._breaker_until - self._clock()).total_seconds())

    async def drain_until_idle(
        self, *, max_batches: int = 1000, should_stop: Callable[[], bool] = lambda: False
    ) -> DrainResult:
        """Svuota la coda a batch; si ferma se non c'e' progresso (backoff, soli errori)."""
        total = DrainResult()
        for _ in range(max_batches):
            if should_stop():
                break
            r = await self.drain_once()
            total = total + r
            if not r.progressed:
                break
        return total

    async def curate_once(self, should_stop: Callable[[], bool] = lambda: False) -> int:
        """Ricostruisce i curated delle partizioni clean modificate (fuori dal loop)."""
        return int(await self._run(self.curate_sync, should_stop))

    def curate_sync(self, should_stop: Callable[[], bool]) -> int:
        done = 0
        with self._dirty_lock:
            todo = sorted(self._dirty)
        for src, day in todo:
            if should_stop():
                break
            try:
                if self.store.build_curated(src, day) is None:
                    self._discard(src, day)
                    continue
                n_in = self.store.read("clean", src, day).num_rows
                cur = self.store.read("curated", src, day)
            except LayerBusy:
                continue  # ricostruzione/retention in corso altrove: resta "dirty", riprova
            except Exception:
                log.exception("curated fallito per %s %s", src, day)
                self.metrics.count(src, "curate_errors")
                continue
            self._discard(src, day)
            self.metrics.add("curated", src, in_=n_in, out=cur.num_rows)
            self.metrics.record_checks("curated", check_curated_rows(cur.to_pylist()))
            done += 1
        return done

    def _discard(self, src: str, day: str) -> None:
        with self._dirty_lock:
            self._dirty.discard((src, day))


async def ingest_once(
    source: IngestSource,
    queue: Queue,
    metrics: PipelineMetrics,
    clock: Callable[[], datetime],
    *,
    max_records: int = 10_000,
) -> int:
    """Legge la sorgente e accoda i record in una busta {source_id, received_utc, record}.

    Ritorna i record accodati; quelli scartati dalla backpressure (politica drop) sono contati.
    I float non finiti diventano testo, cosi' il processor li manda in dead-letter con motivo."""
    sid = source.source_id
    metrics.ensure_source(sid)
    accepted = 0
    total = 0
    try:
        async for record in source.read():
            if total >= max_records:
                break
            total += 1
            envelope = {
                "source_id": sid,
                "received_utc": clock().astimezone(UTC).isoformat(),
                "record": _sanitise(record),
            }
            try:
                if await queue.put(envelope):
                    accepted += 1
                else:
                    metrics.count(sid, "ingest_dropped")
            except PayloadTooLarge:  # un record enorme non ferma gli altri
                metrics.count(sid, "ingest_oversize")
    finally:
        if accepted:
            metrics.seen(sid)
    return accepted
