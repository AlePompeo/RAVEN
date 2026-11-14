# SPDX-License-Identifier: Apache-2.0
"""MLP PyTorch -> ONNX -> onnxruntime. Tolleranza dichiarata ONNX vs PyTorch: 1e-4 dB (float32;
misurato ~4e-6). Saltato se gli extra [dl]/[ml] mancano."""

import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

pytest.importorskip("torch")
pytest.importorskip("onnx")
pytest.importorskip("onnxscript")
pytest.importorskip("onnxruntime")

import numpy as np

from backend.core.errors import InvalidMeasurement, PluginError, PromotionRefused
from backend.core.ports import Predictor
from backend.ml.registry import FileModelRegistry
from backend.plugins.predictor_baseline import data
from backend.plugins.predictor_nn import serving, training
from backend.plugins.predictor_nn.plugin import NNPredictor


@pytest.fixture(scope="module")
def trained(tmp_path_factory: pytest.TempPathFactory):
    root = tmp_path_factory.mktemp("reg")
    reg = FileModelRegistry(root)
    t0 = time.monotonic()
    v, m = training.train_candidate(reg, seed=1)
    return root, v, m, time.monotonic() - t0


def test_onnx_matches_torch_within_tolerance(trained) -> None:
    _, _, m, _ = trained
    assert m["onnx_vs_torch_max_abs_diff"] <= training.ONNX_TOLERANCE


def test_onnx_matches_torch_on_random_inputs_incl_out_of_range() -> None:
    net, _ = training.fit(seed=2, n_train=300, epochs=50)
    sess = serving.make_session(training.export_onnx(net))
    rng = np.random.default_rng(0)
    x = np.column_stack([rng.uniform(0.1, 50, 200), rng.uniform(100, 5000, 200)])
    diff = np.max(np.abs(serving.onnx_predict(sess, x) - training.torch_predict(net, x)))
    assert diff <= training.ONNX_TOLERANCE


def test_dynamic_batch_size() -> None:
    net, _ = training.fit(seed=2, n_train=200, epochs=10)
    sess = serving.make_session(training.export_onnx(net))
    x, _ = data.make_dataset(7, 1)
    assert serving.onnx_predict(sess, x).shape == (7,)
    assert serving.onnx_predict(sess, x[:1]).shape == (1,)


def test_beats_baseline_by_declared_margin_and_time_budget(trained) -> None:
    _, _, m, elapsed = trained
    assert m["skill_vs_baseline"] >= training.MIN_SKILL
    assert m["rmse_db"] < m["baseline_rmse_db"]
    assert elapsed < 60.0  # misurato qualche secondo su CPU


def test_training_deterministic() -> None:
    a, _ = training.fit(seed=5, n_train=200, epochs=20)
    b, _ = training.fit(seed=5, n_train=200, epochs=20)
    x, _ = data.make_dataset(20, 9)
    assert np.allclose(training.torch_predict(a, x), training.torch_predict(b, x), atol=1e-6)


def test_candidate_not_promoted_and_card(trained) -> None:
    root, v, _, _ = trained
    reg = FileModelRegistry(root)
    assert reg.promoted_version() is None
    card = reg.load(v)[1]
    assert card["status"] == "candidate" and "torch" in card["library_versions"]
    with pytest.raises(PromotionRefused):
        reg.promote(v, approver="alice", approved=False)


def test_serving_promoted_model_matches_torch(
    trained, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MODEL_REGISTRY_DIR", str(tmp_path))
    reg = FileModelRegistry(tmp_path / "predictor_nn")
    v, _ = training.train_candidate(reg, seed=3, n_train=1000, epochs=300)
    p = NNPredictor(None)
    assert isinstance(p, Predictor)
    with pytest.raises(PluginError):  # niente promosso: fail-closed
        p.predict({"power_w": 5.0, "distance_km": 1000.0})
    reg.promote(v, approver="alice", approved=True)
    out = p.predict({"power_w": 5.0, "distance_km": 1000.0})["link_margin_db"]
    truth = data.true_link_margin_db(5.0, 1000.0)
    assert abs(out - truth) < 2.0  # sanity: non lontano dal valore fisico (rumore 0.5 dB)
    assert p.model_info()["version"] == v
    with pytest.raises(InvalidMeasurement):
        p.predict({"power_w": float("nan"), "distance_km": 1000.0})
    with pytest.raises(InvalidMeasurement):
        p.predict({"power_w": 5.0})


def test_import_without_extras_degrades_gracefully(tmp_path: Path) -> None:
    """Con torch/onnxruntime/numpy/onnx bloccati: il plugin si importa, l'uso da' PluginError."""
    code = textwrap.dedent(
        f"""
        import sys
        for m in ("torch", "onnxruntime", "numpy", "onnx", "onnxscript"):
            sys.modules[m] = None
        import os
        os.environ["MODEL_REGISTRY_DIR"] = {str(tmp_path)!r}
        from backend.plugins.predictor_nn.plugin import NNPredictor
        from backend.core.errors import PluginError
        p = NNPredictor(None)
        try:
            p.predict({{"power_w": 5.0, "distance_km": 1000.0}})
        except PluginError:
            print("degraded-ok")
        try:
            import backend.plugins.predictor_nn.training
        except ImportError:
            print("training-needs-extra")
        """
    )
    r = subprocess.run(
        [sys.executable, "-c", code], check=False, capture_output=True, text=True, timeout=60
    )
    assert r.returncode == 0, r.stderr
    assert "degraded-ok" in r.stdout and "training-needs-extra" in r.stdout


def test_app_loads_plugins_without_extras() -> None:
    code = (
        "import sys\n"
        "for m in ('torch','onnxruntime','onnx','onnxscript','gymnasium','stable_baselines3'):\n"
        "    sys.modules[m] = None\n"
        "from pathlib import Path\n"
        "from backend.bootstrap import make_loader\n"
        "from backend.core.registry import Registry\n"
        "r = Registry(); print(r.discover(Path('backend/plugins'), make_loader()))\n"
        "r.create('model','predictor-nn'); r.create('environment','env-servo')\n"
    )
    r = subprocess.run(
        [sys.executable, "-c", code], check=False, capture_output=True, text=True, timeout=60
    )
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "[]"
