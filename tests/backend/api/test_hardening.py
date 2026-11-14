# SPDX-License-Identifier: Apache-2.0
import asyncio
import importlib
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.api.routes import TelemetryHub, csv_replay
from backend.api.security import RateLimitMiddleware
from backend.bootstrap import build_app


async def _noop(scope: Any, receive: Any, send: Any) -> None:
    return None


def test_rate_limit_eviction_does_not_reset_everyone() -> None:
    t = [0.0]
    mw = RateLimitMiddleware(_noop, limit=1, max_tracked=3, clock=lambda: t[0])
    assert mw._allow("victim")[0] is True
    assert mw._allow("victim")[0] is False
    for i in range(10):  # un attore inonda di chiavi nuove
        mw._allow(f"flood{i}")
    assert len(mw._hits) <= 3


def test_rate_limit_evicts_oldest_first() -> None:
    mw = RateLimitMiddleware(_noop, limit=1, max_tracked=2)
    mw._allow("a")
    mw._allow("b")
    mw._allow("c")
    assert "a" not in mw._hits and "c" in mw._hits


def test_forwarded_for_ignored_by_default(monkeypatch: Any) -> None:
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "2")
    c = TestClient(build_app())
    codes = [
        c.get("/api/plugins", headers={"X-Forwarded-For": f"1.1.1.{i}"}).status_code
        for i in range(3)
    ]
    assert codes == [200, 200, 429]


def test_forwarded_for_used_when_trusted(monkeypatch: Any) -> None:
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "1")
    monkeypatch.setenv("TRUSTED_PROXY", "1")
    c = TestClient(build_app())
    a = {"X-Forwarded-For": "1.1.1.1, 9.9.9.9"}
    assert c.get("/api/plugins", headers=a).status_code == 200
    assert c.get("/api/plugins", headers=a).status_code == 429
    assert c.get("/api/plugins", headers={"X-Forwarded-For": "2.2.2.2"}).status_code == 200


def test_options_preflight_not_counted(monkeypatch: Any) -> None:
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "1")
    c = TestClient(build_app())
    for _ in range(5):
        c.options("/api/plugins")
    assert c.get("/api/plugins").status_code == 200


def test_sse_503_when_subscribers_capped(monkeypatch: Any) -> None:
    monkeypatch.setenv("TELEMETRY_MAX_SUBSCRIBERS", "1")
    app = build_app()
    app.state.hub.subscribe()  # occupa l'unico slot
    r = TestClient(app).get("/api/telemetry/stream")
    assert r.status_code == 503


def test_hub_capacity() -> None:
    hub = TelemetryHub(max_subscribers=1)
    q = hub.subscribe()
    assert hub.at_capacity
    hub.unsubscribe(q)
    assert not hub.at_capacity


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("RATE_LIMIT_PER_MIN", "abc"),
        ("RATE_LIMIT_PER_MIN", "0"),
        ("RATE_LIMIT_PER_MIN", "-5"),
        ("TELEMETRY_MAX_SUBSCRIBERS", "0"),
        ("MAX_BODY_BYTES", "x"),
        ("CHAT_MAX_STREAM_SECONDS", "0"),
    ],
)
def test_bad_env_gives_clear_startup_error(monkeypatch: Any, name: str, value: str) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(SystemExit) as ei:
        build_app()
    assert name in str(ei.value)


def test_plugin_errors_do_not_leak_paths_or_messages(tmp_path: Path, monkeypatch: Any) -> None:
    import backend.bootstrap as b

    bad = tmp_path / "broken"
    bad.mkdir()
    (bad / "manifest.toml").write_text("SECRET_MARKER = = =")
    monkeypatch.setattr(b, "PLUGINS_DIR", tmp_path)
    body = TestClient(b.build_app()).get("/api/plugins").json()
    assert body["errors"] == [{"plugin": "broken", "error": "ManifestError"}]
    assert str(tmp_path) not in str(body) and "SECRET_MARKER" not in str(body)


def test_body_too_large_by_content_length(monkeypatch: Any) -> None:
    monkeypatch.setenv("MAX_BODY_BYTES", "100")
    c = TestClient(build_app())
    r = c.post("/api/simulations/example-sim/run", json={"inputs": {"x": 1.0}, "pad": "a" * 500})
    assert r.status_code == 413


def test_body_too_large_when_streamed(monkeypatch: Any) -> None:
    monkeypatch.setenv("MAX_BODY_BYTES", "100")
    c = TestClient(build_app())

    def chunks() -> Any:
        for _ in range(10):
            yield b'{"inputs": {},' + b" " * 40

    r = c.post(
        "/api/simulations/example-sim/run",
        content=chunks(),
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 413


def test_input_key_length_bounded() -> None:
    c = TestClient(build_app())
    r = c.post("/api/simulations/example-sim/run", json={"inputs": {"k" * 65: 1.0}})
    assert r.status_code == 422


def test_missing_csv_is_logged_not_fatal(monkeypatch: Any, caplog: Any) -> None:
    monkeypatch.setenv("TELEMETRY_CSV", "/nonexistent/x.csv")
    with caplog.at_level("ERROR"), TestClient(build_app()) as c:
        assert c.get("/health").status_code == 200
    assert "TELEMETRY_CSV" in caplog.text


async def test_header_only_csv_loop_does_not_spin(tmp_path: Path) -> None:
    f = tmp_path / "h.csv"
    f.write_text("power_w\n")
    hub = TelemetryHub()
    task = asyncio.create_task(csv_replay(hub, f, interval_s=0, loop=True))
    await asyncio.sleep(0.3)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    # se girasse a vuoto il test non avrebbe ceduto il controllo: arrivare qui basta


def test_no_module_level_app() -> None:
    mod = importlib.import_module("backend.bootstrap")
    assert not hasattr(mod, "app")
