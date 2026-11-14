# SPDX-License-Identifier: Apache-2.0
"""Download the terrain of every catalogue site outside the 20 m LOLA product (global 237 m product) and precompute the
horizon masks, in parallel.

Same tiles, same cache and same consent rules as the app: this is what the "needs download" confirmation fetches site by site,
done once at install time. The masks are CPU-bound, so they are spread over several processes (each writes its own files).
Run: `python -m backend.domain.raven.prefetch_global [--dry-run] [--jobs N] [--procs N]`.
"""

from __future__ import annotations

import argparse
import os
import threading
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from typing import Any

from backend.domain.grazing import dem_cache
from backend.domain.grazing.dem import FAR_DEM_ID, TILE, DemUnavailable, LolaDem, load_lock
from backend.domain.grazing.dem_select import plan_site
from backend.domain.lunar.model import load_sites
from backend.domain.raven.custom_terrain import TerrainStore

DOWNLOAD_JOBS = 24


def _horizon(site_id: str) -> str | None:
    """Compute and cache the horizon masks of one catalogue site (a one-off computation of about a second); an error text
    or None."""
    from backend.domain.raven import s0_context as s0
    from backend.domain.raven.s5_rf import terrain_params, unified_link_inputs

    tp = terrain_params(unified_link_inputs({}))
    site = s0.load_catalog()[site_id]
    plan = plan_site(site.lat_deg, site.lon_deg_east)
    if plan.status != "ok":
        return None
    kw = TerrainStore().kwargs(site, tp.profile_length_m)
    try:
        for h in sorted({tp.panel_height_m, tp.antenna_height_m}):
            kw["mask_for"](site.lat_deg, site.lon_deg_east, h)
    except Exception as e:  # noqa: BLE001 - a site that cannot be computed stays unknown, the others go on
        return f"{site_id}: {e}"
    return None


def _horizons(procs: int) -> int:
    """The horizon masks of every catalogue site read from the global terrain, so that the 3D viewer shows their link state
    at once. `procs` worker processes."""
    from backend.domain.raven import s0_context as s0

    ids = [x.id for x in s0.load_catalog().values() if x.dem_coverage is not True]
    failed = 0
    with ProcessPoolExecutor(max_workers=max(1, min(procs, len(ids)))) as pool:
        futures = [pool.submit(_horizon, i) for i in ids]
        for done, fut in enumerate(as_completed(futures), 1):
            err = fut.result()
            if err:
                failed += 1
                print(f"  horizon {err}", flush=True)
            print(f"PROGRESS {done} {len(ids)}", flush=True)
    return 1 if failed else 0


def _download_all(dems: dict[str, Any], todo: list[tuple[str, tuple[int, int]]], jobs: int) -> int:
    """The missing tiles of every product through ONE pool, so that the whole download is as parallel as the server allows."""
    lock = threading.Lock()
    total = len(todo)
    state = {"done": 0, "failed": 0}
    step = max(1, total // 50)

    def one(item: tuple[str, tuple[int, int]]) -> str | None:
        pid, tile = item
        try:
            dems[pid].tile(*tile)
        except DemUnavailable as e:
            return f"  tile {pid} {tile[0]}_{tile[1]}: {e}"
        dems[pid]._tiles.pop(
            tile, None
        )  # the tile is on disk: do not keep 190 MB of arrays in memory
        return None

    with ThreadPoolExecutor(max_workers=min(jobs, total)) as pool:
        for fut in as_completed([pool.submit(one, t) for t in todo]):
            msg = fut.result()
            with lock:
                state["done"] += 1
                if msg:
                    state["failed"] += 1
                    print(msg, flush=True)
                if state["done"] % step == 0 or state["done"] == total:
                    print(f"PROGRESS {state['done']} {total}", flush=True)
    return state["failed"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="count the tiles without downloading")
    ap.add_argument("--jobs", type=int, default=DOWNLOAD_JOBS, help="parallel downloads (1-32)")
    ap.add_argument(
        "--procs", type=int, default=min(8, os.cpu_count() or 1), help="processes for the masks"
    )
    args = ap.parse_args(argv)
    if not (1 <= args.jobs <= 32):
        ap.error("--jobs must be in [1, 32]")
    if not (1 <= args.procs <= 64):
        ap.error("--procs must be in [1, 64]")
    store = TerrainStore()
    wanted: dict[str, set[tuple[int, int]]] = {}
    for site in load_sites():
        plan = plan_site(site.lat_deg, site.lon_deg_east)
        if plan.status != "ok":
            print(f"{site.id}: no terrain product, skipped")
            continue
        for pid, tiles in plan.tiles.items():
            wanted.setdefault(pid, set()).update(tiles)
    # the WHOLE 75S 240 m product (about 58 MB): the automatic site search evaluates any polar cell at one comparable terrain product
    far = load_lock(dataset_id=FAR_DEM_ID)
    wanted.setdefault(FAR_DEM_ID, set()).update(
        (ti, tj)
        for ti in range((far.lines - 1) // TILE + 1)
        for tj in range((far.samples - 1) // TILE + 1)
    )
    todo_all: list[tuple[str, tuple[int, int]]] = []
    dems: dict[str, Any] = {}
    for pid, tile_set in sorted(wanted.items()):
        # no per-tile cache-limit check: it lists the whole directory after every write (quadratic over thousands of tiles);
        # the limit is applied once at the end
        dems[pid] = LolaDem(
            store.dir,
            load_lock(dataset_id=pid),
            allow_download=True,
            opener=store.opener,
            fallback_dirs=(store.fallback,) if store.fallback != store.dir else (),
            max_cache_bytes=None,
        )
        todo = [t for t in sorted(tile_set) if not dems[pid].has_tile(*t)]
        print(
            f"{pid}: {len(tile_set)} tiles, {len(tile_set) - len(todo)} cached, {len(todo)} to download"
        )
        todo_all.extend((pid, t) for t in todo)
    if args.dry_run:
        return 0
    if todo_all:
        failed = _download_all(dems, todo_all, args.jobs)
        dem_cache.enforce_limit(store.dir, store.max_bytes)
        if failed:
            return 1
    return _horizons(args.procs)


if __name__ == "__main__":
    raise SystemExit(main())
