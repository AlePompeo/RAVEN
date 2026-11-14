# SPDX-License-Identifier: Apache-2.0
"""Golden outputs of the current lunar and grazing engines (RAVEN migration step M0).

Runs the in-process API (`TestClient`) on FIXED scenarios and freezes the responses under
`tests/backend/domain/golden/`. Two sets:

* `synthetic`: no kernels, no tiles (synthetic ridge profile, analytic sweep, static tables). Always runs.
* `real`: needs the NAIF kernels and the cached LOLA tiles; the test skips it when they are absent.

Each file carries its provenance: commit sha, UTC date, the scenarios (parameters) and the ids and
hashes of the kernel and DEM products. Regenerating after an INTENTIONAL change of numbers is a
decision to record (docs/domain/raven-model.md, sec. 4.1); never regenerate to silence a failure.

Usage: .venv/bin/python scripts/raven_golden.py [--set synthetic|real|all]
"""

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = ROOT / "tests" / "backend" / "domain" / "golden"
START = "2027-04-07T00:00:00Z"
T_ONE = "2027-04-07T00:00:00Z"
# Keys whose value depends on the machine or on cache state, not on the model.
VOLATILE_KEYS = frozenset({"compute_s", "cache", "from_cache", "cache_source", "elapsed_s"})


def _ridge_profile() -> dict[str, list[float]]:
    d = [5.0 * i for i in range(801)]  # 4 km
    z = [max(40.0 - (x - 2000.0) ** 2 / 200.0, 0.0) for x in d]  # 40 m ridge, R = 100 m at 2 km
    return {"distance_m": d, "height_m": z}


SWEEP: dict[str, Any] = {
    "start_utc": START,
    "days": 2,
    "step_min": 30,
    "profile": _ridge_profile(),
    "earth_sweep": {"el_start_deg": 0.0, "el_end_deg": 3.0},
    "overrides": {"rate_bps": 1e4},
}
LUNAR: dict[str, Any] = {
    "site_ids": ["apollo11", "malapert-massif", "haworth"],
    "start_utc": "2027-01-01T00:00:00Z",
    "days": 2,
    "step_min": 60,
}
MISSION: dict[str, Any] = {
    "site_id": "malapert-massif",
    "start_utc": "2027-01-01T00:00:00Z",
    "days": 3,
    "step_min": 60,
}

# (name, set, method, path, payload). `payload` is the JSON body (POST) or the query (GET).
CASES: list[tuple[str, str, str, str, dict[str, Any] | None]] = [
    ("lunar_sites", "synthetic", "GET", "/api/lunar/sites", None),
    ("lunar_defaults", "synthetic", "GET", "/api/lunar/defaults", None),
    ("grazing_defaults", "synthetic", "GET", "/api/grazing/defaults", None),
    ("grazing_compensation", "synthetic", "GET", "/api/grazing/compensation", None),
    ("grazing_antenna", "synthetic", "POST", "/api/grazing/antenna", {}),
    ("grazing_antenna_dsn18", "synthetic", "POST", "/api/grazing/antenna", {"station": "dsn18"}),
    ("grazing_analyze_sweep", "synthetic", "POST", "/api/grazing/analyze", SWEEP),
    (
        "grazing_analyze_sweep_k",
        "synthetic",
        "POST",
        "/api/grazing/analyze",
        {**SWEEP, "overrides": {"rate_bps": 1e5, "tx_power_dbw": 12.0, "antenna_height_m": 3.5}},
    ),
    ("lunar_analyze", "real", "POST", "/api/lunar/analyze", LUNAR),
    ("lunar_timeline", "real", "POST", "/api/lunar/timeline", LUNAR),
    (
        "lunar_solar_terrain",
        "real",
        "POST",
        "/api/lunar/solar-terrain",
        {**LUNAR, "site_ids": ["malapert-massif", "haworth"]},
    ),
    ("lunar_mission_malapert", "real", "POST", "/api/lunar/mission", MISSION),
    (
        "lunar_mission_haworth",
        "real",
        "POST",
        "/api/lunar/mission",
        {**MISSION, "site_id": "haworth"},
    ),
    (
        "lunar_horizon_haworth",
        "real",
        "POST",
        "/api/lunar/horizon",
        {"site_id": "haworth", "observer_height_m": 2},
    ),
    (
        "grazing_analyze_shackleton",
        "real",
        "POST",
        "/api/grazing/analyze",
        {"site_id": "shackleton", "start_utc": START, "days": 2, "step_min": 60},
    ),
    (
        "grazing_compare",
        "real",
        "POST",
        "/api/grazing/compare",
        {
            "site_ids": ["shackleton", "malapert-massif"],
            "start_utc": START,
            "days": 2,
            "step_min": 60,
            "overrides": {"rate_bps": 1e4},
        },
    ),
    ("grazing_snapshot", "real", "GET", "/api/grazing/snapshot", {"t": T_ONE}),
    ("grazing_scene_haworth", "real", "GET", "/api/grazing/scene", {"site": "haworth", "t": T_ONE}),
]


def _git_sha() -> str:
    out = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return out.stdout.strip() or "unknown"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def have_kernels() -> bool:
    from backend.ephemeris import kernels

    try:
        kernels.require_kernels()
    except kernels.EphemerisUnavailable:
        return False
    return True


def have_tiles() -> bool:
    from backend.domain.grazing.dem import DEFAULT_DIR

    return DEFAULT_DIR.is_dir() and any(DEFAULT_DIR.glob("*.f32"))


def _strip(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip(v) for k, v in obj.items() if k not in VOLATILE_KEYS}
    if isinstance(obj, list):
        return [_strip(v) for v in obj]
    return obj


def make_client() -> Any:
    from fastapi.testclient import TestClient

    os.environ["GRAZING_DEM_ALLOW_DOWNLOAD"] = "0"  # never touch the network
    os.environ["RATE_LIMIT_PER_MIN"] = "100000"
    from scripts.raven_reference import build_reference_app

    return TestClient(build_reference_app())


def run_case(client: Any, method: str, path: str, payload: dict[str, Any] | None) -> dict[str, Any]:
    if method == "GET":
        r = client.get(path, params=payload or {})
    else:
        r = client.post(path, json=payload or {})
    body: Any = r.json()
    return {"status": r.status_code, "response": _strip(body)}


def cases_of(which: str) -> Iterator[tuple[str, str, str, str, dict[str, Any] | None]]:
    for c in CASES:
        if which in ("all", c[1]):
            yield c


def provenance(which: str) -> dict[str, Any]:
    from backend.domain.grazing.dem import load_lock

    prov: dict[str, Any] = {
        "git_commit": _git_sha(),
        "generated_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "generator": "scripts/raven_golden.py",
        "set": which,
        "note": (
            "Frozen outputs of the engines BEFORE the RAVEN migration. They pin the current numbers; "
            "they are not validation (see docs/domain/validation.md)."
        ),
        "cases": {n: {"method": m, "path": p, "payload": pl} for n, s, m, p, pl in cases_of(which)},
    }
    if which == "real":
        klock = ROOT / "backend/ephemeris/kernels.lock.json"
        prov["kernels_lock_sha256"] = _sha256(klock)
        prov["kernels"] = [
            {"name": k["name"], "sha256": k["sha256"]}
            for k in json.loads(klock.read_text())["kernels"]
        ]
        prov["dem_lock_sha256"] = _sha256(ROOT / "backend/domain/grazing/dem.lock.json")
        prov["dem_products"] = [
            {"id": load_lock(dataset_id=d).id, "sha256": load_lock(dataset_id=d).sha256}
            for d in ("ldem_85s_20m_float", "ldem_75s_240m_float")
        ]
    return prov


def generate(which: str) -> dict[str, Any]:
    client = make_client()
    out: dict[str, Any] = {}
    for name, _s, method, path, payload in cases_of(which):
        out[name] = run_case(client, method, path, payload)
    return {"provenance": provenance(which), "outputs": out}


def close(a: Any, b: Any, tol: float = 1e-9, path: str = "") -> list[str]:
    """Differences between two JSON values (floats within `tol`, relative or absolute)."""
    if isinstance(a, dict) and isinstance(b, dict):
        diffs: list[str] = []
        if a.keys() != b.keys():
            return [f"{path}: keys differ {sorted(set(a) ^ set(b))}"]
        for k in a:
            diffs += close(a[k], b[k], tol, f"{path}/{k}")
        return diffs
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return [f"{path}: length {len(a)} != {len(b)}"]
        out: list[str] = []
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            out += close(x, y, tol, f"{path}[{i}]")
        return out
    if (
        isinstance(a, float | int)
        and isinstance(b, float | int)
        and not isinstance(a, bool)
        and not isinstance(b, bool)
    ):
        if math.isclose(a, b, rel_tol=tol, abs_tol=tol):
            return []
        return [f"{path}: {a!r} != {b!r}"]
    return [] if a == b else [f"{path}: {a!r} != {b!r}"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=("synthetic", "real", "all"), default="all")
    args = ap.parse_args()
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    sets = ("synthetic", "real") if args.set == "all" else (args.set,)
    for which in sets:
        if which == "real" and not (have_kernels() and have_tiles()):
            print("real set skipped: kernels or LOLA tiles missing", file=sys.stderr)
            return 1
        data = generate(which)
        dest = GOLDEN_DIR / f"{which}.json"
        dest.write_text(
            json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8"
        )
        print(
            f"{dest.relative_to(ROOT)}: {dest.stat().st_size} bytes, {len(data['outputs'])} cases"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
