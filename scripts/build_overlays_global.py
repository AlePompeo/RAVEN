# SPDX-License-Identifier: Apache-2.0
"""Build the shipped whole-Moon overlays (equirectangular, 720 x 360 cells of 0.5 degree) into backend/assets/overlays/global-*.json.

The height is the LOLA LDEM global 237 m product (4.2 GB) read at ONE point per cell by HTTP range requests (259,200 four-byte
ranges in about 2,000 requests): no tile download. The samples are kept in build/lola/global_samples_720x360.npy, so a second run
(or an interrupted one) does no network at all. Sun and Earth directions come from the JPL DE440 kernels (build/ephemeris).
Run: GRAZING_DEM_DIR=build/lola PYTHONPATH=. .venv/bin/python scripts/build_overlays_global.py
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta

import numpy as np

from backend.domain.grazing.dem import (
    NETWORK_RETRY_DELAYS_S,
    TIMEOUT_S,
    DemSpec,
    LolaDem,
    _opener,
    dem_dir,
    load_lock,
    parse_ranges,
)
from backend.domain.raven import overlays_global as og
from backend.ephemeris.engine import Engine

PER_REQUEST = 128
JOBS = 24


def _fetch(spec: DemSpec, offsets: list[int]) -> dict[int, float]:
    ranges = [(o, o + 3) for o in offsets]
    req = urllib.request.Request(
        spec.url, headers={"Range": "bytes=" + ",".join(f"{a}-{b}" for a, b in ranges)}
    )
    last: Exception | None = None
    for delay in (0.0, *NETWORK_RETRY_DELAYS_S):
        time.sleep(delay)
        try:
            with _opener().open(req, timeout=TIMEOUT_S) as resp:
                status, ctype, etag = (
                    resp.status,
                    resp.headers.get("Content-Type", ""),
                    resp.headers.get("ETag"),
                )
                body = resp.read(8 << 20)
            if status != 206:
                raise OSError(f"HTTP {status}")
            if etag is not None and etag != spec.etag:
                raise ValueError("the DEM file changed on the server (ETag differs from the lock)")
            got = parse_ranges(body, ctype, ranges)
            return {o: float(np.frombuffer(got[o], dtype="<f4")[0]) for o in offsets}
        except (urllib.error.URLError, OSError, KeyError) as e:
            last = e
    raise RuntimeError(f"range request failed: {last}")


def sample_heights() -> np.ndarray:
    """Heights in metres at the centre of every 0.5 degree cell (NaN where a sample could not be read)."""
    cache = dem_dir() / "global_samples_720x360.npy"
    if cache.is_file():
        return np.load(cache)
    spec = load_lock(dataset_id="ldem_128_float")
    dem = LolaDem(spec=spec)
    lat, lon = og.grid()
    rows, cols = dem.pixel_arrays(lat.ravel(), lon.ravel())
    r = np.clip(np.rint(rows).astype(np.int64), 0, spec.lines - 1)
    c = np.rint(cols).astype(np.int64) % spec.samples
    offsets = (r * spec.samples + c) * 4
    unique = sorted({int(o) for o in offsets})
    batches = [unique[i : i + PER_REQUEST] for i in range(0, len(unique), PER_REQUEST)]
    print(f"{len(unique)} samples in {len(batches)} requests", flush=True)
    values: dict[int, float] = {}
    with ThreadPoolExecutor(max_workers=JOBS) as pool:
        for n, fut in enumerate(as_completed([pool.submit(_fetch, spec, b) for b in batches]), 1):
            values.update(fut.result())
            if n % 100 == 0:
                print(f"  {n}/{len(batches)}", flush=True)
    km = np.array([values.get(int(o), np.nan) for o in offsets], dtype=np.float64)
    km[(km < spec.min_km - 0.5) | (km > spec.max_km + 0.5)] = (
        np.nan
    )  # outside the product's own range: not a height
    h = (km * 1000.0).reshape(og.HEIGHT, og.WIDTH)
    np.save(cache, h)
    return h


def main() -> int:
    h = sample_heights()
    print("heights", np.nanmin(h), np.nanmax(h), int(np.isnan(h).sum()), "unreadable", flush=True)
    og.ASSETS.mkdir(parents=True, exist_ok=True)

    def write(o: dict) -> None:
        (og.ASSETS / f"global-{o['layer']}.json").write_text(
            json.dumps(o, separators=(",", ":")) + "\n", encoding="utf-8"
        )
        print(o["layer"], o["unit"], round(o["min"], 2), round(o["max"], 2), flush=True)

    write(og.elevation_overlay(h))
    write(og.slope_overlay(h))
    write(og.coverage_overlay())
    print("horizons...", flush=True)
    horizons, trusted = og.horizon_grid(h)
    start = datetime(2027, 1, 1, tzinfo=UTC)
    times = [start + timedelta(hours=6 * i) for i in range(365 * 4)]
    engine = Engine()
    sun_pts = engine.subsolar_point("moon", times)
    earth_pts = engine.sub_earth_point("moon", times)
    for layer, pts, what in (("sun", sun_pts, "Sun"), ("earth", earth_pts, "Earth")):
        print(f"{layer}...", flush=True)
        frac = og.visibility_fraction(
            horizons, trusted, np.asarray(pts.lat_deg), np.asarray(pts.lon_deg_east)
        )
        write(og.fraction_overlay(layer, frac, what))
    print("joint availability and gaps...", flush=True)
    lat, lon = og.grid()
    m = og.joint_metrics(
        horizons,
        trusted,
        lat,
        lon,
        (np.asarray(sun_pts.lat_deg), np.asarray(sun_pts.lon_deg_east)),
        (np.asarray(earth_pts.lat_deg), np.asarray(earth_pts.lon_deg_east)),
        6.0,
    )
    src = "derived: horizons marched over the global LOLA grid (0.5 degree cells, 30 cells, 24 azimuths); Sun and Earth directions from the JPL DE440 ephemerides every 6 h of 2027"
    note = "Regional (15 km cells): terrain smaller than a cell is invisible, so rough ground is overstated. Not validated against NASA illumination products."
    write(og.both_overlay(m["both"], note, src))
    write(og.gap_overlay("sun_gap", m["sun_gap_h"], "Sun", src, note))
    write(og.gap_overlay("earth_gap", m["earth_gap_h"], "Earth", src, note))
    return 0


if __name__ == "__main__":
    sys.exit(main())
