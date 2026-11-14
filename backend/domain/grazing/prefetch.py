# SPDX-License-Identifier: Apache-2.0
"""Prefetch of the LOLA tiles around the default sites (`make grazing-dem`), cached in `GRAZING_DEM_DIR`.

Two locked products, both read only as 128x128-pixel tiles (64 KiB each) intersecting a disc:

* LDEM_85S_20M within `--radius-m` (default 10.5 km: RF profiles and the near solar horizon are 10 km);
  only sites covered by it (latitude <= -85) are fetched;
* LDEM_75S_240M within `--far-radius-m` (default 201 km: the solar horizon mask reaches 200 km,
  `horizon.py`), for the same sites.

For the five covered registry sites (2026-11-04): 348 distinct tiles, 22.8 MB (20 m) plus 276
distinct tiles, 18.1 MB (240 m: the sites share most of them); `--dry-run` prints the counts. Nothing is committed (build/lola). Integrity checks are those
of `dem.LolaDem` (ETag, size, value range, per-tile sha256).
"""

import argparse
import math
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from backend.domain.grazing.dem import (
    FAR_DEM_ID,
    TILE,
    DemOutOfCoverage,
    DemUnavailable,
    LolaDem,
    dem_dir,
    load_lock,
)
from backend.domain.lunar.model import load_sites

__all__ = ["DEFAULT_SITES", "main", "tiles_for_site"]

# The sites the default install makes ready: the polar sites of the first catalogue. Every other covered site downloads its
# own tiles on demand (with the user's consent), or with --all-sites.
DEFAULT_SITES = (
    "malapert-massif",
    "haworth",
    "mons-mouton",
    "nobile-rim",
    "de-gerlache",
    "shackleton",
)
DEFAULT_JOBS = 24


def tiles_for_site(
    dem: LolaDem, lat_deg: float, lon_deg_east: float, radius_m: float
) -> list[tuple[int, int]]:
    """Tile indices (ti, tj) covering the square of half-side `radius_m` around the site."""
    row, col = dem.pixel(lat_deg, lon_deg_east)
    half = math.ceil(radius_m / dem.spec.scale_m)
    s = dem.spec
    r0, r1 = max(0, int(row) - half), min(s.lines - 1, int(row) + half)
    c0, c1 = max(0, int(col) - half), min(s.samples - 1, int(col) + half)

    def near(ti: int, tj: int) -> bool:  # does the tile intersect the disc of radius `half` px?
        dr = max(ti * TILE - row, 0.0, row - (ti * TILE + TILE - 1))
        dc = max(tj * TILE - col, 0.0, col - (tj * TILE + TILE - 1))
        return math.hypot(dr, dc) <= half

    return [
        (ti, tj)
        for ti in range(r0 // TILE, r1 // TILE + 1)
        for tj in range(c0 // TILE, c1 // TILE + 1)
        if near(ti, tj)
    ]


_progress_lock = threading.Lock()


def _download(dem: LolaDem, todo: list[tuple[int, int]], jobs: int) -> int:
    """Fetch the tiles in parallel (each tile is an independent range request); prints `PROGRESS done total` lines."""
    if not todo:
        return 0
    failed = 0
    done = 0
    total = len(todo)

    def one(tile: tuple[int, int]) -> str | None:
        try:
            dem.tile(*tile)
        except DemUnavailable as e:
            return f"  tile {dem.spec.id} {tile[0]}_{tile[1]}: {e}"
        return None

    step = max(1, total // 50)
    with ThreadPoolExecutor(max_workers=min(jobs, total)) as pool:
        for fut in as_completed([pool.submit(one, t) for t in todo]):
            msg = fut.result()
            with _progress_lock:
                done += 1
                if msg:
                    failed += 1
                    print(msg, flush=True)
                if done % step == 0 or done == total:
                    print(f"PROGRESS {done} {total}", flush=True)
    return failed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--radius-m", type=float, default=10_500.0)
    ap.add_argument("--far-radius-m", type=float, default=201_000.0)
    ap.add_argument("--dry-run", action="store_true", help="list the tiles without downloading")
    ap.add_argument(
        "--all-sites",
        action="store_true",
        help="every covered catalogue site, not only the default ones",
    )
    ap.add_argument("--jobs", type=int, default=DEFAULT_JOBS, help="parallel downloads (1-32)")
    args = ap.parse_args(argv)
    if not (500.0 <= args.radius_m <= 30_000.0):
        ap.error("--radius-m must be in [500, 30000]")
    if not (0.0 <= args.far_radius_m <= 250_000.0):
        ap.error("--far-radius-m must be in [0, 250000]")
    if not (1 <= args.jobs <= 32):
        ap.error("--jobs must be in [1, 32]")
    near = LolaDem()
    far = LolaDem(spec=load_lock(dataset_id=FAR_DEM_ID))
    print(f"cache: {dem_dir()}")
    failed = 0
    for dem, radius in ((near, args.radius_m), (far, args.far_radius_m)):
        if radius <= 0:
            continue
        unique: set[tuple[int, int]] = set()
        for site in (x for x in load_sites() if args.all_sites or x.id in DEFAULT_SITES):
            try:
                near.pixel(site.lat_deg, site.lon_deg_east)  # 20 m coverage gates both products
                tiles = tiles_for_site(dem, site.lat_deg, site.lon_deg_east, radius)
            except DemOutOfCoverage:
                print(f"{site.id}: fuori copertura DEM, saltato")
                continue
            print(f"{dem.spec.id} {site.id}: {len(tiles)} tile")
            unique.update(tiles)
        print(
            f"{dem.spec.id}: {len(unique)} tile distinte, {len(unique) * TILE * TILE * 4 / 1e6:.1f} MB"
        )
        if args.dry_run:
            continue
        todo = [t for t in sorted(unique) if not dem.has_tile(*t)]
        print(
            f"{dem.spec.id}: {len(unique) - len(todo)} already cached, {len(todo)} to download with {args.jobs} parallel requests"
        )
        failed += _download(dem, todo, args.jobs)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
