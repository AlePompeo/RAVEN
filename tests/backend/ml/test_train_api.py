# SPDX-License-Identifier: Apache-2.0
import sys
import textwrap
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.adapters.cache_memory import MemoryCache
from backend.api.app import create_app
from backend.core.registry import Registry
from backend.ml.runner import TrainerCommand, TrainerRunner

OK = """
import json, sys
spec = json.load(sys.stdin)
print(json.dumps({"metrics": {"echo": float(spec["config"].get("v", 1))}}))
"""
HANG = "import time\ntime.sleep(600)\n"
BOOM = "raise RuntimeError('hunter2 /srv/secret')\n"
NAN = 'print(\'{"metrics": {"x": NaN}}\')\n'


def build(tmp_path: Path, **kw: Any) -> TestClient:
    cmds: dict[str, TrainerCommand] = {}
    for name, body in {"ok": OK, "hang": HANG, "boom": BOOM, "nan": NAN}.items():
        p = tmp_path / f"{name}.py"
        p.write_text(textwrap.dedent(body))
        cmds[name] = TrainerCommand((sys.executable, "-I", str(p)), timeout_s=20)
    app = create_app(Registry(), MemoryCache())
    app.state.trainer_runner = TrainerRunner(cmds.get, **kw)
    return TestClient(app)


def poll(c: TestClient, job_id: str, want: str = "done", timeout: float = 20.0) -> dict[str, Any]:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        r = c.get(f"/api/jobs/{job_id}")
        assert r.status_code == 200
        if r.json()["status"] == want or r.json()["status"] in ("done", "failed", "cancelled"):
            return r.json()  # type: ignore[no-any-return]
        time.sleep(0.05)
    raise AssertionError("timeout")


def test_train_and_poll(tmp_path: Path) -> None:
    with build(tmp_path) as c:
        r = c.post("/api/train", json={"trainer": "ok", "config": {"v": 2.5}})
        assert r.status_code == 202
        body = r.json()
        assert body["status"] in ("queued", "running")
        assert len(body["id"]) == 32 and body["schema_version"] == "1.0.0"
        assert "config" not in body
        done = poll(c, body["id"])
        assert done["status"] == "done" and done["metrics"] == {"echo": 2.5}


def test_unknown_trainer_404_and_malformed_422(tmp_path: Path) -> None:
    with build(tmp_path) as c:
        assert c.post("/api/train", json={"trainer": "nope"}).status_code == 404
        for bad in ("../x", "A", "", "x" * 65, "a b"):
            assert c.post("/api/train", json={"trainer": bad}).status_code == 422


@pytest.mark.parametrize(
    "config",
    [
        {f"k{i}": 1 for i in range(33)},
        {"a": {"nested": 1}},
        {"a": [1, 2]},
        {"a": "x" * 257},
        {"Bad-Key": 1},
        {"a": None},
    ],
)
def test_config_caps(tmp_path: Path, config: dict[str, Any]) -> None:
    with build(tmp_path) as c:
        assert c.post("/api/train", json={"trainer": "ok", "config": config}).status_code == 422


def test_nan_in_body_rejected(tmp_path: Path) -> None:
    with build(tmp_path) as c:
        r = c.post(
            "/api/train",
            content=b'{"trainer": "ok", "config": {"v": NaN}}',
            headers={"content-type": "application/json"},
        )
        assert r.status_code == 422


def test_extra_body_fields_rejected(tmp_path: Path) -> None:
    with build(tmp_path) as c:
        r = c.post("/api/train", json={"trainer": "ok", "argv": ["rm"]})
        assert r.status_code == 422


@pytest.mark.parametrize(
    "bad", ["zz", "0" * 32, "../etc/passwd", "%2e%2e", "A" * 32, "0" * 33, "0" * 31]
)
def test_invalid_or_unknown_job_ids_404(tmp_path: Path, bad: str) -> None:
    with build(tmp_path) as c:
        assert c.get(f"/api/jobs/{bad}").status_code == 404
        assert c.post(f"/api/jobs/{bad}/cancel").status_code == 404


def test_failure_has_no_internals(tmp_path: Path) -> None:
    with build(tmp_path) as c:
        job = c.post("/api/train", json={"trainer": "boom"}).json()
        done = poll(c, job["id"])
        assert done["status"] == "failed" and done["error"] == "failed"
        text = c.get(f"/api/jobs/{job['id']}").text
        assert "hunter2" not in text and "Traceback" not in text and "/srv" not in text


def test_nonfinite_metrics_rejected(tmp_path: Path) -> None:
    with build(tmp_path) as c:
        job = c.post("/api/train", json={"trainer": "nan"}).json()
        done = poll(c, job["id"])
        assert done["status"] == "failed" and done["error"] == "invalid_output"
        assert done["metrics"] is None


def test_too_many_jobs_429(tmp_path: Path) -> None:
    with build(tmp_path, max_concurrent=1, max_active=2) as c:
        ids = [c.post("/api/train", json={"trainer": "hang"}).json()["id"] for _ in range(2)]
        r = c.post("/api/train", json={"trainer": "hang"})
        assert r.status_code == 429 and r.headers["retry-after"] == "5"
        assert "hang" not in r.text
        for i in ids:
            c.post(f"/api/jobs/{i}/cancel")
        assert c.post("/api/train", json={"trainer": "ok"}).status_code == 202


def test_per_ip_hourly_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ML_TRAIN_PER_HOUR", "2")
    monkeypatch.delenv("TRUSTED_PROXY", raising=False)
    with build(tmp_path, max_active=10) as c:
        for _ in range(2):
            assert c.post("/api/train", json={"trainer": "ok"}).status_code == 202
        r = c.post("/api/train", json={"trainer": "ok"}, headers={"X-Forwarded-For": "9.9.9.9"})
        assert r.status_code == 429 and int(r.headers["retry-after"]) > 0
        assert c.get("/health").status_code == 200  # solo POST /api/train e' contato


def test_per_ip_limit_honours_trusted_proxy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ML_TRAIN_PER_HOUR", "1")
    monkeypatch.setenv("TRUSTED_PROXY", "1")
    with build(tmp_path, max_active=10) as c:
        h1, h2 = {"X-Forwarded-For": "1.1.1.1"}, {"X-Forwarded-For": "2.2.2.2"}
        assert c.post("/api/train", json={"trainer": "ok"}, headers=h1).status_code == 202
        assert c.post("/api/train", json={"trainer": "ok"}, headers=h1).status_code == 429
        assert c.post("/api/train", json={"trainer": "ok"}, headers=h2).status_code == 202


@pytest.mark.parametrize("bad", ["0", "-3", "abc"])
def test_per_ip_limit_env_validated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad: str
) -> None:
    from backend.api.app import ConfigError

    monkeypatch.setenv("ML_TRAIN_PER_HOUR", bad)
    with pytest.raises(ConfigError):
        build(tmp_path)


def test_default_per_ip_limit_is_20(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ML_TRAIN_PER_HOUR", raising=False)
    c = build(tmp_path)
    assert c.app.state.train_limiter._limit == 20  # type: ignore[attr-defined]


def test_no_promote_route_under_api(tmp_path: Path) -> None:
    c = build(tmp_path)
    paths = list(c.app.openapi()["paths"])  # type: ignore[attr-defined]
    assert any(p.startswith("/api/train") for p in paths)
    assert not [p for p in paths if p.startswith("/api") and "promot" in p.lower()]
    assert not [p for p in paths if p.startswith("/api") and "rollback" in p.lower()]


def test_cancel_running_job_kills_process(tmp_path: Path) -> None:
    with build(tmp_path) as c:
        job = c.post("/api/train", json={"trainer": "hang"}).json()
        end = time.monotonic() + 20
        while c.get(f"/api/jobs/{job['id']}").json()["status"] != "running":
            assert time.monotonic() < end
            time.sleep(0.02)
        runner = c.app.state.trainer_runner  # type: ignore[attr-defined]
        while not runner._procs:  # "running" precede di poco la creazione del processo
            assert time.monotonic() < end
            time.sleep(0.01)
        assert len(runner._procs) == 1
        proc = next(iter(runner._procs.values()))
        r = c.post(f"/api/jobs/{job['id']}/cancel")
        assert r.json()["status"] == "cancelled"
        assert proc.returncode is not None and not runner._procs  # processo ucciso e reaped


def test_cancel_queued_job_via_api(tmp_path: Path) -> None:
    with build(tmp_path, max_concurrent=1, max_active=4) as c:
        first = c.post("/api/train", json={"trainer": "hang"}).json()
        second = c.post("/api/train", json={"trainer": "hang"}).json()
        r = c.post(f"/api/jobs/{second['id']}/cancel").json()
        assert r["status"] == "cancelled" and r["started_utc"] is None
        c.post(f"/api/jobs/{first['id']}/cancel")


def test_history_bounded_via_api(tmp_path: Path) -> None:
    with build(tmp_path, max_history=2, max_active=10) as c:
        ids = []
        for _ in range(4):
            j = c.post("/api/train", json={"trainer": "ok"}).json()
            poll(c, j["id"])
            ids.append(j["id"])
        assert c.get(f"/api/jobs/{ids[0]}").status_code == 404
        assert c.get(f"/api/jobs/{ids[-1]}").status_code == 200


def test_default_app_lists_trainer_plugin_but_unknown_runs_404() -> None:
    from backend.bootstrap import build_app

    with TestClient(build_app()) as c:
        assert c.post("/api/train", json={"trainer": "does-not-exist"}).status_code == 404
