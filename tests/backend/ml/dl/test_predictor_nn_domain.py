# SPDX-License-Identifier: Apache-2.0
"""Dominio di addestramento, seme riservato al test set e disgiunzione train/test (extra [dl])."""

from pathlib import Path

import pytest

pytest.importorskip("torch")
pytest.importorskip("onnx")
pytest.importorskip("onnxscript")
pytest.importorskip("onnxruntime")

from backend.core.errors import PluginError
from backend.ml.registry import FileModelRegistry
from backend.plugins.predictor_baseline import data
from backend.plugins.predictor_nn import training
from backend.plugins.predictor_nn.plugin import NNPredictor


def test_fixed_test_seed_rejected_as_training_seed(tmp_path: Path) -> None:
    for s in (data.FIXED_TEST_SEED, -1, True):
        with pytest.raises(ValueError):
            training.fit(s, n_train=50, epochs=1)
    with pytest.raises(ValueError):
        training.train_candidate(FileModelRegistry(tmp_path), seed=data.FIXED_TEST_SEED)
    assert FileModelRegistry(tmp_path).list_versions() == []


def test_train_and_test_samples_disjoint() -> None:
    x_test, _ = data.fixed_test_set()
    test_rows = {tuple(r) for r in x_test.tolist()}
    for seed in (0, 1, 2, data.FIXED_TEST_SEED + 1, data.FIXED_TEST_SEED - 1):
        x, _ = data.make_dataset(2000, seed)
        assert test_rows.isdisjoint({tuple(r) for r in x.tolist()})


def test_serving_rejects_inputs_outside_training_domain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dominio di addestramento: potenza [1, 20] W, distanza [500, 2000] km; margine 10% sui bordi (min*0.9, max*1.1)."""
    monkeypatch.setenv("MODEL_REGISTRY_DIR", str(tmp_path))
    reg = FileModelRegistry(tmp_path / "predictor_nn")
    v, m = training.train_candidate(reg, seed=3, n_train=1000, epochs=300)
    assert 1.0 <= m["train_power_w_min"] < 1.1 and 19.9 < m["train_power_w_max"] <= 20.0
    reg.promote(v, approver="alice", approved=True)
    p = NNPredictor(None)
    p.predict({"power_w": 10.0, "distance_km": 1000.0})
    p.predict({"power_w": 21.5, "distance_km": 2140.0})  # dentro il +10%
    for bad in (
        {"power_w": 25.0, "distance_km": 1000.0},
        {"power_w": 0.2, "distance_km": 1000.0},
        {"power_w": 10.0, "distance_km": 2300.0},
        {"power_w": 10.0, "distance_km": 300.0},
    ):
        with pytest.raises(PluginError, match="dominio di addestramento"):
            p.predict(bad)


def test_serving_fails_closed_without_domain_in_card(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MODEL_REGISTRY_DIR", str(tmp_path))
    reg = FileModelRegistry(tmp_path / "predictor_nn")
    net, y = training.fit(seed=4, n_train=300, epochs=20)
    x, _ = data.make_dataset(300, 4)
    v = reg.save(
        training.export_onnx(net),
        {
            "seed": 4,
            "dataset_sha256": data.sha256_of(x, y),
            "library_versions": {"numpy": "x"},
            "metrics": {training.SKILL_KEY: 0.9},
            "threshold": {training.SKILL_KEY: 0.25},
        },
    )
    reg.promote(v, approver="alice", approved=True)
    with pytest.raises(PluginError, match="dominio"):
        NNPredictor(None).predict({"power_w": 10.0, "distance_km": 1000.0})
