# SPDX-License-Identifier: Apache-2.0
"""Convergence study of the split-step rounded-ridge residual against ITU-R P.526-9 T(m, n).

Same physics as scripts/gen_compensation_table.py (2D scalar paraxial split-step, plane wave from the
Earth side, perfectly absorbing parabolic ridge, receiver d1 = 2000 m behind the tip, lambda = 0.0357 m),
with every numerical knob exposed: transverse step dy, march step dx across the ridge, window N dy,
truncation depth, a cos^2 absorbing layer and the step of the free propagation after the ridge.
Prints residual R = L_splitstep - J_exact (dB) per configuration and the ITU T(m, n) for the same cells.
Results and their reading: docs/domain/validation.md, "Validazione radio" (2026-11-04).

    .venv/bin/python -m scripts.study_splitstep_convergence        (about 2 minutes)
"""

import math
from typing import Any

import numpy as np

from backend.domain.grazing.compensation import p526_rounded_term_db
from backend.domain.grazing.diffraction import knife_edge_loss_db

LAM, D = 0.0357, 2000.0
NUS = np.array([0.0, 1.0, 3.0, 8.0])
RADII = (20.0, 100.0, 400.0)
# (dy, dx, absorber): the table setting first, then refinements with an absorbing layer
CONFIGS = (
    (0.1, 2.0, False),
    (0.1, 2.0, True),
    (0.05, 0.5, True),
    (0.025, 0.25, True),
    (0.0125, 0.125, True),
    (0.0125, 0.0625, True),
)


def splitstep_loss_db(
    radius_m: float,
    nus: Any,
    dy: float,
    dx: float,
    absorb: bool,
    window_m: float = 1638.4,
    truncation_m: float = 20.0,
    z_step_m: float = 25.0,
) -> Any:
    n = 1 << (round(window_m / dy) - 1).bit_length()
    y = (np.arange(n) - n // 2) * dy
    fy = np.fft.fftfreq(n, dy)
    half = n * dy / 2
    if absorb:  # cos^2 taper on the outer 15 % of each side, applied after every step
        w = np.clip((np.abs(y) / half - 0.85) / 0.15, 0.0, 1.0)
        mask = np.cos(0.5 * math.pi * w) ** 2
    else:
        mask = np.ones(n)

    def prop(e: Any, dz: float) -> Any:
        return np.fft.ifft(np.fft.fft(e) * np.exp(-1j * math.pi * LAM * dz * fy**2)) * mask

    e = np.ones(n, complex) * mask
    x_end = 0.0
    if radius_m == 0:
        e[y <= 0] = 0
    else:
        half_w = math.sqrt(2 * radius_m * truncation_m)
        for x in np.arange(-half_w, half_w + dx, dx):
            e[y < -x * x / (2 * radius_m)] = 0
            e = prop(e, dx)
        x_end = half_w + dx
    rest = D - x_end
    k = max(1, math.ceil(rest / z_step_m)) if absorb else 1
    for _ in range(k):
        e = prop(e, rest / k)
    inten = np.abs(e) ** 2
    ref = inten[(y > 0.1831 * 2 * half) & (y < 0.3662 * 2 * half)].mean()
    rx = -np.asarray(nus) * math.sqrt(LAM * D / 2)
    return np.interp(rx, y, -10 * np.log10(inten / ref))


def main() -> None:
    print("nu =", NUS.tolist())
    for r in RADII:
        itu = p526_rounded_term_db(NUS, r, D, 1e12, LAM)
        print(f"R = {r:.0f} m  ITU-R P.526-9 T(m,n): {np.round(itu, 3).tolist()}")
        for dy, dx, ab in CONFIGS:
            res = splitstep_loss_db(r, NUS, dy, dx, ab) - knife_edge_loss_db(NUS)
            print(f"   dy={dy:<7} dx={dx:<7} absorber={ab!s:5}  R_ss = {np.round(res, 3).tolist()}")
    for dy, dx, ab in CONFIGS[:1] + CONFIGS[-2:-1]:
        k = splitstep_loss_db(0.0, NUS, dy, dx, ab) - knife_edge_loss_db(NUS)
        print(f"knife edge check dy={dy}: L_ss - J_exact = {np.round(k, 3).tolist()}")


if __name__ == "__main__":
    main()
