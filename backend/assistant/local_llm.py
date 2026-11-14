# SPDX-License-Identifier: Apache-2.0
"""Local language model for RAVEN SI, run by llama.cpp as a separate process on the loopback interface only.

Nothing is downloaded here (the installer does it, only on request: `scripts/install_local_llm.py`, `./install.sh --with-llm`). The server starts on
the first request, is stopped after five idle minutes and at exit, and is never started when the free memory is below the minimum, so the web app
keeps working (rules only) on a small machine. The model is a Western, permissively licensed one (see docs/design/site-discovery-plan.md).
"""

from __future__ import annotations

import asyncio
import atexit
import json
import os
import socket
import subprocess
import time
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any, Final

import httpx

LLM_DIR: Final = Path(
    os.environ.get("RAVEN_LLM_DIR") or Path(__file__).resolve().parents[2] / "build" / "llm"
)
DEFAULT_MIN_FREE_MB: Final = 4096
IDLE_S: Final = float(os.environ.get("RAVEN_LLM_IDLE_S", "300"))
START_TIMEOUT_S: Final = 120.0
CONTEXT: Final = 5120  # tokens: the assistant prompt (about 2.5k) plus the answer (up to 1k); bounds the key-value cache


LOCAL_ID: Final = "raven-local"  # provider id of the bundled model in the assistant's candidates
LOCAL_TIMEOUT_S: Final = (
    120.0  # a 3B model on a few cores needs tens of seconds for a grounded answer
)


class LocalUnavailable(Exception):
    """The bundled model could not be started (not installed, memory too low, failed start); the assistant falls back to the next candidate."""

    code = "unavailable"


def server_path() -> Path:
    return LLM_DIR / "llama" / "llama-server"


def model_path() -> Path:
    return LLM_DIR / "model.gguf"


def manifest() -> dict[str, Any]:
    """What the installer wrote (model name, sha256, size); {} when nothing is installed."""
    try:
        data = json.loads((LLM_DIR / "manifest.json").read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def installed() -> bool:
    m = manifest()
    return (
        server_path().is_file()
        and os.access(server_path(), os.X_OK)
        and model_path().is_file()
        and model_path().stat().st_size == m.get("size")
    )


def min_free_mb() -> int:
    """Free memory required before the server starts: the installer writes it with the model (RAVEN_LLM_MIN_FREE_MB overrides it)."""
    env = os.environ.get("RAVEN_LLM_MIN_FREE_MB")
    if env and env.isdigit():
        return int(env)
    v = manifest().get("min_free_mb")
    return v if isinstance(v, int) and v > 0 else DEFAULT_MIN_FREE_MB


def free_mb() -> int | None:
    """MemAvailable of the machine in MB; None where it cannot be read."""
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) // 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class LocalLLM:
    def __init__(self) -> None:
        self.proc: subprocess.Popen[bytes] | None = None
        self.port = 0
        self.last_used = 0.0
        self.lock = asyncio.Lock()
        self.reaper: asyncio.Task[None] | None = None
        self.error: str | None = None

    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def status(self) -> dict[str, Any]:
        free = free_mb()
        m = manifest()
        return {
            "installed": installed(),
            "running": self.running(),
            "model": m.get("name"),
            "free_mb": free,
            "min_free_mb": min_free_mb(),
            "enough_memory": free is None or free >= min_free_mb(),
            "idle_unload_s": IDLE_S,
            "last_error": self.error,
        }

    def stop(self) -> None:
        p, self.proc = self.proc, None
        if p is not None and p.poll() is None:
            p.terminate()
            try:
                p.wait(10)
            except subprocess.TimeoutExpired:
                p.kill()

    async def _reap(self) -> None:
        while self.running():
            await asyncio.sleep(min(15.0, max(0.05, IDLE_S / 4)))
            if time.monotonic() - self.last_used > IDLE_S and not self.lock.locked():
                self.stop()

    async def _healthy(self) -> bool:
        try:
            async with httpx.AsyncClient(trust_env=False, timeout=2.0) as c:
                return (await c.get(f"http://127.0.0.1:{self.port}/health")).status_code == 200
        except httpx.HTTPError:
            return False

    def _spawn(self) -> subprocess.Popen[bytes]:
        LLM_DIR.mkdir(parents=True, exist_ok=True)
        threads = max(1, min(os.cpu_count() or 4, 8))
        with (LLM_DIR / "server.log").open("wb") as log:
            return subprocess.Popen(
                [
                    str(server_path()),
                    "-m",
                    str(model_path()),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(self.port),
                    "-c",
                    str(CONTEXT),
                    "-t",
                    str(threads),
                    "--parallel",
                    "1",
                    "--no-webui",
                ],
                stdout=subprocess.DEVNULL,
                stderr=log,
                cwd=str(server_path().parent),
            )

    async def ensure(self) -> tuple[str, str] | None:
        """(base /v1 URL, model name) of the running server, starting it if needed; None when it is not installed or the memory is too low."""
        if not installed():
            return None
        async with self.lock:
            if not self.running():
                free = free_mb()
                if free is not None and free < min_free_mb():
                    self.error = "not_enough_memory"
                    return None
                self.port = _free_port()
                self.proc = await asyncio.to_thread(self._spawn)
                t0 = time.monotonic()
                while not await self._healthy():
                    if not self.running() or time.monotonic() - t0 > START_TIMEOUT_S:
                        self.error = "start_failed"
                        self.stop()
                        return None
                    await asyncio.sleep(0.5)
                self.error = None
            self.last_used = time.monotonic()
            if self.reaper is None or self.reaper.done():
                self.reaper = asyncio.create_task(self._reap())
        return f"http://127.0.0.1:{self.port}/v1", str(manifest().get("name") or "local")

    def touch(self) -> None:
        self.last_used = time.monotonic()


MANAGER: Final = LocalLLM()


def usable() -> bool:
    """Installed, and either already running or with enough free memory to start: only then it is offered as a candidate."""
    if not installed():
        return False
    if MANAGER.running():
        return True
    free = free_mb()
    return free is None or free >= min_free_mb()


class LazyProvider:
    """Provider of the assistant for the bundled model: starts the server on the first use, then delegates to an OpenAI-compatible provider
    that `make(base_url, model)` builds (injected so this module does not depend on the plugin layer)."""

    def __init__(self, make: Callable[[str, str], Any]) -> None:
        self._make = make

    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        ep = await MANAGER.ensure()
        if ep is None:
            raise LocalUnavailable
        async for piece in self._make(*ep).stream(messages):
            MANAGER.touch()
            yield piece


atexit.register(MANAGER.stop)
