# SPDX-License-Identifier: Apache-2.0
"""Terrain product selection and tile planning for custom sites (docs/domain/raven-model.md, S2).

For a point given by the user this module decides, without any network access:

* which LOLA products can give its terrain: LDEM_85S_20M (20 m) near the south pole, LDEM_75S_240M
  (240 m) south of 75 S, LDEM_128_FLOAT (about 237 m at the equator, global) elsewhere. Outside every
  product, or when no radius of at least 30 km fits the data cap, the terrain is UNKNOWN (never a flat
  horizon);
* the exact set of 128x128 tiles (64 KiB each) that the horizon mask and the RF profile read, so that
  the dry-run estimate equals what a download fetches: the tiles come from the very sample points of
  the mask (1440 azimuths, the radial steps of the configuration), with the bilinear neighbours;
* the range of the far horizon: 200 km if the tiles fit the per-site cap (10 MB), else the largest of
  150, 100, 75, 50 and 30 km that does. A shorter range is declared in every result (terrain beyond it
  is not seen, so the horizon is a lower bound there).

Nothing is downloaded here. `dem_cache`/`LolaDem` do the fetching, only for the planned tiles.
"""

import json
import math
import threading
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from backend.domain.grazing.dem import (
    TILE,
    DemSpec,
    load_lock,
)
from backend.domain.grazing.geometry import great_circle_destination
from backend.domain.grazing.horizon import MaskConfig

__all__ = [
    "MAX_REQUEST_BYTES",
    "MAX_SITE_BYTES",
    "TILE_BYTES",
    "WIRE_FACTOR",
    "TerrainPlan",
    "choose_products",
    "has_terrain_product",
    "plan_site",
]

TILE_BYTES = TILE * TILE * 4
WIRE_FACTOR = (
    1.28  # bytes on the wire per tile byte (multipart/byteranges headers; measured 1.27-1.28)
)
MAX_SITE_BYTES = 10_000_000  # per custom site, counted on the wire
MAX_REQUEST_BYTES = 40_000_000  # per request, on the wire (what is still to be downloaded)
RANGES_M = (200_000.0, 150_000.0, 100_000.0, 75_000.0, 50_000.0, 30_000.0)
NEAR_M = 10_000.0
EDGE_PX = 2.0  # margin of the planned discs, pixels
N_AZ = 1440
NEAR_20M = "ldem_85s_20m_float"
POLAR_240M = "ldem_75s_240m_float"
GLOBAL_ID = "ldem_128_float"
_R_M = 1_737_400.0


@dataclass(frozen=True)
class TerrainPlan:
    """What the terrain of one point needs. `status`: ok | unknown | exceeds_site_cap."""

    lat_deg: float
    lon_deg_east: float
    status: str
    reason: str
    near_id: str | None = None
    far_id: str | None = None
    resolution_m: float | None = None  # of the near product (the RF profile and the near horizon)
    far_resolution_m: float | None = None
    range_m: float | None = None  # far horizon range actually planned
    config: MaskConfig | None = None
    tiles: dict[str, tuple[tuple[int, int], ...]] = field(default_factory=dict)

    @property
    def n_tiles(self) -> int:
        return sum(len(v) for v in self.tiles.values())

    @property
    def bytes_total(self) -> int:
        """Size of the tiles on disk."""
        return self.n_tiles * TILE_BYTES

    @property
    def bytes_wire(self) -> int:
        """Estimated bytes to transfer for all of them (the cap of 10 MB is on this number)."""
        return int(self.n_tiles * TILE_BYTES * WIRE_FACTOR)

    def needed(self) -> dict[str, set[tuple[int, int]]]:
        return {k: set(v) for k, v in self.tiles.items()}

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "reason": self.reason,
            "near_product": self.near_id,
            "far_product": self.far_id,
            "resolution_m": self.resolution_m,
            "far_resolution_m": self.far_resolution_m,
            "range_km": None if self.range_m is None else self.range_m / 1000.0,
            "tiles": self.n_tiles,
            "mb_total": round(self.bytes_total / 1e6, 2),
            "mb_transfer": round(self.bytes_wire / 1e6, 2),
        }


def _deg(m: float) -> float:
    return math.degrees(m / _R_M)


def choose_products(lat_deg: float, coarse: bool = False) -> list[tuple[str, str]]:
    """Candidate (near, far) products for a latitude, best resolution first. Always ends with the
    global product; the caller drops those whose coverage does not contain the planned disc."""
    out: list[tuple[str, str]] = []
    if (
        lat_deg <= -85.0 and not coarse
    ):  # `coarse`: every cell on the same 240 m product (comparable candidates)
        out.append((NEAR_20M, POLAR_240M))
    if lat_deg <= -75.0:
        out.append((POLAR_240M, POLAR_240M))
    out.append((GLOBAL_ID, GLOBAL_ID))
    return out


def has_terrain_product(lat_deg: float) -> bool:
    """A product exists for this latitude (the global one covers every point); cheap, no tile planning."""
    return -90.0 <= lat_deg <= 90.0


def _covers_disc(spec: DemSpec, lat_deg: float, radius_m: float) -> bool:
    if spec.projection == "cylindrical":
        return True  # the seam is handled by wrapping; the poles by the tile cap
    return lat_deg + _deg(radius_m) <= -spec.max_lat_deg


def _tile_entries(
    spec: DemSpec, lat: float, lon: float, dist_m: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """(codes, distances) of every tile touched by the mask samples at `dist_m` over 1440 azimuths,
    with the bilinear neighbours. code = ti * 100000 + tj (tj wrapped for the cylindrical product)."""
    az = np.radians(np.arange(N_AZ, dtype=np.float64) * (360.0 / N_AZ))[:, None]
    delta = (dist_m / _R_M)[None, :]
    la, lo = great_circle_destination(lat, lon, az, delta)
    row, col = spec.pixel_arrays(la.ravel(), lo.ravel())
    d = np.broadcast_to(dist_m[None, :], la.shape).ravel()
    r0 = np.floor(row).astype(np.int64)
    c0 = np.floor(col).astype(np.int64)
    codes: list[np.ndarray] = []
    dists: list[np.ndarray] = []
    for dr in (0, 1):
        for dc in (0, 1):
            r, c = r0 + dr, c0 + dc
            if dr == 1 or dc == 1:  # a neighbour only matters on a tile edge
                keep = ((r0 % TILE == TILE - 1) & (dr == 1)) | ((c0 % TILE == TILE - 1) & (dc == 1))
                if not keep.any():
                    continue
                r, c, dd = r[keep], c[keep], d[keep]
            else:
                dd = d
            if spec.projection == "cylindrical":
                c = c % spec.samples
            ok = (r >= 0) & (c >= 0) & (r < spec.lines) & (c < spec.samples)
            codes.append((r[ok] // TILE) * 100_000 + c[ok] // TILE)
            dists.append(dd[ok])
    return np.concatenate(codes), np.concatenate(dists)


def _decode(codes: np.ndarray) -> tuple[tuple[int, int], ...]:
    u = np.unique(codes)
    return tuple((int(x) // 100_000, int(x) % 100_000) for x in u)


_PLANS: dict[tuple[float, float, bool], TerrainPlan] = {}
_PLANS_MAX = 128
_PLAN_LOCK = threading.Lock()


SHIPPED_PLANS = Path(__file__).resolve().parents[2] / "assets" / "terrain_plans.json"
_SHIPPED: dict[str, dict[str, object]] | None = None


def plan_to_json(plan: TerrainPlan) -> dict[str, object]:
    cfg = plan.config
    return {
        "status": plan.status,
        "reason": plan.reason,
        "near_id": plan.near_id,
        "far_id": plan.far_id,
        "resolution_m": plan.resolution_m,
        "far_resolution_m": plan.far_resolution_m,
        "range_m": plan.range_m,
        "config": None
        if cfg is None
        else {
            "near_m": cfg.near_m,
            "far_m": cfg.far_m,
            "near_step_m": cfg.near_step_m,
            "far_step_m": cfg.far_step_m,
            "n_azimuths": cfg.n_azimuths,
        },
        "tiles": {k: [list(t) for t in v] for k, v in plan.tiles.items()},
    }


def plan_key(lat: float, lon: float) -> str:
    return f"{round(lat, 6):.6f},{round(lon, 6):.6f}"


def _shipped(lat: float, lon: float) -> TerrainPlan | None:
    """The plan of a catalogue site precomputed by `scripts/build_terrain_plans.py` (a test keeps it equal to the computation)."""
    global _SHIPPED
    if _SHIPPED is None:
        try:
            _SHIPPED = json.loads(SHIPPED_PLANS.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _SHIPPED = {}
    raw = _SHIPPED.get(plan_key(lat, lon))
    if raw is None:
        return None
    try:
        cfg = raw["config"]
        return TerrainPlan(
            lat,
            lon,
            str(raw["status"]),
            str(raw["reason"]),
            raw["near_id"],  # type: ignore[arg-type]
            raw["far_id"],  # type: ignore[arg-type]
            raw["resolution_m"],  # type: ignore[arg-type]
            raw["far_resolution_m"],  # type: ignore[arg-type]
            raw["range_m"],  # type: ignore[arg-type]
            None if cfg is None else MaskConfig(**cfg),  # type: ignore[arg-type]
            {k: tuple((int(a), int(b)) for a, b in v) for k, v in raw["tiles"].items()},  # type: ignore[union-attr]
        )
    except (KeyError, TypeError, ValueError):
        return None


def plan_site(lat_deg: float, lon_deg_east: float, coarse: bool = False) -> TerrainPlan:
    """The terrain plan of a point (memoised). Pure computation, no I/O besides reading the lock. `coarse` forces the 240 m polar product
    even where the 20 m one exists, so that many candidate cells are compared on the same terrain."""
    lon = ((lon_deg_east + 180.0) % 360.0) - 180.0
    key = (round(lat_deg, 6), round(lon, 6), coarse)
    hit = _PLANS.get(key)
    if hit is not None:
        return hit
    with (
        _PLAN_LOCK
    ):  # one computation at a time: a background warm-up and a request never repeat the same work
        hit = _PLANS.get(key)
        if hit is not None:
            return hit
        plan = (None if coarse else _shipped(key[0], key[1])) or _plan(key[0], key[1], coarse)
        if len(_PLANS) >= _PLANS_MAX:
            _PLANS.pop(next(iter(_PLANS)))
        _PLANS[key] = plan
        return plan


def _plan(lat: float, lon: float, coarse: bool = False) -> TerrainPlan:
    if not (math.isfinite(lat) and math.isfinite(lon) and -90.0 <= lat <= 90.0):
        return TerrainPlan(lat, lon, "unknown", "outside_coverage")
    cands = choose_products(lat, coarse)
    entries: dict[
        tuple[str, str],
        list[tuple[DemSpec, DemSpec, np.ndarray, np.ndarray, np.ndarray, np.ndarray]],
    ] = {}
    smallest_over: TerrainPlan | None = None
    for near_id, far_id in cands:  # best resolution first, then the widest range that fits
        for r_m in RANGES_M:
            ns = load_lock(dataset_id=near_id)
            fs = load_lock(dataset_id=far_id)
            if not (
                _covers_disc(ns, lat, NEAR_M + EDGE_PX * ns.scale_m) and _covers_disc(fs, lat, r_m)
            ):
                continue
            ck = (near_id, far_id)
            if ck not in entries:
                near_d = np.arange(ns.scale_m, NEAR_M + 1e-6, ns.scale_m)
                far_d = np.arange(NEAR_M + fs.scale_m, 200_000.0 + 1e-6, fs.scale_m)
                nc, nd = _tile_entries(ns, lat, lon, near_d)
                fc, fd = _tile_entries(fs, lat, lon, far_d)
                entries[ck] = [(ns, fs, nc, nd, fc, fd)]
            ns, fs, nc, nd, fc, fd = entries[ck][0]
            tiles: dict[str, set[tuple[int, int]]] = {}
            tiles.setdefault(near_id, set()).update(_decode(nc))
            tiles.setdefault(far_id, set()).update(_decode(fc[fd <= r_m]))
            n = sum(len(v) for v in tiles.values())
            cfg = MaskConfig(
                near_m=NEAR_M,
                far_m=r_m,
                near_step_m=ns.scale_m,
                far_step_m=fs.scale_m,
                n_azimuths=N_AZ,
            )
            plan = TerrainPlan(
                lat,
                lon,
                "ok" if n * TILE_BYTES * WIRE_FACTOR <= MAX_SITE_BYTES else "exceeds_site_cap",
                "ok"
                if n * TILE_BYTES * WIRE_FACTOR <= MAX_SITE_BYTES
                else "needs more than the per-site cap",
                near_id,
                far_id,
                ns.scale_m,
                fs.scale_m,
                r_m,
                cfg,
                {k: tuple(sorted(v)) for k, v in tiles.items()},
            )
            if plan.status == "ok":
                return plan
            if smallest_over is None or n < smallest_over.n_tiles:
                smallest_over = plan
    if smallest_over is not None:
        return smallest_over
    return TerrainPlan(lat, lon, "unknown", "outside_coverage")
