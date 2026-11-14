# SPDX-License-Identifier: Apache-2.0
"""Generator of the multi-fidelity rounded-ridge correction table R(nu, radius).

Reproduces part A of `research papers, scripts and planning/compensation_demo.py` (not modified):
a split-step Fresnel full-wave simulator (2D, scalar, paraxial, perfectly absorbing parabolic ridge
truncated 20 m below the tip, plane wave) is compared with the exact knife edge; the residual
    R(nu, radius) = L_splitstep(nu, radius) - J_exact(nu)         [dB]
is stored on the grid nu in [-1.5, 3.0] step 0.05 x radius in {0, 5, 10, 20, 50, 100, 200, 400} m,
together with a Gaussian-process smooth fit (the table used at run time), the oscillation envelope
|simulated - GP| (reported as UNCERTAINTY, not as correction) and the > 4 MAD anomaly flags.

Needs the optional extra `[ml]` (scikit-learn) ONLY for the GP fit; `simulate_residuals` needs just
numpy/scipy. Takes about a minute. Deterministic: simulator has no randomness, the GP validation
subset uses numpy `default_rng(3)` (the seed of the script).

    .venv/bin/python scripts/gen_compensation_table.py [--out PATH] [--check]

`--check` regenerates and compares with the stored file (exit 1 on mismatch beyond tolerance).
"""

import argparse
import hashlib
import json
import math
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from scipy.special import fresnel

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.domain.grazing.wave import make_grid, propagate, ridge_field

HERE = Path(__file__).resolve()
DEFAULT_OUT = (
    HERE.parents[1] / "backend" / "domain" / "grazing" / "data" / "compensation_table.json"
)
LAM, DIST, N, DY = 0.0357, 2000.0, 2**14, 0.1
DX = 2.0
TRUNCATION_M = 20.0
NUS = np.round(np.arange(-1.5, 3.01, 0.05), 2)
RADII = (0, 5, 10, 20, 50, 100, 200, 400)
SEED = 3
MAD_K = 4.0
SMOOTH_HALF_WINDOW = 3  # cells (0.15 in nu) for the oscillation envelope
OSC_NU = -0.78  # below this the residual oscillates (Fresnel): see model doc 2.8
TREND_CELLS = 11
SCHEMA = "compensation_table v1"

_y, _fy = make_grid(N, DY)


def knife_exact_db(nu: Any) -> Any:
    s, c = fresnel(nu)
    a = (0.5 - c) - 1j * (0.5 - s)
    return -20.0 * np.log10(np.abs((1 + 1j) / 2 * a))


def hi_fidelity_loss(radius_m: float, dx: float = DX) -> Any:
    """Loss (dB) at DIST from a ridge of radius R (R = 0: knife edge), plane wave, split-step."""
    e, x_end, _ = ridge_field(_y, _fy, LAM, radius_m, dx, TRUNCATION_M)
    e = propagate(e, _fy, LAM, DIST - x_end)
    inten = np.abs(e) ** 2
    i0 = inten[(_y > 300) & (_y < 600)].mean()
    return -10.0 * np.log10(inten / i0)


def simulate_residuals(radii: Any = RADII, nus: Any = NUS) -> Any:
    """Residual table [len(radii), len(nus)] = split-step loss - exact knife edge (dB)."""
    nus_a = np.asarray(nus, dtype=float)
    yo = -nus_a * math.sqrt(LAM * DIST / 2)
    out = np.empty((len(radii), len(nus_a)))
    for i, r in enumerate(radii):
        out[i] = np.interp(yo, _y, hi_fidelity_loss(float(r))) - knife_exact_db(nus_a)
    return out


def _features(radii: Any, nus: Any) -> Any:
    rr, nn = np.meshgrid(np.log10(np.asarray(radii, float) + 1.0), nus, indexing="ij")
    return np.c_[nn.ravel(), rr.ravel()]


def gp_fit_and_anomalies(sim: Any) -> tuple[Any, Any, dict[str, float]]:
    """GP smooth table, anomaly flags (> 4 MAD) and the 25 %-missing validation RMSEs."""
    from scipy.interpolate import griddata
    from sklearn.gaussian_process import GaussianProcessRegressor as GPR
    from sklearn.gaussian_process.kernels import RBF, WhiteKernel
    from sklearn.gaussian_process.kernels import ConstantKernel as Ck

    x = _features(RADII, NUS)
    z = sim.ravel()
    n = len(z)
    rng = np.random.default_rng(SEED)
    idx = rng.permutation(n)
    miss, keep = idx[: n // 4], idx[n // 4 :]
    kern = Ck(1.0) * RBF([0.5, 0.8]) + WhiteKernel(1e-3)
    gp_part = GPR(kern, normalize_y=True, n_restarts_optimizer=1, random_state=SEED).fit(
        x[keep], z[keep]
    )
    pred_gp = gp_part.predict(x[miss])
    pred_lin = griddata(x[keep], z[keep], x[miss], method="linear")
    ok = ~np.isnan(pred_lin)

    def rmse(a: Any, b: Any) -> float:
        return float(math.sqrt(np.mean((a - b) ** 2)))

    gp_all = GPR(kern, normalize_y=True, random_state=SEED).fit(x, z)
    smooth = gp_all.predict(x)
    res = z - smooth
    mad = 1.4826 * np.median(np.abs(res - np.median(res)))
    flag = np.abs(res - np.median(res)) > MAD_K * mad
    val = {
        "missing_cells": len(miss),
        "rmse_zero_db": rmse(z[miss], 0.0),
        "rmse_linear_db": rmse(z[miss][ok], pred_lin[ok]),
        "rmse_gp_db": rmse(z[miss], pred_gp),
        "mad_db": float(mad),
        "anomalies": int(flag.sum()),
        "anomalies_nu_lt_m078": int((flag & (x[:, 0] < -0.78)).sum()),
    }
    shape = sim.shape
    return smooth.reshape(shape), flag.reshape(shape), val


def correction_table(sim: Any, gp: Any) -> tuple[Any, Any]:
    """(trend, correction): the GP interpolates the Fresnel oscillations (noise level at its lower
    bound), so for nu < OSC_NU the correction is a moving average over TREND_CELLS cells of the
    simulation (the smooth trend); the oscillation around it goes to the uncertainty."""
    from scipy.ndimage import uniform_filter1d

    trend = uniform_filter1d(sim, size=TREND_CELLS, axis=1, mode="nearest")
    return trend, np.where(NUS[None, :] < OSC_NU, trend, gp)


def oscillation_envelope(sim: Any, smooth: Any) -> Any:
    """max over +-SMOOTH_HALF_WINDOW cells of |simulated - correction|: uncertainty, not correction."""
    d = np.abs(sim - smooth)
    pad = np.pad(d, ((0, 0), (SMOOTH_HALF_WINDOW, SMOOTH_HALF_WINDOW)), mode="edge")
    w = 2 * SMOOTH_HALF_WINDOW + 1
    return np.max([pad[:, k : k + d.shape[1]] for k in range(w)], axis=0)


def _r(a: Any, nd: int = 4) -> Any:
    return np.round(np.asarray(a, dtype=float), nd).tolist()


def build() -> dict[str, Any]:
    import scipy
    import sklearn

    sim = simulate_residuals()
    smooth, flag, val = gp_fit_and_anomalies(sim)
    trend, corr = correction_table(sim, smooth)
    env = oscillation_envelope(sim, corr)
    script_bytes = HERE.read_bytes()
    return {
        "schema": SCHEMA,
        "version": "1",
        "meaning": "R(nu, radius) = L_splitstep - J_exact_knife_edge [dB]; bilinear in (nu, log10(radius+1)). "
        "Correction at run time = correction_db (gp_db for nu >= -0.78, moving-average trend_db below); uncertainty = oscillation_envelope_db; anomaly = > 4 MAD cell.",
        "nu": _r(NUS, 2),
        "radius_m": list(RADII),
        "simulated_db": _r(sim),
        "gp_db": _r(smooth),
        "trend_db": _r(trend),
        "correction_db": _r(corr),
        "oscillation_envelope_db": _r(env),
        "anomaly": flag.astype(int).tolist(),
        "validation": val,
        "provenance": {
            "generator": "scripts/gen_compensation_table.py",
            "generator_sha256": hashlib.sha256(script_bytes).hexdigest(),
            "source_script": "research papers, scripts and planning/compensation_demo.py (part A)",
            "parameters": {
                "wavelength_m": LAM,
                "distance_m": DIST,
                "n_samples": N,
                "dy_m": DY,
                "dx_m": DX,
                "truncation_m": TRUNCATION_M,
                "nu_grid": [float(NUS[0]), float(NUS[-1]), 0.05],
                "radii_m": list(RADII),
                "gp_kernel": "C(1.0) * RBF([0.5, 0.8]) + White(1e-3), normalize_y, features (nu, log10(R+1))",
                "mad_k": MAD_K,
                "smooth_half_window_cells": SMOOTH_HALF_WINDOW,
                "oscillation_nu_threshold": OSC_NU,
                "trend_cells": TREND_CELLS,
            },
            "seed": SEED,
            "libraries": {
                "python": platform.python_version(),
                "numpy": np.__version__,
                "scipy": scipy.__version__,
                "scikit-learn": sklearn.__version__,
            },
            "generated_utc": datetime.now(UTC).strftime("%Y-%m-%d"),
            "assumptions": "2D scalar paraxial, perfectly absorbing ridge, plane wave (Earth at infinity), "
            "reference distance 2000 m: a simulation, not a measurement",
        },
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--check", action="store_true", help="compare with the stored file, no write")
    args = ap.parse_args(argv)
    table = build()
    if args.check:
        old = json.loads(args.out.read_text(encoding="utf-8"))
        err = float(np.max(np.abs(np.array(old["simulated_db"]) - np.array(table["simulated_db"]))))
        print(f"max |simulated_old - simulated_new| = {err:.5f} dB")
        return 0 if err < 1e-3 else 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(table, indent=1) + "\n", encoding="utf-8")
    print(f"written {args.out} ({args.out.stat().st_size} bytes)", file=sys.stderr)
    print(json.dumps(table["validation"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
