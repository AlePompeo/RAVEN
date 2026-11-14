# SPDX-License-Identifier: Apache-2.0
"""Terrain of custom sites: dry-run estimate, capped on-demand download and the S2 hooks.

Flow (docs/domain/raven-model.md, S2; docs/process/decisions-2026-11-04.md, minimal download):

1. `TerrainStore.estimate(sites)` plans every site (`dem_select.plan_site`) and counts, per product,
   the tiles it needs and those already cached. It never touches the network.
2. `TerrainStore.download(sites)` fetches ONLY the missing planned tiles, from the fixed PDS URLs of
   `dem.lock.json` (`LolaDem` refuses any other host), then trims the disk cache to its cap (oldest
   tiles first, the tiles of this request are kept). The caller must have been told (`allow_download`).
3. `TerrainStore.kwargs(site)` gives `terrain()` the per-site `mask_for`/`profile_for`, reading the
   cache only. A tile that is missing stays unknown (never a flat horizon); a site without terrain
   gets a `mask_for` that reports "outside coverage".

Caps: 10 MB per site (`MAX_SITE_BYTES`, the plan picks a shorter far range to fit, else the site has
no terrain), 40 MB of downloads per request (`MAX_REQUEST_BYTES`), disk cache `GRAZING_DEM_CACHE_MAX_MB`
(default 200).
"""

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from backend.domain.grazing import dem_cache
from backend.domain.grazing.analysis import ProfileCache
from backend.domain.grazing.dem import TILE, DemOutOfCoverage, LolaDem, dem_dir, load_lock
from backend.domain.grazing.dem_select import (
    MAX_REQUEST_BYTES,
    MAX_SITE_BYTES,
    TILE_BYTES,
    WIRE_FACTOR,
    TerrainPlan,
    plan_site,
)
from backend.domain.grazing.horizon import HorizonMask, MaskStore
from backend.domain.grazing.terrain import TerrainProfile, profile_from_dem
from backend.domain.raven.s0_context import SiteRecord

__all__ = ["MAX_REQUEST_BYTES", "MAX_SITE_BYTES", "TerrainStore", "terrain_block"]


def _mb(n: int) -> float:
    return round(n / 1e6, 2)


class TerrainStore:
    def __init__(
        self,
        directory: Path | None = None,
        *,
        fallback: Path | None = None,
        max_bytes: int | None = None,
        opener: Any = None,
    ) -> None:
        self.dir = directory if directory is not None else dem_cache.custom_dir()
        self.fallback = fallback if fallback is not None else dem_dir()
        self.max_bytes = max_bytes if max_bytes is not None else dem_cache.max_cache_bytes()
        self.opener = opener
        self.masks = MaskStore(
            directory=self.dir / "horizon",
            max_disk_bytes=self.max_bytes,
            quota_directory=self.dir,
        )
        self.profiles = ProfileCache()

    # -- products -----------------------------------------------------------------------------
    def dem(self, dataset_id: str, *, allow_download: bool = False) -> LolaDem:
        return LolaDem(
            self.dir,
            load_lock(dataset_id=dataset_id),
            allow_download=allow_download,
            opener=self.opener,
            fallback_dirs=(self.fallback,) if self.fallback != self.dir else (),
            max_cache_bytes=self.max_bytes,
        )

    # -- estimate -----------------------------------------------------------------------------
    def _missing(self, plan: TerrainPlan) -> dict[str, list[tuple[int, int]]]:
        out: dict[str, list[tuple[int, int]]] = {}
        for pid, tiles in plan.tiles.items():
            d = self.dem(pid)
            out[pid] = [t for t in tiles if not d.has_tile(*t)]
        return out

    def cached_checker(self) -> Callable[[SiteRecord], bool]:
        """A fast `site -> all planned tiles are in the cache` test for many sites at once: the cache directories are listed
        once (a file name set) instead of one `stat` per tile. Valid for the moment of the call."""
        import os

        names: set[str] = set()
        for d in (self.dir, *(() if self.fallback == self.dir else (self.fallback,))):
            try:
                names.update(e.name for e in os.scandir(d))
            except OSError:
                continue

        def ok(site: SiteRecord) -> bool:
            plan = plan_site(site.lat_deg, site.lon_deg_east)
            if plan.status != "ok":
                return True  # nothing to download; the terrain is reported as unavailable elsewhere
            for pid, tiles in plan.tiles.items():
                for ti, tj in tiles:
                    base = f"{pid}.t{TILE}.{ti}_{tj}"
                    if f"{base}.f32" not in names or f"{base}.sha256" not in names:
                        return False
            return True

        return ok

    def estimate(self, sites: Sequence[SiteRecord]) -> dict[str, Any]:
        """Dry run: tiles and MB per site and in total, what is cached, the caps. No network."""
        rows: list[dict[str, Any]] = []
        union: dict[str, set[tuple[int, int]]] = {}
        for s in sites:
            plan = plan_site(s.lat_deg, s.lon_deg_east)
            miss = self._missing(plan) if plan.status == "ok" else {}
            n_miss = sum(len(v) for v in miss.values())
            if plan.status == "ok":
                for pid, tl in miss.items():
                    union.setdefault(pid, set()).update(tl)
            rows.append(
                {
                    "id": s.id,
                    "name": s.name,
                    "lat_deg": s.lat_deg,
                    "lon_deg_east": s.lon_deg_east,
                    **plan.to_dict(),
                    "products": [
                        {
                            "id": pid,
                            "scale_m": load_lock(dataset_id=pid).scale_m,
                            "tiles": len(tl),
                            "tiles_cached": len(tl) - len(miss.get(pid, tl)),
                        }
                        for pid, tl in plan.tiles.items()
                    ]
                    if plan.status != "unknown"
                    else [],
                    "tiles_cached": plan.n_tiles - n_miss if plan.status == "ok" else 0,
                    "tiles_to_download": n_miss,
                    "mb_to_download": _mb(int(n_miss * TILE_BYTES * WIRE_FACTOR)),
                    "terrain_available": plan.status == "ok",
                }
            )
        n_dl = sum(len(v) for v in union.values())
        return {
            "sites": rows,
            "tile_bytes": TILE_BYTES,
            "wire_factor": WIRE_FACTOR,
            "mb_total": _mb(sum(r["tiles"] * TILE_BYTES for r in rows if r["terrain_available"])),
            "mb_to_download": _mb(int(n_dl * TILE_BYTES * WIRE_FACTOR)),
            "needs_download": n_dl > 0,
            "request_over_cap": n_dl * TILE_BYTES * WIRE_FACTOR > MAX_REQUEST_BYTES,
            "caps": {
                "site_mb": MAX_SITE_BYTES / 1e6,
                "request_mb": MAX_REQUEST_BYTES / 1e6,
                "cache_mb": self.max_bytes / 1e6,
            },
            "cache": {
                "used_mb": _mb(dem_cache.usage_bytes(self.dir)),
                "max_mb": self.max_bytes / 1e6,
            },
        }

    # -- download -----------------------------------------------------------------------------
    def download(self, sites: Sequence[SiteRecord]) -> int:
        """Fetch the missing planned tiles; returns how many. Raises `DemUnavailable` on a failure."""
        n = 0
        keep: list[Path] = []
        for s in sites:
            plan = plan_site(s.lat_deg, s.lon_deg_east)
            if plan.status != "ok":
                continue
            for pid, tiles in plan.tiles.items():
                d = self.dem(pid, allow_download=True)
                for ti, tj in tiles:
                    had = d.has_tile(ti, tj)
                    d.tile(ti, tj)
                    n += 0 if had else 1
                    keep.append(d._tile_path(ti, tj))
        for p in keep:
            if p.exists():
                dem_cache.touch(p)
                dem_cache.touch(p.with_suffix(".sha256"))
        dem_cache.enforce_limit(self.dir, self.max_bytes, protect=keep)
        return n

    # -- S2 hooks -----------------------------------------------------------------------------
    def kwargs(
        self,
        site: SiteRecord,
        profile_length_m: float,
        *,
        compute: bool = True,
        coarse: bool = False,
    ) -> dict[str, Any]:
        """`terrain()` keyword arguments for a custom site: its product, cache only. Without `compute` an uncached horizon
        mask is reported as unavailable instead of being computed (the snapshot of many sites must stay quick)."""
        plan = plan_site(site.lat_deg, site.lon_deg_east, coarse)
        if (
            plan.status != "ok"
            or plan.config is None
            or plan.near_id is None
            or plan.far_id is None
        ):

            def no_terrain(lat: float, lon: float, h: float) -> HorizonMask:
                raise DemOutOfCoverage("no terrain product within the data cap")

            return {"mask_for": no_terrain, "profile_for": None, "injected": False}
        near = self.dem(plan.near_id)
        far = near if plan.far_id == plan.near_id else self.dem(plan.far_id)
        needed = plan.needed()
        cfg = plan.config

        def mask_for(lat: float, lon: float, h: float) -> HorizonMask:
            return self.masks.get(
                lat, lon, h, cfg, near_dem=near, far_dem=far, needed=needed, compute=compute
            )

        def profile_for(azq: float) -> TerrainProfile:
            key = (
                near.spec.id,
                round(site.lat_deg, 5),
                round(site.lon_deg_east, 5),
                azq,
                profile_length_m,
            )
            return self.profiles.get(
                key,
                lambda: profile_from_dem(
                    near, site.lat_deg, site.lon_deg_east, azq, profile_length_m
                ),
            )

        return {"mask_for": mask_for, "profile_for": profile_for, "injected": False}


def terrain_block(site: SiteRecord, mask_meta: dict[str, Any] | None, state: str) -> dict[str, Any]:
    """The 'terrain' entry of a result: which product(s) and resolution, or why it is unknown."""
    plan = plan_site(site.lat_deg, site.lon_deg_east) if site.custom else None
    out: dict[str, Any] = {"state": "known" if state == "ok" else "unknown", "reason": state}
    if mask_meta is not None:
        prods = mask_meta.get("products") or []
        out["products"] = [{"id": p["id"], "resolution_m": p["scale_m"]} for p in prods]
        out["resolution_m"] = prods[0]["scale_m"] if prods else None
        out["horizon_range_km"] = mask_meta["far_range_m"][1] / 1000.0
    else:
        out.update(products=[], resolution_m=None, horizon_range_km=None)
    if plan is not None and plan.status == "exceeds_site_cap":
        out["reason"] = "exceeds_site_cap"
    out["custom"] = site.custom
    return out
