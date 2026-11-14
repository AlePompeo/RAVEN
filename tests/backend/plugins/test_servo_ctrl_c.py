# SPDX-License-Identifier: Apache-2.0
"""Tests of the servo_ctrl_c plugin (PI controller + host HAL) via ExecSimulation.

Reference plant (used unless stated): first-order servo, tau = 0.1 s,
dt = 0.01 s, ADC 0..3.3 V over 0..180 deg (1 V = 54.5 deg), start at 0 deg.
Gains kp=2, ki=20 give closed-loop poles s^2*tau + (1+kp)s + ki = 0 ->
zeta = 3/(2*sqrt(0.1*20)) ~ 1.06, i.e. essentially critically damped, so
without actuator limits there is no overshoot. The default servo slew limit
(90 deg/s) is lifted to 1000 deg/s for the "linear" tests, otherwise it would
itself cause integrator windup and a large overshoot.
"""

import math
import shutil
import subprocess
from pathlib import Path

import pytest

from backend.adapters.subprocess_sim import ExecSimulation
from backend.core.errors import PluginError

ROOT = Path(__file__).resolve().parents[3]
PLUGIN = ROOT / "backend/plugins/servo_ctrl_c"
SOURCES = [
    PLUGIN / "servo_ctrl.c",
    PLUGIN / "control.c",
    ROOT / "contracts/hal/hal_host.c",
]
CFLAGS = ["-std=c99", "-Wall", "-Wextra", "-Werror", "-pedantic", "-O2"]
INCLUDES = [f"-I{ROOT / 'contracts/hal'}", f"-I{PLUGIN}"]


def test_host_hal_axes_are_independent(tmp_path):
    if not shutil.which("gcc"):
        pytest.skip("gcc assente")
    out = tmp_path / "hal_two_axis"
    subprocess.run(
        [
            "gcc",
            *CFLAGS,
            *INCLUDES,
            "-o",
            str(out),
            str(ROOT / "tests/backend/plugins/hal_two_axis.c"),
            str(ROOT / "contracts/hal/hal_host.c"),
            "-lm",
        ],
        check=True,
    )
    subprocess.run([str(out)], check=True)


@pytest.fixture(scope="module")
def gimbal_bin(tmp_path_factory):
    if not shutil.which("gcc"):
        pytest.skip("gcc assente")
    out = tmp_path_factory.mktemp("gimbal") / "gimbal_tracker"
    subprocess.run(
        [
            "gcc",
            *CFLAGS,
            *INCLUDES,
            "-o",
            str(out),
            str(PLUGIN / "gimbal_tracker.c"),
            str(PLUGIN / "control.c"),
            str(ROOT / "contracts/hal/hal_host.c"),
            "-lm",
        ],
        check=True,
    )
    return out


def test_gimbal_tracks_two_axes_across_azimuth_wrap(gimbal_bin):
    trajectory = "3 60\n359 10\n0 11\n1 12\n"
    run = subprocess.run(
        [str(gimbal_bin)], input=trajectory, capture_output=True, text=True, check=True
    )
    rows = [list(map(float, line.split())) for line in run.stdout.splitlines()]
    assert len(rows) == 3
    assert rows[0] == [359.0, 10.0, 0.0]
    assert rows[-1][0] == pytest.approx(361.0, abs=0.1)
    assert rows[-1][1] == pytest.approx(12.0, abs=0.1)
    assert all(row[2] == 0 for row in rows)


def test_gimbal_reports_mechanical_limit(gimbal_bin):
    run = subprocess.run(
        [str(gimbal_bin)], input="2 60\n0 0\n150 0\n", capture_output=True, text=True, check=True
    )
    az, el, limited = map(float, run.stdout.splitlines()[-1].split())
    assert az <= 90.0
    assert el == pytest.approx(0.0, abs=0.1)
    assert limited == 1


@pytest.mark.parametrize("trajectory", ["2 60\n0 0\n", "1 60\nNaN 0\n", "1 60\n0 0\nextra\n"])
def test_gimbal_rejects_invalid_input_without_output(gimbal_bin, trajectory):
    run = subprocess.run(
        [str(gimbal_bin)], input=trajectory, capture_output=True, text=True, check=False
    )
    assert run.returncode == 2
    assert run.stdout == ""


# Tolerances (see the comment next to each use).
NOISE_FREE_STEADY_ERR_DEG = (
    0.05  # observed ~1e-5; float32 rounding only, 0.05 = 0.03% of the 180 deg range
)
NOISE_FREE_SETTLE_S = 0.5  # observed 0.19 s; 2.5x margin against compiler/libm differences
NOISE_V = 0.01  # = 0.55 deg sigma on the angle reading
NOISY_STEADY_ERR_DEG = 1.0  # observed 0.02-0.12; ~2 sigma of the sensor noise, the loop filters it
NOISY_OVERSHOOT_DEG = 2.0  # observed ~0.49; ~4 sigma of the sensor noise
SAT_FRACTION = 0.9  # setpoint 200 deg: observed 289/300 saturated (first steps are not yet clipped)


@pytest.fixture(scope="session", params=["plain", "sanitized", "ubsan-trap"])
def sim(request, tmp_path_factory):
    if not shutil.which("gcc"):
        pytest.skip("gcc assente")
    out = tmp_path_factory.mktemp(request.param) / "servo_ctrl"
    flags = {
        "plain": [],
        # needs libasan/libubsan; skipped when the runtime is not installed
        "sanitized": ["-fsanitize=address,undefined", "-fno-sanitize-recover=all", "-g"],
        # no runtime library needed: UB aborts the process (SIGILL) instead of reporting
        "ubsan-trap": ["-fsanitize=undefined", "-fsanitize-trap=undefined", "-g"],
    }
    extra = flags[request.param]
    cmd = ["gcc", *CFLAGS, *extra, *INCLUDES, "-o", str(out), *map(str, SOURCES), "-lm"]
    build = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if build.returncode != 0:
        if request.param != "plain":
            pytest.skip(f"runtime sanitizer non disponibile: {build.stderr[:200]}")
        pytest.fail(build.stderr)
    return ExecSimulation([str(out)], PLUGIN), out


def base(**over):
    p = {
        "setpoint_deg": 45.0,
        "kp": 2.0,
        "ki": 20.0,
        "steps": 300,
        "dt_s": 0.01,
        "plant_tau_s": 0.1,
        "sensor_noise_v": 0.0,
        "seed": 1,
        "plant_rate_dps": 1000.0,
    }
    p.update(over)
    return p


async def run(sim, **over):
    return await sim[0].run(base(**over), timeout_s=5)


async def test_converges_noise_free(sim):
    r = await run(sim)
    assert abs(r["final_angle_deg"] - 45.0) < NOISE_FREE_STEADY_ERR_DEG
    assert r["steady_error_deg"] < NOISE_FREE_STEADY_ERR_DEG
    assert r["settle_time_s"] < NOISE_FREE_SETTLE_S
    assert r["max_overshoot_deg"] < 0.1  # zeta ~ 1.06: no overshoot expected
    assert r["saturated_steps"] == 0


async def test_converges_with_noise_and_bounded_overshoot(sim):
    r = await run(sim, sensor_noise_v=NOISE_V)
    assert r["steady_error_deg"] < NOISY_STEADY_ERR_DEG
    assert r["max_overshoot_deg"] < NOISY_OVERSHOOT_DEG


async def test_saturation_counted_when_setpoint_out_of_range(sim):
    r = await run(sim, setpoint_deg=200.0, kp=3.0, ki=30.0)
    assert r["saturated_steps"] >= SAT_FRACTION * 300
    assert abs(r["final_angle_deg"] - 180.0) < 0.05  # servo end stop
    assert r["steady_error_deg"] == pytest.approx(20.0, abs=0.1)


async def test_anti_windup_recovers_faster(sim):
    # default slew limit (90 deg/s) saturates the output for a long time
    kw = {"setpoint_deg": 90.0, "kp": 3.0, "ki": 30.0, "steps": 600, "plant_rate_dps": 90.0}
    on = await run(sim, anti_windup=1, **kw)
    off = await run(sim, anti_windup=0, **kw)
    # observed settle: 1.43 s with vs 4.79 s without; require at least 40 % shorter
    assert on["settle_time_s"] <= 0.6 * off["settle_time_s"]
    # observed overshoot: 12 deg vs 76 deg
    assert on["max_overshoot_deg"] < 0.5 * off["max_overshoot_deg"]
    assert on["saturated_steps"] > 0


async def test_deterministic_for_same_seed_and_different_for_other(sim):
    a = await run(sim, sensor_noise_v=NOISE_V, seed=7)
    b = await run(sim, sensor_noise_v=NOISE_V, seed=7)
    c = await run(sim, sensor_noise_v=NOISE_V, seed=8)
    assert a == b
    assert a != c


async def test_seed_irrelevant_without_noise(sim):
    assert await run(sim, seed=1) == await run(sim, seed=999)


@pytest.mark.parametrize(
    "over",
    [
        {"kp": 1000.0, "ki": 1000.0, "dt_s": 1.0, "plant_tau_s": 1.0, "steps": 1000},
        {"setpoint_deg": -720.0},
        {"setpoint_deg": 720.0, "sensor_noise_v": 0.1},
        {"setpoint_deg": 0.0},
        {"steps": 100000, "dt_s": 0.0001, "plant_tau_s": 0.0001},
        {"kp": 0.0, "ki": 0.0},
    ],
)
async def test_outputs_finite(sim, over):
    r = await run(sim, **over)
    assert set(r) == {
        "final_angle_deg",
        "steady_error_deg",
        "max_overshoot_deg",
        "settle_time_s",
        "saturated_steps",
    }
    assert all(math.isfinite(v) for v in r.values())


@pytest.mark.parametrize(
    "over",
    [
        {"dt_s": -0.01},
        {"dt_s": 0.0},
        {"dt_s": 2.0},
        {"steps": 0},
        {"steps": 1e9},
        {"steps": 10.5},
        {"kp": -1.0},
        {"ki": -1.0},
        {"kp": 1001.0},
        {"setpoint_deg": 721.0},
        {"plant_tau_s": 0.0},
        {"plant_tau_s": 0.005},  # tau < dt: explicit Euler unstable
        {"sensor_noise_v": -0.1},
        {"sensor_noise_v": 0.5},
        {"seed": -1},
        {"seed": 4294967296.0},
        {"anti_windup": 2},
        {"plant_rate_dps": 0.0},
    ],
)
async def test_invalid_input_rejected_via_exec_simulation(sim, over):
    with pytest.raises(PluginError, match="exit 2"):
        await run(sim, **over)


def raw(sim, text):
    return subprocess.run(
        [str(sim[1])], check=False, input=text, capture_output=True, text=True, timeout=5
    )


@pytest.mark.parametrize("bad", ["nan", "inf", "-inf", "1e999", "abc", "", "1.0x"])
def test_non_finite_or_garbage_values_exit_2_with_empty_stdout(sim, bad):
    # ExecSimulation refuses to send NaN/inf, so feed the binary directly
    lines = "".join(f"{k}={v}\n" for k, v in base().items() if k != "kp")
    r = raw(sim, lines + f"kp={bad}\n")
    assert r.returncode == 2
    assert r.stdout == ""


@pytest.mark.parametrize(
    "bad_field", ["setpoint_deg", "ki", "dt_s", "plant_tau_s", "sensor_noise_v", "steps", "seed"]
)
def test_nan_in_any_field_exit_2(sim, bad_field):
    lines = "".join(f"{k}={'nan' if k == bad_field else v}\n" for k, v in base().items())
    r = raw(sim, lines)
    assert r.returncode == 2
    assert r.stdout == ""


async def test_nan_rejected_before_spawn_by_exec_simulation(sim):
    with pytest.raises(PluginError):
        await run(sim, kp=float("nan"))


def test_missing_unknown_duplicate_keys_exit_2(sim):
    full = "".join(f"{k}={v}\n" for k, v in base().items())
    missing = "".join(f"{k}={v}\n" for k, v in base().items() if k != "seed")
    for text in (missing, full + "bogus=1\n", full + "kp=3\n", full + "no_equals\n", ""):
        r = raw(sim, text)
        assert r.returncode == 2, text
        assert r.stdout == ""


def test_overlong_line_rejected(sim):
    r = raw(sim, "kp=" + "1" * 500 + "\n")
    assert r.returncode == 2
    assert r.stdout == ""
