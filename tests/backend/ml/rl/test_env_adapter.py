# SPDX-License-Identifier: Apache-2.0
import math
import random

import pytest

from backend.core.ports import Environment
from backend.ml.rl.env_adapter import SAT_PENALTY, SimulationEnv


def rollout(env: SimulationEnv, seed: int, policy) -> list:
    obs, _ = env.reset(seed=seed)
    out = [obs]
    done = False
    while not done:
        obs, r, term, trunc, _ = env.step(policy(obs))
        out.append((obs, r, term, trunc))
        done = term or trunc
    return out


def test_satisfies_environment_port() -> None:
    env = SimulationEnv()
    assert isinstance(env, Environment)
    assert env.observation_space.shape == (3,)
    assert env.action_space.shape == (1,)
    assert env.action_space.low == (-1.0,) and env.action_space.high == (1.0,)


def test_reset_contract() -> None:
    obs, info = SimulationEnv().reset(seed=1)
    assert len(obs) == 3 and all(math.isfinite(x) and -1 <= x <= 1 for x in obs)
    assert isinstance(info, dict) and "setpoint_deg" in info


def test_step_contract() -> None:
    env = SimulationEnv()
    env.reset(seed=1)
    obs, r, term, trunc, info = env.step([0.0])
    assert len(obs) == 3 and isinstance(r, float) and isinstance(term, bool)
    assert isinstance(trunc, bool) and isinstance(info, dict)


def test_step_before_reset_and_after_done_raise() -> None:
    env = SimulationEnv(max_steps=2)
    with pytest.raises(RuntimeError):
        env.step([0.0])
    env.reset(seed=3)
    env.step([0.0])
    env.step([0.0])
    with pytest.raises(RuntimeError):
        env.step([0.0])


def test_determinism_same_seed() -> None:
    def pol(o):
        return [0.7 * o[0]]

    assert rollout(SimulationEnv(), 11, pol) == rollout(SimulationEnv(), 11, pol)
    assert rollout(SimulationEnv(), 11, pol) != rollout(SimulationEnv(), 12, pol)


def test_unseeded_reset_continues_stream_but_is_reproducible() -> None:
    a, b = SimulationEnv(), SimulationEnv()
    a.reset(seed=5)
    b.reset(seed=5)
    assert a.reset() == b.reset()


def test_truncation_at_max_steps() -> None:
    env = SimulationEnv(max_steps=7)
    env.reset(seed=2)
    for i in range(7):
        _, _, term, trunc, _ = env.step([0.0])
        assert not term
        assert trunc == (i == 6)


def test_termination_on_settled() -> None:
    env = SimulationEnv(setpoint_range_deg=0.0, sensor_noise_deg=0.0)
    env.reset(seed=1)  # setpoint 0, angle 0, velocity 0: already settled
    _, _, term, trunc, info = env.step([0.0])
    assert term and not trunc and info["settled"]


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
def test_non_finite_action_rejected(bad: float) -> None:
    env = SimulationEnv()
    env.reset(seed=1)
    with pytest.raises(ValueError):
        env.step([bad])
    # lo stato non e' stato corrotto: si puo' continuare
    obs, r, *_ = env.step([0.0])
    assert all(math.isfinite(x) for x in obs) and math.isfinite(r)


@pytest.mark.parametrize("bad", [[], [0.0, 0.0], "x", None, [None], [True], [1j]])
def test_malformed_action_rejected(bad) -> None:
    env = SimulationEnv()
    env.reset(seed=1)
    with pytest.raises(ValueError):
        env.step(bad)


def test_action_clipped_and_penalised() -> None:
    env = SimulationEnv(sensor_noise_deg=0.0)
    env.reset(seed=4)
    _, r_in, _, _, i_in = env.step([1.0])
    env.reset(seed=4)
    _, r_out, _, _, i_out = env.step([1e300])
    assert not i_in["action_clipped"] and i_out["action_clipped"]
    assert i_out["applied_action"] == 1.0
    assert r_out == pytest.approx(r_in - SAT_PENALTY)


def test_reward_bounds_and_observation_bounds_under_random_actions() -> None:
    rng = random.Random(0)
    env = SimulationEnv()
    lo = -(env.max_abs_error_deg / env.reward_scale_deg) - SAT_PENALTY
    for seed in range(20):
        env.reset(seed=seed)
        done = False
        while not done:
            a = rng.choice([-1e9, -1.0, 0.0, 1.0, 1e9, rng.uniform(-3, 3)])
            obs, r, term, trunc, _ = env.step([a])
            assert lo <= r <= 0.0
            assert all(-1.0 <= x <= 1.0 for x in obs)
            done = term or trunc


def test_reward_is_negative_abs_error() -> None:
    env = SimulationEnv(sensor_noise_deg=0.0)
    _, info = env.reset(seed=9)
    _, r, _, _, i = env.step([0.0])
    assert r == pytest.approx(-abs(i["error_deg"]) / env.reward_scale_deg)
    assert info["setpoint_deg"] == i["setpoint_deg"]


@pytest.mark.parametrize("seed", [-1, 2**32, True, 1.5, "1"])
def test_bad_seed_rejected(seed) -> None:
    with pytest.raises(ValueError):
        SimulationEnv().reset(seed=seed)


@pytest.mark.parametrize(
    "kw",
    [
        {"max_steps": 0},
        {"max_steps": 10**9},
        {"sensor_noise_deg": -1.0},
        {"setpoint_range_deg": float("nan")},
        {"dt_s": 0.0},
    ],
)
def test_bad_config_rejected(kw) -> None:
    with pytest.raises(ValueError):
        SimulationEnv(**kw)
