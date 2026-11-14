# SPDX-License-Identifier: Apache-2.0
"""Addestramento reale via API: subprocess + limite di memoria di default + registro su disco."""

import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("sklearn")
pytest.importorskip("skl2onnx")
pytest.importorskip("onnxruntime")

from backend.bootstrap import build_app
from backend.ml.registry import FileModelRegistry


def wait_done(c: TestClient, job_id: str) -> dict[str, Any]:
    end = time.monotonic() + 90
    while time.monotonic() < end:
        j = c.get(f"/api/jobs/{job_id}").json()
        if j["status"] in ("done", "failed", "cancelled"):
            return j  # type: ignore[no-any-return]
        time.sleep(0.1)
    raise AssertionError("timeout")


def test_real_trainer_creates_candidate_never_promoted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MODEL_REGISTRY_DIR", str(tmp_path / "reg"))
    with TestClient(build_app()) as c:
        r = c.post(
            "/api/train",
            json={"trainer": "trainer-baseline", "config": {"n_train": 400, "seed": 4}},
        )
        assert r.status_code == 202
        job = wait_done(c, r.json()["id"])
    assert job["status"] == "done", job
    assert job["model_version"] == "v0001"
    assert job["metrics"]["skill_vs_baseline"] > 0.25
    reg = FileModelRegistry(tmp_path / "reg")
    assert reg.promoted_version() is None
    assert reg.load("v0001")[1]["status"] == "candidate"


def test_real_trainer_bad_config_fails_generically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MODEL_REGISTRY_DIR", str(tmp_path / "reg"))
    with TestClient(build_app()) as c:
        r = c.post("/api/train", json={"trainer": "trainer-baseline", "config": {"n_train": 1}})
        job = wait_done(c, r.json()["id"])
        assert job["status"] == "failed" and job["error"] == "failed"
        assert "n_train" not in c.get(f"/api/jobs/{job['id']}").text
