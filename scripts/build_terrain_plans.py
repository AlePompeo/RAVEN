# SPDX-License-Identifier: Apache-2.0
"""Precompute the terrain plan of every catalogue site into backend/assets/terrain_plans.json.

A plan is pure geometry (which tiles of which product a site needs), so it is shipped instead of recomputed by every server
start (about 0.3 s per site). `tests/backend/domain/grazing/test_terrain_plans.py` keeps the file equal to the computation.
Run: `PYTHONPATH=. .venv/bin/python scripts/build_terrain_plans.py`.
"""

from __future__ import annotations

import json

from backend.domain.grazing import dem_select as ds
from backend.domain.lunar.model import load_sites


def build() -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    for site in load_sites():
        lon = ((site.lon_deg_east + 180.0) % 360.0) - 180.0
        out[ds.plan_key(site.lat_deg, lon)] = ds.plan_to_json(
            ds._plan(round(site.lat_deg, 6), round(lon, 6))
        )
    return out


if __name__ == "__main__":
    ds.SHIPPED_PLANS.write_text(
        json.dumps(build(), separators=(",", ":"), sort_keys=True), encoding="utf-8"
    )
    print(f"wrote {ds.SHIPPED_PLANS}")
