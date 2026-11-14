# SPDX-License-Identifier: Apache-2.0
"""Typed inputs of the lunar analysis: sites, link, energy and time window.

Every numeric parameter is declared once in `PARAMS` with value, unit, validated bounds and a
source label: `V` = read from a primary source, `D` = derived by a repeatable formula from V
values, `I` = ILLUSTRATIVE (design choice, not verified). Nothing here is a measurement: results
are "potential under stated assumptions" (docs/domain/method.md). Sources: docs/domain/assumptions.md.
"""

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, fields
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from backend.domain.raven import params as reg
from backend.domain.raven.params import (
    DSN104Q,
    DSN301P,
    ILLUSTRATIVE,
    SOA22,
    TP2019,
    ParamError,
)
from backend.ephemeris.timeutil import TimeError, parse_utc

__all__ = [
    "DSN104Q",
    "DSN301P",
    "ILLUSTRATIVE",
    "PARAMS",
    "SOA22",
    "TP2019",
    "AnalysisWindow",
    "EnergyParams",
    "LinkParams",
    "ParamError",
    "ParamSpec",
    "Site",
    "defaults_table",
    "load_sites",
]

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
ORIENTATIONS = ("horizontal", "tilted", "tracking")
SUN_SEMIDIAMETER_DEG = reg.value(
    "common.sun_semidiameter_fixed_deg"
)  # apparent solar semi-diameter


@dataclass(frozen=True)
class ParamSpec:
    """Legacy view of a registry entry (`backend.domain.raven.params`): `key` is the legacy name."""

    key: str
    group: str  # link | energy | window
    default: float
    unit: str
    lo: float
    hi: float
    status: str  # V | D | I
    source: str  # citation, or "illustrative"
    note: str = ""


def legacy_view(scope: str) -> list[ParamSpec]:
    """The registry entries of `scope` as legacy specs, in the order of the old tables."""
    return [
        ParamSpec(s.name, s.group, s.default, s.unit, s.lo, s.hi, s.tag, s.source, s.note)
        for s in reg.scope_specs(scope)
    ]


_SPECS = legacy_view("lunar")
PARAMS: dict[str, ParamSpec] = {s.key: s for s in _SPECS}


def defaults_table() -> list[dict[str, Any]]:
    """All parameters as rows: key, group, value, unit, bounds, status, source."""
    rows: list[dict[str, Any]] = [
        {
            "key": s.key,
            "group": s.group,
            "value": s.default,
            "unit": s.unit,
            "min": s.lo,
            "max": s.hi,
            "status": s.status,
            "source": s.source,
            "note": s.note,
        }
        for s in _SPECS
    ]
    rows.append(
        {
            "key": "orientation",
            "group": "energy",
            "value": "horizontal",
            "unit": "-",
            "allowed": list(ORIENTATIONS),
            "status": "I",
            "source": ILLUSTRATIVE,
            "note": "horizontal | tilted (tilt_deg, tilt_azimuth_deg) | tracking (normal = Sun)",
        }
    )
    return rows


def _num(key: str, raw: object) -> float:
    return reg.REGISTRY[f"lunar.{key}"].check(raw)


def _gather(group: str, over: Mapping[str, object]) -> dict[str, float]:
    known = {s.key for s in _SPECS}
    for k in over:
        if k not in known and k != "orientation":
            raise ParamError("unknown")
    return {s.key: _num(s.key, over.get(s.key, s.default)) for s in _SPECS if s.group == group}


@dataclass(frozen=True)
class LinkParams:
    frequency_ghz: float
    tx_power_w: float
    tx_antenna_gain_dbi: float
    tx_dish_diameter_m: float
    tx_aperture_efficiency: float
    pointing_loss_db: float
    other_losses_db: float
    ground_gt_dbk: float
    data_rate_bps: float
    required_ebn0_db: float
    implementation_loss_db: float
    required_margin_db: float
    earth_site_elevation_mask_deg: float
    ground_station_min_elevation_deg: float

    @classmethod
    def from_overrides(cls, over: Mapping[str, object] | None = None) -> "LinkParams":
        return cls(**_gather("link", over or {}))

    def to_dict(self) -> dict[str, float]:
        return {f.name: getattr(self, f.name) for f in fields(self)}


@dataclass(frozen=True)
class EnergyParams:
    array_area_m2: float
    cell_efficiency: float
    packing_factor: float
    degradation_fraction: float
    tilt_deg: float
    tilt_azimuth_deg: float
    sun_elevation_mask_deg: float
    battery_capacity_wh: float
    charge_efficiency: float
    discharge_efficiency: float
    min_soc: float
    initial_soc: float
    survival_load_w: float
    active_load_w: float
    pa_efficiency: float
    comms_duty: float
    orientation: str = "horizontal"

    def __post_init__(self) -> None:
        if self.orientation not in ORIENTATIONS:
            raise ParamError("orientation")
        if self.min_soc >= 1.0:
            raise ParamError("min_soc")

    @classmethod
    def from_overrides(cls, over: Mapping[str, object] | None = None) -> "EnergyParams":
        over = over or {}
        orientation = over.get("orientation", "horizontal")
        if not isinstance(orientation, str):
            raise ParamError("orientation")
        return cls(orientation=orientation, **_gather("energy", over))

    def to_dict(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in fields(self)}


@dataclass(frozen=True)
class AnalysisWindow:
    start_utc: datetime
    days: float
    step_min: float

    def __post_init__(self) -> None:
        if self.start_utc.tzinfo is None or self.start_utc.utcoffset() != timedelta(0):
            raise ParamError("start_utc")
        _num("days", self.days)
        _num("step_min", self.step_min)

    @classmethod
    def build(cls, start_utc: str | datetime, days: object, step_min: object) -> "AnalysisWindow":
        try:
            t = parse_utc(start_utc)
        except (TimeError, TypeError, ValueError):
            raise ParamError("start_utc") from None
        return cls(t, _num("days", days), _num("step_min", step_min))

    @property
    def n_steps(self) -> int:
        return max(1, math.floor(self.days * 1440.0 / self.step_min + 1e-9))

    @property
    def dt_h(self) -> float:
        return self.step_min / 60.0

    def instants(self) -> list[datetime]:
        """Step START instants t0 + i*dt, i = 0..n_steps-1 (each step represents [t_i, t_i+dt))."""
        dt = timedelta(minutes=self.step_min)
        return [self.start_utc + i * dt for i in range(self.n_steps)]

    def to_dict(self) -> dict[str, Any]:
        s = self.start_utc.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        return {
            "start_utc": s,
            "days": self.days,
            "step_min": self.step_min,
            "n_steps": self.n_steps,
        }


@dataclass(frozen=True)
class Site:
    id: str
    name: str
    lat_deg: float
    lon_deg_east: float
    kind: str
    source_url: str
    verified: bool
    coordinate_basis: str

    def __post_init__(self) -> None:
        if not self.id or not self.name:
            raise ValueError("site without id or name")
        if not (math.isfinite(self.lat_deg) and -90.0 <= self.lat_deg <= 90.0):
            raise ValueError(f"site {self.id}: invalid latitude")
        if not (math.isfinite(self.lon_deg_east) and -180.0 <= self.lon_deg_east <= 180.0):
            raise ValueError(f"site {self.id}: invalid longitude")

    def to_dict(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in fields(self)}


def load_sites(path: Path | None = None) -> list[Site]:
    """Read and validate backend/domain/data/sites.json (unique ids, ranges, required fields)."""
    raw = json.loads((path or DATA_DIR / "sites.json").read_text(encoding="utf-8"))
    sites = [
        Site(
            id=str(r["id"]),
            name=str(r["name"]),
            lat_deg=float(r["lat_deg"]),
            lon_deg_east=float(r["lon_deg_east"]),
            kind=str(r["kind"]),
            source_url=str(r["source"]["url"]),
            verified=bool(r["verified"]),
            coordinate_basis=str(r["coordinate_basis"]),
        )
        for r in raw["sites"]
    ]
    ids = [s.id for s in sites]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate site ids")
    return sites
