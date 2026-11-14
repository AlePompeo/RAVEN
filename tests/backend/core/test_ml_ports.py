# SPDX-License-Identifier: Apache-2.0
import subprocess
import sys
from pathlib import Path

import pytest

from backend.core.errors import PluginError
from backend.core.manifest import load_manifest
from backend.core.ports import ModelRegistry, Predictor, Trainer

ROOT = Path(__file__).resolve().parents[3]


class FakePredictor:
    def predict(self, features):
        return {"y": 1.0}

    def model_info(self):
        return {"version": "v0001"}


class FakeTrainer:
    def fit(self, dataset_ref, config):
        return {"metrics": {"r2": 0.9}}


class FakeRegistry:
    def save(self, model, card):
        return "v0001"

    def load(self, version):
        return b"", {}

    def list_versions(self):
        return []

    def promoted_version(self):
        return None

    def promote(self, version, *, approver, approved=False):
        return {}

    def rollback(self, *, approver):
        return "v0001"


def test_ml_protocols_are_structural():
    assert isinstance(FakePredictor(), Predictor)
    assert isinstance(FakeTrainer(), Trainer)
    assert isinstance(FakeRegistry(), ModelRegistry)
    assert not isinstance(object(), Predictor)


@pytest.mark.parametrize("kind", ["model", "trainer", "environment"])
def test_manifest_accepts_ml_kinds(tmp_path: Path, kind: str) -> None:
    (tmp_path / "manifest.toml").write_text(
        f'id="x"\nkind="{kind}"\nversion="0.1.0"\nentry="python:a.b:C"\nlicense="Apache-2.0"\n'
    )
    assert load_manifest(tmp_path / "manifest.toml").kind == kind


def test_manifest_still_rejects_unknown_kind(tmp_path: Path) -> None:
    (tmp_path / "manifest.toml").write_text(
        'id="x"\nkind="nope"\nversion="0.1.0"\nentry="python:a.b:C"\nlicense="MIT"\n'
    )
    with pytest.raises(PluginError):
        load_manifest(tmp_path / "manifest.toml")


BLOCKER = r"""
import importlib.abc, sys
sys.path.insert(0, sys.argv[1])
BLOCKED = {"torch", "sklearn", "gymnasium", "stable_baselines3", "pandas", "numpy", "scipy",
           "onnx", "onnxruntime", "skl2onnx", "joblib"}
class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in BLOCKED:
            raise ModuleNotFoundError("blocked: " + name)
sys.meta_path.insert(0, Blocker())
for m in list(sys.modules):
    if m.split(".")[0] in BLOCKED:
        del sys.modules[m]
"""


def run_blocked(code: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", "-c", BLOCKER + code, str(ROOT)],
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
        cwd=ROOT,
    )


def test_app_starts_without_ml_extras() -> None:
    code = """
from fastapi.testclient import TestClient
from backend.bootstrap import build_app
app = build_app()
kinds = {(m.kind, m.id) for m in app.state.registry.manifests()}
assert ("model", "predictor-baseline") in kinds, kinds
assert ("trainer", "trainer-baseline") in kinds, kinds
assert ("simulation", "example-sim") in kinds
r = TestClient(app).get("/health")
assert r.status_code == 200, r.status_code
print("ok")
"""
    r = run_blocked(code)
    assert r.returncode == 0, r.stderr[-2000:]
    assert "ok" in r.stdout


def test_core_tests_pass_without_ml_extras() -> None:
    code = """
import pytest
raise SystemExit(pytest.main(["-q", "-p", "no:cacheprovider", "tests/backend/core",
                              "--deselect", "tests/backend/core/test_ml_ports.py"]))
"""
    r = run_blocked(code)
    assert r.returncode == 0, (r.stdout + r.stderr)[-2000:]


def test_ml_plugin_modules_import_without_ml_libs() -> None:
    code = """
import importlib, sys
for name in ("backend.ml.registry", "backend.ml.runner", "backend.ml.worker",
             "backend.api.ml_routes", "backend.plugins.predictor_baseline.plugin",
             "backend.plugins.trainer_baseline.plugin"):
    importlib.import_module(name)
from backend.core.errors import PluginError
from backend.plugins.predictor_baseline.plugin import BaselinePredictor
try:
    BaselinePredictor(None).predict({"power_w": 1.0, "distance_km": 1000.0})
except PluginError:
    pass
else:
    raise SystemExit("atteso PluginError")
assert not any(m.split(".")[0] in ("numpy", "sklearn", "onnxruntime", "skl2onnx")
               for m in sys.modules)
print("ok")
"""
    r = run_blocked(code)
    assert r.returncode == 0, r.stderr[-2000:]
    assert "ok" in r.stdout


def test_core_does_not_import_ml_libraries() -> None:
    code = """
import importlib, pkgutil, backend.core
for mod in pkgutil.iter_modules(backend.core.__path__):
    importlib.import_module("backend.core." + mod.name)
print("ok")
"""
    r = run_blocked(code)
    assert r.returncode == 0, r.stderr[-2000:]
