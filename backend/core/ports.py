# SPDX-License-Identifier: Apache-2.0
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Simulation(Protocol):
    async def run(
        self, inputs: Mapping[str, float], *, timeout_s: float
    ) -> Mapping[str, float]: ...


@runtime_checkable
class CachePort(Protocol):
    async def get(self, key: str, *, allow_stale: bool = False) -> bytes | None: ...
    async def set(self, key: str, value: bytes, ttl_s: float) -> None: ...


@runtime_checkable
class DataSource(Protocol):
    async def fetch(self, query: Mapping[str, Any]) -> Mapping[str, Any]: ...


@runtime_checkable
class LLMProvider(Protocol):
    def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]: ...


@runtime_checkable
class FirmwareSim(Protocol):
    """Firmware simulato a passi (spec 12.2); async come Simulation (adapter exec/QEMU)."""

    async def load(self, image: str) -> None: ...
    async def step(self, dt_s: float, inputs: Mapping[str, float]) -> Mapping[str, float]: ...
    async def reset(self) -> None: ...


@runtime_checkable
class Estimator(Protocol):
    """Stimatore di stato (spec 12.2). Sincrono: calcolo in-process, senza I/O.

    `update` restituisce la stima come mappa nome_con_unita -> valore. `dt_s` opzionale in
    `update` imposta il passo in modo atomico: applicato solo se la misura e' valida.
    Le misure non valide sollevano `InvalidMeasurement` (ValueError) e non alterano lo stato.
    """

    def predict(self, dt_s: float) -> None: ...
    def update(
        self, measurement: Mapping[str, float], dt_s: float | None = None
    ) -> Mapping[str, float]: ...
    def reset(self) -> None: ...


@runtime_checkable
class Predictor(Protocol):
    """Modello di inferenza (spec 13.2, kind `model`). Sincrono, solo inferenza.

    `predict` riceve feature con unita' nel nome e restituisce la previsione come mappa
    nome_con_unita -> valore finito. `model_info` descrive il modello in uso (versione, metriche).
    """

    def predict(self, features: Mapping[str, float]) -> Mapping[str, float]: ...
    def model_info(self) -> Mapping[str, Any]: ...


@runtime_checkable
class Trainer(Protocol):
    """Addestramento (spec 13.2, kind `trainer`). Eseguito SOLO in un subprocess dal runner.

    `fit` restituisce `{"metrics": {nome: float finito}, "model_version": str | None}`.
    Un trainer salva candidati nel registro, non li promuove mai (cancello umano).
    """

    def fit(self, dataset_ref: str, config: Mapping[str, Any]) -> Mapping[str, Any]: ...


@runtime_checkable
class ModelRegistry(Protocol):
    """Registro di modelli versionati con model card (spec 13.2)."""

    def save(self, model: bytes, card: Mapping[str, Any]) -> str: ...
    def load(self, version: str) -> tuple[bytes, Mapping[str, Any]]: ...
    def list_versions(self) -> Sequence[Mapping[str, Any]]: ...
    def promoted_version(self) -> str | None: ...
    def promote(
        self, version: str, *, approver: str, approved: bool = False
    ) -> Mapping[str, Any]: ...
    def rollback(self, *, approver: str) -> str: ...


# --- Pipeline dati (spec 14.2). Solo tipi standard: nessuna libreria dati nel core. ---


@dataclass(frozen=True)
class QueueItem:
    """Consegna di un messaggio. `attempt` = tentativi che consumano il budget; `lease` identifica
    la singola consegna (ack/nack con lease scaduto e riconsegnato: no-op, ritornano False)."""

    id: int
    payload: Mapping[str, Any]
    attempt: int
    lease: int = 0


@runtime_checkable
class IngestSource(Protocol):
    """Produce record grezzi (mappe) da una sorgente. `source_id` e' lo slug della sorgente."""

    source_id: str

    def read(self) -> AsyncIterator[Mapping[str, Any]]: ...


@runtime_checkable
class Queue(Protocol):
    """Coda at-least-once con limite, ack/nack e dead-letter.

    `put` ritorna False se il messaggio e' stato scartato (politica drop_with_counter).
    `get` ritorna None allo scadere di `timeout_s`. `ack`/`nack` ritornano False se il lease
    non e' piu' valido (scaduto e riconsegnato). `nack(requeue=False)` manda in dead-letter;
    `nack(count_attempt=False, delay_s=d)` rilascia senza consumare un tentativo (guasto
    d'infrastruttura) e rende il messaggio visibile dopo `d` secondi (backoff).
    """

    async def put(self, payload: Mapping[str, Any]) -> bool: ...
    async def get(self, timeout_s: float | None = None) -> QueueItem | None: ...
    async def ack(self, item: QueueItem) -> bool: ...
    async def nack(
        self,
        item: QueueItem,
        reason: str,
        *,
        requeue: bool = True,
        delay_s: float = 0.0,
        count_attempt: bool = True,
    ) -> bool: ...
    def dead_letters(self) -> Sequence[Mapping[str, Any]]: ...
    def stats(self) -> Mapping[str, int]: ...
    def close(self) -> None: ...


@runtime_checkable
class Processor(Protocol):
    """Messaggio -> zero o piu' record puliti; solleva ValueError con motivo leggibile da macchina."""

    def process(self, message: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]: ...


@runtime_checkable
class Store(Protocol):
    """Scrive i livelli raw/clean/curated (colonnare, partizionato per sorgente e data)."""

    def write(
        self, layer: str, source_id: str, rows: Sequence[Mapping[str, Any]]
    ) -> Sequence[str]: ...
    def visible_files(self, layer: str) -> Sequence[str]: ...


@runtime_checkable
class QueryEngine(Protocol):
    """Solo interrogazioni predefinite con parametri legati; mai SQL dal client."""

    def names(self) -> Sequence[str]: ...
    def query(self, name: str, params: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]: ...


@runtime_checkable
class Scheduler(Protocol):
    """Job periodici con timeout, non sovrapposizione e isolamento dei guasti."""

    def add_job(
        self, name: str, fn: Callable[[], Awaitable[None]], *, interval_s: float, timeout_s: float
    ) -> None: ...
    async def run_now(self, name: str) -> str: ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    def status(self) -> Mapping[str, Mapping[str, Any]]: ...


# --- Ambiente RL (spec 13.2, kind `environment`). Nessuna libreria RL/numerica nel core. ---


@dataclass(frozen=True)
class BoxSpace:
    """Spazio continuo limitato: `low`/`high` per componente, `shape` della forma (tuple)."""

    low: tuple[float, ...]
    high: tuple[float, ...]
    shape: tuple[int, ...]


@runtime_checkable
class Environment(Protocol):
    """Ambiente episodico stile Gymnasium ma con soli tipi standard (sincrono, in-process).

    `reset(seed)` -> `(osservazione, info)`; `step(azione)` ->
    `(osservazione, ricompensa, terminated, truncated, info)`. Le azioni non finite sollevano
    `ValueError`; un passo prima di `reset` o dopo la fine dell'episodio solleva `RuntimeError`.
    """

    observation_space: BoxSpace
    action_space: BoxSpace

    def reset(self, seed: int | None = None) -> tuple[tuple[float, ...], dict[str, Any]]: ...
    def step(
        self, action: Sequence[float]
    ) -> tuple[tuple[float, ...], float, bool, bool, dict[str, Any]]: ...


# --- Reti e protocolli (spec 15). Solo porte: nessun socket/ssl nel core (import-linter). ---
# Tutto cio' che arriva da un Transport e' NON fidato: le implementazioni applicano limiti
# espliciti (dimensione, velocita', code) e non sollevano mai eccezioni non tipizzate.


@runtime_checkable
class Transport(Protocol):
    """Endpoint di rete asincrono (TCP/UDP/loopback). Nessun listener parte senza `start`.

    `receive` restituisce `(peer, dati)` oppure `None` a trasporto chiuso. `send` con `peer=None`
    usa il peer predefinito (client) o l'unico peer connesso. `stats` restituisce contatori
    (messaggi, scarti, oversize, rate-limit...) per le metriche della pagina "Pipeline dati".
    """

    async def start(self) -> None: ...
    async def send(self, data: bytes, peer: str | None = None) -> None: ...
    async def receive(self) -> tuple[str, bytes] | None: ...
    async def close(self) -> None: ...
    def stats(self) -> Mapping[str, int]: ...


@runtime_checkable
class Framer(Protocol):
    """Delimitazione dei messaggi in un flusso di byte, decodifica incrementale.

    `feed` accetta frammenti arbitrari e restituisce i messaggi completi. Solleva un errore di
    protocollo tipizzato se il flusso non e' recuperabile (es. lunghezza dichiarata oltre il
    massimo); i framer con risincronizzazione scartano e contano invece di sollevare.
    """

    def feed(self, data: bytes) -> Sequence[bytes]: ...
    def encode(self, payload: bytes) -> bytes: ...
    def reset(self) -> None: ...


@runtime_checkable
class ProtocolCodec(Protocol):
    """Codifica/decodifica di un protocollo con validazione. `decode` solleva solo ProtocolError."""

    def encode(self, message: Any) -> bytes: ...
    def decode(self, data: bytes) -> Any: ...


@runtime_checkable
class Channel(Protocol):
    """Canale simulato (ritardo, perdita, errori sui bit, banda, contatti), deterministico.

    Il tempo e' esplicito (`now_s`, secondi su un orologio virtuale iniettato): nessuno sleep.
    `send` accoda un frame; `deliver` restituisce i frame il cui istante di arrivo e' <= now_s.
    """

    def send(self, data: bytes, *, now_s: float) -> None: ...
    def deliver(self, now_s: float) -> list[bytes]: ...
    def stats(self) -> Mapping[str, int]: ...


class ReportRenderer(Protocol):
    """Renders a sanitised report document (HTML + CSS) to PDF bytes (spec: server PDF, 9 Nov).

    Synchronous and CPU-bound: callers run it in a worker thread. Implementations must not fetch any
    external resource (only data: URIs), must be deterministic for equal input and must raise
    `RendererUnavailable` when the engine or its system libraries are missing.
    """

    def render(self, request: "ReportRenderRequest") -> bytes: ...


class RendererUnavailable(RuntimeError):
    """The PDF engine (optional extra `pdf`) or its system libraries are not available."""


@dataclass(frozen=True)
class ReportRenderRequest:
    body_html: str  # already sanitised
    css: str  # already sanitised
    title: str
    subtitle: str
    lang: str  # 'it' | 'en'
    created: str  # ISO 8601 UTC, e.g. 2026-11-09T10:00:00Z
