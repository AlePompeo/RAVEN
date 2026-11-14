# SPDX-License-Identifier: Apache-2.0
"""S0 site and time: the context every other stage reads (docs/domain/raven-model.md, 2.3).

* `SiteRecord` carries the provenance of the coordinates (source URL, access date, note, `verified`
  = copied from the cited source). The catalogue is `backend/domain/data/sites.json`; a site with
  invalid coordinates is an error, never filled in.
* One time grid for the whole chain: `n_steps = max(1, floor(days * 1440 / step_min + 1e-9))`
  (the lunar formula; the grazing one differs only by the 1e-9). Over the cap is an error: the
  steps are never decimated.
* Step i stands for [t_i, t_i + dt); the geometry is sampled at t_i.
"""

import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from backend.domain.raven import params as reg
from backend.domain.raven.known import Known

__all__ = [
    "CATALOG_PATH",
    "CUSTOM_PREFIX",
    "MAX_CUSTOM_SITES",
    "Limits",
    "S0Error",
    "SiteRecord",
    "SiteResolver",
    "StepCapExceeded",
    "TimeGrid",
    "TimeWindow",
    "build_grid",
    "check_total_steps",
    "custom_site",
    "default_limits",
    "load_catalog",
    "n_steps",
    "normalise_lon",
    "resolve_site",
    "sanitise_name",
]

CATALOG_PATH = Path(__file__).resolve().parents[1] / "data" / "sites.json"
USER_SOURCE_NOTE = "coordinates given by the user, not verified"
CUSTOM_PREFIX = (
    "c-"  # no catalogue id starts with it, so a custom id never clashes with a catalogue one
)
MAX_CUSTOM_SITES = 8
_CUSTOM_ID = re.compile(r"^c-[a-z0-9](?:[a-z0-9-]{0,30}[a-z0-9])?$")
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._,()'-]{0,39}$")


class S0Error(ValueError):
    """Invalid site or window. `key` names the field; the message never contains the input."""

    def __init__(self, key: str) -> None:
        super().__init__("invalid site or window")
        self.key = key


class StepCapExceeded(S0Error):
    """The window has more steps than the cap (the API answers 422; there is no decimation)."""


@dataclass(frozen=True)
class SiteRecord:
    """A lunar site with the provenance of its coordinates."""

    id: str
    name: str
    lat_deg: float  # planetocentric, Mean Earth / Polar Axis frame
    lon_deg_east: float  # east positive, -180..180
    kind: str
    coordinate_basis: str
    source_url: str
    source_accessed: str
    source_note: str
    verified: bool  # True = coordinates copied from the source, not region centres
    dem_coverage: Known[
        bool
    ]  # terrain data available (custom: a plan within the caps); None = lock unreadable
    custom: bool = False  # given by the user in this request, never in the catalogue
    panel_height_m: float | None = None  # custom sites only: own heights (else the request's)
    antenna_height_m: float | None = None

    def to_dict(self) -> dict[str, object]:
        return {f: getattr(self, f) for f in self.__dataclass_fields__}


@dataclass(frozen=True)
class TimeWindow:
    start_utc: datetime  # timezone-aware UTC
    days: float
    step_min: float


@dataclass(frozen=True)
class Limits:
    """Bounds of a window and caps on the number of steps (never decimated: over the cap = error)."""

    max_days: float
    min_step_min: float
    max_step_min: float
    max_steps_per_site: int
    max_steps_total: int


@dataclass(frozen=True)
class TimeGrid:
    """One grid for the whole chain. Step i stands for [t_i, t_i + dt), geometry sampled at t_i."""

    start_utc: datetime
    step_min: float
    n_steps: int
    instants: tuple[datetime, ...]
    t_unix: tuple[float, ...]


class SiteResolver(Protocol):
    def __call__(self, site_id: str) -> SiteRecord: ...


def default_limits() -> Limits:
    """Limits from the registry: the widest legacy window bounds and the D9 caps."""
    return Limits(
        max_days=reg.get("lunar.days").hi,
        min_step_min=reg.get("grazing.window_step_min").lo,
        max_step_min=reg.get("lunar.step_min").hi,
        max_steps_per_site=int(reg.value("common.max_steps_per_site")),
        max_steps_total=int(reg.value("common.max_steps_total")),
    )


def _dem_coverage(lat_deg: float) -> Known[bool]:
    try:
        from backend.domain.grazing.dem import load_lock

        return lat_deg <= -load_lock().max_lat_deg
    except (OSError, KeyError, ValueError):
        return None


def _checked(site_id: str, lat_deg: float, lon_deg_east: float) -> None:
    if not site_id:
        raise S0Error("site_id")
    if not (math.isfinite(lat_deg) and -90.0 <= lat_deg <= 90.0):
        raise S0Error("lat_deg")
    if not (math.isfinite(lon_deg_east) and -180.0 <= lon_deg_east <= 180.0):
        raise S0Error("lon_deg_east")


def load_catalog(path: Path | None = None) -> dict[str, SiteRecord]:
    """Read the catalogue with provenance; unique ids, valid coordinates, required fields."""
    raw = json.loads((path or CATALOG_PATH).read_text(encoding="utf-8"))
    out: dict[str, SiteRecord] = {}
    for r in raw["sites"]:
        sid, lat, lon = str(r["id"]), float(r["lat_deg"]), float(r["lon_deg_east"])
        _checked(sid, lat, lon)
        if sid in out or sid.startswith(CUSTOM_PREFIX):
            raise S0Error("site_id")
        src = r["source"]
        out[sid] = SiteRecord(
            id=sid,
            name=str(r["name"]),
            lat_deg=lat,
            lon_deg_east=lon,
            kind=str(r["kind"]),
            coordinate_basis=str(r["coordinate_basis"]),
            source_url=str(src["url"]),
            source_accessed=str(src["accessed"]),
            source_note=str(src["note"]),
            verified=bool(r["verified"]),
            dem_coverage=_dem_coverage(lat),
        )
    return out


def resolve_site(site_id: str, catalog: dict[str, SiteRecord] | None = None) -> SiteRecord:
    """A catalogue site by id; an unknown id is an error (no echo of the id)."""
    cat = catalog if catalog is not None else load_catalog()
    try:
        return cat[site_id]
    except KeyError:
        raise S0Error("site_id") from None


def normalise_lon(lon_deg_east: float) -> float:
    """East longitude in (-180, 180]; 0..360 input (a common convention) is accepted."""
    if not (math.isfinite(lon_deg_east) and -180.0 <= lon_deg_east <= 360.0):
        raise S0Error("lon_deg_east")
    lon = ((lon_deg_east + 180.0) % 360.0) - 180.0
    return 180.0 if lon == -180.0 and lon_deg_east >= 180.0 else lon


def sanitise_name(name: str) -> str:
    """A display name: 1..40 characters of letters, digits, space and ._,()'- ; anything else is an error."""
    n = name.strip()
    if not _NAME.fullmatch(n):
        raise S0Error("name")
    return n


def custom_site(
    site_id: str,
    lat_deg: float,
    lon_deg_east: float,
    *,
    name: str | None = None,
    panel_height_m: float | None = None,
    antenna_height_m: float | None = None,
    strict: bool = False,
) -> SiteRecord:
    """A site given by the user: never `verified`, coordinates range-checked.

    `strict` (the API) also demands the `c-` id prefix, a sanitised name, heights in the model's range
    and decides terrain availability from the tile plan (the product that covers the point)."""
    if strict:
        if not _CUSTOM_ID.fullmatch(site_id):
            raise S0Error("site_id")
        lon_deg_east = normalise_lon(lon_deg_east)
        lon_deg_east = round(lon_deg_east, 5)
        for h in (panel_height_m, antenna_height_m):
            if h is not None and not (math.isfinite(h) and 0.1 <= h <= 100.0):
                raise S0Error("height")
    _checked(site_id, lat_deg, lon_deg_east)
    label = sanitise_name(name) if (strict and name is not None) else (name or site_id)
    coverage: Known[bool] = _dem_coverage(lat_deg)
    if strict:
        try:
            from backend.domain.grazing.dem_select import plan_site

            coverage = plan_site(lat_deg, lon_deg_east).status == "ok"
        except (OSError, KeyError, ValueError):
            coverage = None
    return SiteRecord(
        id=site_id,
        name=label,
        lat_deg=lat_deg,
        lon_deg_east=lon_deg_east,
        kind="user",
        coordinate_basis="point",
        source_url="",
        source_accessed="",
        source_note=USER_SOURCE_NOTE,
        verified=False,
        dem_coverage=coverage,
        custom=strict,
        panel_height_m=panel_height_m,
        antenna_height_m=antenna_height_m,
    )


def n_steps(days: float, step_min: float) -> int:
    """The single step-count formula of the chain."""
    return max(1, math.floor(days * 1440.0 / step_min + 1e-9))


def check_total_steps(n_sites: int, steps_per_site: int, limits: Limits | None = None) -> None:
    """Raise `StepCapExceeded` if a multi-site request is over the total cap."""
    lim = limits or default_limits()
    if n_sites < 1 or n_sites * steps_per_site > lim.max_steps_total:
        raise StepCapExceeded("total_steps")


def build_grid(window: TimeWindow, limits: Limits | None = None) -> TimeGrid:
    """The time grid of a window: exact instants, no decimation, error over the cap."""
    lim = limits or default_limits()
    t0 = window.start_utc
    if t0.tzinfo is None or t0.utcoffset() != timedelta(0):
        raise S0Error("start_utc")
    days, step = window.days, window.step_min
    if not (math.isfinite(days) and 0.0 < days <= lim.max_days):
        raise S0Error("days")
    if not (math.isfinite(step) and lim.min_step_min <= step <= lim.max_step_min):
        raise S0Error("step_min")
    n = n_steps(days, step)
    if n > lim.max_steps_per_site:
        raise StepCapExceeded("steps_per_site")
    dt = timedelta(minutes=step)
    inst = tuple((t0 + i * dt).astimezone(UTC) for i in range(n))
    return TimeGrid(
        start_utc=t0,
        step_min=step,
        n_steps=n,
        instants=inst,
        t_unix=tuple(t.timestamp() for t in inst),
    )
