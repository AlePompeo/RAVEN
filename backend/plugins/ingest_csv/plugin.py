# SPDX-License-Identifier: Apache-2.0
"""IngestSource da file CSV (spec 14.2). Mappa le colonne sul contratto telemetry senza validare:
la validazione, la normalizzazione e lo scarto con motivo sono del Processor della pipeline.

Colonne note: t_utc, site_id, schema_version, power_w, link_margin_db, {sun,earth}_{az,el}_deg.
Celle vuote -> campo omesso. Celle numeriche non convertibili in numero finito restano testo
("nan", "abc"), cosi' il Processor le manda in dead-letter con il motivo. Colonne sconosciute
passano invariate (verranno rifiutate come `unknown_field`). Mappatura propria: non si importa
nulla da `backend.api`.
"""

import asyncio
import csv
import hashlib
import math
import os
import re
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

from backend.core.manifest import Manifest

SOURCE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
DEFAULT_SCHEMA_VERSION = "1.0.0"
DEFAULT_MAX_ROWS = 100_000
DEFAULT_MAX_BYTES = 50 * 1024 * 1024
PREVIEW_ROWS = 20
COMMIT_EVERY = 1000  # righe fra due registrazioni dello stato di lettura
HEAD_BYTES = 64 * 1024
TAIL_BYTES = 4 * 1024
_NUMERIC = {"power_w", "link_margin_db"}
_NESTED = {"sun", "earth"}
_NESTED_FIELDS = {"az_deg", "el_deg"}
_TEXT = {"t_utc", "site_id", "schema_version"}


def _number(cell: str) -> float | str:
    try:
        value = float(cell)
    except ValueError:
        return cell
    return value if math.isfinite(value) else cell


@dataclass
class _State:
    """Cosa e' gia' stato letto: percorso, offset in byte dopo l'ultima riga consumata, (size,
    mtime_ns) del file a fine scansione e hash di testa/coda del prefisso consumato."""

    path: str
    offset: int
    size: int
    mtime_ns: int
    head: str
    tail: str
    header: list[str]
    complete: bool


class CsvIngestSource:
    def __init__(
        self,
        manifest: Manifest,
        *,
        path: str | Path | None = None,
        source_id: str | None = None,
        site_id: str | None = None,
        max_rows: int = DEFAULT_MAX_ROWS,
        max_bytes: int = DEFAULT_MAX_BYTES,
    ) -> None:
        self.manifest = manifest
        self.source_id = source_id or manifest.id
        if not SOURCE_RE.fullmatch(self.source_id):
            raise ValueError("source_id non valido")
        self._path = path
        self._site_id = site_id or os.environ.get("INGEST_CSV_SITE_ID")
        self._max_rows, self._max_bytes = max_rows, max_bytes
        self._state: _State | None = None

    def _resolve(self) -> Path:
        raw = self._path or os.environ.get("INGEST_CSV_PATH")
        if not raw:
            raise FileNotFoundError("INGEST_CSV_PATH non impostata")
        p = Path(raw)
        if not p.is_file():
            raise FileNotFoundError("file CSV non trovato")
        if p.stat().st_size > self._max_bytes:
            raise ValueError("file CSV oltre il limite di dimensione")
        return p

    def _map(self, row: Mapping[str, str | None]) -> dict[str, Any]:
        rec: dict[str, Any] = {}
        nested: dict[str, dict[str, Any]] = {}
        for key, cell in row.items():
            if not key or cell is None or cell.strip() == "":
                continue
            cell = cell.strip()
            obj, _, field = key.partition("_")
            if key in _NUMERIC:
                rec[key] = _number(cell)
            elif key in _TEXT:
                rec[key] = cell
            elif obj in _NESTED and field in _NESTED_FIELDS:
                nested.setdefault(obj, {})[field] = _number(cell)
            else:
                rec[key] = cell
        rec.update(nested)
        rec.setdefault("schema_version", DEFAULT_SCHEMA_VERSION)
        if self._site_id:
            rec.setdefault("site_id", self._site_id)
        return rec

    def reset(self) -> None:
        """Dimentica lo stato di lettura: il prossimo poll rilegge il file dall'inizio."""
        self._state = None

    @staticmethod
    def _fingerprint(f: BinaryIO, offset: int) -> tuple[str, str]:
        """Hash dell'inizio del file e della coda gia' consumata: riconosce rotazione/riscrittura."""
        f.seek(0)
        head = hashlib.sha256(f.read(min(offset, HEAD_BYTES))).hexdigest()
        start = max(0, offset - TAIL_BYTES)
        f.seek(start)
        tail = hashlib.sha256(f.read(offset - start)).hexdigest()
        return head, tail

    def _prefix_unchanged(self, path: Path, state: _State, size: int) -> bool:
        if size < state.offset:  # troncato
            return False
        with path.open("rb") as f:
            return self._fingerprint(f, state.offset) == (state.head, state.tail)

    async def _rows(self, *, stateful: bool, limit: int) -> AsyncIterator[Mapping[str, Any]]:
        """Righe nuove dall'ultimo poll (stateful) oppure dall'inizio (anteprima).

        Lo stato avanza solo dopo che il consumatore ha ripreso il generatore, quindi una riga
        consegnata ma non elaborata viene riconsegnata al poll successivo (at-least-once).
        Solo righe complete (terminate da newline) vengono emesse; una riga in scrittura attende.
        Limite: una cella CSV con newline fra virgolette non e' supportata (lettura per riga)."""
        path = self._resolve()
        st = path.stat()
        state = self._state if stateful else None
        if state is not None:
            if state.path != str(path) or not self._prefix_unchanged(path, state, st.st_size):
                state = None  # altro file, troncato o riscritto: da capo
            elif state.complete and state.size == st.st_size and state.mtime_ns == st.st_mtime_ns:
                return  # file invariato dall'ultimo poll
        with path.open("rb") as f:
            if state is None:
                first = f.readline()
                if not first.endswith(b"\n"):
                    return  # intestazione ancora incompleta
                header = next(csv.reader([first.decode("utf-8", "replace").strip("\r\n")]))
                offset = len(first)
            else:
                header, offset = state.header, state.offset
                f.seek(offset)
            emitted = 0
            complete = True
            while True:
                raw = f.readline()
                if not raw or not raw.endswith(b"\n"):
                    break  # fine file, oppure riga parziale in scrittura
                text = raw.decode("utf-8", "replace").strip("\r\n")
                if text.strip() == "":
                    offset += len(raw)
                    continue
                if emitted >= limit:
                    complete = False
                    break
                cells = next(csv.reader([text]))
                record = self._map(dict(zip(header, cells, strict=False)))
                emitted += 1
                yield record
                offset += len(raw)
                if emitted % COMMIT_EVERY == 0:
                    # stato per blocchi (l'hash costa fino a ~68 KB): al peggio un consumatore
                    # interrotto si vede riconsegnare un blocco, che la dedup scarta
                    if stateful:
                        self._commit(path, st, offset, header, f, complete=False)
                    await asyncio.sleep(0)  # non monopolizzare il loop su file grandi
            if stateful:
                self._commit(path, st, offset, header, f, complete=complete)

    def _commit(
        self,
        path: Path,
        st: os.stat_result,
        offset: int,
        header: list[str],
        f: BinaryIO,
        *,
        complete: bool,
    ) -> None:
        pos = f.tell()
        head, tail = self._fingerprint(f, offset)
        f.seek(pos)
        self._state = _State(
            str(path), offset, st.st_size, st.st_mtime_ns, head, tail, header, complete
        )

    async def read(self) -> AsyncIterator[Mapping[str, Any]]:
        """Emette solo le righe nuove dall'ultimo poll (massimo `max_rows` per poll)."""
        async for rec in self._rows(stateful=True, limit=self._max_rows):
            yield rec

    async def fetch(self, query: Mapping[str, Any]) -> Mapping[str, Any]:
        """Anteprima limitata (DataSource) senza consumare lo stato di lettura."""
        preview = [r async for r in self._rows(stateful=False, limit=PREVIEW_ROWS)]
        return {"source_id": self.source_id, "preview": preview}
