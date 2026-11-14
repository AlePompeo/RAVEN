# SPDX-License-Identifier: Apache-2.0
"""Illustrative two-axis tracking using the C PI controller and host HAL."""

import subprocess
import sys
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

Arr = NDArray[np.float64]
EXECUTABLE = (
    Path(__file__).resolve().parents[2]
    / "plugins"
    / "servo_ctrl_c"
    / "bin"
    / ("gimbal_tracker.exe" if sys.platform == "win32" else "gimbal_tracker")
)


class GimbalUnavailable(RuntimeError):
    """The host gimbal executable is missing or could not complete its simulation."""


def track(az_deg: Arr, el_deg: Arr, interval_s: float) -> tuple[Arr, Arr, NDArray[np.bool_]]:
    """Simulate starting aligned; interpolate the shortest azimuth path between samples."""
    data = f"{len(az_deg)} {interval_s:.9f}\n" + "".join(
        f"{az:.12f} {el:.12f}\n" for az, el in zip(az_deg, el_deg, strict=True)
    )
    try:
        result = subprocess.run(
            [str(EXECUTABLE)],
            input=data,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GimbalUnavailable("simulatore gimbal C non disponibile") from exc
    if result.returncode != 0:
        raise GimbalUnavailable("simulazione gimbal C fallita")
    try:
        rows = np.array(
            [[float(value) for value in line.split()] for line in result.stdout.splitlines()],
            dtype=np.float64,
        )
    except ValueError as exc:
        raise GimbalUnavailable("risposta gimbal C non valida") from exc
    if rows.shape != (len(az_deg), 3) or not np.isfinite(rows).all():
        raise GimbalUnavailable("risposta gimbal C non valida")
    if not np.isin(rows[:, 2], [0.0, 1.0]).all():
        raise GimbalUnavailable("risposta gimbal C non valida")
    return rows[:, 0], rows[:, 1], np.asarray(rows[:, 2], dtype=np.bool_)
