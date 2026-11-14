# SPDX-License-Identifier: Apache-2.0
"""Whole-Moon map overlays (equirectangular, like the colour map of the 3D Moon): height, regional slope, data coverage, share
of 2027 with the Sun above the horizon and with the Earth above the horizon.

Honest by construction, like the polar overlays: a cell whose height was not read is NODATA (0), never a value. The height is the
LOLA LDEM global 237 m product sampled at one point per 0.5 degree cell (about 15 km at the equator): features smaller than a cell
are aliased and the regional slope is the slope between neighbouring cells, not the slope under a lander. The illumination and Earth
layers march horizons over that grid (rays of 30 cells, about 450 km) and read the Sun and Earth sub-points every 6 hours of 2027:
a regional estimate that cannot see terrain smaller than a cell, so it OVERSTATES the sunlight of rough ground. The polar overlays
(2 km cells) are better near the south pole. Not validated against NASA illumination products.
"""

from __future__ import annotations

import base64
import json
import math
from pathlib import Path
from typing import Any, Final

import numpy as np
from numpy.typing import NDArray

from backend.domain.raven.overlays import MOON_RADIUS_M, NODATA, _encode

WIDTH: Final = 720
HEIGHT: Final = 360
ASSETS: Final = Path(__file__).resolve().parents[2] / "assets" / "overlays"
HORIZON_AZIMUTHS: Final = 24
HORIZON_CELLS: Final = 30
SOURCE: Final = "NASA LRO LOLA LDEM global 237 m, one point per 0.5 degree cell (height over the 1737.4 km reference sphere)"

Arr = NDArray[np.float64]


def grid(width: int = WIDTH, height: int = HEIGHT) -> tuple[Arr, Arr]:
    """Latitude and longitude (east, degrees) of every cell centre; row 0 is the north pole, column 0 is longitude -180."""
    lat = 90.0 - (np.arange(height) + 0.5) / height * 180.0
    lon = -180.0 + (np.arange(width) + 0.5) / width * 360.0
    lon2, lat2 = np.meshgrid(lon, lat)
    return lat2, lon2


def _base(layer: str, width: int, height: int) -> dict[str, Any]:
    return {
        "layer": layer,
        "scope": "global",
        "projection": "equirectangular",
        "size": width,
        "width": width,
        "height": height,
        "nodata": NODATA,
        "encoding": "uint8-linear",
    }


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def elevation_overlay(h: Arr) -> dict[str, Any]:
    valid = np.isfinite(h)
    data, lo, hi = _encode(h, valid)
    return _base("elevation", h.shape[1], h.shape[0]) | {
        "unit": "m",
        "min": lo,
        "max": hi,
        "tag": "D",
        "kind": "sequential",
        "data_b64": _b64(data),
        "source": SOURCE,
        "note": "Stretched between the 1st and 99th percentile of the cells; one point per cell, so small features are aliased.",
    }


def slope_overlay(h: Arr) -> dict[str, Any]:
    """Regional slope between neighbouring cells (degrees), on the sphere (a cell is narrower towards the poles)."""
    height, width = h.shape
    lat, _lon = grid(width, height)
    dlat_m = math.radians(180.0 / height) * MOON_RADIUS_M
    dlon_m = np.maximum(math.radians(360.0 / width) * MOON_RADIUS_M * np.cos(np.radians(lat)), 1.0)
    valid = np.isfinite(h)
    filled = np.where(valid, h, 0.0)
    gy = np.zeros_like(filled)
    gx = np.zeros_like(filled)
    gy[1:-1] = (filled[2:] - filled[:-2]) / (2.0 * dlat_m)
    gx = (np.roll(filled, -1, axis=1) - np.roll(filled, 1, axis=1)) / (2.0 * dlon_m)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    ok = valid.copy()
    for shift, axis in ((1, 0), (-1, 0), (1, 1), (-1, 1)):
        ok &= np.roll(valid, shift, axis=axis)
    ok[0] = ok[-1] = False  # the polar rows have no north or south neighbour
    ok &= (
        np.abs(lat) < 88.0
    )  # a cell of the last rows is a few km wide: its east-west gradient means nothing
    data, lo, hi = _encode(slope, ok)
    return _base("slope", width, height) | {
        "unit": "deg",
        "min": lo,
        "max": hi,
        "tag": "D",
        "kind": "sequential",
        "data_b64": _b64(data),
        "cell_m": round(dlat_m, 1),
        "source": f"derived from {SOURCE}",
        "note": "Regional slope at the scale of one 0.5 degree cell (about 15 km), not the slope under a lander; steep local terrain is smoothed out.",
    }


def coverage_overlay(width: int = WIDTH, height: int = HEIGHT) -> dict[str, Any]:
    """Which LOLA product the model reads at each cell: 20 m (85S and south), 240 m (75S to 85S) or the global 237 m."""
    lat, _lon = grid(width, height)
    classes = np.where(lat <= -85.0, 3, np.where(lat <= -75.0, 2, 1)).astype(np.uint8)
    return _base("coverage", width, height) | {
        "unit": "class",
        "min": 1.0,
        "max": 3.0,
        "tag": "D",
        "kind": "categorical",
        "classes": [
            {
                "value": 1,
                "label": "LOLA global 237 m: terrain after the download consent (installed by the installer)",
            },
            {"value": 2, "label": "LOLA 240 m (LDEM 75S): height and horizon, no 20 m detail"},
            {"value": 3, "label": "LOLA 20 m (LDEM 85S): full terrain model"},
        ],
        "data_b64": _b64(classes.tobytes()),
        "source": "footprint of the LOLA LDEM products used by the model",
        "note": "The map shows the best product that covers each latitude, not what is cached on this computer.",
    }


# -- horizons on the sphere -----------------------------------------------------------------------------------------
def _sample(h: Arr, lat_deg: Arr, lon_deg: Arr) -> Arr:
    """Bilinear sample of the global grid at (lat, lon); longitude wraps, a cell with no height gives NaN."""
    height, width = h.shape
    y = (90.0 - lat_deg) / 180.0 * height - 0.5
    x = (lon_deg + 180.0) / 360.0 * width - 0.5
    y0 = np.floor(y).astype(int)
    fy = y - y0
    y0c = np.clip(y0, 0, height - 1)
    y1c = np.clip(y0 + 1, 0, height - 1)
    x0 = np.floor(x).astype(int)
    fx = x - x0
    x0m = x0 % width
    x1m = (x0 + 1) % width
    return np.asarray(
        h[y0c, x0m] * (1 - fx) * (1 - fy)
        + h[y0c, x1m] * fx * (1 - fy)
        + h[y1c, x0m] * (1 - fx) * fy
        + h[y1c, x1m] * fx * fy
    )


def horizon_grid(
    h: Arr, n_az: int = HORIZON_AZIMUTHS, max_cells: int = HORIZON_CELLS
) -> tuple[NDArray[np.float32], NDArray[np.bool_]]:
    """Horizon elevation (degrees) of every cell for `n_az` azimuths (clockwise from local north), by marching `max_cells` steps of
    one cell width along great circles, with the curvature drop. A cell with no height, or a ray that meets one, has no horizon."""
    height, width = h.shape
    lat, lon = grid(width, height)
    la0, lo0 = np.radians(lat), np.radians(lon)
    step_m = math.radians(360.0 / width) * MOON_RADIUS_M
    h0 = np.where(np.isfinite(h), h, 0.0)
    trusted = np.isfinite(h) & (np.abs(lat) < 89.0)
    out = np.full((n_az, height, width), -90.0, dtype=np.float32)
    for ia in range(n_az):
        a = 2.0 * math.pi * ia / n_az
        best = np.full(h.shape, -np.inf)
        bad = np.zeros(h.shape, dtype=bool)
        for k in range(1, max_cells + 1):
            d = k * step_m
            delta = d / MOON_RADIUS_M
            lat2 = np.arcsin(
                np.clip(
                    np.sin(la0) * math.cos(delta) + np.cos(la0) * math.sin(delta) * math.cos(a),
                    -1.0,
                    1.0,
                )
            )
            lon2 = lo0 + np.arctan2(
                math.sin(a) * math.sin(delta) * np.cos(la0),
                math.cos(delta) - np.sin(la0) * np.sin(lat2),
            )
            z = _sample(h, np.degrees(lat2), np.degrees(lon2))
            bad |= ~np.isfinite(z)
            ang = np.degrees(np.arctan2(z - h0 - d * d / (2.0 * MOON_RADIUS_M), d))
            best = np.fmax(best, ang)
        out[ia] = np.where(np.isfinite(best) & ~bad, best, -90.0)
        trusted &= ~bad
    return out, trusted


def _alt_az(lat_deg: Arr, lon_deg: Arr, sub_lat_deg: float, sub_lon_deg: float) -> tuple[Arr, Arr]:
    """Elevation and azimuth (from north, clockwise) of a body at infinity whose sub-point is (sub_lat, sub_lon)."""
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
    sub_lat_deg: Arr,
    sub_lon_deg: Arr,
) -> Arr:
    """Share of the instants at which the body (its sub-points) is above the horizon of each trusted cell; NaN elsewhere. The body is
    a point at infinity: the Earth's parallax of about 1 degree and the Sun's disc are neglected."""
    n_az, height, width = horizons.shape
    lat, lon = grid(width, height)
    idx = np.flatnonzero(trusted.ravel())
    la, lo = lat.ravel()[idx], lon.ravel()[idx]
    hz = horizons.reshape(n_az, -1)[:, idx]
    cols = np.arange(idx.size)
    seen = np.zeros(idx.size)
    for t in range(len(sub_lat_deg)):
        el, az = _alt_az(la, lo, float(sub_lat_deg[t]), float(sub_lon_deg[t]))
        b = np.rint(az / 360.0 * n_az).astype(int) % n_az
        seen += el > hz[b, cols]
    out = np.full(height * width, np.nan)
    out[idx] = seen / max(1, len(sub_lat_deg))
    return out.reshape(height, width)


def fraction_overlay(layer: str, fraction: Arr, what: str) -> dict[str, Any]:
    height, width = fraction.shape
    valid = np.isfinite(fraction)
    data, lo, hi = _encode(np.nan_to_num(fraction) * 100.0, valid, fixed=(0.0, 100.0))
    return _base(layer, width, height) | {
        "unit": "%",
        "min": lo,
        "max": hi,
        "tag": "D",
        "kind": "sequential",
        "data_b64": _b64(data),
        "source": "derived: horizons marched over the global LOLA grid (0.5 degree cells, 30 cells, 24 azimuths); "
        f"{what} direction from the JPL DE440 ephemerides every 6 h of 2027 (libration included)",
        "note": f"Share of 2027 with the {what} above the regional horizon. The {what} is a point at infinity (Earth parallax of about 1 "
        "degree and the Sun's disc are not resolved) and terrain smaller than a 15 km cell is invisible, so rough ground is overstated. "
        "Not validated against NASA illumination products. Cells with an unreadable height are no data.",
    }


def load_precomputed(layer: str, directory: Path = ASSETS) -> dict[str, Any] | None:
    """The shipped global raster of a layer (scripts/build_overlays_global.py), or None."""
    try:
        out: dict[str, Any] = json.loads(
            (directory / f"global-{layer}.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return None
    ok = out.get("layer") == layer and out.get("projection") == "equirectangular"
    return out if ok else None


# -- joint availability (both bodies at once) and the longest gaps --------------------------------------------------
def joint_metrics(
    horizons: NDArray[np.float32],
    trusted: NDArray[np.bool_],
    lat: Arr,
    lon: Arr,
    sun: tuple[Arr, Arr],
    earth: tuple[Arr, Arr],
    step_h: float,
) -> dict[str, Arr]:
    """Over the instants given by the (lat, lon) sub-points of the Sun and the Earth: the share of time with BOTH above the horizon, and
    the longest run without the Sun and without the Earth (hours). `lat` and `lon` are the cell centres (any shape equal to the grid of
    `horizons`). NaN where the horizon is not trustworthy. The runs are limited by the span of the series (a gap that crosses its end is
    cut) and have the resolution `step_h`."""
    n_az = horizons.shape[0]
    shape = lat.shape
    idx = np.flatnonzero(trusted.ravel())
    la, lo = lat.ravel()[idx], lon.ravel()[idx]
    hz = horizons.reshape(n_az, -1)[:, idx]
    cols = np.arange(idx.size)
    both = np.zeros(idx.size)
    sun_sum = np.zeros(idx.size)
    earth_sum = np.zeros(idx.size)
    run_s = np.zeros(idx.size)
    run_e = np.zeros(idx.size)
    gap_s = np.zeros(idx.size)
    gap_e = np.zeros(idx.size)
    n = len(sun[0])
    for t in range(n):
        el_s, az_s = _alt_az(la, lo, float(sun[0][t]), float(sun[1][t]))
        el_e, az_e = _alt_az(la, lo, float(earth[0][t]), float(earth[1][t]))
        vs = el_s > hz[np.rint(az_s / 360.0 * n_az).astype(int) % n_az, cols]
        ve = el_e > hz[np.rint(az_e / 360.0 * n_az).astype(int) % n_az, cols]
        both += vs & ve
        sun_sum += vs
        earth_sum += ve
        run_s = np.where(vs, 0.0, run_s + 1.0)
        run_e = np.where(ve, 0.0, run_e + 1.0)
        gap_s = np.fmax(gap_s, run_s)
        gap_e = np.fmax(gap_e, run_e)
    out: dict[str, Arr] = {}
    for name, v in (
        ("both", both / max(1, n)),
        ("sun", sun_sum / max(1, n)),
        ("earth", earth_sum / max(1, n)),
        ("sun_gap_h", gap_s * step_h),
        ("earth_gap_h", gap_e * step_h),
    ):
        full = np.full(shape[0] * shape[1], np.nan)
        full[idx] = v
        out[name] = full.reshape(shape)
    return out


def both_overlay(fraction: Arr, scope_note: str, source_note: str) -> dict[str, Any]:
    o = fraction_overlay("both", fraction, "Sun and Earth together")
    o["source"] = source_note
    o["note"] = (
        "Share of 2027 with the Sun AND the Earth above the regional horizon at the same time: the proxy of the useful hours (the Sun and "
        "Earth layers alone are marginals). " + scope_note
    )
    return o


def gap_overlay(
    layer: str, hours: Arr, body: str, source_note: str, scope_note: str
) -> dict[str, Any]:
    """The longest stretch of 2027 without the body above the horizon (hours), on a 1st to 99th percentile scale."""
    height, width = hours.shape
    valid = np.isfinite(hours)
    data, lo, hi = _encode(np.nan_to_num(hours), valid)
    return _base(layer, width, height) | {
        "unit": "h",
        "min": lo,
        "max": hi,
        "tag": "D",
        "kind": "sequential",
        "data_b64": _b64(data),
        "source": source_note,
        "note": f"Longest stretch of 2027 without the {body} above the regional horizon (a night for the Sun, a blackout for the Earth), in "
        "hours at the resolution of the sampling (6 h); a stretch that crosses the end of the year is cut. "
        + scope_note,
    }
