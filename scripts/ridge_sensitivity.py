# SPDX-License-Identifier: Apache-2.0
"""Numerical sensitivity of one rounded-ridge case, not an experimental validation.

Run from the repository root: .venv/bin/python scripts/ridge_sensitivity.py
The baseline follows gen_compensation_table.py: scalar plane wave, 2 km distance,
3.57 cm wavelength, 400 m radius and a parabola truncated 20 m below the tip.
Each other row changes one numerical or profile parameter from that baseline.
"""

import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.domain.grazing.wave import make_grid, propagate, ridge_field

WAVELENGTH_M = 0.0357
DISTANCE_M = 2000.0
RADIUS_M = 400.0
CASES = (
    (0.1, 2.0, 20.0, 16384),
    (0.1, 1.0, 20.0, 16384),
    (0.1, 0.5, 20.0, 16384),
    (0.05, 2.0, 20.0, 32768),
    (0.025, 2.0, 20.0, 65536),
    (0.1, 2.0, 10.0, 16384),
    (0.1, 2.0, 40.0, 16384),
    (0.1, 2.0, 20.0, 32768),
)


def loss_at_nus(dy: float, dx: float, truncation: float, n: int) -> tuple[float, float]:
    y, fy = make_grid(n, dy)
    field, x_end, _ = ridge_field(y, fy, WAVELENGTH_M, RADIUS_M, dx, truncation)
    field = propagate(field, fy, WAVELENGTH_M, DISTANCE_M - x_end)
    intensity = np.abs(field) ** 2
    reference = intensity[(y > 300) & (y < 600)].mean()
    targets = -np.array([0.0, 3.0]) * math.sqrt(WAVELENGTH_M * DISTANCE_M / 2)
    # Match the table generator: interpolate loss in dB, not intensity.
    with np.errstate(divide="ignore"):
        loss = -10 * np.log10(intensity / reference)
    result = np.interp(targets, y, loss)
    return float(result[0]), float(result[1])


def main() -> None:
    baseline = loss_at_nus(*CASES[0])
    print("dy_m,dx_m,truncation_m,n,loss_nu0_db,loss_nu3_db,delta_nu3_db")
    for case in CASES:
        loss0, loss3 = baseline if case == CASES[0] else loss_at_nus(*case)
        print(
            f"{case[0]:g},{case[1]:g},{case[2]:g},{case[3]},"
            f"{loss0:.6f},{loss3:.6f},{loss3 - baseline[1]:+.6f}"
        )


if __name__ == "__main__":
    main()
