# SPDX-License-Identifier: Apache-2.0
"""Store a livelli raw/clean/curated su Parquet (pyarrow), partizionato per sorgente e data.

Layout: <root>/<layer>/source=<id>/date=YYYY-MM-DD/part-*.parquet
- Scritture atomiche: file temporaneo `.tmp-*` nella stessa directory + fsync + os.replace. I lettori
  elencano solo `part-*.parquet`, quindi non vedono mai file parziali.
- Compattazione: il file unito dichiara in `hb_replaces` (metadati Parquet) i file che sostituisce;
  `visible_files` nasconde i file sostituiti, quindi non ci sono doppioni nemmeno se il processo
  muore prima di cancellare i sorgenti (la pulizia riprende alla compattazione successiva).
- Lineage: ogni riga clean porta `raw_file_id`; ogni riga curated elenca i `raw_file_ids`.
"""

import contextlib
import fcntl
import json
import logging
import os
import re
import shutil
import threading
import time
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.compute as pc  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from backend.pipeline.reserved import CANARY_SOURCE

log = logging.getLogger(__name__)
LAYERS = ("raw", "clean", "curated")
SOURCE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TS = pa.timestamp("us", tz="UTC")
REPLACES_KEY = b"hb_replaces"
CURATED_FILE = "part-agg"

SCHEMAS: dict[str, pa.Schema] = {
    "raw": pa.schema(
        [("source_id", pa.string()), ("received_utc", _TS), ("payload_json", pa.string())]
    ),
    "clean": pa.schema(
        [
            ("source_id", pa.string()),
            ("site_id", pa.string()),
            ("t_utc", _TS),
            ("schema_version", pa.string()),
            ("power_w", pa.float64()),
            ("link_margin_db", pa.float64()),
            ("sun_az_deg", pa.float64()),
            ("sun_el_deg", pa.float64()),
            ("earth_az_deg", pa.float64()),
            ("earth_el_deg", pa.float64()),
            ("received_utc", _TS),
            ("raw_file_id", pa.string()),
        ]
    ),
    "curated": pa.schema(
        [
            ("source_id", pa.string()),
            ("site_id", pa.string()),
            ("hour_utc", _TS),
            ("n", pa.int64()),
            ("power_w_mean", pa.float64()),
            ("power_w_min", pa.float64()),
            ("power_w_max", pa.float64()),
            ("raw_file_ids", pa.list_(pa.string())),
        ]
    ),
}
_TIME_COLUMN = {"raw": "received_utc", "clean": "t_utc", "curated": "hour_utc"}
_OPTIONAL = {
    "link_margin_db", "sun_az_deg", "sun_el_deg", "earth_az_deg", "earth_el_deg",
}  # fmt: skip


# Solo la corruzione verificata del formato Parquet. Gli OSError (EMFILE, EIO, EACCES...) sono
# transitori e si propagano: un file sano non viene mai spostato per un errore di I/O.
_CORRUPT = (pa.ArrowInvalid,)

# Ordine di acquisizione dei lock di livello. Chi ne tiene piu' di uno li prende in quest'ordine
# (retention del raw: curated poi raw; build_curated: solo curated). I lettori non prendono lock.
LOCK_ORDER = ("curated", "clean", "raw")


class StoreError(ValueError):
    pass


class LockOrderError(RuntimeError):
    """Violazione dell'ordine dei lock (curated -> clean -> raw): rischio di deadlock."""


class LayerBusy(RuntimeError):
    """Il lock del livello e' occupato (manutenzione in corso): riprovare piu' tardi."""


def _check_layer(layer: str) -> None:
    if layer not in LAYERS:
        raise StoreError(f"livello sconosciuto: {layer!r}")


def _check_source(source_id: str) -> None:
    if not isinstance(source_id, str) or not SOURCE_RE.fullmatch(source_id):
        raise StoreError("source_id non valido")


def _check_date(day: str) -> None:
    if not isinstance(day, str) or not DATE_RE.fullmatch(day):
        raise StoreError("data non valida (YYYY-MM-DD)")


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_write(
    table: pa.Table, final: Path, metadata: Mapping[bytes, bytes] | None = None
) -> None:
    tmp = final.with_name(f".tmp-{uuid.uuid4().hex}")
    try:
        if metadata:
            table = table.replace_schema_metadata({**(table.schema.metadata or {}), **metadata})
        pq.write_table(table, tmp, compression="zstd")
        fd = os.open(tmp, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, final)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    _fsync_dir(final.parent)


def _new_file_id(prefix: str = "part") -> str:
    return f"{prefix}-{time.time_ns():020d}-{uuid.uuid4().hex[:8]}"


class ParquetStore:
    def __init__(
        self, root: str | Path, *, clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    ) -> None:
        self.root = Path(root).resolve()
        self._clock = clock
        self._replaces_cache: dict[tuple[str, int, int], list[str]] = {}
        self._cache_lock = threading.Lock()
        self._held = threading.local()  # lock di livello tenuti dal thread (controllo d'ordine)
        self.quarantined: list[str] = []  # file corrotti messi da parte (`*.corrupt`)
        self.retention_skipped: list[str] = []  # partizioni raw non cancellate perche' referenziate
        self.root.mkdir(parents=True, exist_ok=True)
        self.discard_canary()  # residui di un crash durante la sonda di salute

    # ---- scrittore unico per livello (flock) ----

    def lock_path(self, layer: str) -> Path:
        _check_layer(layer)
        return self.root / ".locks" / f"{layer}.lock"

    @contextlib.contextmanager
    def _layer_lock(self, layer: str, wait_s: float = 0.0) -> Iterator[bool]:
        """Lock esclusivo non bloccante (fcntl.flock, Linux/macOS) valido fra thread E processi:
        compattazione, retention e ricostruzione dei curated non si sovrappongono mai sullo stesso
        livello. Se e' occupato cede il turno (False) invece di attendere. Il kernel lo rilascia se il
        processo muore. Ordine obbligatorio `LOCK_ORDER`: acquisire un livello che precede (o uguale a)
        uno gia' tenuto dal thread solleva LockOrderError."""
        _check_layer(layer)
        held: list[str] = self._held.__dict__.setdefault("layers", [])
        if any(LOCK_ORDER.index(h) >= LOCK_ORDER.index(layer) for h in held):
            raise LockOrderError(f"ordine dei lock violato: {held} poi {layer}")
        path = self.lock_path(layer)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            deadline = time.monotonic() + wait_s
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        yield False
                        return
                    time.sleep(0.01)
            held.append(layer)
            try:
                yield True
            finally:
                held.remove(layer)
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)

    def discard_canary(self) -> None:
        """Rimuove i file del canarino di salute (scritto con `write("clean", CANARY_SOURCE, ...)`)."""
        for layer in LAYERS:
            shutil.rmtree(self.root / layer / f"source={CANARY_SOURCE}", ignore_errors=True)

    # ---- scrittura ----

    def _partition_dir(self, layer: str, source_id: str, day: str) -> Path:
        return self.root / layer / f"source={source_id}" / f"date={day}"

    def _build_table(
        self, layer: str, source_id: str, rows: Sequence[Mapping[str, Any]]
    ) -> pa.Table:
        schema = SCHEMAS[layer]
        required = [n for n in schema.names if n not in _OPTIONAL]
        tcol = _TIME_COLUMN[layer]
        prepared: list[dict[str, Any]] = []
        for r in rows:
            row = {"source_id": source_id, **r}
            missing = [c for c in required if row.get(c) is None]
            if missing or row["source_id"] != source_id:
                raise StoreError(
                    f"riga non valida per il livello {layer}: {missing or 'source_id'}"
                )
            t = row[tcol]
            if not isinstance(t, datetime) or t.tzinfo is None:
                raise StoreError(f"{tcol} deve essere un datetime con fuso orario")
            prepared.append({k: row.get(k) for k in schema.names})
        try:
            return pa.Table.from_pylist(prepared, schema=schema)
        except (pa.ArrowInvalid, pa.ArrowTypeError, OverflowError) as e:
            raise StoreError(
                f"righe non conformi allo schema {layer}: {type(e).__name__}"
            ) from None

    def write(self, layer: str, source_id: str, rows: Sequence[Mapping[str, Any]]) -> list[str]:
        """Scrive le righe (un file per data) e ritorna gli id dei file creati."""
        _check_layer(layer)
        _check_source(source_id)
        if not rows:
            return []
        table = self._build_table(layer, source_id, rows)
        tcol = _TIME_COLUMN[layer]
        days = pc.strftime(table.column(tcol), format="%Y-%m-%d").to_pylist()
        by_day: dict[str, list[int]] = {}
        for i, d in enumerate(days):
            by_day.setdefault(d, []).append(i)
        ids: list[str] = []
        for day, idx in sorted(by_day.items()):
            part = table.take(pa.array(idx))
            if layer == "clean":
                part = part.sort_by("t_utc")
            d = self._partition_dir(layer, source_id, day)
            d.mkdir(parents=True, exist_ok=True)
            fid = _new_file_id()
            _atomic_write(part, d / f"{fid}.parquet")
            ids.append(fid)
        return ids

    # ---- elenco / lettura ----

    def _partition_dirs(
        self, layer: str, source_id: str | None = None, day: str | None = None
    ) -> list[Path]:
        base = self.root / layer
        if not base.is_dir():
            return []
        out: list[Path] = []
        for sdir in sorted(base.glob("source=*")):
            if source_id is not None and sdir.name != f"source={source_id}":
                continue
            if sdir.is_symlink() or not sdir.is_dir():
                continue
            if sdir.name == f"source={CANARY_SOURCE}" and source_id != CANARY_SOURCE:
                continue  # il canarino di salute non e' mai visibile ai lettori
            for ddir in sorted(sdir.glob("date=*")):
                if ddir.is_symlink() or not ddir.is_dir():
                    continue
                if day is not None and ddir.name != f"date={day}":
                    continue
                out.append(ddir)
        return out

    def _replaces(self, f: Path) -> list[str]:
        st = f.stat()
        key = (str(f), st.st_mtime_ns, st.st_size)
        with self._cache_lock:
            cached = self._replaces_cache.get(key)
        if cached is None:
            md = pq.read_schema(f).metadata or {}
            cached = list(json.loads(md.get(REPLACES_KEY, b"[]")))
            with self._cache_lock:
                if len(self._replaces_cache) > 4096:
                    self._replaces_cache.clear()
                self._replaces_cache[key] = cached
        return cached

    def _confirm_corrupt(self, f: Path) -> bool:
        """Conferma la corruzione: il footer e' illeggibile OPPURE una lettura completa del singolo
        file fallisce con ArrowInvalid. Un file che si legge per intero e' sano (un errore di
        colonne/schema della richiesta non e' corruzione). Gli OSError propagano: non verificabile."""
        try:
            pq.ParquetFile(f).metadata  # noqa: B018  solo il footer
        except _CORRUPT:
            return True
        try:
            pq.read_table(f)
        except _CORRUPT:
            return True
        return False

    def quarantine(self, f: Path) -> None:
        """Isola un file di cui la corruzione e' STATA CONFERMATA: rinomina in `*.corrupt` (fuori dal
        glob dei lettori). Non cancella mai. Se dopo la rinuncia la partizione non ha piu' file
        visibili (esclusi quelli nascosti da una compattazione) logga CRITICAL. Prende il lock del
        livello (a meno che il thread lo tenga gia') cosi' il controllo non corre con compattazioni."""
        layer = f.resolve().relative_to(self.root).parts[0]
        held: list[str] = self._held.__dict__.setdefault("layers", [])
        with contextlib.ExitStack() as stack:
            locked = True
            if layer not in held:
                try:
                    locked = stack.enter_context(self._layer_lock(layer, wait_s=5.0))
                except LockOrderError:
                    locked = False
            try:
                os.replace(f, f.with_name(f.name + ".corrupt"))
            except FileNotFoundError:
                return
            self.quarantined.append(str(f))
            log.error("file Parquet corrotto messo in quarantena: %s", f)
            remaining = self._partition_files(f.parent)[0]
            if not remaining:
                log.critical(
                    "quarantena dell'UNICO file leggibile della partizione %s: dati non leggibili%s",
                    f.parent,
                    "" if locked else " (lock del livello non ottenuto)",
                )

    def quarantine_invalid(self, layer: str) -> int:
        """Verifica ogni file visibile e mette in quarantena solo quelli con corruzione confermata.
        Errori di I/O: file non verificabile, lasciato dov'e'."""
        n = 0
        for name in self.visible_files(layer):
            f = Path(name)
            try:
                if self._confirm_corrupt(f):
                    self.quarantine(f)
                    n += 1
            except FileNotFoundError:
                continue
            except OSError:
                log.warning("file non verificabile (errore di I/O), non spostato: %s", f)
        return n

    def _partition_files(self, ddir: Path) -> tuple[list[Path], list[Path]]:
        """(visibili, nascosti perche' sostituiti da una compattazione) in una partizione."""
        files = sorted(ddir.glob("part-*.parquet"))
        hidden: set[str] = set()
        readable: list[Path] = []
        for f in files:
            if f.name.startswith("part-c"):
                try:
                    hidden.update(self._replaces(f))
                except FileNotFoundError:
                    continue
                except _CORRUPT:
                    if not self._confirm_corrupt(f):
                        raise StoreError(f"metadati non conformi in {f.name}") from None
                    self.quarantine(f)  # footer illeggibile: la partizione resta leggibile
                    continue
            readable.append(f)
        visible = [f for f in readable if f.stem not in hidden]
        return visible, [f for f in readable if f.stem in hidden]

    def visible_files(
        self, layer: str, source_id: str | None = None, date: str | None = None
    ) -> list[str]:
        _check_layer(layer)
        if source_id is not None:
            _check_source(source_id)
        if date is not None:
            _check_date(date)
        out: list[str] = []
        for ddir in self._partition_dirs(layer, source_id, date):
            out.extend(str(f) for f in self._partition_files(ddir)[0])
        return out

    def _read_file(self, f: str | Path, columns: list[str] | None) -> pa.Table | None:
        """Legge un file. Se la corruzione e' confermata (`_confirm_corrupt`) lo mette in quarantena
        e ritorna None; un errore di colonne/schema su un file sano e' uno StoreError chiaro."""
        try:
            return pq.read_table(f, columns=columns)
        except FileNotFoundError:
            raise
        except _CORRUPT as e:
            if self._confirm_corrupt(Path(f)):
                self.quarantine(Path(f))
                return None
            raise StoreError(
                f"colonne o schema non conformi in {Path(f).name}: {type(e).__name__}"
            ) from None

    def read(
        self,
        layer: str,
        source_id: str | None = None,
        date: str | None = None,
        columns: Sequence[str] | None = None,
    ) -> pa.Table:
        """Legge i file visibili; `columns` = proiezione (legge solo quelle colonne dal disco).
        Un file corrotto viene messo in quarantena e saltato (errore nel log), non rompe la lettura."""
        cols = list(columns) if columns is not None else None
        tables: list[pa.Table] = []
        for attempt in range(3):
            files = self.visible_files(layer, source_id, date)
            try:
                got = [self._read_file(f, cols) for f in files]
            except FileNotFoundError:  # compattazione/retention concorrente: riprova
                if attempt == 2:
                    raise
                continue
            tables = [t for t in got if t is not None]
            if len(tables) < len(got) and attempt < 2:
                continue  # un file e' stato messo in quarantena: rielenca (i sorgenti nascosti tornano)
            break
        if not tables:
            empty = SCHEMAS[layer].empty_table()
            return empty.select(cols) if cols is not None else empty
        return pa.concat_tables(tables, promote_options="permissive")

    def resolve_raw_ids(self, ids: Sequence[str]) -> dict[str, str | None]:
        """Id raw originale -> id del file raw visibile che lo contiene oggi (anche dopo la
        compattazione, tramite `hb_replaces`); None se il file non esiste piu'."""
        mapping: dict[str, str] = {}
        for ddir in self._partition_dirs("raw"):
            for f in self._partition_files(ddir)[0]:
                mapping[f.stem] = f.stem
                if f.name.startswith("part-c"):
                    for old in self._replaces(f):
                        mapping[old] = f.stem
        return {i: mapping.get(i) for i in ids}

    def clean_keys(self, source_id: str, day: str) -> set[tuple[str, datetime]]:
        """Chiavi (site_id, t_utc) gia' presenti in clean per la partizione (dedup al riavvio).
        Legge solo le due colonne chiave (proiezione Parquet)."""
        table = self.read("clean", source_id, day, columns=["site_id", "t_utc"])
        return set(
            zip(table.column("site_id").to_pylist(), table.column("t_utc").to_pylist(), strict=True)
        )

    # ---- manutenzione ----

    def _merge(self, layer: str, tables: list[pa.Table]) -> pa.Table:
        merged = pa.concat_tables(tables, promote_options="permissive")
        if layer != "clean" or merged.num_rows == 0:
            return merged
        merged = merged.sort_by(
            [("site_id", "ascending"), ("t_utc", "ascending"), ("received_utc", "ascending")]
        )
        # chiave ripetuta: vince il primo ricevuto (stessa politica del Deduplicator della pipeline)
        site, t = merged.column("site_id"), merged.column("t_utc")
        n = merged.num_rows
        same_prev = pc.and_(
            pc.equal(site.slice(1), site.slice(0, n - 1)), pc.equal(t.slice(1), t.slice(0, n - 1))
        )
        keep = pa.chunked_array([pa.array([True]), pc.invert(same_prev.combine_chunks())])
        return merged.filter(keep).sort_by("t_utc")

    def compact(
        self,
        layer: str,
        *,
        min_files: int = 4,
        should_stop: Callable[[], bool] = lambda: False,
    ) -> int:
        """Unisce i file piccoli di ogni partizione (clean: dedup per chiave). Ritorna le partizioni unite."""
        _check_layer(layer)
        if isinstance(min_files, bool) or not isinstance(min_files, int) or min_files < 2:
            raise StoreError("min_files deve essere un intero >= 2")
        if layer == "curated":
            return 0  # un solo file deterministico per partizione, gia' sostituito atomicamente
        with self._layer_lock(layer) as got:
            if not got:
                log.info("compattazione di %s gia' in corso altrove: salto", layer)
                return 0
            return self._compact_locked(layer, min_files, should_stop)

    def _compact_locked(self, layer: str, min_files: int, should_stop: Callable[[], bool]) -> int:
        merged_count = 0
        for ddir in self._partition_dirs(layer):
            if should_stop():  # cooperativo: un thread non si puo' uccidere
                break
            visible, hidden = self._partition_files(ddir)
            for f in hidden:  # ripresa dopo un crash tra pubblicazione e pulizia
                os.unlink(f)
            if len(visible) < min_files:
                continue
            tables = [self._read_file(f, None) for f in visible]
            if any(t is None for t in tables):
                continue  # un file corrotto e' ora in quarantena: si riprova al prossimo giro
            replaced: list[str] = []
            for f in visible:
                replaced.append(f.stem)
                replaced.extend(self._replaces(f))
            table = self._merge(layer, [t for t in tables if t is not None])
            final = ddir / f"{_new_file_id('part-c')}.parquet"
            _atomic_write(table, final, {REPLACES_KEY: json.dumps(sorted(set(replaced))).encode()})
            for f in visible:
                os.unlink(f)
            merged_count += 1
        return merged_count

    def _protected_raw_files(self) -> set[str]:
        """File raw visibili ancora referenziati (anche via compattazione) dai curated rimasti."""
        referenced: set[str] = set()
        for name in self.visible_files("curated"):
            table = self._read_file(name, ["raw_file_ids"])
            if table is None:
                continue
            for ids in table.column("raw_file_ids").to_pylist():
                referenced.update(ids or [])
        return {v for v in self.resolve_raw_ids(sorted(referenced)).values() if v}

    def apply_retention(
        self,
        days_by_layer: Mapping[str, int],
        *,
        should_stop: Callable[[], bool] = lambda: False,
        force: bool = False,
    ) -> int:
        """Elimina le partizioni con data < oggi - giorni. Ritorna il numero di partizioni rimosse.

        I livelli si trattano nell'ordine curated, clean, raw: i raw ancora referenziati dal lineage
        dei curated *rimasti* non vengono cancellati (salvo `force=True`) e finiscono in
        `retention_skipped`. Un livello in compattazione (lock occupato) viene rimandato."""
        for layer, days in days_by_layer.items():
            _check_layer(layer)
            if isinstance(days, bool) or not isinstance(days, int) or days < 1:
                raise StoreError("la retention deve essere un intero >= 1 giorno")
        today = self._clock().astimezone(UTC).date()
        self.retention_skipped = []
        removed = 0
        for layer in sorted(days_by_layer, key=LAYERS.index, reverse=True):
            with contextlib.ExitStack() as stack:
                # il raw si cancella solo tenendo anche il lock dei curated (ordine curated -> raw):
                # una ricostruzione in corso non puo' referenziare file che stiamo eliminando
                if layer == "raw" and not stack.enter_context(self._layer_lock("curated")):
                    log.info("retention di raw rimandata: curated in ricostruzione")
                    continue
                got = stack.enter_context(self._layer_lock(layer))
                if not got:
                    log.info("retention di %s rimandata: livello in manutenzione", layer)
                    continue
                cutoff = today - timedelta(days=days_by_layer[layer])
                protected = self._protected_raw_files() if layer == "raw" and not force else set()
                for ddir in self._partition_dirs(layer):
                    if should_stop():
                        return removed
                    try:
                        pdate = date.fromisoformat(ddir.name.removeprefix("date="))
                    except ValueError:
                        continue
                    if pdate >= cutoff:
                        continue
                    if protected and any(f.stem in protected for f in ddir.glob("part-*.parquet")):
                        self.retention_skipped.append(
                            f"raw {ddir.parent.name}/{ddir.name}: referenziato dal lineage di un curated"
                        )
                        log.warning("retention: %s non cancellato (lineage)", ddir)
                        continue
                    shutil.rmtree(ddir)
                    removed += 1
                    try:
                        ddir.parent.rmdir()  # solo se vuota
                    except OSError:
                        pass
        return removed

    def cleanup_tmp(self, max_age_s: float = 3600.0) -> int:
        """Rimuove i `.tmp-*` abbandonati da un crash (mai visibili ai lettori)."""
        now = time.time()
        n = 0
        for tmp in self.root.rglob(".tmp-*"):
            try:
                if tmp.is_file() and now - tmp.stat().st_mtime >= max_age_s:
                    os.unlink(tmp)
                    n += 1
            except OSError:
                continue
        return n

    # ---- curated ----

    def build_curated(self, source_id: str, day: str) -> str | None:
        """Aggregati orari di una partizione clean, con lineage verso i file raw. Idempotente.
        Tiene il lock del livello curated (LayerBusy se occupato: riprovare piu' tardi)."""
        _check_source(source_id)
        _check_date(day)
        with self._layer_lock("curated") as got:
            if not got:
                raise LayerBusy("curated in manutenzione")
            return self._build_curated_locked(source_id, day)

    def _build_curated_locked(self, source_id: str, day: str) -> str | None:
        clean = self.read("clean", source_id, day)
        if clean.num_rows == 0:
            return None
        hour = pc.floor_temporal(clean.column("t_utc"), unit="hour")
        grouped = (
            clean.append_column("hour_utc", hour)
            .group_by(["site_id", "hour_utc"])
            .aggregate(
                [
                    ("power_w", "count"),
                    ("power_w", "mean"),
                    ("power_w", "min"),
                    ("power_w", "max"),
                    ("raw_file_id", "distinct"),
                ]
            )
        )
        rows = [
            {
                "source_id": source_id,
                "site_id": r["site_id"],
                "hour_utc": r["hour_utc"],
                "n": r["power_w_count"],
                "power_w_mean": r["power_w_mean"],
                "power_w_min": r["power_w_min"],
                "power_w_max": r["power_w_max"],
                "raw_file_ids": sorted(x for x in r["raw_file_id_distinct"] if x is not None),
            }
            for r in grouped.to_pylist()
        ]
        rows.sort(key=lambda r: (r["site_id"], r["hour_utc"]))
        table = self._build_table("curated", source_id, rows)
        d = self._partition_dir("curated", source_id, day)
        d.mkdir(parents=True, exist_ok=True)
        _atomic_write(table, d / f"{CURATED_FILE}.parquet")  # sostituzione atomica
        return CURATED_FILE
