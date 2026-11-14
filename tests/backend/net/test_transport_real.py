# SPDX-License-Identifier: Apache-2.0
"""Trasporti TCP/UDP su loopback reale con porte effimere (Task 19 step 2). Niente rete esterna."""

import asyncio
import socket
import struct

import pytest

from backend.core.ports import Transport
from backend.net.config import ListenerConfig
from backend.net.errors import LimitExceeded, TransportClosed
from backend.net.transport import (
    TcpClientTransport,
    TcpServerTransport,
    UdpTransport,
    start_listeners,
)

T = 3.0  # timeout di guardia dei test (mai attese reali lunghe)


def cfg(kind="tcp_server", **kw):
    base = {"name": "t", "kind": kind, "host": "127.0.0.1", "port": 0}
    base.update(kw)
    return ListenerConfig(**base)


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


async def raw_client(port):
    return await asyncio.open_connection("127.0.0.1", port)


def frame(payload: bytes, width=2) -> bytes:
    return len(payload).to_bytes(width, "big") + payload


async def eventually(pred, timeout=T):
    end = asyncio.get_running_loop().time() + timeout
    while not pred():
        if asyncio.get_running_loop().time() > end:
            raise AssertionError("condizione non raggiunta")
        await asyncio.sleep(0.01)


@pytest.fixture
async def tcp():
    made = []

    async def make(**kw):
        s = TcpServerTransport(cfg(**kw))
        await s.start()
        made.append(s)
        return s

    yield make
    for s in made:
        await s.close()


async def test_default_bind_is_loopback_and_port_ephemeral(tcp):
    s = await tcp()
    assert isinstance(s, Transport)
    assert s.bound_address[0] == "127.0.0.1"
    assert s.bound_address[1] > 0


async def test_tcp_connect_exchange_and_disconnect(tcp):
    s = await tcp()
    r, w = await raw_client(s.bound_address[1])
    w.write(frame(b"hello") + frame(b"world"))
    await w.drain()
    p1, d1 = await asyncio.wait_for(s.receive(), T)
    _, d2 = await asyncio.wait_for(s.receive(), T)
    assert (d1, d2) == (b"hello", b"world")
    await s.send(b"reply", peer=p1)
    assert await asyncio.wait_for(r.readexactly(7), T) == frame(b"reply")
    w.close()
    await eventually(lambda: s.stats()["disconnects"] == 1)
    st = s.stats()
    assert st["connections"] == 1 and st["received"] == 2 and st["sent"] == 1
    with pytest.raises(TransportClosed):
        await s.send(b"x", peer=p1)  # peer non piu' connesso


async def test_abrupt_reset_does_not_break_server(tcp):
    s = await tcp()
    sock = socket.create_connection(("127.0.0.1", s.bound_address[1]))
    sock.sendall(frame(b"par")[:2])  # frame a meta'
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
    sock.close()  # RST
    await eventually(lambda: s.stats()["disconnects"] == 1)
    # il server serve ancora
    _r, w = await raw_client(s.bound_address[1])
    w.write(frame(b"ok"))
    await w.drain()
    assert (await asyncio.wait_for(s.receive(), T))[1] == b"ok"
    w.close()


async def test_slow_client_closed_by_idle_timeout(tcp):
    s = await tcp(idle_timeout_s=0.2)
    r, w = await raw_client(s.bound_address[1])
    assert await asyncio.wait_for(r.read(10), T) == b""  # il server chiude: EOF pulito
    assert s.stats()["idle_timeouts"] == 1
    w.close()


async def test_slowloris_partial_frame_closed_by_message_timeout(tcp):
    s = await tcp(idle_timeout_s=5.0, message_timeout_s=0.3)
    _r, w = await raw_client(s.bound_address[1])
    w.write(b"\x00\x10")  # dichiara 16 byte
    await w.drain()

    async def trickle():
        try:
            for _ in range(100):
                w.write(b"a")
                await w.drain()
                await asyncio.sleep(0.05)  # mai inattivo abbastanza per l'idle timeout
        except (ConnectionError, OSError):
            pass

    t = asyncio.create_task(trickle())
    await eventually(lambda: s.stats()["message_timeouts"] == 1)
    t.cancel()
    assert s.stats()["idle_timeouts"] == 0
    w.close()


async def test_oversize_message_closes_cleanly_and_counts(tcp):
    s = await tcp(max_message_bytes=100)
    r, w = await raw_client(s.bound_address[1])
    w.write(b"\xff\xff")  # dichiara 65535 > 100: rifiutato prima di leggere/allocare
    await w.drain()
    assert await asyncio.wait_for(r.read(10), T) == b""
    assert s.stats()["oversize"] == 1 and s.stats()["received"] == 0
    # una connessione successiva funziona
    _r2, w2 = await raw_client(s.bound_address[1])
    w2.write(frame(b"x" * 100))  # esattamente al limite: ok
    await w2.drain()
    assert (await asyncio.wait_for(s.receive(), T))[1] == b"x" * 100
    w.close()
    w2.close()


async def test_max_connections_enforced(tcp):
    s = await tcp(max_connections=2)
    port = s.bound_address[1]
    c = [await raw_client(port) for _ in range(2)]
    await eventually(lambda: s.stats()["connections"] == 2)
    r3, w3 = await raw_client(port)
    assert await asyncio.wait_for(r3.read(10), T) == b""
    assert s.stats()["rejected_connections"] == 1
    c[0][1].close()
    await eventually(lambda: s.stats()["disconnects"] == 1)
    r4, w4 = await raw_client(port)  # lo slot liberato e' riutilizzabile
    w4.write(frame(b"hi"))
    await w4.drain()
    assert (await asyncio.wait_for(s.receive(), T))[1] == b"hi"
    for _, w in c[1:] + [(r3, w3), (r4, w4)]:
        w.close()


async def test_flood_above_rate_limit_is_dropped_and_counted():
    clock = FakeClock()
    s = TcpServerTransport(
        cfg(rate_msgs_per_s=1.0, rate_burst=5, rate_disconnect_after=10**6, queue_size=1000),
        clock=clock,
    )
    await s.start()
    try:
        _r, w = await raw_client(s.bound_address[1])
        w.write(b"".join(frame(bytes([i % 256])) for i in range(100)))
        await w.drain()
        await eventually(lambda: s.stats()["received"] + s.stats()["rate_limited"] == 100)
        st = s.stats()
        assert st["received"] == 5 and st["rate_limited"] == 95  # orologio fermo: solo il burst
        clock.t += 2.0  # 2 s virtuali = 2 token
        w.write(frame(b"a") * 4)
        await w.drain()
        await eventually(lambda: s.stats()["received"] + s.stats()["rate_limited"] == 104)
        assert s.stats()["received"] == 7
        w.close()
    finally:
        await s.close()


async def test_sustained_flood_disconnects_peer():
    s = TcpServerTransport(
        cfg(rate_msgs_per_s=1.0, rate_burst=1, rate_disconnect_after=20), clock=FakeClock()
    )
    await s.start()
    try:
        r, w = await raw_client(s.bound_address[1])
        w.write(b"".join(frame(b"z") for _ in range(200)))
        await w.drain()
        assert await asyncio.wait_for(r.read(10), T) == b""
        w.close()
    finally:
        await s.close()


async def test_bounded_queue_drops_with_policy_and_counter(tcp):
    s = await tcp(queue_size=3, drop_policy="drop_oldest", rate_msgs_per_s=1e6, rate_burst=10**6)
    _r, w = await raw_client(s.bound_address[1])
    w.write(b"".join(frame(bytes([i])) for i in range(10)))
    await w.drain()
    await eventually(lambda: s.stats()["received"] == 10)
    got = [(await asyncio.wait_for(s.receive(), T))[1] for _ in range(3)]
    assert got == [b"\x07", b"\x08", b"\x09"]
    assert s.stats()["dropped"] == 7
    w.close()


async def test_close_unblocks_receive_and_is_idempotent():
    s = TcpServerTransport(cfg())
    await s.start()
    r, w = await raw_client(s.bound_address[1])
    waiter = asyncio.create_task(s.receive())
    await asyncio.sleep(0.05)
    await s.close()
    assert await asyncio.wait_for(waiter, T) is None
    await s.close()
    assert await asyncio.wait_for(r.read(10), T) == b""
    w.close()


async def test_send_oversize_raises_limit_exceeded(tcp):
    s = await tcp(max_message_bytes=8)
    with pytest.raises(LimitExceeded):
        await s.send(b"x" * 9, peer="127.0.0.1:1")


async def test_tcp_client_to_server_roundtrip(tcp):
    s = await tcp()
    c = TcpClientTransport(cfg("tcp_client", port=s.bound_address[1]))
    await c.start()
    try:
        await c.send(b"ping")
        peer, data = await asyncio.wait_for(s.receive(), T)
        assert data == b"ping"
        await s.send(b"pong", peer=peer)
        assert (await asyncio.wait_for(c.receive(), T))[1] == b"pong"
    finally:
        await c.close()
    assert await asyncio.wait_for(c.receive(), T) is None
    with pytest.raises(TransportClosed):
        await c.send(b"x")


async def test_tcp_client_connection_refused_is_typed_error():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()  # porta chiusa
    c = TcpClientTransport(cfg("tcp_client", port=port))
    with pytest.raises(TransportClosed):
        await c.start()


# --- UDP ---


async def udp_sock_send(port, data):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.sendto(data, ("127.0.0.1", port))
    return s


async def test_udp_datagram_roundtrip_and_oversize_dropped():
    u = UdpTransport(cfg("udp", max_message_bytes=100))
    await u.start()
    try:
        port = u.bound_address[1]
        s = await udp_sock_send(port, b"a" * 101)  # oltre il limite
        s.sendto(b"b" * 100, ("127.0.0.1", port))
        peer, data = await asyncio.wait_for(u.receive(), T)
        assert data == b"b" * 100  # il datagramma oversize non e' stato consegnato
        assert u.stats()["oversize"] == 1 and u.stats()["received"] == 1
        await u.send(b"back", peer=peer)
        s.settimeout(T)
        assert s.recv(100) == b"back"
        with pytest.raises(LimitExceeded):
            await u.send(b"x" * 101, peer=peer)
        s.close()
    finally:
        await u.close()


async def test_udp_large_65k_datagram_rejected():
    u = UdpTransport(cfg("udp", max_message_bytes=512))
    await u.start()
    try:
        s = await udp_sock_send(u.bound_address[1], b"z" * 60000)
        await eventually(lambda: u.stats()["oversize"] == 1)
        assert u.stats()["received"] == 0
        s.close()
    finally:
        await u.close()


async def test_udp_rate_limit_per_peer_and_peer_table_bounded():
    clock = FakeClock()
    u = UdpTransport(cfg("udp", rate_msgs_per_s=1.0, rate_burst=3, max_peers=4), clock=clock)
    await u.start()
    try:
        s = await udp_sock_send(u.bound_address[1], b"0")
        for i in range(1, 20):
            s.sendto(bytes([i]), ("127.0.0.1", u.bound_address[1]))
        await eventually(lambda: u.stats()["received"] + u.stats()["rate_limited"] == 20)
        assert u.stats()["received"] == 3
        assert u.peer_table_size <= 4
        s.close()
    finally:
        await u.close()


async def test_udp_queue_overflow_counts_drops():
    u = UdpTransport(
        cfg("udp", queue_size=2, rate_msgs_per_s=1e6, rate_burst=10**6, drop_policy="drop_newest")
    )
    await u.start()
    try:
        s = await udp_sock_send(u.bound_address[1], b"0")
        for i in range(1, 6):
            s.sendto(bytes([i]), ("127.0.0.1", u.bound_address[1]))
        await eventually(lambda: u.stats()["received"] + u.stats()["dropped"] >= 6)
        assert (await u.receive())[1] == b"0"
        assert u.stats()["dropped"] == 4
        s.close()
    finally:
        await u.close()


async def test_udp_client_exchange_with_server():
    srv = UdpTransport(cfg("udp"))
    await srv.start()
    cli = UdpTransport(cfg("udp_client", port=srv.bound_address[1]))
    await cli.start()
    try:
        await cli.send(b"x1")
        peer, data = await asyncio.wait_for(srv.receive(), T)
        assert data == b"x1"
        await srv.send(b"y1", peer=peer)
        assert (await asyncio.wait_for(cli.receive(), T))[1] == b"y1"
        with pytest.raises(Exception, match="peer"):
            await srv.send(b"nopeer")  # il server UDP richiede un peer esplicito
    finally:
        await cli.close()
        await srv.close()
    assert await srv.receive() is None


def _free_udp_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


async def test_udp_multicast_explicit_group_and_interface():
    port = _free_udp_port()
    mc = {"port": port, "group": "239.255.42.99", "interface": "127.0.0.1"}
    a = UdpTransport(cfg("udp_multicast", **mc))
    b = UdpTransport(cfg("udp_multicast", **mc))
    try:
        await a.start()
        await b.start()
    except Exception as e:  # noqa: BLE001 - ambiente senza multicast su loopback
        await a.close()
        await b.close()
        pytest.skip(f"multicast non disponibile su questo host: {e!r}")
    try:
        await a.send(b"mcast")
        try:
            got = await asyncio.wait_for(b.receive(), 1.0)
        except TimeoutError:
            pytest.skip("multicast non consegnato su loopback in questo host (interfaccia lo)")
        assert got is not None and got[1] == b"mcast"
    finally:
        await a.close()
        await b.close()


async def test_start_listeners_none_configured_starts_nothing(monkeypatch):
    monkeypatch.delenv("NET_LISTENERS", raising=False)
    assert await start_listeners([]) == []


async def test_start_listeners_from_config_and_close():
    ts = await start_listeners([cfg("tcp_server", name="a"), cfg("udp", name="b")])
    try:
        assert len(ts) == 2
        assert all(isinstance(t, Transport) for t in ts)
    finally:
        for t in ts:
            await t.close()


def test_direct_config_object_cannot_bypass_public_bind_guard(monkeypatch):
    from backend.net.errors import NetConfigError

    monkeypatch.delenv("NET_ALLOW_PUBLIC_BIND", raising=False)
    with pytest.raises(NetConfigError):
        TcpServerTransport(cfg(host="0.0.0.0"))
    with pytest.raises(NetConfigError):
        UdpTransport(cfg("udp", host="0.0.0.0"))
    with pytest.raises(NetConfigError):
        UdpTransport(cfg("udp_multicast", port=5000, group="10.1.1.1", interface="127.0.0.1"))
