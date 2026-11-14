# SPDX-License-Identifier: Apache-2.0
"""Processor di telemetria (spec 14): valida sul contratto, normalizza unita'/tempi, deduplica.

Messaggio in ingresso (payload di coda):
    {"source_id": slug, "received_utc": ISO-8601 (opzionale), "record": {...telemetria...}}
Riga `clean` in uscita: record piatto con tempi UTC. Un record scartato solleva `RecordRejected`
con `reason = "<codice>[:<campo>]"` (leggibile da macchina, campo ripulito da input ostile).
"""

import math
import re
from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from pydantic import ValidationError

from backend.contracts_models import Telemetry
from backend.pipeline.reserved import CANARY_SOURCE

SOURCE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_FIELD_CLEAN = re.compile(r"[^A-Za-z0-9_.]")
_NESTED = ("sun", "earth")
RAD_TO_DEG = 180.0 / math.pi

Key = tuple[str, datetime]  # (site_id, t_utc); la sorgente e' nella partizione


class RecordRejected(ValueError):
    def __init__(self, code: str, field: str | None = None) -> None:
        self.code = code
        self.field = _FIELD_CLEAN.sub("_", field)[:64] if field else None
        self.reason = f"{code}:{self.field}" if self.field else code
        super().__init__(self.reason)


def parse_reason(reason: str) -> tuple[str, str | None]:
    code, _, field = reason.partition(":")
    return code, field or None


def _is_num(v: Any) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool)


_TEXT_FIELDS = {"site_id", "schema_version", "t_utc"}
_NON_FINITE_TEXT = {"nan", "inf", "+inf", "-inf", "infinity", "+infinity", "-infinity"}


def _scan_non_finite(obj: Any, path: str = "") -> None:
    """NaN/inf come float o come testo ("nan", "inf": cosi' arrivano da CSV/JSON stretto)."""
    if isinstance(obj, float) and not math.isfinite(obj):
        raise RecordRejected("non_finite_value", path)
    if (
        isinstance(obj, str)
        and path not in _TEXT_FIELDS
        and obj.strip().lower() in _NON_FINITE_TEXT
    ):
        raise RecordRejected("non_finite_value", path)
    if isinstance(obj, Mapping):
        for k, v in obj.items():
            _scan_non_finite(v, f"{path}.{k}" if path else str(k))
    elif isinstance(obj, list | tuple):
        for i, v in enumerate(obj):
            _scan_non_finite(v, f"{path}.{i}" if path else str(i))


def _parse_time(value: Any, field: str) -> datetime:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.strip())
        except ValueError:
            raise RecordRejected("invalid_timestamp", field) from None
    elif _is_num(value):
        try:
            return datetime.fromtimestamp(value, UTC)
        except (OverflowError, OSError, ValueError):
            raise RecordRejected("invalid_timestamp", field) from None
    else:
        raise RecordRejected("invalid_timestamp", field)
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise RecordRejected("naive_timestamp", field)
    return dt.astimezone(UTC)


def try_parse_time(value: Any) -> datetime | None:
    """Stessa funzione di parsing del processor, senza eccezioni: None se non valido."""
    try:
        return _parse_time(value, "")
    except RecordRejected:
        return None


def _convert(
    src: dict[str, Any], old: str, new: str, factor: float, field_prefix: str = ""
) -> None:
    if old not in src:
        return
    if new in src:
        raise RecordRejected("conflicting_units", f"{field_prefix}{new}")
    value = src.pop(old)
    if not _is_num(value):
        raise RecordRejected("schema_violation", f"{field_prefix}{old}")
    src[new] = value * factor


def _normalise_units(rec: dict[str, Any]) -> None:
    _convert(rec, "power_kw", "power_w", 1000.0)
    for name in _NESTED:
        sub = rec.get(name)
        if isinstance(sub, dict):
            sub = dict(sub)
            rec[name] = sub
            _convert(sub, "az_rad", "az_deg", RAD_TO_DEG, f"{name}.")
            _convert(sub, "el_rad", "el_deg", RAD_TO_DEG, f"{name}.")


class TelemetryProcessor:
    """Processor puro (nessuno stato): un messaggio -> una riga clean oppure RecordRejected."""

    def __init__(self, now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self._now = now

    def process(self, message: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
        if not isinstance(message, Mapping):
            raise RecordRejected("not_an_object")
        source = message.get("source_id")
        if (
            not isinstance(source, str)
            or not SOURCE_RE.fullmatch(source)
            or source == CANARY_SOURCE
        ):
            raise RecordRejected("invalid_source_id")
        received_raw = message.get("received_utc")
        try:
            received = self._now() if received_raw is None else _parse_time(received_raw, "")
        except RecordRejected:
            raise RecordRejected("invalid_received_utc") from None
        record = message.get("record")
        if not isinstance(record, Mapping):
            raise RecordRejected("not_an_object")
        _scan_non_finite(record)
        rec = dict(record)
        _normalise_units(rec)
        rec["t_utc"] = _parse_time(rec.get("t_utc"), "t_utc")
        try:
            tel = Telemetry.model_validate(rec, strict=True)
        except ValidationError as e:
            err = e.errors()[0]
            loc = ".".join(str(p) for p in err["loc"])
            code = {"extra_forbidden": "unknown_field", "missing": "missing_field"}.get(
                err["type"], "schema_violation"
            )
            raise RecordRejected(code, loc) from None
        sun, earth = tel.sun, tel.earth
        return [
            {
                "source_id": source,
                "site_id": tel.site_id,
                "t_utc": tel.t_utc.astimezone(UTC),
                "schema_version": tel.schema_version,
                "power_w": tel.power_w,
                "link_margin_db": tel.link_margin_db,
                "sun_az_deg": sun.az_deg if sun else None,
                "sun_el_deg": sun.el_deg if sun else None,
                "earth_az_deg": earth.az_deg if earth else None,
                "earth_el_deg": earth.el_deg if earth else None,
                "received_utc": received,
            }
        ]


@dataclass(frozen=True)
class Admission:
    is_new: bool
    out_of_order: bool = False
    pending: bool = False  # duplicato di una chiave ammessa ma non ancora durevole


@dataclass
class _Partition:
    keys: set[Key]
    pending: set[Key]
    watermark: datetime | None


class Deduplicator:
    """Chiave di dedup = (source_id, site_id, t_utc). Stato per partizione (sorgente, giorno UTC).

    Protocollo a due fasi: `admit` ammette la chiave *provvisoriamente* (pending); solo dopo la
    scrittura durevole il chiamante fa `commit`; in caso di errore `forget`/`rollback_pending`
    rilasciano la chiave, quindi il retry non e' mai un falso duplicato. Le partizioni con chiavi
    pendenti sono "bloccate" e non vengono espulse dall'LRU.
    Alla prima visita di una partizione le chiavi gia' scritte si rileggono con `loader` (sicuro
    al riavvio). La memoria e' limitata dal numero di chiavi (`max_keys`) oltre che dal numero di
    partizioni (`max_partitions`). `out_of_order` = t_utc < massimo gia' visto nella partizione:
    il record e' accettato, solo segnalato.
    Non e' thread-safe: usarlo da un solo thread alla volta (il Pipeline serializza i batch).
    """

    def __init__(
        self,
        loader: Callable[[str, str], set[Key]] | None = None,
        max_partitions: int = 64,
        max_keys: int = 2_000_000,
    ) -> None:
        self._loader = loader
        self._max, self._max_keys = max_partitions, max_keys
        self._parts: OrderedDict[tuple[str, str], _Partition] = OrderedDict()
        self._total = 0

    def _evict(self) -> None:
        for pk in list(self._parts):
            if len(self._parts) <= self._max and self._total <= self._max_keys:
                return
            part = self._parts[pk]
            if part.pending:
                continue
            if len(self._parts) <= 1:
                return
            self._total -= len(part.keys)
            del self._parts[pk]

    def _partition(self, source: str, day: date) -> _Partition:
        pk = (source, day.isoformat())
        part = self._parts.get(pk)
        if part is None:
            keys = set(self._loader(*pk)) if self._loader else set()
            part = _Partition(keys, set(), max((t for _, t in keys), default=None))
            self._parts[pk] = part
            self._total += len(keys)
            self._evict_except(pk)
        else:
            self._parts.move_to_end(pk)
        return part

    def _evict_except(self, keep: tuple[str, str]) -> None:
        keep_part = self._parts.pop(keep)
        self._parts[keep] = keep_part  # il piu' recente: l'ultimo a essere espulso
        self._evict()

    def _find(self, row: Mapping[str, Any]) -> tuple[_Partition | None, Key]:
        t: datetime = row["t_utc"]
        part = self._parts.get((row["source_id"], t.astimezone(UTC).date().isoformat()))
        return part, (row["site_id"], t)

    def admit(self, row: Mapping[str, Any]) -> Admission:
        t: datetime = row["t_utc"]
        part = self._partition(row["source_id"], t.astimezone(UTC).date())
        key = (row["site_id"], t)
        if key in part.keys:
            return Admission(False, pending=key in part.pending)
        late = part.watermark is not None and t < part.watermark
        part.keys.add(key)
        part.pending.add(key)
        self._total += 1
        if part.watermark is None or t > part.watermark:
            part.watermark = t
        return Admission(True, late)

    def commit(self, row: Mapping[str, Any]) -> None:
        part, key = self._find(row)
        if part is not None:
            part.pending.discard(key)

    def forget(self, row: Mapping[str, Any]) -> None:
        part, key = self._find(row)
        if part is not None and key in part.keys:
            part.keys.discard(key)
            part.pending.discard(key)
            self._total -= 1

    def rollback_pending(self) -> None:
        for part in self._parts.values():
            for key in part.pending:
                part.keys.discard(key)
                self._total -= 1
            part.pending.clear()

    def has_pending(self) -> bool:
        return any(p.pending for p in self._parts.values())

    def is_committed(self, row: Mapping[str, Any]) -> bool:
        part, key = self._find(row)
        return part is not None and key in part.keys and key not in part.pending

    def total_keys(self) -> int:
        return self._total
