# SPDX-License-Identifier: Apache-2.0
"""The local model manager, against a fake llama-server (a tiny script that answers /health): installed check, memory guard, lazy start, reuse,
idle unload and stop. No real model is needed."""

import asyncio
import json
import os
import stat
from pathlib import Path

import pytest

from backend.assistant import local_llm as ll

FAKE = """#!/usr/bin/env python3
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
port = int(sys.argv[sys.argv.index("--port") + 1])
assert sys.argv[sys.argv.index("--host") + 1] == "127.0.0.1"
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"ok")
    def log_message(self, *a):
        pass
HTTPServer(("127.0.0.1", port), H).serve_forever()
"""


def _install(root: Path) -> None:
    (root / "llama").mkdir(parents=True)
    srv = root / "llama" / "llama-server"
    srv.write_text(FAKE)
    srv.chmod(srv.stat().st_mode | stat.S_IXUSR)
    (root / "model.gguf").write_bytes(b"x" * 1000)
    (root / "manifest.json").write_text(json.dumps({"name": "fake-model", "size": 1000}))


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(ll, "LLM_DIR", tmp_path)
    monkeypatch.setattr(ll, "MANAGER", ll.LocalLLM())
    return tmp_path


def test_not_installed_means_no_model_and_no_process(home: Path) -> None:
    assert not ll.installed()
    assert asyncio.run(ll.MANAGER.ensure()) is None
    st = ll.MANAGER.status()
    assert st["installed"] is False and st["running"] is False


def test_a_size_mismatch_is_not_installed(home: Path) -> None:
    _install(home)
    (home / "model.gguf").write_bytes(b"x" * 10)  # a truncated download
    assert not ll.installed()


def test_low_memory_refuses_to_start(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install(home)
    monkeypatch.setattr(ll, "free_mb", lambda: 500)
    assert asyncio.run(ll.MANAGER.ensure()) is None
    assert not ll.MANAGER.running() and ll.MANAGER.status()["enough_memory"] is False
    assert ll.MANAGER.error == "not_enough_memory"


def test_starts_lazily_on_loopback_reuses_the_process_and_stops(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install(home)
    monkeypatch.setattr(ll, "free_mb", lambda: 8000)

    async def go() -> tuple[tuple[str, str] | None, tuple[str, str] | None]:
        a = await ll.MANAGER.ensure()
        b = await ll.MANAGER.ensure()
        return a, b

    a, b = asyncio.run(go())
    try:
        assert a is not None and a == b  # one process, reused
        assert (
            a[0].startswith("http://127.0.0.1:") and a[0].endswith("/v1") and a[1] == "fake-model"
        )
        assert ll.MANAGER.running() and ll.MANAGER.status()["running"] is True
        pid = ll.MANAGER.proc.pid  # type: ignore[union-attr]
    finally:
        ll.MANAGER.stop()
    assert not ll.MANAGER.running()
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_an_idle_server_is_unloaded(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install(home)
    monkeypatch.setattr(ll, "free_mb", lambda: 8000)
    monkeypatch.setattr(ll, "IDLE_S", 0.4)

    async def go() -> bool:
        assert await ll.MANAGER.ensure() is not None
        for _ in range(60):
            await asyncio.sleep(0.1)
            if not ll.MANAGER.running():
                return True
        return False

    try:
        assert asyncio.run(go())
    finally:
        ll.MANAGER.stop()
