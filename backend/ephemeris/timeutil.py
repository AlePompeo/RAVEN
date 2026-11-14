# SPDX-License-Identifier: Apache-2.0
"""Parsing rigoroso degli istanti UTC (solo libreria standard: usabile senza l'extra `sky`)."""

import math
import re
from datetime import UTC, datetime, timedelta

MAX_SAMPLES = 200_000
_ISO_Z = re.compile(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?Z", re.ASCII)


class TimeError(ValueError):
    """Istante non valido (formato non UTC ISO-8601 con Z, o non finito)."""


def parse_utc(value: str | datetime) -> datetime:
    """UTC rigoroso: stringa `YYYY-MM-DDTHH:MM:SS[.ffffff]Z` o datetime con offset zero."""
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise TimeError("datetime deve essere UTC (offset 0)")
        return value.astimezone(UTC)
    if not isinstance(value, str):
        raise TimeError("istante non valido")
    m = _ISO_Z.fullmatch(value)
    if not m:
        raise TimeError("formato richiesto: AAAA-MM-GGThh:mm:ss[.ffffff]Z (UTC)")
    y, mo, d, h, mi, s, frac = m.groups()
    try:
        return datetime(
            int(y),
            int(mo),
            int(d),
            int(h),
            int(mi),
            int(s),
            int((frac or "0").ljust(6, "0")),
            tzinfo=UTC,
        )
    except ValueError:
        raise TimeError("data o ora inesistente") from None


def utc_grid(t0: str | datetime, t1: str | datetime, step_s: float) -> list[datetime]:
    """Istanti t0, t0+step, ... <= t1 (inclusivo)."""
    a, b = parse_utc(t0), parse_utc(t1)
    if not (math.isfinite(step_s) and step_s > 0):
        raise TimeError("passo non valido")
    if b < a:
        raise TimeError("intervallo invertito")
    n = int((b - a).total_seconds() // step_s) + 1
    if n > MAX_SAMPLES:
        raise TimeError("troppi campioni")
    return [a + timedelta(seconds=i * step_s) for i in range(n)]
