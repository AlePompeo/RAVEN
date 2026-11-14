# SPDX-License-Identifier: Apache-2.0
"""Pre-1.4 terrain arithmetic for historical golden tests only, never production validation."""

import math

import numpy as np
from numpy.typing import NDArray

Arr = NDArray[np.float64]


def destination(lat_deg: float, lon_deg: float, az: Arr, delta: Arr) -> tuple[Arr, Arr]:
    """Archived polar-unstable ray construction; intentionally retains the old behaviour."""
    p1, l1 = math.radians(lat_deg), math.radians(lon_deg)
    sp = math.sin(p1) * np.cos(delta) + math.cos(p1) * np.sin(delta) * np.cos(az)
    p2 = np.arcsin(np.clip(sp, -1.0, 1.0))
    l2 = l1 + np.arctan2(
        np.sin(az) * np.sin(delta) * math.cos(p1), np.cos(delta) - math.sin(p1) * sp
    )
    return np.degrees(p2), np.mod(np.degrees(l2) + 180.0, 360.0) - 180.0


def ridge_radius(d: Arr, z: Arr, k: int, spacing: float) -> tuple[float, bool]:
    """Archived unconstrained fit: does not qualify a crest or its physical curvature."""
    lo = hi = k
    while lo > 0 and z[k] - z[lo - 1] <= 20.0:
        lo -= 1
    while hi < z.size - 1 and z[k] - z[hi + 1] <= 20.0:
        hi += 1
    if hi - lo + 1 < 5:
        return math.nan, False
    x = d[lo : hi + 1] - d[k]
    c2 = float(np.polyfit(x, z[lo : hi + 1] - z[k], 2)[0])
    if c2 >= 0.0:
        return math.nan, False
    rc = -1.0 / (2.0 * c2)
    return rc, rc >= 2.0 * spacing
