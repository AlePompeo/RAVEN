# SPDX-License-Identifier: Apache-2.0
"""Interrogazioni predefinite e relativi parametri (solo pydantic: nessuna dipendenza da duckdb).

Il client sceglie un nome fra quelli qui elencati e fornisce parametri validati; il testo SQL
vive solo in `query.py` e non e' mai influenzabile dal client.
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

MAX_ROWS = 1000
SITE_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$"
SOURCE_ID_PATTERN = r"^[a-z0-9][a-z0-9_-]{0,63}$"
QUERY_NAME_PATTERN = r"^[a-z][a-z_]{0,31}$"

SiteId = Annotated[str, StringConstraints(pattern=SITE_ID_PATTERN)]
SourceId = Annotated[str, StringConstraints(pattern=SOURCE_ID_PATTERN)]
RowLimit = Annotated[int, Field(ge=1, le=MAX_ROWS)]


class _Params(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=False)


class LatestSamples(_Params):
    """Ultimi `limit` campioni per sito (e per sorgente)."""

    site_id: SiteId | None = None
    source_id: SourceId | None = None
    limit: RowLimit = 100


class PowerHourly(_Params):
    """Potenza aggregata per ora (media/min/max) di un sito nelle ultime `hours` ore."""

    site_id: SiteId
    source_id: SourceId | None = None
    hours: Annotated[int, Field(ge=1, le=720)] = 24
    limit: RowLimit = 720


class StaleSources(_Params):
    """Sorgenti il cui ultimo dato ricevuto e' piu' vecchio di `threshold_s` secondi."""

    threshold_s: Annotated[int, Field(ge=1, le=366 * 86400)] = 300
    limit: RowLimit = 100


QUERY_MODELS: dict[str, type[_Params]] = {
    "latest_samples": LatestSamples,
    "power_hourly": PowerHourly,
    "stale_sources": StaleSources,
}


class UnknownQuery(KeyError):
    pass


class QueryError(RuntimeError):
    """Errore del motore (messaggio generico: i dettagli vanno solo nel log)."""
