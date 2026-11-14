# SPDX-License-Identifier: Apache-2.0
"""predictor_baseline/trainer_baseline: seme riservato al test set e dominio di addestramento."""

from pathlib import Path

import pytest

pytest.importorskip("numpy")
pytest.importorskip("sklearn")
pytest.importorskip("skl2onnx")
pytest.importorskip("onnxruntime")

from backend.core.errors import PluginError
from backend.ml.registry import FileModelRegistry
from backend.plugins.predictor_baseline import data, training
from backend.plugins.predictor_baseline.plugin import BaselinePredictor
from backend.plugins.trainer_baseline.plugin import BOUNDS, BaselineTrainer


def test_fixed_test_seed_rejected_as_training_seed(tmp_path: Path) -> None:
    reg = FileModelRegistry(tmp_path)
    with pytest.raises(ValueError, match="riservato"):
        training.train_candidate(reg, seed=data.FIXED_TEST_SEED, n_train=50, n_estimators=2)
    assert reg.list_versions() == []


def test_trainer_baseline_rejects_reserved_seed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MODEL_REGISTRY_DIR", str(tmp_path))
    assert BOUNDS["seed"][1] >= data.FIXED_TEST_SEED  # il seme e' nei limiti: serve il controllo
    with pytest.raises(ValueError, match="riservato"):
        BaselineTrainer(None).fit("", {"seed": data.FIXED_TEST_SEED, "n_train": 50})


def test_train_and_test_samples_disjoint() -> None:
    x_test, _ = data.fixed_test_set()
    test_rows = {tuple(r) for r in x_test.tolist()}
    for seed in (0, 1, data.FIXED_TEST_SEED - 1, data.FIXED_TEST_SEED + 1):
        x, _ = data.make_dataset(2000, seed)
        assert test_rows.isdisjoint({tuple(r) for r in x.tolist()})


def test_serving_domain_check_with_10_percent_margin_and_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MODEL_REGISTRY_DIR", str(tmp_path))
    reg = FileModelRegistry(tmp_path)
    v, m = training.train_candidate(reg, seed=1, n_train=1000, n_estimators=100)
    assert 1.0 <= m["train_power_w_min"] < 1.2 and 500.0 <= m["train_distance_km_min"] < 560.0
    reg.promote(v, approver="alice", approved=True)
    p = BaselinePredictor(None)
    p.predict({"power_w": 10.0, "distance_km": 1000.0})
    p.predict({"power_w": 21.5, "distance_km": 2150.0})  # dentro max*1.1
    for bad in (
        {"power_w": 30.0, "distance_km": 1000.0},
        {"power_w": 0.5, "distance_km": 1000.0},
        {"power_w": 10.0, "distance_km": 2500.0},
        {"power_w": 10.0, "distance_km": 400.0},
    ):
        with pytest.raises(PluginError, match="dominio di addestramento"):
            p.predict(bad)


def test_serving_fails_closed_when_card_has_no_ranges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import numpy as np
    from skl2onnx import to_onnx
    from sklearn.linear_model import LinearRegression

    monkeypatch.setenv("MODEL_REGISTRY_DIR", str(tmp_path))
    x, y = data.make_dataset(200, 2)
    blob = to_onnx(LinearRegression().fit(x, y), x[:1].astype(np.float32)).SerializeToString()
    reg = FileModelRegistry(tmp_path)
    v = reg.save(
        blob,
        {
            "seed": 2,
            "dataset_sha256": data.sha256_of(x, y),
            "library_versions": {"numpy": "x"},
            "metrics": {training.SKILL_KEY: 0.9},
            "threshold": {training.SKILL_KEY: 0.25},
        },
    )
    reg.promote(v, approver="alice", approved=True)
    with pytest.raises(PluginError, match="dominio"):
        BaselinePredictor(None).predict({"power_w": 10.0, "distance_km": 1000.0})
