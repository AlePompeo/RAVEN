# SPDX-License-Identifier: Apache-2.0
"""Metriche e controlli di qualita' per livello (spec 14.1/14.5). Python puro, senza librerie dati.

Per livello: record in / out / dropped (scartati, p.es. duplicati) / dead_letter.
Per sorgente: last_seen, lag (secondi dall'ultimo dato ricevuto), data_lag (secondi dall'ultimo
istante di misura), stato `ok` | `stale` | `no_data`. Un orologio iniettato rende lo stato testabile.
"""

import functools
import math
import threading
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

LAYERS = ("raw", "clean", "curated")
FUTURE_TOLERANCE = timedelta(minutes=5)
_ZERO = {"in": 0, "out": 0, "dropped": 0, "dead_letter": 0}


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _positive(value: float, what: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError(f"{what} deve essere un numero finito > 0")
    return float(value)


class _Source:
    def __init__(self, registered: datetime, stale_after_s: float | None) -> None:
        self.registered = registered
        self.stale_after_s = stale_after_s
        self.last_seen: datetime | None = None
        self.last_data_t: datetime | None = None
        self.layers = {layer: dict(_ZERO) for layer in LAYERS}
        self.counters: dict[str, int] = {}


def _locked[F: Callable[..., Any]](fn: F) -> F:
    @functools.wraps(fn)
    def wrapper(self: "PipelineMetrics", *a: Any, **k: Any) -> Any:
        with self._lock:
            return fn(self, *a, **k)

    return wrapper  # type: ignore[return-value]


class PipelineMetrics:
    def __init__(self, clock: Callable[[], datetime], stale_after_s: float = 300.0) -> None:
        self._clock = clock
        self._default_stale = _positive(stale_after_s, "stale_after_s")
        self._lock = threading.RLock()  # aggiornata dai thread dei job, letta dal loop
        self._sources: dict[str, _Source] = {}
        self._quality: dict[str, dict[str, dict[str, int]]] = {}

    def _source(self, source_id: str) -> _Source:
        s = self._sources.get(source_id)
        if s is None:
            s = self._sources[source_id] = _Source(self._clock(), None)
        return s

    @_locked
    def ensure_source(self, source_id: str) -> None:
        self._source(source_id)

    @_locked
    def register_source(self, source_id: str, stale_after_s: float | None = None) -> None:
        if stale_after_s is not None:
            stale_after_s = _positive(stale_after_s, "stale_after_s")
        s = self._source(source_id)
        s.stale_after_s = stale_after_s

    @_locked
    def add(
        self, layer: str, source_id: str, *, in_: int = 0, out: int = 0, dropped: int = 0,
        dead_letter: int = 0,
    ) -> None:  # fmt: skip
        if layer not in LAYERS:
            raise ValueError(f"livello sconosciuto: {layer!r}")
        c = self._source(source_id).layers[layer]
        c["in"] += in_
        c["out"] += out
        c["dropped"] += dropped
        c["dead_letter"] += dead_letter

    @_locked
    def count(self, source_id: str, name: str, n: int = 1) -> None:
        s = self._source(source_id)
        s.counters[name] = s.counters.get(name, 0) + n

    @_locked
    def seen(self, source_id: str, data_t: datetime | None = None) -> None:
        s = self._source(source_id)
        s.last_seen = self._clock()
        if data_t is not None and (s.last_data_t is None or data_t > s.last_data_t):
            s.last_data_t = data_t

    @_locked
    def quality(self, layer: str, check: str, passed: int, failed: int) -> None:
        c = self._quality.setdefault(layer, {}).setdefault(check, {"passed": 0, "failed": 0})
        c["passed"] += passed
        c["failed"] += failed

    @_locked
    def record_checks(self, layer: str, results: Mapping[str, tuple[int, int]]) -> None:
        for check, (passed, failed) in results.items():
            self.quality(layer, check, passed, failed)

    @_locked
    def snapshot(self) -> dict[str, Any]:
        now = self._clock()
        totals = {layer: dict(_ZERO) for layer in LAYERS}
        sources: dict[str, Any] = {}
        stale: list[str] = []
        for sid, s in sorted(self._sources.items()):
            for layer in LAYERS:
                for k, v in s.layers[layer].items():
                    totals[layer][k] += v
            threshold = s.stale_after_s or self._default_stale
            ref = s.last_seen or s.registered
            silent = max(0.0, (now - ref).total_seconds())
            if silent > threshold:
                status = "stale"
                stale.append(sid)
            else:
                status = "ok" if s.last_seen else "no_data"
            sources[sid] = {
                "status": status,
                "stale_after_s": threshold,
                "last_seen_utc": _iso(s.last_seen) if s.last_seen else None,
                "lag_s": silent if s.last_seen else None,
                "last_data_utc": _iso(s.last_data_t) if s.last_data_t else None,
                "data_lag_s": max(0.0, (now - s.last_data_t).total_seconds())
                if s.last_data_t
                else None,
                "layers": {k: dict(v) for k, v in s.layers.items()},
                "counters": dict(s.counters),
            }
        return {
            "generated_at_utc": _iso(now),
            "layers": totals,
            "sources": sources,
            "stale_sources": stale,
            "quality": {k: {c: dict(v) for c, v in d.items()} for k, d in self._quality.items()},
        }


# ---- controlli di qualita' per livello: (superati, falliti) per controllo ----


def _tally(
    rows: Sequence[Mapping[str, Any]], pred: Callable[[Mapping[str, Any]], bool]
) -> tuple[int, int]:
    ok = sum(1 for r in rows if pred(r))
    return ok, len(rows) - ok


def check_raw_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, tuple[int, int]]:
    return {"non_empty_payload": _tally(rows, lambda r: bool(r.get("payload_json")))}


def _finite(v: Any) -> bool:
    return v is None or (isinstance(v, int | float) and math.isfinite(v))


def check_clean_rows(
    rows: Sequence[Mapping[str, Any]], now: datetime
) -> dict[str, tuple[int, int]]:
    numeric = (
        "power_w",
        "link_margin_db",
        "sun_az_deg",
        "sun_el_deg",
        "earth_az_deg",
        "earth_el_deg",
    )
    return {
        "required_fields": _tally(
            rows,
            lambda r: all(
                r.get(k) is not None for k in ("source_id", "site_id", "t_utc", "power_w")
            ),
        ),
        "finite_values": _tally(rows, lambda r: all(_finite(r.get(k)) for k in numeric)),
        "not_in_future": _tally(rows, lambda r: r["t_utc"] <= now + FUTURE_TOLERANCE),
        "received_not_before_measured": _tally(
            rows,
            lambda r: (
                r.get("received_utc") is None or r["received_utc"] >= r["t_utc"] - FUTURE_TOLERANCE
            ),
        ),
    }


def check_curated_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, tuple[int, int]]:
    return {
        "n_positive": _tally(rows, lambda r: r["n"] > 0),
        "min_le_mean_le_max": _tally(
            rows, lambda r: r["power_w_min"] <= r["power_w_mean"] <= r["power_w_max"]
        ),
    }
