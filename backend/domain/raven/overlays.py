# SPDX-License-Identifier: Apache-2.0
"""Map overlays of the south-polar disc (remote-sensing style rasters): terrain height, regional slope, data coverage.

The disc is the azimuthal equidistant map of the frontend (pole at the centre, longitude clockwise from the top, radius 1 at
`limit_lat_deg`). Honest by construction: a cell outside the disc, or whose height cannot be read, is NODATA (0), never a value.
Height is the LOLA LDEM 75S 240 m product (tag D, measured and gridded); the slope is DERIVED from it at the scale of one map cell
(about 2 km), so it is a regional slope, not the slope under a lander. Coverage is the footprint of the two LOLA products used by
the model. No value is interpolated between sites.
"""

from __future__ import annotations

import base64
import json
import math
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

import numpy as np
from numpy.typing import NDArray

MOON_RADIUS_M: Final = 1_737_400.0
NODATA: Final = 0
LAYERS: Final = ("elevation", "slope", "coverage", "sun", "earth", "both", "sun_gap", "earth_gap")
DEFAULT_LIMIT_LAT: Final = -75.0
MIN_SIZE, MAX_SIZE = 64, 512
PRECOMPUTED_SIZE: Final = 384  # the size of the shipped rasters (scripts/build_overlays.py)
ASSETS: Final = Path(__file__).resolve().parents[2] / "assets" / "overlays"

Arr = NDArray[np.float64]
Sampler = Callable[[Arr, Arr], Arr]


def disc(size: int, limit_lat_deg: float) -> tuple[Arr, Arr, NDArray[np.bool_]]:
    """Latitude and longitude (east, degrees) of every cell centre and the mask of the cells inside the disc."""
    c = (np.arange(size) + 0.5) / size * 2.0 - 1.0
    x, y = np.meshgrid(c, c)  # row index grows downwards, like the canvas
    rho = np.hypot(x, y)
    inside = rho <= 1.0
    lat = -90.0 + rho * (90.0 + limit_lat_deg)
    lon = np.degrees(np.arctan2(x, -y))
    return lat, lon, inside


def _encode(
    values: Arr, valid: NDArray[np.bool_], fixed: tuple[float, float] | None = None
) -> tuple[bytes, float, float]:
    """Linear 8-bit stretch between the 1st and 99th percentile of the valid cells (or a fixed range), 1..255; invalid cells are 0."""
    out = np.zeros(values.shape, dtype=np.uint8)
    if not valid.any():
        return out.tobytes(), 0.0, 0.0
    lo, hi = (
        fixed if fixed is not None else (float(v) for v in np.percentile(values[valid], [1, 99]))
    )
    if hi <= lo:
        hi = lo + 1.0
    scaled = 1.0 + np.clip((values - lo) / (hi - lo), 0.0, 1.0) * 254.0
    out[valid] = np.rint(scaled[valid]).astype(np.uint8)
    return out.tobytes(), lo, hi


def compute_overlay(
    layer: str,
    *,
    size: int = 256,
    limit_lat_deg: float = DEFAULT_LIMIT_LAT,
    sampler: Sampler | None = None,
    near_limit_lat_deg: float = -85.0,
) -> dict[str, Any]:
    """One overlay as a JSON-ready dict: an 8-bit raster (base64, row-major, 0 = no data) plus its scale, unit, source and tag."""
    if layer not in LAYERS or layer in (
        "sun",
        "earth",
        "both",
        "sun_gap",
        "earth_gap",
    ):  # the illumination layers come from fraction_overlay
        raise ValueError("layer")
    if not (MIN_SIZE <= size <= MAX_SIZE) or not (-89.0 <= limit_lat_deg <= -60.0):
        raise ValueError("size or limit")
    lat, lon, inside = disc(size, limit_lat_deg)
    base: dict[str, Any] = {
        "layer": layer,
        "size": size,
        "limit_lat_deg": limit_lat_deg,
        "nodata": NODATA,
        "encoding": "uint8-linear",
    }
    if layer == "coverage":
        classes = np.where(inside, np.where(lat <= near_limit_lat_deg, 2, 1), 0).astype(np.uint8)
        return base | {
            "unit": "class",
            "min": 1.0,
            "max": 2.0,
            "tag": "D",
            "kind": "categorical",
            "classes": [
                {"value": 1, "label": "LOLA 240 m (LDEM 75S): height and horizon, no 20 m detail"},
                {"value": 2, "label": "LOLA 20 m (LDEM 85S): full terrain model"},
            ],
            "data_b64": base64.b64encode(classes.tobytes()).decode("ascii"),
            "source": "footprint of the LOLA LDEM 20 m (85S) and 240 m (75S) products used by the model",
            "note": "Outside the disc and north of the limit: no data. Sites outside the 20 m product use the global 237 m product after the download consent.",
        }
    if sampler is None:
        raise ValueError("sampler")
    h = np.full(lat.shape, np.nan)
    h[inside] = sampler(lat[inside], lon[inside])
    valid = inside & np.isfinite(h)
    if layer == "elevation":
        data, lo, hi = _encode(h, valid)
        return base | {
            "unit": "m",
            "min": lo,
            "max": hi,
            "tag": "D",
            "kind": "sequential",
            "data_b64": base64.b64encode(data).decode("ascii"),
            "source": "NASA LRO LOLA LDEM 75S 240 m (height over the 1737.4 km reference sphere)",
            "note": "Stretched between the 1st and 99th percentile of the visible cells; cells that cannot be read are no data.",
        }
    cell_m = 2.0 * math.radians(90.0 + limit_lat_deg) * MOON_RADIUS_M / size
    filled = np.where(valid, h, np.nan)
    gy, gx = np.gradient(np.nan_to_num(filled, nan=0.0), cell_m)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    # the gradient is only meaningful where the cell and its four neighbours are valid
    ok = valid.copy()
    for shift, axis in ((1, 0), (-1, 0), (1, 1), (-1, 1)):
        ok &= np.roll(valid, shift, axis=axis)
    data, lo, hi = _encode(slope, ok)
    return base | {
        "unit": "deg",
        "min": lo,
        "max": hi,
        "tag": "D",
        "kind": "sequential",
        "data_b64": base64.b64encode(data).decode("ascii"),
        "cell_m": round(cell_m, 1),
        "source": "derived from LOLA LDEM 75S 240 m at the scale of one map cell",
        "note": f"Regional slope at about {cell_m / 1000:.1f} km per cell, not the slope under a lander; steep local terrain is smoothed out.",
    }


def load_precomputed(
    layer: str, size: int, limit_lat_deg: float, directory: Path = ASSETS
) -> dict[str, Any] | None:
    """The shipped raster of a layer when it matches the request, else None (the caller computes or answers unavailable)."""
    if layer == "coverage" or size != PRECOMPUTED_SIZE or limit_lat_deg != DEFAULT_LIMIT_LAT:
        return None
    path = directory / f"{layer}.json"
    try:
        out: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return out if out.get("layer") == layer and out.get("size") == size else None


# -- regional illumination and Earth visibility from the height grid ------------------------------------------------
HORIZON_AZIMUTHS: Final = 24
HORIZON_CELLS: Final = 30  # rays reach 30 cells (about 72 km at 384 cells over a 75 S disc)


def _bilinear(h: Arr, x: Arr, y: Arr) -> Arr:
    """Bilinear sample of the grid at float (column, row); outside the grid or on an unknown cell the answer is NaN."""
    n = h.shape[0]
    x0 = np.floor(x).astype(int)
    y0 = np.floor(y).astype(int)
    ok = (x0 >= 0) & (y0 >= 0) & (x0 < n - 1) & (y0 < n - 1)
    x0c = np.clip(x0, 0, n - 2)
    y0c = np.clip(y0, 0, n - 2)
    fx, fy = x - x0c, y - y0c
    v = (
        h[y0c, x0c] * (1 - fx) * (1 - fy)
        + h[y0c, x0c + 1] * fx * (1 - fy)
        + h[y0c + 1, x0c] * (1 - fx) * fy
        + h[y0c + 1, x0c + 1] * fx * fy
    )
    return np.where(ok, v, np.nan)


def horizon_grid(
    h: Arr, limit_lat_deg: float, n_az: int = HORIZON_AZIMUTHS, max_cells: int = HORIZON_CELLS
) -> tuple[NDArray[np.float32], NDArray[np.bool_]]:
    """Horizon elevation (degrees) of every cell for `n_az` azimuths (clockwise from local north), by marching `max_cells` cells over
    the height grid with the curvature drop. Returns the horizons and the mask of the cells where it is trustworthy: the rays of the
    outer ring leave the disc and the cells with an unreadable height have no horizon (no data, never a guess)."""
    size = h.shape[0]
    _lat, lon, inside = disc(size, limit_lat_deg)
    cell_m = 2.0 * math.radians(90.0 + limit_lat_deg) * MOON_RADIUS_M / size
    c = np.arange(size) + 0.5
    cx, cy = np.meshgrid(c, c)
    rho = np.hypot((cx / size) * 2 - 1, (cy / size) * 2 - 1)
    trusted = inside & np.isfinite(h) & (rho <= 1.0 - max_cells / (size / 2.0))
    lam = np.radians(lon)
    out = np.full((n_az, size, size), -90.0, dtype=np.float32)
    h0 = np.where(np.isfinite(h), h, 0.0)
    for ia in range(n_az):
        a = 2.0 * math.pi * ia / n_az
        # local north is outward along the map radius, east is clockwise: see SitePolarMap and moonMap.ts
        dx = math.cos(a) * np.sin(lam) + math.sin(a) * np.cos(lam)
        dy = -math.cos(a) * np.cos(lam) + math.sin(a) * np.sin(lam)
        best = np.full((size, size), -np.inf)
        for k in range(1, max_cells + 1):
            z = _bilinear(h, cx - 0.5 + k * dx, cy - 0.5 + k * dy)
            d = k * cell_m
            ang = np.degrees(np.arctan2(z - h0 - d * d / (2.0 * MOON_RADIUS_M), d))
            best = np.fmax(best, ang)
        out[ia] = np.where(np.isfinite(best), best, -90.0)
    return out, trusted


def _alt_az_of(
    lat_deg: Arr, lon_deg: Arr, sub_lat_deg: float, sub_lon_deg: float
) -> tuple[Arr, Arr]:
    """Elevation and azimuth (from north, clockwise) of a body at infinity whose sub-point is (sub_lat, sub_lon), seen from each cell."""
    p, s = np.radians(lat_deg), math.radians(sub_lat_deg)
    dl = math.radians(sub_lon_deg) - np.radians(lon_deg)
    sin_el = np.sin(p) * math.sin(s) + np.cos(p) * math.cos(s) * np.cos(dl)
    az = (
        np.degrees(
            np.arctan2(
                np.sin(dl) * math.cos(s),
                np.cos(p) * math.sin(s) - np.sin(p) * math.cos(s) * np.cos(dl),
            )
        )
        % 360.0
    )
    return np.degrees(np.arcsin(np.clip(sin_el, -1.0, 1.0))), az


def visibility_fraction(
    horizons: NDArray[np.float32],
    trusted: NDArray[np.bool_],
    limit_lat_deg: float,
    sub_lat_deg: Arr,
    sub_lon_deg: Arr,
) -> Arr:
    """Share of the instants at which the body (given by its sub-points) is above the horizon of each trusted cell; NaN elsewhere.
    The body is a point at infinity (the Earth's parallax of about 1 degree and the Sun's disc are neglected: a regional estimate)."""
    n_az, size, _ = horizons.shape
    lat, lon, _inside = disc(size, limit_lat_deg)
    idx = np.flatnonzero(trusted.ravel())
    la, lo = lat.ravel()[idx], lon.ravel()[idx]
    hz = horizons.reshape(n_az, -1)[:, idx]
    cols = np.arange(idx.size)
    seen = np.zeros(idx.size)
    for t in range(len(sub_lat_deg)):
        el, az = _alt_az_of(la, lo, float(sub_lat_deg[t]), float(sub_lon_deg[t]))
        b = np.rint(az / 360.0 * n_az).astype(int) % n_az
        seen += el > hz[b, cols]
    out = np.full(size * size, np.nan)
    out[idx] = seen / max(1, len(sub_lat_deg))
    return out.reshape(size, size)


def fraction_overlay(
    layer: str, fraction: Arr, size: int, limit_lat_deg: float, source: str, note: str
) -> dict[str, Any]:
    """A fraction of time (0..1, NaN = no data) as a percent overlay on a fixed 0..100 scale."""
    valid = np.isfinite(fraction)
    data, lo, hi = _encode(np.nan_to_num(fraction) * 100.0, valid, fixed=(0.0, 100.0))
    return {
        "layer": layer,
        "size": size,
        "limit_lat_deg": limit_lat_deg,
        "nodata": NODATA,
        "encoding": "uint8-linear",
        "unit": "%",
        "min": lo,
        "max": hi,
        "tag": "D",
        "kind": "sequential",
        "data_b64": base64.b64encode(data).decode("ascii"),
        "source": source,
        "note": note,
    }
