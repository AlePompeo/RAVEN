# SPDX-License-Identifier: Apache-2.0
"""Fix round 1 (revisione di sicurezza): limite per IP, timer di frame con rumore, rate limiter
non resettabile da evizione/spoofing, guardia multicast, framer personalizzati difettosi."""

import asyncio
import socket

import pytest

from backend.net.config import ListenerConfig, parse_listeners
from backend.net.errors import NetConfigError
from backend.net.framing import DelimiterFramer, KissFramer, SlipFramer
from backend.net.transport import (
    PeerLimiter,
    TcpServerTransport,
    UdpTransport,
    normalize_peer_key,
)

T = 3.0


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def cfg(kind="tcp_server", **kw):
    base = {"name": "t", "kind": kind, "host": "127.0.0.1", "port": 0}
    base.update(kw)
    return ListenerConfig(**base)


async def eventually(pred, timeout=T):
    end = asyncio.get_running_loop().time() + timeout
    while not pred():
        if asyncio.get_running_loop().time() > end:
            raise AssertionError("condizione non raggiunta")
        await asyncio.sleep(0.01)


# --- (4) rate limiter ---


def test_normalize_peer_key_ipv6_per_64_and_mapped_ipv4():
    assert normalize_peer_key("192.0.2.7") == "192.0.2.7"
    a = normalize_peer_key("2001:db8:1:2:aaaa:bbbb:cccc:dddd")
    b = normalize_peer_key("2001:db8:1:2:1111:2222:3333:4444")
    assert a == b == "2001:db8:1:2::/64"
    assert normalize_peer_key("2001:db8:1:3::1") != a
    assert normalize_peer_key("::ffff:192.0.2.7") == "192.0.2.7"
    assert normalize_peer_key("not-an-ip") == "not-an-ip"


def test_spoofed_ipv6_in_one_64_share_one_bucket():
    clock = FakeClock()
    lim = PeerLimiter(1.0, 3, 100, clock, global_rate=1e9, global_burst=10**9)
    allowed = sum(lim.allow(f"2001:db8::{i:x}:1") for i in range(500))
    assert allowed == 3
    assert len(lim) == 1


def test_table_full_unknown_peers_share_overflow_bucket_and_known_not_reset():
    clock = FakeClock()
    lim = PeerLimiter(1.0, 2, 3, clock, global_rate=1e9, global_burst=10**9)
    for ip in ("10.0.0.1", "10.0.0.2", "10.0.0.3"):  # riempiono la tabella e consumano il burst
        assert lim.allow(ip) and lim.allow(ip)
        assert not lim.allow(ip)
    # 1000 sorgenti nuove (spoofing): solo il bucket condiviso di overflow, non un burst ciascuna
    passed = sum(lim.allow(f"172.16.{i // 250}.{i % 250}") for i in range(1000))
    assert passed <= 2
    assert len(lim) == 3
    assert lim.overflow_hits >= 998
    # i peer noti NON sono stati evitti ne' resettati dall'attacco
    assert not lim.allow("10.0.0.1")


def test_lossless_eviction_after_bucket_would_be_full():
    clock = FakeClock()
    lim = PeerLimiter(1.0, 2, 2, clock, global_rate=1e9, global_burst=10**9)
    assert lim.allow("10.0.0.1") and lim.allow("10.0.0.2")
    clock.t += 5.0  # i bucket si sono riempiti: evictarli non perde informazione
    assert lim.allow("10.0.0.3") and lim.allow("10.0.0.3")
    assert not lim.allow("10.0.0.3")
    assert lim.overflow_hits == 0
    assert len(lim) == 2


def test_global_rate_cap_across_many_peers():
    clock = FakeClock()
    lim = PeerLimiter(100.0, 100, 1000, clock, global_rate=1.0, global_burst=5)
    passed = sum(lim.allow(f"10.1.{i // 250}.{i % 250}") for i in range(200))
    assert passed == 5
    clock.t += 3.0
    assert sum(lim.allow(f"10.2.0.{i}") for i in range(50)) == 3


async def test_udp_many_sources_bounded_by_peer_table_and_global_cap():
    clock = FakeClock()
    u = UdpTransport(
        cfg(
            "udp",
            max_peers=2,
            rate_burst=1,
            rate_msgs_per_s=1.0,
            global_rate_msgs_per_s=1000.0,
            global_rate_burst=1000,
        ),
        clock=clock,
    )
    await u.start()
    try:
        socks = []
        for i in range(2, 22):  # 20 indirizzi sorgente distinti 127.0.0.2 .. 127.0.0.21
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.bind((f"127.0.0.{i}", 0))
            s.sendto(b"x", ("127.0.0.1", u.bound_address[1]))
            socks.append(s)
        await eventually(lambda: u.stats()["received"] + u.stats()["rate_limited"] == 20)
        # 2 peer in tabella (1 messaggio ciascuno) + al piu' 1 dal bucket condiviso di overflow
        assert u.stats()["received"] <= 3
        assert u.peer_table_size <= 2
        assert u.stats()["peer_table_overflow"] >= 17
        for s in socks:
            s.close()
    finally:
        await u.close()


# --- (2) limite di connessioni per IP ---


async def test_one_ip_cannot_starve_another():
    s = TcpServerTransport(cfg(max_connections=4, max_connections_per_ip=2, idle_timeout_s=30.0))
    await s.start()
    port = s.bound_address[1]
    opened = []
    try:
        a = [await asyncio.open_connection("127.0.0.1", port) for _ in range(2)]
        opened += a
        await eventually(lambda: s.stats()["connections"] == 2)
        r3, w3 = await asyncio.open_connection("127.0.0.1", port)  # 3a dallo stesso IP
        opened.append((r3, w3))
        assert await asyncio.wait_for(r3.read(10), T) == b""
        assert s.stats()["rejected_per_ip"] == 1
        # un altro IP (127.0.0.2) trova ancora posto
        b = await asyncio.open_connection("127.0.0.1", port, local_addr=("127.0.0.2", 0))
        opened.append(b)
        await eventually(lambda: s.stats()["connections"] == 3)
        b2 = await asyncio.open_connection("127.0.0.1", port, local_addr=("127.0.0.3", 0))
        opened.append(b2)
        await eventually(lambda: s.stats()["connections"] == 4)
        assert s.stats()["rejected_connections"] == 0
        # liberato uno slot dell'IP A, A puo' riconnettersi
        a[0][1].close()
        await eventually(lambda: s.stats()["disconnects"] >= 1)
        again = await asyncio.open_connection("127.0.0.1", port)
        opened.append(again)
        await eventually(lambda: s.stats()["connections"] == 5)
    finally:
        for _, w in opened:
            w.close()
        await s.close()


def test_config_per_ip_default_small_and_validated():
    [c] = parse_listeners(
        [{"name": "x", "kind": "tcp_server", "host": "127.0.0.1", "port": 0}], allow_public=False
    )
    assert c.max_connections_per_ip == 2
    for bad in (0, -1, 1.5, "2"):
        with pytest.raises(NetConfigError):
            parse_listeners(
                [{"name": "x", "kind": "tcp_server", "port": 0, "max_connections_per_ip": bad}],
                allow_public=False,
            )


# --- (3) timer di messaggio con rumore ---


@pytest.mark.parametrize(
    "factory",
    [
        lambda: SlipFramer(max_payload=8),
        lambda: KissFramer(max_payload=8),
        lambda: DelimiterFramer(b"\n", max_payload=8),
    ],
    ids=["slip", "kiss", "delim1"],
)
async def test_junk_trickle_closed_by_message_timeout(factory):
    s = TcpServerTransport(cfg(idle_timeout_s=10.0, message_timeout_s=0.3), framer_factory=factory)
    await s.start()
    _r, w = await asyncio.open_connection("127.0.0.1", s.bound_address[1])
    try:
        w.write(b"\xc0\x00" if factory().__class__ is not DelimiterFramer else b"")

        async def trickle():
            try:
                for _ in range(200):
                    w.write(b"J")  # mai un frame completo, pending resta 0 in stato di scarto
                    await w.drain()
                    await asyncio.sleep(0.05)
            except (ConnectionError, OSError):
                pass

        t = asyncio.create_task(trickle())
        await eventually(lambda: s.stats()["message_timeouts"] == 1)
        assert s.stats()["idle_timeouts"] == 0
        t.cancel()
    finally:
        w.close()
        await s.close()


async def test_junk_flood_closed_by_discard_cap_and_counts_framing_error():
    s = TcpServerTransport(
        cfg(idle_timeout_s=10.0, message_timeout_s=10.0),
        framer_factory=lambda: SlipFramer(max_payload=8, max_discard_bytes=100),
    )
    await s.start()
    r, w = await asyncio.open_connection("127.0.0.1", s.bound_address[1])
    try:
        w.write(b"\xc0" + b"Z" * 500)
        await w.drain()
        assert await asyncio.wait_for(r.read(10), T) == b""
        assert s.stats()["framing_errors"] >= 1
    finally:
        w.close()
        await s.close()


class ExplodingFramer:
    def feed(self, data):
        raise RuntimeError("bug nel framer")

    def encode(self, payload):
        return payload

    def reset(self):
        pass


async def test_custom_framer_non_protocol_exception_drops_connection_not_server():
    s = TcpServerTransport(cfg(), framer_factory=ExplodingFramer)
    await s.start()
    r, w = await asyncio.open_connection("127.0.0.1", s.bound_address[1])
    try:
        w.write(b"abc")
        await w.drain()
        assert await asyncio.wait_for(r.read(10), T) == b""
        assert s.stats()["framing_errors"] == 1
        r2, w2 = await asyncio.open_connection("127.0.0.1", s.bound_address[1])
        w2.write(b"x")
        await w2.drain()
        assert await asyncio.wait_for(r2.read(10), T) == b""  # il server e' ancora vivo
        w2.close()
    finally:
        w.close()
        await s.close()


# --- minor: guardia multicast ---


def mc(**kw):
    base = {
        "name": "m",
        "kind": "udp_multicast",
        "host": "127.0.0.1",
        "port": 5000,
        "group": "239.1.2.3",
        "interface": "127.0.0.1",
    }
    base.update(kw)
    return base


@pytest.mark.parametrize("iface", ["8.8.8.8", "93.184.216.34"])
def test_multicast_public_interface_refused_without_opt_in(iface):
    with pytest.raises(NetConfigError, match="NET_ALLOW_PUBLIC_BIND"):
        parse_listeners([mc(interface=iface)], allow_public=False)
    assert parse_listeners([mc(interface=iface)], allow_public=True)[0].interface == iface


@pytest.mark.parametrize(
    "iface", ["127.0.0.1", "10.0.0.5", "192.168.1.2", "172.16.0.9", "169.254.3.4"]
)
def test_multicast_private_or_loopback_interface_allowed(iface):
    assert parse_listeners([mc(interface=iface)], allow_public=False)[0].interface == iface


@pytest.mark.parametrize("group", ["224.0.0.1", "224.0.0.251", "224.0.0.255"])
def test_multicast_reserved_local_block_refused_unless_explicit(group):
    with pytest.raises(NetConfigError, match="224.0.0"):
        parse_listeners([mc(group=group)], allow_public=False)
    ok = parse_listeners([mc(group=group, allow_reserved_group=True)], allow_public=False)
    assert ok[0].group == group


def test_multicast_group_outside_range_refused_and_normal_group_ok():
    for g in ("10.0.0.1", "240.0.0.1", "223.255.255.255"):
        with pytest.raises(NetConfigError):
            parse_listeners([mc(group=g)], allow_public=False)
    assert parse_listeners([mc(group="224.0.1.1")], allow_public=False)
    assert parse_listeners([mc(group="239.255.255.255")], allow_public=False)
