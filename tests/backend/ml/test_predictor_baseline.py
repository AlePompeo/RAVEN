# SPDX-License-Identifier: Apache-2.0
from pathlib import Path

import pytest

pytest.importorskip("numpy")
pytest.importorskip("sklearn")
pytest.importorskip("skl2onnx")
pytest.importorskip("onnxruntime")

from backend.core.errors import PluginError, PromotionRefused
from backend.core.ports import Predictor, Trainer
from backend.ml.registry import FileModelRegistry
from backend.plugins.predictor_baseline import data, training
from backend.plugins.predictor_baseline.plugin import BaselinePredictor
from backend.plugins.trainer_baseline.plugin import BaselineTrainer


@pytest.fixture(scope="module")
def trained(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str, dict[str, float]]:
    root = tmp_path_factory.mktemp("reg")
    reg = FileModelRegistry(root)
    version, metrics = training.train_candidate(reg, seed=1, n_train=2000)
    return root, version, metrics


def test_dataset_is_deterministic_and_documented() -> None:
    x1, y1 = data.make_dataset(100, seed=3)
    x2, y2 = data.make_dataset(100, seed=3)
    assert (x1 == x2).all() and (y1 == y2).all()
    assert x1.shape == (100, 2)
    assert data.FEATURES == ("power_w", "distance_km")
    assert data.TARGET == "link_margin_db"
    xt, _ = data.fixed_test_set()
    assert xt.shape[0] == data.N_TEST
    assert data.sha256_of(x1, y1) != data.sha256_of(*data.make_dataset(100, seed=4))


def test_test_set_is_disjoint_from_training_seeds() -> None:
    xt, _ = data.fixed_test_set()
    xr, _ = data.make_dataset(2000, seed=1)
    assert not (xt[:5] == xr[:5]).all()


def test_candidate_beats_baseline_by_declared_margin(trained) -> None:
    _, _, m = trained
    assert m["rmse_db"] < m["baseline_rmse_db"]
    assert m["skill_vs_baseline"] >= training.MIN_SKILL
    # il baseline e' il migliore tra media e regressione lineare
    assert m["baseline_rmse_db"] <= min(m["baseline_mean_rmse_db"], m["baseline_linear_rmse_db"])


def test_card_records_reproducibility_info(trained) -> None:
    root, v, _ = trained
    _, card = FileModelRegistry(root).load(v)
    assert card["seed"] == 1
    assert len(card["dataset_sha256"]) == 64
    for lib in ("numpy", "scikit-learn", "skl2onnx", "onnxruntime"):
        assert lib in card["library_versions"]
    assert card["threshold"]["skill_vs_baseline"] >= training.MIN_SKILL
    assert card["format"] == "onnx"


def test_training_is_reproducible(tmp_path: Path) -> None:
    r1 = FileModelRegistry(tmp_path / "a")
    r2 = FileModelRegistry(tmp_path / "b")
    _, m1 = training.train_candidate(r1, seed=5, n_train=500)
    _, m2 = training.train_candidate(r2, seed=5, n_train=500)
    assert m1 == m2
    assert r1.load("v0001")[1]["dataset_sha256"] == r2.load("v0001")[1]["dataset_sha256"]


def test_promoted_model_predicts(trained, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root, v, _ = trained
    reg = FileModelRegistry(tmp_path / "reg")
    blob, card = FileModelRegistry(root).load(v)
    reg.save(
        blob,
        {
            k: card[k]
            for k in ("seed", "dataset_sha256", "library_versions", "metrics", "threshold")
        },
    )
    reg.promote("v0001", approver="alice", approved=True)
    monkeypatch.setenv("MODEL_REGISTRY_DIR", str(tmp_path / "reg"))
    p = BaselinePredictor(None)  # type: ignore[arg-type]
    assert isinstance(p, Predictor)
    out = p.predict({"power_w": 10.0, "distance_km": 1000.0})
    truth = data.true_link_margin_db(10.0, 1000.0)
    assert abs(out["link_margin_db"] - truth) < 3.0
    assert p.model_info()["version"] == "v0001"


def test_predict_requires_promoted_model(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MODEL_REGISTRY_DIR", str(tmp_path / "empty"))
    p = BaselinePredictor(None)  # type: ignore[arg-type]
    with pytest.raises(PluginError):
        p.predict({"power_w": 10.0, "distance_km": 1000.0})


@pytest.mark.parametrize(
    "feat",
    [
        {"power_w": 10.0},
        {"power_w": float("nan"), "distance_km": 1000.0},
        {"power_w": -1.0, "distance_km": 1000.0},
        {"power_w": 10.0, "distance_km": float("inf")},
        {"power_w": 10.0, "distance_km": 0.0},
        {"power_w": "10", "distance_km": 1000.0},
    ],
)
def test_predict_rejects_invalid_features(feat, trained, monkeypatch: pytest.MonkeyPatch) -> None:
    root, _, _ = trained
    monkeypatch.setenv("MODEL_REGISTRY_DIR", str(root))
    with pytest.raises(ValueError):
        BaselinePredictor(None).predict(feat)  # type: ignore[arg-type]


def test_regression_is_blocked(tmp_path: Path) -> None:
    """Dopo la promozione di un buon modello, un candidato peggiore non passa il cancello."""
    reg = FileModelRegistry(tmp_path / "reg")
    good, m_good = training.train_candidate(reg, seed=1, n_train=2000)
    reg.promote(good, approver="alice", approved=True)
    bad, m_bad = training.train_candidate(reg, seed=2, n_train=40, n_estimators=2, max_depth=1)
    assert m_bad["skill_vs_baseline"] < m_good["skill_vs_baseline"]
    with pytest.raises(PromotionRefused):
        reg.promote(bad, approver="alice", approved=True)
    assert reg.promoted_version() == good


def test_weak_model_below_declared_margin_is_blocked(tmp_path: Path) -> None:
    reg = FileModelRegistry(tmp_path / "reg")
    v, m = training.train_candidate(reg, seed=2, n_train=20, n_estimators=1, max_depth=1)
    assert m["skill_vs_baseline"] < training.MIN_SKILL
    with pytest.raises(PromotionRefused):
        reg.promote(v, approver="alice", approved=True)


def test_trainer_saves_candidate_but_never_promotes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("MODEL_REGISTRY_DIR", str(tmp_path / "reg"))
    t = BaselineTrainer(None)  # type: ignore[arg-type]
    assert isinstance(t, Trainer)
    out = t.fit("", {"seed": 3, "n_train": 500})
    assert out["model_version"] == "v0001"
    assert out["metrics"]["skill_vs_baseline"] > 0
    reg = FileModelRegistry(tmp_path / "reg")
    assert reg.promoted_version() is None
    assert reg.load("v0001")[1]["status"] == "candidate"


@pytest.mark.parametrize(
    "cfg",
    [
        {"n_train": 10**9},
        {"n_train": 5},
        {"seed": "x"},
        {"n_estimators": 0},
        {"max_depth": 100},
        {"unknown": 1},
    ],
)
def test_trainer_validates_config(cfg, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MODEL_REGISTRY_DIR", str(tmp_path / "reg"))
    with pytest.raises(ValueError):
        BaselineTrainer(None).fit("", cfg)  # type: ignore[arg-type]


def test_bad_registry_env_maps_to_plugin_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("MODEL_REGISTRY_DIR", str(tmp_path / "bad-env"))
    monkeypatch.setenv("ML_MAX_CANDIDATES", "0")
    with pytest.raises(PluginError):
        BaselinePredictor(None).predict({"power_w": 10.0, "distance_km": 1000.0})  # type: ignore[arg-type]
    with pytest.raises(PluginError):
        BaselinePredictor(None).model_info()  # type: ignore[arg-type]


def test_registry_is_not_rebuilt_on_every_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("MODEL_REGISTRY_DIR", str(tmp_path / "once"))
    monkeypatch.delenv("ML_MAX_CANDIDATES", raising=False)
    built = 0
    real_init = FileModelRegistry.__init__

    def counting(self, *a, **k):  # type: ignore[no-untyped-def]
        nonlocal built
        built += 1
        real_init(self, *a, **k)

    monkeypatch.setattr(FileModelRegistry, "__init__", counting)
    for _ in range(5):
        with pytest.raises(PluginError):  # nessun modello promosso
            BaselinePredictor(None).predict({"power_w": 10.0, "distance_km": 1000.0})  # type: ignore[arg-type]
    assert built == 1


def test_predict_does_not_rehash_or_rebuild_session_per_call(
    trained, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from backend.ml import registry as regmod
    from backend.plugins.predictor_baseline import plugin as plug

    root, v, _ = trained
    reg = FileModelRegistry(tmp_path / "reg")
    blob, card = FileModelRegistry(root).load(v)
    keys = ("seed", "dataset_sha256", "library_versions", "metrics", "threshold")
    reg.save(blob, {k: card[k] for k in keys})
    reg.promote("v0001", approver="alice", approved=True)
    monkeypatch.setenv("MODEL_REGISTRY_DIR", str(tmp_path / "reg"))
    plug._cache.clear()
    hashes = sessions = 0
    real_hash, real_session = regmod._sha256_hex, training.make_session

    def count_hash(data: bytes) -> str:
        nonlocal hashes
        hashes += 1
        return real_hash(data)

    def count_session(b: bytes):  # type: ignore[no-untyped-def]
        nonlocal sessions
        sessions += 1
        return real_session(b)

    monkeypatch.setattr(regmod, "_sha256_hex", count_hash)
    monkeypatch.setattr(training, "make_session", count_session)
    p = BaselinePredictor(None)  # type: ignore[arg-type]
    for _ in range(6):
        p.predict({"power_w": 10.0, "distance_km": 1000.0})
        p.model_info()
    assert sessions == 1
    assert hashes <= 2  # una verifica al primo uso, poi nessuna
