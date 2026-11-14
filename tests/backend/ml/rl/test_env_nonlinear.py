# SPDX-License-Identifier: Apache-2.0
"""Non linearita' opzionali dell'impianto (deadband, stiction, backlash): default OFF."""

import math
import random

import pytest

pytest.importorskip("numpy")  # extra [ml]/[rl]

from backend.ml.rl import evaluation as ev
from backend.ml.rl.env_adapter import PROFILES, ServoPlant, SimulationEnv, profile_kwargs


def plant(**kw: float) -> ServoPlant:
    return ServoPlant(dt_s=0.1, tau_s=0.3, rate_dps=90.0, angle_limit_deg=180.0, **kw)


def rollout(env: SimulationEnv, seed: int) -> list[tuple[float, ...]]:
    env.reset(seed=seed)
    out, done = [], False
    while not done:
        obs, r, term, trunc, _ = env.step([0.5 if len(out) % 7 < 4 else -0.3])
        out.append((*obs, r))
        done = term or trunc
    return out


def test_defaults_off_equal_explicit_zeros() -> None:
    zeros = SimulationEnv(deadband_deg=0.0, stiction_dps=0.0, backlash_deg=0.0)
    assert rollout(SimulationEnv(), 3) == rollout(zeros, 3)
    assert PROFILES["nominal"] == {}


def test_deadband_ignores_small_commanded_displacement() -> None:
    # u*rate*dt = u*9 deg per step; deadband 1 deg -> |u| < 0.111 ignorato
    p = plant(deadband_deg=1.0)
    for _ in range(10):
        p.advance(0.1)
    assert p.angle_deg == 0.0
    for _ in range(3):
        p.advance(0.2)
    assert p.angle_deg > 0.0
    q = plant()
    for _ in range(10):
        q.advance(0.1)
    assert q.angle_deg > 0.0  # senza deadband si muove


def test_stiction_sticks_at_low_speed_and_breaks_away() -> None:
    p = plant(stiction_dps=5.0)
    for _ in range(10):
        p.advance(0.03)  # target 2.7 dps <= 5: resta fermo
    assert p.angle_deg == 0.0 and p.velocity_dps == 0.0
    for _ in range(5):
        p.advance(1.0)  # target 90 dps: stacco
    assert p.velocity_dps > 5.0 and p.angle_deg > 0.0
    for _ in range(40):
        p.advance(0.0)  # frena: sotto la soglia "si incolla" invece di decadere
    assert p.velocity_dps == 0.0


def test_backlash_play_on_reversal_and_invariant() -> None:
    p = plant(backlash_deg=2.0)
    for _ in range(6):
        p.advance(1.0)
    assert p.angle_deg > 0
    rng = random.Random(1)
    for _ in range(300):
        p.advance(rng.uniform(-1, 1))
        assert abs(p._motor_deg - p.angle_deg) <= 1.0 + 1e-9  # gioco b/2 per lato


def test_backlash_output_holds_after_reversal() -> None:
    p = plant(backlash_deg=4.0)
    p.advance(1.0)
    p.advance(1.0)
    held = p.angle_deg
    p.velocity_dps = 0.0
    p.advance(-0.05)  # piccolo moto inverso (< 2 deg di gioco): l'uscita non cambia
    assert p.angle_deg == held


@pytest.mark.parametrize(
    "kw",
    [
        {"deadband_deg": -1.0},
        {"stiction_dps": float("nan")},
        {"backlash_deg": float("inf")},
        {"deadband_deg": 100.0},
    ],
)
def test_nonlinear_parameters_validated(kw: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        SimulationEnv(**kw)


def test_servo_realistic_profile_declared_values() -> None:
    """Valori scelti PRIMA del confronto, illustrativi (non misurati): vedi docs/ml.md."""
    assert profile_kwargs("servo_realistic") == {
        "deadband_deg": 1.0,
        "stiction_dps": 5.0,
        "backlash_deg": 1.0,
    }
    with pytest.raises(ValueError):
        profile_kwargs("nope")
    env = SimulationEnv(**profile_kwargs("servo_realistic"))
    assert rollout(env, 5) == rollout(SimulationEnv(**profile_kwargs("servo_realistic")), 5)


def test_reward_and_obs_bounds_hold_with_nonlinearities() -> None:
    env = SimulationEnv(**profile_kwargs("servo_realistic"))
    lo = -(env.max_abs_error_deg / env.reward_scale_deg) - 0.05
    rng = random.Random(0)
    for seed in range(10):
        env.reset(seed=seed)
        done = False
        while not done:
            obs, r, term, trunc, _ = env.step([rng.uniform(-2, 2)])
            assert lo <= r <= 0.0 and all(math.isfinite(x) and -1 <= x <= 1 for x in obs)
            done = term or trunc


def test_perturbation_scales_nonlinear_parameters_within_20_percent() -> None:
    base = profile_kwargs("servo_realistic")
    seen = set()
    for s in range(50):
        e = ev.perturbed_env(s, base)
        for name, nominal in base.items():
            v = getattr(e, name)
            assert 0.8 * nominal - 1e-9 <= v <= 1.2 * nominal + 1e-9
        seen.add(e.deadband_deg)
    assert len(seen) > 10
    zero = ev.perturbed_env(1, {})  # parametri a 0 restano 0
    assert zero.deadband_deg == zero.stiction_dps == zero.backlash_deg == 0.0
