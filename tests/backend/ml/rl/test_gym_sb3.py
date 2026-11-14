# SPDX-License-Identifier: Apache-2.0
"""Shim Gymnasium e esempio Stable-Baselines3 (extra [rl]); saltati se gli extra mancano."""

import subprocess
import sys
import time

import pytest

gym = pytest.importorskip("gymnasium")
np = pytest.importorskip("numpy")

from backend.plugins.env_servo.gym_shim import ServoGymEnv


def test_gymnasium_check_env_passes() -> None:
    from gymnasium.utils.env_checker import check_env

    check_env(ServoGymEnv(), skip_render_check=True)


def test_gym_determinism() -> None:
    a, b = ServoGymEnv(), ServoGymEnv()
    oa, _ = a.reset(seed=4)
    ob, _ = b.reset(seed=4)
    assert np.array_equal(oa, ob)
    assert a.step(np.array([0.3]))[1] == b.step(np.array([0.3]))[1]


def test_gym_nan_action_rejected() -> None:
    e = ServoGymEnv()
    e.reset(seed=0)
    with pytest.raises(ValueError):
        e.step(np.array([np.nan]))


def test_shim_import_without_gymnasium_fails_clearly() -> None:
    code = "import sys; sys.modules['gymnasium']=None; import backend.plugins.env_servo.gym_shim"
    p = subprocess.run([sys.executable, "-c", code], check=False, capture_output=True, text=True)
    assert p.returncode != 0 and "extra [rl]" in p.stderr


def test_sb3_ppo_smoke_improves_over_zero_action() -> None:
    """PPO (SB3, CPU) 8k passi: solo uno smoke test sull'integrazione, NON un benchmark.

    Con cosi' pochi passi PPO non e' garantito batta il P; si richiede soltanto che batta
    nettamente l'azione zero (ritorno medio -42 sullo stesso insieme di semi).
    """
    pytest.importorskip("stable_baselines3")
    pytest.importorskip("torch")
    from stable_baselines3 import PPO

    from backend.ml.rl import linear_policy as lp
    from backend.ml.rl.env_adapter import SimulationEnv

    t0 = time.monotonic()
    model = PPO("MlpPolicy", ServoGymEnv(), seed=0, n_steps=512, batch_size=128, device="cpu")
    model.learn(total_timesteps=8192)
    assert time.monotonic() - t0 < 120.0

    def pol(obs):  # type: ignore[no-untyped-def]
        return float(model.predict(np.array(obs, dtype=np.float32), deterministic=True)[0][0])

    env = SimulationEnv()
    seeds = lp.eval_seeds(30)
    assert lp.mean_return(env, pol, seeds) > 0.5 * lp.mean_return(env, lp.zero_policy, seeds)
