# SPDX-License-Identifier: Apache-2.0
"""S6 DSN visibility (docs/domain/raven-model.md, 2.9; migration step M6).

Geometric visibility of the Moon centre from the three DSN complexes (34 m BWG antenna each,
coordinates DSN 810-005/301 Rev. P Table 5) above `lunar.ground_station_min_elevation_deg` (registry,
tag V, 6 deg). It is NOT scheduling and NOT antenna assignment. The 18 m class has no verified
station list: its visibility is unknown (`unknown_station`), never visible by default.
"""

from dataclasses import dataclass
from typing import Literal

from backend.domain.raven import params as reg
from backend.domain.raven.known import Known, Reason
from backend.domain.raven.s1_geometry import Geometry

__all__ = ["Dsn", "dsn"]


@dataclass(frozen=True)
class Dsn:
    complex_visible: dict[str, list[bool]]
    any_visible: list[Known[bool]]
    station_class: str
    min_elevation_deg: float
    reason: list[Reason]


def dsn(
    geo: Geometry,
    station: Literal["dsn34", "dsn18"] = "dsn34",
    min_elevation_deg: float | None = None,
) -> Dsn:
    """S6 over the grid of `geo`. The threshold defaults to the registry value."""
    thr = (
        reg.value("lunar.ground_station_min_elevation_deg")
        if min_elevation_deg is None
        else min_elevation_deg
    )
    n = geo.dsn_moon_el_deg.shape[1]
    per = {
        c: [bool(v) for v in (geo.dsn_moon_el_deg[k] >= thr)]
        for k, c in enumerate(geo.dsn_complexes)
    }
    if station == "dsn34":
        anyv: list[Known[bool]] = [bool(v) for v in (geo.dsn_moon_el_deg >= thr).any(axis=0)]
        reason = [Reason.OK] * n
    else:
        anyv = [None] * n
        reason = [Reason.UNKNOWN_STATION] * n
    return Dsn(per, anyv, station, thr, reason)
