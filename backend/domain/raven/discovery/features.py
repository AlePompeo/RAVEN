# SPDX-License-Identifier: Apache-2.0
"""Features of every candidate cell, read from the shipped overlays (nothing is recomputed): the physical proxy the surrogate starts from.

A candidate is a cell where EVERY layer has a value; a cell with no data in any layer is not a candidate (unknown stays unknown, it is not
filled). Polar scope: the south-polar disc of the overlays (2.4 km cells, down from 75 degrees south). Values are decoded from the 8-bit
rasters with the scale each overlay declares (`min`, `max`), so a feature has its physical unit.
"""

from __future__ import annotations

import base64
import math
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Final

import numpy as np
from numpy.typing import NDArray

from backend.domain.raven import overlays as ov
from backend.domain.raven import overlays_global as og

Arr = NDArray[np.float64]
LAYERS: Final = ("elevation", "slope", "sun", "earth", "both", "sun_gap", "earth_gap")
NAMES: Final = ("rho", "sin_lon", "cos_lon", *LAYERS)
# What the surrogate learns from (chosen on 74 real core evaluations, 14-day window: with these the cross-validated error on the useful share is
# 0.07-0.09 against 0.11 with all ten features and 0.23 for the mean; the longitude, height and slope features only added noise at this scale).
SURROGATE_FEATURES: Final = ("rho", "sun", "earth", "both", "sun_gap", "earth_gap")


@dataclass(frozen=True)
class Features:
    lat: Arr  # candidate cells only
    lon: Arr
    x: Arr  # (n, len(NAMES))
    names: tuple[str, ...]
    index: NDArray[np.int64]  # flat index into the size x size raster of each candidate
    size: int
    labels: tuple[
        str, ...
    ] = ()  # a name per candidate when the candidates are named places (the catalogue)


def decode(o: dict[str, Any]) -> Arr:
    """Physical values of an overlay (size x size); NaN where the raster is the no-data value."""
    n = int(o["size"])
    raw = np.frombuffer(base64.b64decode(o["data_b64"]), dtype=np.uint8)
    if raw.size != n * n:
        raise ValueError("malformed raster")
    lo, hi = float(o["min"]), float(o["max"])
    v = lo + (raw.astype(np.float64) - 1.0) / 254.0 * (hi - lo)
    return np.where(raw == o["nodata"], np.nan, v).reshape(n, n)


def polar_features(directory: Path = ov.ASSETS) -> Features:
    """Feature matrix of the polar candidates from the shipped overlays; raises ValueError when a layer is missing."""
    layers: dict[str, Arr] = {}
    size = 0
    for name in LAYERS:
        o = ov.load_precomputed(name, ov.PRECOMPUTED_SIZE, ov.DEFAULT_LIMIT_LAT, directory)
        if o is None:
            raise ValueError(f"overlay '{name}' is not available")
        layers[name] = decode(o)
        size = int(o["size"])
    lat, lon, inside = ov.disc(size, ov.DEFAULT_LIMIT_LAT)
    stack = np.stack([layers[k].ravel() for k in LAYERS], axis=1)
    ok = inside.ravel() & np.isfinite(stack).all(axis=1)
    idx = np.flatnonzero(ok).astype(np.int64)
    la, lo_ = lat.ravel()[idx], lon.ravel()[idx]
    rho = (90.0 + la) / (90.0 + ov.DEFAULT_LIMIT_LAT)
    x = np.column_stack([rho, np.sin(np.radians(lo_)), np.cos(np.radians(lo_)), stack[idx]])
    return Features(la, lo_, x, NAMES, idx, size)


HEIGHTS: Final = ov.ASSETS / "polar-heights.npy"
MAX_SAMPLES: Final = 240


@lru_cache(maxsize=2)
def polar_horizons(path: Path = HEIGHTS) -> tuple[NDArray[np.float32], NDArray[np.bool_]]:
    """Horizons of every polar cell (24 azimuths) marched over the shipped height grid; computed once per process (a few seconds)."""
    return ov.horizon_grid(np.load(path).astype(np.float64), ov.DEFAULT_LIMIT_LAT)


def window_features(
    feat: Features, engine: Any, start: datetime, days: float, heights: Path = HEIGHTS
) -> Features:
    """The Sun and Earth features for the brief's own window (not the mean of 2027): the shares with the Sun, the Earth and both above the
    horizon, and the longest night and blackout, from the same horizons and the ephemerides of that window. A 14-day window is a very different
    thing from the year (a lunar night lasts 14 days); the yearly layers would be a weak predictor of it. Cells without a trustworthy horizon
    keep the yearly value (they are rare and the surrogate has the yearly features for them)."""
    step_h = max(1.0, float(math.ceil(days * 24.0 / MAX_SAMPLES)))
    times = [start + timedelta(hours=step_h * i) for i in range(int(days * 24.0 / step_h) + 1)]
    sun = engine.subsolar_point("moon", times)
    earth = engine.sub_earth_point("moon", times)
    hz, trusted = polar_horizons(heights)
    lat, lon, _inside = ov.disc(feat.size, ov.DEFAULT_LIMIT_LAT)
    m = og.joint_metrics(
        hz,
        trusted,
        lat,
        lon,
        (np.asarray(sun.lat_deg), np.asarray(sun.lon_deg_east)),
        (np.asarray(earth.lat_deg), np.asarray(earth.lon_deg_east)),
        step_h,
    )
    x = feat.x.copy()
    for name, key, scale in (
        ("sun", "sun", 100.0),
        ("earth", "earth", 100.0),
        ("both", "both", 100.0),
        ("sun_gap", "sun_gap_h", 1.0),
        ("earth_gap", "earth_gap_h", 1.0),
    ):
        v = m[key].ravel()[feat.index] * scale
        col = feat.names.index(name)
        x[:, col] = np.where(np.isfinite(v), v, x[:, col])
    return replace(feat, x=x)
