# SPDX-License-Identifier: Apache-2.0
"""Measure decision D4: how often terrain beyond the RF profile hides the Earth (RAVEN M4).

For each DEM-covered catalogue site, over one window, S2 reports per step whether the highest
terrain at the Earth azimuth lies beyond `profile_length_m` and above the Earth centre
(`far_terrain_hides_earth`) and the resulting `terrain_reason`. The count is a lower bound (the mask
keeps only the highest sample per azimuth). Prints JSON; nothing is written to the repository.

Usage: .venv/bin/python scripts/raven_d4_measure.py [--start 2027-01-01T00:00:00Z] [--days 365] [--step 60]
"""

import argparse
import json
import sys
from datetime import datetime
from typing import Any

from backend.domain.raven import s0_context as s0
from backend.domain.raven import s1_geometry as s1
from backend.domain.raven import s2_terrain as s2
from backend.domain.raven.known import Reason


def measure(start: str, days: float, step: float) -> dict[str, Any]:
    from backend.ephemeris.engine import get_engine

    eng = get_engine()
    lim = s0.default_limits()
    lim = s0.Limits(lim.max_days, lim.min_step_min, lim.max_step_min, 10**6, 10**6)
    grid = s0.build_grid(s0.TimeWindow(datetime.fromisoformat(start), days, step), lim)
    out: dict[str, Any] = {
        "window": {"start_utc": start, "days": days, "step_min": step, "n_steps": grid.n_steps},
        "profile_length_m": s2.TerrainParams.from_registry().profile_length_m,
        "sites": {},
    }
    for site in s0.load_catalog().values():
        if site.dem_coverage is not True:
            continue
        geo = s1.geometry(eng, site, grid)
        t = s2.terrain(site, geo)
        n = grid.n_steps
        up = [i for i in range(n) if geo.earth_el_deg[i] > 0.0]
        far = t.far_terrain_hides_earth
        row = {
            "steps": n,
            "earth_above_flat_horizon": len(up),
            "far_terrain_hides_earth_all_steps": sum(1 for v in far if v is True),
            "far_terrain_hides_earth_when_earth_above_flat": sum(1 for i in up if far[i] is True),
            "far_terrain_unknown": sum(1 for v in far if v is None),
            "reason_counts": {r.value: sum(1 for x in t.terrain_reason if x is r) for r in Reason},
            "earth_el_deg_range": [
                round(float(geo.earth_el_deg.min()), 3),
                round(float(geo.earth_el_deg.max()), 3),
            ],
            "earth_az_deg_range": [
                round(float(geo.earth_az_deg.min()), 2),
                round(float(geo.earth_az_deg.max()), 2),
            ],
            "mask_complete_fraction": (t.mask_meta or {}).get("complete_azimuth_fraction"),
        }
        hid = [i for i in up if far[i] is True]
        if hid:
            row["hidden_by_far_terrain_distance_m_range"] = [
                round(min(t.earth_horizon_distance_m[i] or 0.0 for i in hid)),
                round(max(t.earth_horizon_distance_m[i] or 0.0 for i in hid)),
            ]
            row["hidden_excess_deg_max"] = round(
                max((t.earth_horizon_deg[i] or 0.0) - float(geo.earth_el_deg[i]) for i in hid), 3
            )
        out["sites"][site.id] = row
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2027-01-01T00:00:00Z")
    ap.add_argument("--days", type=float, default=365.0)
    ap.add_argument("--step", type=float, default=60.0)
    a = ap.parse_args()
    print(json.dumps(measure(a.start, a.days, a.step), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
