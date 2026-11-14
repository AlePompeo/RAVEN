# SPDX-License-Identifier: Apache-2.0
"""Phase 0 of the site discovery: how long does one RAVEN core evaluation take?

Measures POST /api/raven/evaluate (14 days, 60 min steps, no steps in the answer) on catalogue sites, in process, in two regimes:
`cold` = first evaluation of a site in this process (masks come from disk or are computed) and `warm` = the same site at another
start date (masks in memory). The budget of the search (how many evaluations fit in 90 s) is derived from these numbers.
Run: GRAZING_DEM_DIR=build/lola PYTHONPATH=. .venv/bin/python scripts/measure_core_cost.py [N_SITES]
"""

from __future__ import annotations

import statistics
import sys
import time

from fastapi.testclient import TestClient

from backend.bootstrap import build_app


def body(site: str, start: str) -> dict[str, object]:
    return {"site_id": site, "start_utc": start, "days": 14, "step_min": 60, "include_steps": False}


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    with TestClient(build_app()) as c:
        sites = [s["id"] for s in c.get("/api/raven/sites").json()["sites"]]
        # an even spread over the catalogue (polar 20 m sites and northern 237 m sites)
        pick = [sites[int(i * len(sites) / n)] for i in range(n)]
        cold: list[float] = []
        warm: list[float] = []
        for s in pick:
            t0 = time.perf_counter()
            r = c.post("/api/raven/evaluate", json=body(s, "2027-04-07T00:00:00Z"))
            cold.append(time.perf_counter() - t0)
            if r.status_code != 200:
                print(f"{s}: HTTP {r.status_code}", flush=True)
                continue
            t0 = time.perf_counter()
            c.post("/api/raven/evaluate", json=body(s, "2027-05-07T00:00:00Z"))
            warm.append(time.perf_counter() - t0)
        for name, v in (("cold", cold), ("warm", warm)):
            if v:
                q = sorted(v)
                print(
                    f"{name}: n={len(v)} median {statistics.median(v):.2f} s, mean {statistics.mean(v):.2f} s, "
                    f"p90 {q[int(0.9 * (len(q) - 1))]:.2f} s, max {q[-1]:.2f} s"
                )
        if warm:
            print(f"evaluations in 90 s at the warm median: {int(90 / statistics.median(warm))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
