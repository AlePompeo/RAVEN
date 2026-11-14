# SPDX-License-Identifier: Apache-2.0
"""Step 1 (Task 19): porte di rete nel core, isolamento da socket/ssl, loopback in memoria."""

import asyncio
import subprocess
import sys
from pathlib import Path

import pytest

from backend.core.ports import Channel, Framer, ProtocolCodec, Transport

ROOT = Path(__file__).resolve().parents[3]


class FakeTransport:
    async def start(self) -> None: ...
    async def send(self, data, peer=None) -> None: ...
    async def receive(self):
        return None

    async def close(self) -> None: ...
    def stats(self):
        return {}


class FakeFramer:
    def feed(self, data):
        return []

    def encode(self, payload):
        return payload

    def reset(self) -> None: ...


class FakeCodec:
    def encode(self, message):
        return b""

    def decode(self, data):
        return None


class FakeChannel:
    def send(self, data, *, now_s): ...

    def deliver(self, now_s):
        return []

    def stats(self):
        return {}


def test_protocols_runtime_checkable():
    assert isinstance(FakeTransport(), Transport)
    assert isinstance(FakeFramer(), Framer)
    assert isinstance(FakeCodec(), ProtocolCodec)
    assert isinstance(FakeChannel(), Channel)
    assert not isinstance(object(), Transport)


def test_real_implementations_satisfy_ports():
    from backend.net.transport import LoopbackTransport

    assert isinstance(LoopbackTransport(), Transport)


async def test_loopback_pair_roundtrip_and_close():
    from backend.net.errors import TransportClosed
    from backend.net.transport import loopback_pair

    a, b = loopback_pair(max_message_bytes=16)
    await a.start()
    await b.start()
    await a.send(b"hello")
    got = await asyncio.wait_for(b.receive(), 1)
    assert got is not None
    peer, data = got
    assert data == b"hello"
    assert peer
    await a.close()
    assert await asyncio.wait_for(b.receive(), 1) is None  # peer chiuso -> None, niente hang
    with pytest.raises(TransportClosed):
        await a.send(b"x")


async def test_loopback_enforces_message_limit_and_counts():
    from backend.net.errors import LimitExceeded
    from backend.net.transport import loopback_pair

    a, _b = loopback_pair(max_message_bytes=4)
    with pytest.raises(LimitExceeded):
        await a.send(b"12345")
    assert a.stats()["oversize"] == 1


async def test_loopback_bounded_queue_drop_policy():
    from backend.net.transport import loopback_pair

    a, b = loopback_pair(max_message_bytes=8, queue_size=2, drop_policy="drop_oldest")
    for i in range(5):
        await a.send(bytes([i]))
    got = [(await b.receive())[1] for _ in range(2)]  # type: ignore[index]
    assert got == [b"\x03", b"\x04"]
    assert b.stats()["dropped"] == 3

    a, b = loopback_pair(max_message_bytes=8, queue_size=2, drop_policy="drop_newest")
    for i in range(5):
        await a.send(bytes([i]))
    got = [(await b.receive())[1] for _ in range(2)]  # type: ignore[index]
    assert got == [b"\x00", b"\x01"]
    assert b.stats()["dropped"] == 3


def test_core_has_no_network_imports_and_app_starts_without_net():
    """Il core non importa socket/ssl e la creazione dell'app non carica backend.net."""
    code = (
        "import sys\n"
        "from backend.bootstrap import build_app\n"
        "import backend.core.ports\n"
        "build_app()\n"
        "assert 'backend.net' not in sys.modules, 'backend.net caricato all avvio'\n"
        "import backend.core, pkgutil\n"
        "for m in pkgutil.iter_modules(backend.core.__path__):\n"
        "    src = open(backend.core.__path__[0] + '/' + m.name + '.py').read()\n"
        "    assert 'import socket' not in src and 'import ssl' not in src, m.name\n"
    )
    r = subprocess.run(
        [sys.executable, "-I", "-c", code],
        check=False,
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={"PYTHONPATH": str(ROOT), "PATH": "/usr/bin:/bin"},
    )
    assert r.returncode == 0, r.stderr


def test_no_listener_started_without_config(monkeypatch):
    """Senza NET_LISTENERS nessun listener: la configurazione vuota produce lista vuota."""
    from backend.net.config import load_listeners

    monkeypatch.delenv("NET_LISTENERS", raising=False)
    assert load_listeners() == []
