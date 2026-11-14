# SPDX-License-Identifier: Apache-2.0
"""Split-step Fresnel (angular spectrum, FFT) propagation of a plane wave past a ridge.

Page "Onda 3D" of docs/domain/grazinglink-plan.md. 2D scalar paraxial model, the same used by
`research papers, scripts and planning/onda_3d_bozza.py` and `compensation_demo.py` (not modified) and by
`scripts/gen_compensation_table.py`, which imports the primitives below (`make_grid`, `ridge_field`,
`propagate`): the ridge is a perfectly absorbing parabola y = -x^2/(2R) truncated 20 m below the tip
(R = 0: knife edge), the field is advanced with exp(-j pi lambda dz fy^2) in the spatial-frequency domain.

Axes: x = distance from the ridge tip, y = height above the line of sight (the tip is at y = 0), so that the
knife-edge parameter is nu = -y sqrt(2 / (lambda x)) (nu > 0 in shadow, model doc sec. 2.3). Intensity is
relative to the free-field value, estimated far above the ridge (band 0.18 L .. 0.37 L of the window).

Limits of the model, stated: scalar, paraxial, 2D, no ground, no Moon curvature, the FFT window is periodic
(a second, mirrored edge sits at +-L/2, so only |y| << L/2 is meaningful: bounded to 200 m for L >= 1600 m).
Everything is deterministic (no randomness) and the work is capped (FFT size, steps, total FFT work).
"""

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from backend.domain.grazing.diffraction import knife_edge_loss_db

__all__ = [
    "MAX_FFT",
    "MAX_STEPS",
    "RIDGE_DX_M",
    "TRUNCATION_M",
    "WaveParams",
    "make_grid",
    "propagate",
    "ridge_field",
    "simulate_wave",
]

Arr = NDArray[np.float64]
C_LIGHT = 299_792_458.0
MAX_FFT = 2**15
MIN_FFT = 2**12
MAX_STEPS = 400  # propagation rows (excluding the ridge sub-steps)
MAX_WORK = 20_000_000  # sum over FFT pairs of N: worst case about 1 s on the dev machine
RIDGE_DX_M = 2.0
TRUNCATION_M = 20.0
WINDOW_M = 1600.0
BAND = (0.1831, 0.3662)  # fractions of L for the free-field reference (300..600 m at L = 1638.4)
MAX_NX, MAX_NY, MAX_SECTION = 120, 160, 800


def make_grid(n: int, dy: float, offset: float = 0.0) -> tuple[Arr, Arr]:
    """Heights y = (i - n/2 + offset) dy and the matching spatial frequencies (offset 0.5: edge between samples)."""
    y = (np.arange(n) - n // 2 + offset) * dy
    return np.asarray(y, dtype=np.float64), np.asarray(np.fft.fftfreq(n, dy), dtype=np.float64)


def propagate(e: Any, fy: Arr, wavelength_m: float, dz_m: float) -> Any:
    """Free-space Fresnel step of length dz (angular spectrum)."""
    return np.fft.ifft(np.fft.fft(e) * np.exp(-1j * math.pi * wavelength_m * dz_m * fy**2))


def ridge_field(
    y: Arr,
    fy: Arr,
    wavelength_m: float,
    radius_m: float,
    dx: float = RIDGE_DX_M,
    truncation_m: float = TRUNCATION_M,
) -> tuple[Any, float, int]:
    """Plane wave just past the ridge: (field, x_end from the tip, number of FFT steps)."""
    e = np.ones(len(y), complex)
    if radius_m == 0:
        e[y <= 0] = 0
        return e, 0.0, 0
    w = math.sqrt(2 * radius_m * truncation_m)
    steps = 0
    for x in np.arange(-w, w + dx, dx):
        e[y < -x * x / (2 * radius_m)] = 0
        e = propagate(e, fy, wavelength_m, dx)
        steps += 1
    return e, w + dx, steps


@dataclass(frozen=True)
class WaveParams:
    """Inputs of `simulate_wave` (SI units). Validated by `validate`, which raises ValueError."""

    wavelength_m: float = 0.0357
    radius_m: float = 0.0
    distance_m: float = 2000.0
    step_m: float = 20.0
    y_min_m: float = -40.0
    y_max_m: float = 40.0
    dy_m: float = 0.1
    nx: int = 100
    ny: int = 160
    n_section: int = 400

    def validate(self) -> None:
        nums: tuple[float, ...] = (self.wavelength_m, self.radius_m, self.distance_m, self.step_m)
        nums = (*nums, self.y_min_m, self.y_max_m, self.dy_m)
        if not all(math.isfinite(v) for v in nums):
            raise ValueError("non-finite input")
        ok = 0.005 <= self.wavelength_m <= 1.0 and 0 <= self.radius_m <= 400.0
        ok = ok and 100.0 <= self.distance_m <= 5000.0 and 0.5 <= self.step_m <= 1000.0
        ok = ok and -200.0 <= self.y_min_m <= -1.0 and 1.0 <= self.y_max_m <= 200.0
        ok = ok and 0.05 <= self.dy_m <= 0.4
        ok = (
            ok
            and 2 <= self.nx <= MAX_NX
            and 2 <= self.ny <= MAX_NY
            and 2 <= self.n_section <= MAX_SECTION
        )
        if not ok:
            raise ValueError("input out of bounds")


def _fft_size(dy: float) -> int:
    n = 2 ** math.ceil(math.log2(WINDOW_M / dy))
    return int(min(MAX_FFT, max(MIN_FFT, n)))


def _r4(a: Any) -> list[Any]:
    out: list[Any] = np.round(np.asarray(a, dtype=np.float32).astype(np.float64), 4).tolist()
    return out


def simulate_wave(p: WaveParams) -> dict[str, Any]:
    """Intensity grid |E|^2 (x, y), the section at the end distance, the exact knife-edge curve and metadata."""
    p.validate()
    lam, dy = p.wavelength_m, p.dy_m
    n = _fft_size(dy)
    y, fy = make_grid(n, dy, offset=0.5)  # edge exactly at y = 0, between two samples
    length = n * dy
    ridge_steps = (
        0
        if p.radius_m == 0
        else math.ceil(2 * math.sqrt(2 * p.radius_m * TRUNCATION_M) / RIDGE_DX_M) + 2
    )
    x_first_est = 0.0 if p.radius_m == 0 else math.sqrt(2 * p.radius_m * TRUNCATION_M) + RIDGE_DX_M
    if p.distance_m <= x_first_est + p.step_m:
        raise ValueError("distance too short for this ridge")
    n_int = min(MAX_STEPS - 1, math.ceil((p.distance_m - x_first_est) / p.step_m))
    if (ridge_steps + n_int + 1) * n > MAX_WORK:
        raise ValueError("compute budget exceeded")

    e, x_first, rsteps = ridge_field(y, fy, lam, p.radius_m)
    xs = np.linspace(x_first, p.distance_m, n_int + 1)
    keep = sorted({round(v) for v in np.linspace(0, n_int, min(p.nx, n_int + 1))})
    win = (y >= p.y_min_m - 2 * dy) & (y <= p.y_max_m + 2 * dy)
    yw = y[win]
    y_out = np.linspace(p.y_min_m, p.y_max_m, p.ny)
    band = (y > BAND[0] * length) & (y < BAND[1] * length)
    rows: list[Arr] = []
    pos = x_first
    z_max = 0.0
    inten = np.abs(e) ** 2
    for k, x in enumerate(xs):
        if k > 0:
            e = propagate(e, fy, lam, float(x - pos))
            z_max = max(z_max, float(x - pos))
            pos = float(x)
            inten = np.abs(e) ** 2
        if k in keep:
            rows.append(np.interp(y_out, yw, inten[win]))
    i0 = float(inten[band].mean())
    # rows are stored raw and divided by the free-field reference (constant in x) measured at the end
    grid = np.asarray(rows, dtype=np.float32) / np.float32(i0)
    y_sec = np.linspace(p.y_min_m, p.y_max_m, p.n_section)
    sec = np.interp(y_sec, yw, inten[win]) / i0
    nu = -y_sec * math.sqrt(2.0 / (lam * p.distance_m))
    exact = 10.0 ** (-knife_edge_loss_db(nu) / 10.0)
    diff = sec - exact
    z_ok = n * dy * dy / lam
    step_eff = float((xs[-1] - xs[0]) / n_int)
    warnings: list[str] = []
    if max(z_max, RIDGE_DX_M if rsteps else 0.0) > z_ok:
        warnings.append(
            "kernel_aliasing: dz > N dy^2 / lambda, the Fresnel kernel is under-sampled"
        )
    if dy > math.sqrt(lam * step_eff) / 2:
        warnings.append(
            "dy_coarse: dy > sqrt(lambda dx) / 2, fringes near the ridge are under-resolved"
        )
    if lam / (2 * dy) > 0.5:
        warnings.append("paraxial: lambda / (2 dy) > 0.5 rad, outside the paraxial approximation")
    if n_int == MAX_STEPS - 1 and step_eff > p.step_m * 1.0001:
        warnings.append("step_raised: step increased to respect the cap on the number of steps")
    return {
        "x_m": _r2(xs[keep]),
        "y_m": _r2(y_out),
        "intensity": [_r4(r) for r in grid],
        "section": {
            "x_m": round(float(p.distance_m), 3),
            "y_m": _r2(y_sec),
            "nu": _r4(nu),
            "intensity": _r4(sec),
            "knife_edge_exact": _r4(exact),
            "max_abs_diff_vs_knife": round(float(np.max(np.abs(diff))), 4),
            "rms_diff_vs_knife": round(float(np.sqrt(np.mean(diff**2))), 4),
        },
        "meta": {
            "model": "split-step Fresnel (angular spectrum), 2D scalar paraxial, plane wave",
            "wavelength_m": lam,
            "frequency_ghz": round(C_LIGHT / lam / 1e9, 4),
            "radius_m": p.radius_m,
            "ridge": "knife-edge"
            if p.radius_m == 0
            else "rounded (parabola, truncated 20 m below the tip)",
            "fft_size": n,
            "dy_m": dy,
            "window_m": round(length, 3),
            "grid_shape": [len(keep), p.ny],
            "steps": n_int,
            "ridge_steps": rsteps,
            "step_m_requested": p.step_m,
            "step_m_effective": round(step_eff, 4),
            "x_start_m": round(float(x_first), 3),
            "kernel_dz_max_m": round(z_max, 3),
            "kernel_dz_limit_m": round(z_ok, 3),
            "free_field_reference": round(i0, 6),
            "nu_convention": "nu = -y sqrt(2 / (lambda x)); nu > 0 in shadow (model doc 2.3)",
            "warnings": warnings,
        },
    }


def _r2(a: Any) -> list[Any]:
    out: list[Any] = np.round(np.asarray(a, dtype=np.float64), 3).tolist()
    return out
