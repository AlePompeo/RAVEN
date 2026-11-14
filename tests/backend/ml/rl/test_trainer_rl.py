# SPDX-License-Identifier: Apache-2.0
"""Gate di promozione RL contro un baseline PD sintonizzato.

Disegno (vedi backend/ml/rl/training.py): baseline = migliore di una griglia P/PD sintonizzata sui
semi di TRAINING (vede errore E velocita', come la politica); guadagno = (R_pol - R_base)/|R_base|
su 300 episodi di valutazione appaiati (stessi semi); IC bootstrap appaiato al 95% (2000 ricampioni,
seme fisso); soglia sul limite INFERIORE dell'IC, nominale e con impianto perturbato (+-20% tau e
rate). Su questo impianto un PD ben sintonizzato e' quasi ottimo: ARS lo eguaglia, non lo batte di
0.15, quindi il candidato ARS di esempio NON supera il gate (e il registro rifiuta la promozione).
"""

import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("numpy")
pytest.importorskip("onnx")
pytest.importorskip("onnxruntime")

import numpy as np

from backend.bootstrap import build_app
from backend.core.errors import PromotionRefused
from backend.ml.registry import FileModelRegistry
from backend.ml.rl import evaluation as ev
from backend.ml.rl import linear_policy as lp
from backend.ml.rl.env_adapter import SimulationEnv
from backend.ml.rl.training import (
    CI_KEY,
    CI_PERT_KEY,
    MIN_GAIN,
    eval_seed_base,
    evaluate,
    train_candidate,
)

TIME_BUDGET_S = 30.0  # misurato ~3-4 s (ARS 20 episodi per valutazione + 2x300 episodi di eval)


# ---- bootstrap -------------------------------------------------------------------------------
def test_bootstrap_is_deterministic_and_paired() -> None:
    rng = np.random.default_rng(1)
    base = -rng.uniform(2, 4, 300)
    pol = base * 0.8 + rng.normal(0, 0.05, 300)  # 20% migliore, appaiato
    a = ev.bootstrap_gain(pol, base)
    b = ev.bootstrap_gain(pol, base)
    assert a == b
    mean, low = a
    assert low <= mean and abs(mean - 0.2) < 0.03
    assert low > 0.15  # l'appaiamento rende l'IC stretto
    assert ev.bootstrap_gain(pol, base, seed=1) != ev.bootstrap_gain(pol, base, seed=2)


def test_bootstrap_rejects_bad_input() -> None:
    with pytest.raises(ValueError):
        ev.bootstrap_gain(np.array([-1.0, -2.0]), np.array([-1.0]))
    with pytest.raises(ValueError):
        ev.bootstrap_gain(np.array([-1.0]), np.array([0.0]))


# ---- gate ------------------------------------------------------------------------------------
def tuned_baseline() -> tuple[Any, float, float]:
    env = SimulationEnv()
    return ev.tune_pd(env, ev.tuning_seeds())


def test_pd_tuned_only_on_training_seeds() -> None:
    assert set(ev.tuning_seeds()).isdisjoint(lp.eval_seeds(1000))
    _, kp, kd = tuned_baseline()
    assert (kp, kd) in ev.PD_GRID
    assert kp < max(g[0] for g in ev.PD_GRID) and kd > min(g[1] for g in ev.PD_GRID)  # non al bordo


def test_policy_no_better_than_tuned_pd_fails_gate(tmp_path: Path) -> None:
    pd, kp, kd = tuned_baseline()
    blob = lp.policy_to_onnx(np.array([kp, kd, 0.0]))  # stessa politica del baseline
    m = evaluate(blob, baseline=pd, seed_base=eval_seed_base(0), n_eval=300)
    assert m[CI_KEY] < MIN_GAIN and m[CI_PERT_KEY] < MIN_GAIN
    reg = FileModelRegistry(tmp_path)
    v = reg.save(
        blob,
        {
            "seed": 0,
            "dataset_sha256": "0" * 64,
            "library_versions": {"numpy": "x"},
            "metrics": m,
            "threshold": {CI_KEY: MIN_GAIN, CI_PERT_KEY: MIN_GAIN},
        },
    )
    with pytest.raises(PromotionRefused):
        reg.promote(v, approver="alice", approved=True)


def test_clearly_better_policy_passes_gate_and_needs_human(tmp_path: Path) -> None:
    """PD sintonizzato contro un baseline volutamente debole (P con guadagno 2): supera il gate."""
    _, kp, kd = tuned_baseline()
    blob = lp.policy_to_onnx(np.array([kp, kd, 0.0]))
    m = evaluate(blob, baseline=lp.p_controller, seed_base=eval_seed_base(0), n_eval=300)
    assert m[CI_KEY] >= MIN_GAIN and m[CI_PERT_KEY] >= MIN_GAIN
    reg = FileModelRegistry(tmp_path)
    v = reg.save(
        blob,
        {
            "seed": 0,
            "dataset_sha256": "0" * 64,
            "library_versions": {"numpy": "x"},
            "metrics": m,
            "threshold": {CI_KEY: MIN_GAIN, CI_PERT_KEY: MIN_GAIN},
        },
    )
    with pytest.raises(PromotionRefused):
        reg.promote(v, approver="alice", approved=False)
    assert reg.promote(v, approver="alice", approved=True)["status"] == "promoted"


def test_paired_eval_uses_identical_seeds_and_perturbed_set_differs() -> None:
    seeds = [lp.EVAL_SEED_BASE + i for i in range(5)]
    nominal = ev.episode_returns(lambda s: SimulationEnv(), lp.p_controller, seeds)
    again = ev.episode_returns(lambda s: SimulationEnv(), lp.p_controller, seeds)
    pert = ev.episode_returns(ev.perturbed_env, lp.p_controller, seeds)
    assert np.array_equal(nominal, again) and not np.array_equal(nominal, pert)


def test_perturbation_within_20_percent_and_deterministic() -> None:
    for s in range(50):
        e = ev.perturbed_env(s)
        assert 0.8 * 0.3 - 1e-12 <= e.tau_s <= 1.2 * 0.3 + 1e-12
        assert 0.8 * 90 - 1e-9 <= e.rate_dps <= 1.2 * 90 + 1e-9
        assert (e.tau_s, e.rate_dps) == (ev.perturbed_env(s).tau_s, ev.perturbed_env(s).rate_dps)
    assert len({ev.perturbed_env(s).tau_s for s in range(20)}) > 10


def test_eval_blocks_fresh_per_candidate_and_disjoint_from_training() -> None:
    train = {lp.TRAIN_SEED_BASE + i for i in range(5000)}
    bases = {eval_seed_base(s) for s in range(20)}
    assert len(bases) == 20  # un blocco nuovo per ogni seme registrato
    for b in bases:
        blk = set(range(b, b + 300)) | set(
            range(b + ev.PERTURBED_OFFSET, b + ev.PERTURBED_OFFSET + 300)
        )
        assert blk.isdisjoint(train) and max(blk) <= 2**32 - 1
    assert eval_seed_base(3) == eval_seed_base(3)  # riproducibile dal seme


# ---- addestramento ARS -----------------------------------------------------------------------
def test_ars_candidate_metrics_card_and_honest_gate(tmp_path: Path) -> None:
    reg = FileModelRegistry(tmp_path)
    t0 = time.monotonic()
    version, m = train_candidate(reg, seed=0)
    assert time.monotonic() - t0 < TIME_BUDGET_S
    card = reg.load(version)[1]
    assert card["status"] == "candidate" and reg.promoted_version() is None
    assert set(card["threshold"]) == {CI_KEY, CI_PERT_KEY}
    for k in (
        "gain_mean",
        "gain_ci_low",
        "gain_mean_perturbed",
        "gain_ci_low_perturbed",
        "eval_seed_base",
        "n_eval",
        "gain_mean_vs_untuned_p",
    ):
        assert k in card["metrics"]
    assert card["metrics"]["eval_seed_base"] == eval_seed_base(0)
    # profilo registrato nella card (servo_realistic di default, valori dichiarati in anticipo)
    assert card["metrics"]["profile_deadband_deg"] == 1.0
    assert card["metrics"]["profile_stiction_dps"] == 5.0
    assert card["metrics"]["profile_backlash_deg"] == 1.0
    assert m["n_eval"] >= 300
    # contro il P non sintonizzato (guadagno 2) e l'azione zero la politica e' molto migliore...
    assert m["gain_mean_vs_untuned_p"] > 0.2
    # ...ma contro un PD sintonizzato non c'e' margine reale: il gate rifiuta (comportamento atteso)
    assert m[CI_KEY] < MIN_GAIN
    with pytest.raises(PromotionRefused):
        reg.promote(version, approver="alice", approved=True)


def test_nominal_profile_records_zero_nonlinearities(tmp_path: Path) -> None:
    reg = FileModelRegistry(tmp_path)
    _, m = train_candidate(reg, seed=0, iterations=3, profile="nominal")
    assert (
        m["profile_deadband_deg"] == m["profile_stiction_dps"] == m["profile_backlash_deg"] == 0.0
    )
    with pytest.raises(ValueError):
        train_candidate(reg, seed=0, iterations=1, profile="nope")


def test_eval_seeds_disjoint_from_training_seeds() -> None:
    train = {lp.TRAIN_SEED_BASE + i for i in range(5000)}
    assert train.isdisjoint(lp.eval_seeds(500))


def test_training_is_deterministic() -> None:
    env = SimulationEnv()
    a = lp.ars_train(env, seed=3, iterations=5, directions=4)
    b = lp.ars_train(SimulationEnv(), seed=3, iterations=5, directions=4)
    assert np.array_equal(a, b)


def test_onnx_policy_matches_numpy_policy() -> None:
    w = np.array([3.0, -0.5, 0.2])
    onnx_p, np_p = lp.onnx_policy(lp.policy_to_onnx(w)), lp.linear(w)
    rng = np.random.default_rng(0)
    for obs in rng.uniform(-1, 1, size=(50, 3)):
        assert abs(onnx_p(obs.tolist()) - np_p(obs.tolist())) < lp.ONNX_TOLERANCE


def test_onnx_vs_numpy_check_rejects_mismatch() -> None:
    w = np.array([3.0, -0.5, 0.2])
    lp.check_onnx_matches(w, lp.policy_to_onnx(w))
    with pytest.raises(ValueError):
        lp.check_onnx_matches(w, lp.policy_to_onnx(w + 0.5))


def test_ars_rejects_nonfinite_init() -> None:
    with pytest.raises(ValueError):
        lp.ars_train(
            SimulationEnv(), seed=0, iterations=1, directions=2, init=np.array([np.nan, 0, 0])
        )


def wait_done(c: TestClient, job_id: str) -> dict[str, Any]:
    end = time.monotonic() + 120
    while time.monotonic() < end:
        j = c.get(f"/api/jobs/{job_id}").json()
        if j["status"] in ("done", "failed", "cancelled"):
            return j  # type: ignore[no-any-return]
        time.sleep(0.1)
    raise AssertionError("timeout")


def test_trainer_rl_runs_through_runner_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MODEL_REGISTRY_DIR", str(tmp_path / "reg"))
    t0 = time.monotonic()
    with TestClient(build_app()) as c:
        r = c.post("/api/train", json={"trainer": "trainer-rl", "config": {"seed": 2}})
        assert r.status_code == 202
        job = wait_done(c, r.json()["id"])
        bad = c.post("/api/train", json={"trainer": "trainer-rl", "config": {"n_eval": 10}})
        bad_job = wait_done(c, bad.json()["id"])
        bad2 = c.post("/api/train", json={"trainer": "trainer-rl", "config": {"profile": "x"}})
        assert wait_done(c, bad2.json()["id"])["status"] == "failed"
    assert job["status"] == "done", job
    assert time.monotonic() - t0 < 90.0
    assert CI_KEY in job["metrics"]
    reg = FileModelRegistry(tmp_path / "reg")
    assert reg.promoted_version() is None
    assert reg.load(job["model_version"])[1]["status"] == "candidate"
    assert bad_job["status"] == "failed"
