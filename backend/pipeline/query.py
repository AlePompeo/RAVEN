# SPDX-License-Identifier: Apache-2.0
"""QueryEngine DuckDB su Parquet: SOLO interrogazioni predefinite con parametri legati.

Difese (nomi delle impostazioni verificati su duckdb 1.5.6 con `duckdb_settings()`):
- connessione `read_only=True` su un database vuoto (nessuna scrittura possibile);
- `allowed_paths=[<file Parquet visibili>]` (solo quelli elencati dallo store), poi `enable_external_access=false` e `lock_configuration=true`:
  nessun altro file (ne' nuovi file nello store), nessun ATTACH/COPY/estensione, configurazione non riapribile;
- il testo SQL e' costante; i valori arrivano solo come parametri legati (`?`);
- l'elenco dei file e' deciso dallo store (`visible_files`), mai dal client;
- tetto di righe (`max_rows`), `memory_limit` e `threads` limitati.
"""

import logging
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import duckdb
from pydantic import BaseModel

from backend.pipeline.query_spec import (
    MAX_ROWS,
    QUERY_MODELS,
    LatestSamples,
    PowerHourly,
    QueryError,
    StaleSources,
    UnknownQuery,
)
from backend.pipeline.store import ParquetStore

log = logging.getLogger(__name__)

_TS = "strftime({col} AT TIME ZONE 'UTC', '%Y-%m-%dT%H:%M:%S.%fZ')"
_FILES = "read_parquet(?, union_by_name=true)"

_SQL_LATEST = f"""
SELECT source_id, site_id, {_TS.format(col="t_utc")} AS t_utc, power_w, link_margin_db,
       sun_az_deg, sun_el_deg, earth_az_deg, earth_el_deg
FROM {_FILES}
WHERE (?::VARCHAR IS NULL OR site_id = ?) AND (?::VARCHAR IS NULL OR source_id = ?)
QUALIFY row_number() OVER (PARTITION BY source_id, site_id ORDER BY t_utc DESC) <= ?
ORDER BY site_id, source_id, t_utc DESC
LIMIT ?
"""

_SQL_HOURLY = f"""
SELECT source_id, site_id,
       {_TS.format(col="date_trunc('hour', t_utc)")} AS hour_utc,
       count(*) AS n, avg(power_w) AS power_w_mean, min(power_w) AS power_w_min,
       max(power_w) AS power_w_max
FROM {_FILES}
WHERE site_id = ? AND (?::VARCHAR IS NULL OR source_id = ?) AND t_utc >= ?::TIMESTAMPTZ
GROUP BY source_id, site_id, date_trunc('hour', t_utc)
ORDER BY date_trunc('hour', t_utc) DESC, source_id
LIMIT ?
"""

_SQL_STALE = f"""
SELECT source_id, {_TS.format(col="last_received")} AS last_received_utc,
       {_TS.format(col="last_t")} AS last_t_utc, n, silent_s
FROM (
  SELECT source_id, max(received_utc) AS last_received, max(t_utc) AS last_t, count(*) AS n,
         epoch(?::TIMESTAMPTZ) - epoch(max(received_utc)) AS silent_s
  FROM {_FILES}
  GROUP BY source_id
)
WHERE silent_s > ?
ORDER BY silent_s DESC, source_id
LIMIT ?
"""


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class DuckDbQueryEngine:
    def __init__(
        self,
        store: ParquetStore,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        max_rows: int = MAX_ROWS,
        memory_limit: str = "256MB",
        threads: int = 2,
    ) -> None:
        if max_rows < 1:
            raise ValueError("max_rows deve essere >= 1")
        self._store, self._clock, self._max_rows = store, clock, max_rows
        self._memory_limit, self._threads = memory_limit, threads
        meta = store.root / ".meta"
        meta.mkdir(parents=True, exist_ok=True)
        self._db_file = meta / "query.duckdb"
        if not self._db_file.exists():
            duckdb.connect(str(self._db_file)).close()  # database vuoto, poi solo read_only

    def names(self) -> Sequence[str]:
        return sorted(QUERY_MODELS)

    def _connect(self, files: Sequence[str]) -> duckdb.DuckDBPyConnection:
        con = duckdb.connect(
            str(self._db_file),
            read_only=True,
            config={
                "memory_limit": self._memory_limit,
                "threads": self._threads,
                "allow_community_extensions": False,
                "autoinstall_known_extensions": False,
                "autoload_known_extensions": False,
            },
        )
        # ordine obbligatorio: allowed_paths non e' modificabile dopo enable_external_access=false
        con.execute("SET allowed_paths=?", [list(files)])
        con.execute("SET TimeZone='UTC'")
        con.execute("SET enable_external_access=false")
        con.execute("SET lock_configuration=true")
        return con

    def connect_for_test(self, files: Sequence[str]) -> duckdb.DuckDBPyConnection:
        return self._connect(files)

    def query(self, name: str, params: Mapping[str, Any]) -> list[dict[str, Any]]:
        model_cls = QUERY_MODELS.get(name) if isinstance(name, str) else None
        if model_cls is None:
            raise UnknownQuery(name if isinstance(name, str) and len(name) < 64 else "?")
        return self.execute_validated(name, model_cls.model_validate(dict(params)))

    def execute_validated(self, name: str, p: BaseModel) -> list[dict[str, Any]]:
        limit = self._max_rows
        now = self._clock().astimezone(UTC)
        source = getattr(p, "source_id", None)
        files = self._store.visible_files("clean", source if _valid_source(source) else None)
        if not files:
            return []
        if isinstance(p, LatestSamples):
            sql = _SQL_LATEST
            args: list[Any] = [
                files,
                p.site_id,
                p.site_id,
                p.source_id,
                p.source_id,
                p.limit,
                limit,
            ]
        elif isinstance(p, PowerHourly):
            since = _iso(now - timedelta(hours=p.hours))
            sql = _SQL_HOURLY
            args = [files, p.site_id, p.source_id, p.source_id, since, min(p.limit, limit)]
        elif isinstance(p, StaleSources):
            sql = _SQL_STALE
            args = [files, _iso(now), float(p.threshold_s), min(p.limit, limit)]
        else:
            raise UnknownQuery(name)
        # `files` e' il primo `?` nell'ordine del testo SQL; per _SQL_STALE e' dopo il tempo "now"
        if isinstance(p, StaleSources):
            args = [_iso(now), files, float(p.threshold_s), min(p.limit, limit)]
        for attempt in range(2):
            try:
                con = self._connect(files)
                try:
                    cur = con.execute(sql, args)
                    cols = [d[0] for d in cur.description]
                    return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]
                finally:
                    con.close()
            except duckdb.Error:
                if attempt == 0:
                    # compattazione/retention concorrente oppure file corrotto: i file con footer
                    # illeggibile vengono messi in quarantena, si rielenca e si riprova una volta
                    self._store.quarantine_invalid("clean")
                    files = self._store.visible_files(
                        "clean", source if _valid_source(source) else None
                    )
                    if not files:
                        return []
                    if isinstance(p, StaleSources):
                        args[1] = files
                    else:
                        args[0] = files
                    continue
                log.exception("query %s fallita", name)
                raise QueryError("interrogazione non riuscita") from None
        raise QueryError("interrogazione non riuscita")  # pragma: no cover


def _valid_source(source: Any) -> bool:
    from backend.pipeline.store import SOURCE_RE

    return isinstance(source, str) and bool(SOURCE_RE.fullmatch(source))
