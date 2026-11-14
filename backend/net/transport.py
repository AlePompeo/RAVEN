# SPDX-License-Identifier: Apache-2.0
"""Trasporti di rete asincroni con limiti espliciti (spec 15).

Garanzie comuni (tutte testate): la dimensione massima del messaggio e' controllata PRIMA di
allocare/consegnare; le code sono limitate con politica di scarto esplicita e contatori; il
rate limit e' per peer (token bucket, tabella peer limitata); nessun raw socket, nessuna
modalita' promiscua. Questo modulo e' l'unico a toccare `socket`; il core non lo importa.
"""

import asyncio
import contextlib
import ipaddress
import os
import socket
import time
from collections import OrderedDict, deque
from collections.abc import Callable, Mapping
from dataclasses import asdict
from typing import Any

from backend.core.ports import Framer
from backend.net.config import ListenerConfig, parse_listeners
from backend.net.errors import (
    FramingError,
    LimitExceeded,
    ProtocolError,
    TransportClosed,
    TransportError,
)
from backend.net.framing import LengthPrefixFramer

Clock = Callable[[], float]


class Stats:
    """Contatori monotoni di un trasporto (esposti come `Mapping[str, int]`)."""

    NAMES = (
        "received",  # messaggi consegnati alla coda
        "sent",
        "oversize",  # messaggi/dichiarazioni oltre max_message_bytes
        "rate_limited",
        "dropped",  # scartati per coda piena (politica di scarto)
        "idle_timeouts",
        "message_timeouts",
        "rejected_connections",  # oltre max_connections
        "rejected_per_ip",  # oltre max_connections_per_ip
        "peer_table_overflow",  # messaggi da peer sconosciuti a tabella piena
        "connections",
        "disconnects",
        "framing_errors",
        "bytes_in",
        "bytes_out",
        "socket_errors",
    )

    def __init__(self) -> None:
        self._c: dict[str, int] = dict.fromkeys(self.NAMES, 0)

    def inc(self, name: str, n: int = 1) -> None:
        self._c[name] += n

    def snapshot(self) -> dict[str, int]:
        return dict(self._c)

    def __getitem__(self, name: str) -> int:
        return self._c[name]


class BoundedQueue:
    """Coda FIFO limitata, singolo consumatore. A coda piena applica `drop_policy`:
    `drop_oldest` scarta l'elemento piu' vecchio (telemetria: il dato recente vale di piu'),
    `drop_newest` scarta quello in arrivo. Ogni scarto incrementa `dropped`.
    `close()` lascia drenare gli elementi presenti, poi `get()` restituisce `None`."""

    def __init__(self, maxsize: int, drop_policy: str = "drop_oldest") -> None:
        if maxsize < 1:
            raise ValueError("maxsize >= 1")
        if drop_policy not in ("drop_oldest", "drop_newest"):
            raise ValueError("drop_policy non valida")
        self._q: deque[Any] = deque()
        self._max = maxsize
        self._policy = drop_policy
        self._event = asyncio.Event()
        self._closed = False
        self.dropped = 0

    def __len__(self) -> int:
        return len(self._q)

    def put(self, item: Any) -> bool:
        """True se l'elemento e' stato accodato (anche scartando il piu' vecchio)."""
        if self._closed:
            return False
        if len(self._q) >= self._max:
            self.dropped += 1
            if self._policy == "drop_newest":
                return False
            self._q.popleft()
        self._q.append(item)
        self._event.set()
        return True

    def close(self) -> None:
        self._closed = True
        self._event.set()

    async def get(self) -> Any | None:
        while not self._q:
            if self._closed:
                return None
            self._event.clear()
            await self._event.wait()
        return self._q.popleft()


class TokenBucket:
    """Token bucket con orologio iniettabile: `rate` token/s, capienza `burst`."""

    def __init__(self, rate: float, burst: int, clock: Clock) -> None:
        self._rate = rate
        self._burst = float(burst)
        self._clock = clock
        self._tokens = float(burst)
        self._last = clock()

    def is_full(self) -> bool:
        """True se il bucket e' (o sarebbe) al massimo: eliminarlo non perde informazione."""
        elapsed = max(0.0, self._clock() - self._last)
        return self._tokens + elapsed * self._rate >= self._burst

    def allow(self) -> bool:
        now = self._clock()
        elapsed = max(0.0, now - self._last)
        self._last = now
        self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            return True
        return False


class LoopbackTransport:
    """Trasporto in memoria per i test: nessun socket, stessi limiti e contatori degli altri."""

    def __init__(
        self,
        *,
        name: str = "loopback",
        max_message_bytes: int = 4096,
        queue_size: int = 1024,
        drop_policy: str = "drop_oldest",
    ) -> None:
        self.name = name
        self._max = max_message_bytes
        self._inbox = BoundedQueue(queue_size, drop_policy)
        self._peer: LoopbackTransport | None = None
        self._closed = False
        self._stats = Stats()

    async def start(self) -> None:
        return None

    async def send(self, data: bytes, peer: str | None = None) -> None:
        if self._closed or self._peer is None or self._peer._closed:
            raise TransportClosed("loopback chiuso o non connesso")
        if len(data) > self._max:
            self._stats.inc("oversize")
            raise LimitExceeded(f"messaggio di {len(data)} byte oltre il limite {self._max}")
        self._peer._deliver(self.name, bytes(data))
        self._stats.inc("sent")
        self._stats.inc("bytes_out", len(data))

    def _deliver(self, sender: str, data: bytes) -> None:
        if self._inbox.put((sender, data)):
            self._stats.inc("received")
            self._stats.inc("bytes_in", len(data))
        self._stats._c["dropped"] = self._inbox.dropped

    async def receive(self) -> tuple[str, bytes] | None:
        item: tuple[str, bytes] | None = await self._inbox.get()
        return item

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._inbox.close()
        if self._peer is not None:
            self._peer._inbox.close()

    def stats(self) -> Mapping[str, int]:
        return self._stats.snapshot()


def loopback_pair(
    *, max_message_bytes: int = 4096, queue_size: int = 1024, drop_policy: str = "drop_oldest"
) -> tuple[LoopbackTransport, LoopbackTransport]:
    kw: dict[str, Any] = {
        "max_message_bytes": max_message_bytes,
        "queue_size": queue_size,
        "drop_policy": drop_policy,
    }
    a = LoopbackTransport(name="loopback-a", **kw)
    b = LoopbackTransport(name="loopback-b", **kw)
    a._peer, b._peer = b, a
    return a, b


# --- Trasporti reali (asyncio). Nessun listener parte se non e' configurato esplicitamente. ---

READ_CHUNK = 16384
FramerFactory = Callable[[], Framer]


def validate_config(cfg: ListenerConfig) -> None:
    """Applica anche agli oggetti costruiti a mano le stesse regole del parsing JSON
    (bind pubblico rifiutato, limiti, multicast esplicito). Solleva `NetConfigError`."""
    parse_listeners([asdict(cfg)], allow_public=os.environ.get("NET_ALLOW_PUBLIC_BIND") == "1")


def default_framer_factory(cfg: ListenerConfig) -> FramerFactory:
    width = 2 if cfg.max_message_bytes <= 0xFFFF else 4
    return lambda: LengthPrefixFramer(width, max_payload=cfg.max_message_bytes)


def _fmt_peer(addr: Any) -> str:
    if not addr:
        return "unknown:0"
    return f"{addr[0]}:{addr[1]}"


def _addr2(addr: Any) -> tuple[str, int]:
    return (str(addr[0]), int(addr[1])) if addr else ("", 0)


def _parse_peer(peer: str) -> tuple[str, int]:
    host, sep, port_s = peer.rpartition(":")
    try:
        ip = ipaddress.ip_address(host)
        port = int(port_s)
    except ValueError:
        raise TransportError("peer non valido (atteso ip:porta)") from None
    if not sep or not 0 < port < 65536:
        raise TransportError("peer non valido (atteso ip:porta)")
    return str(ip), port


def normalize_peer_key(ip: str) -> str:
    """Chiave di rate limit/conteggio: IPv4 as-is; IPv4-mapped IPv6 -> IPv4; IPv6 -> rete /64
    (un singolo host/sito IPv6 ha almeno un /64: variare i 64 bit bassi non da' bucket nuovi)."""
    try:
        addr = ipaddress.ip_address(ip.split("%", 1)[0])
    except ValueError:
        return ip
    if isinstance(addr, ipaddress.IPv6Address):
        if addr.ipv4_mapped is not None:
            return str(addr.ipv4_mapped)
        return str(ipaddress.ip_network(f"{addr}/64", strict=False))
    return str(addr)


class PeerLimiter:
    """Token bucket per chiave (`normalize_peer_key`) piu' un tetto GLOBALE del listener.

    La tabella e' limitata a `max_peers`. A tabella piena un peer sconosciuto prende il posto del
    meno recente SOLO se il bucket di quest'ultimo e' gia' pieno (eliminarlo non perde
    informazione); altrimenti condivide un unico bucket di overflow: l'evizione non azzera mai un
    bucket in uso e sorgenti spoofate non ottengono un burst ciascuna (`overflow_hits`)."""

    def __init__(
        self,
        rate: float,
        burst: int,
        max_peers: int,
        clock: Clock,
        *,
        global_rate: float,
        global_burst: int,
    ) -> None:
        self._rate, self._burst, self._max, self._clock = rate, burst, max_peers, clock
        self._table: OrderedDict[str, TokenBucket] = OrderedDict()
        self._overflow = TokenBucket(rate, burst, clock)
        self._global = TokenBucket(global_rate, global_burst, clock)
        self.overflow_hits = 0

    def __len__(self) -> int:
        return len(self._table)

    def allow(self, key: str) -> bool:
        key = normalize_peer_key(key)
        b = self._table.get(key)
        if b is None:
            if len(self._table) >= self._max:
                oldest_key, oldest = next(iter(self._table.items()))
                if oldest.is_full():
                    del self._table[oldest_key]
                    b = TokenBucket(self._rate, self._burst, self._clock)
                    self._table[key] = b
                else:
                    self.overflow_hits += 1
                    b = self._overflow
            else:
                b = TokenBucket(self._rate, self._burst, self._clock)
                self._table[key] = b
        else:
            self._table.move_to_end(key)
        if not b.allow():
            return False
        return self._global.allow()


class _NetBase:
    def __init__(self, cfg: ListenerConfig, clock: Clock | None) -> None:
        validate_config(cfg)
        self.cfg = cfg
        self._clock: Clock = clock or time.monotonic
        self._stats = Stats()
        self._queue = BoundedQueue(cfg.queue_size, cfg.drop_policy)
        self._limiter = PeerLimiter(
            cfg.rate_msgs_per_s,
            cfg.rate_burst,
            cfg.max_peers,
            self._clock,
            global_rate=cfg.global_rate_msgs_per_s,
            global_burst=cfg.global_rate_burst,
        )
        self._closing = False
        self.bound_address: tuple[str, int] = ("", 0)

    @property
    def peer_table_size(self) -> int:
        return len(self._limiter)

    def stats(self) -> Mapping[str, int]:
        s = self._stats.snapshot()
        s["dropped"] = self._queue.dropped
        s["peer_table_overflow"] = self._limiter.overflow_hits
        return s

    async def receive(self) -> tuple[str, bytes] | None:
        item: tuple[str, bytes] | None = await self._queue.get()
        return item

    def _enqueue(self, peer: str, data: bytes) -> None:
        if self._queue.put((peer, data)):
            self._stats.inc("received")


class _TcpBase(_NetBase):
    def __init__(
        self, cfg: ListenerConfig, framer_factory: FramerFactory | None, clock: Clock | None
    ) -> None:
        super().__init__(cfg, clock)
        self._framer_factory = framer_factory or default_framer_factory(cfg)
        self._encoder = self._framer_factory()
        self._conns: dict[str, asyncio.StreamWriter] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    def _account(self, framer: Any, before: tuple[int, int], raised: bool) -> None:
        ov = getattr(framer, "oversize", 0) - before[0]
        er = getattr(framer, "errors", 0) - before[1]
        if ov > 0:
            self._stats.inc("oversize", ov)
        if er > 0 or raised:
            self._stats.inc("framing_errors", max(er, 1 if raised else 0))

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        loop = asyncio.get_running_loop()
        peer = _fmt_peer(writer.get_extra_info("peername"))
        ip = normalize_peer_key(peer.rpartition(":")[0])
        framer = self._framer_factory()
        self._conns[peer] = writer
        self._stats.inc("connections")
        cfg = self.cfg
        last_rx = loop.time()
        partial_since: float | None = None
        violations = 0
        try:
            while not self._closing:
                dl_idle = last_rx + cfg.idle_timeout_s
                dl_msg = (
                    partial_since + cfg.message_timeout_s if partial_since is not None else None
                )
                deadline = dl_idle if dl_msg is None else min(dl_idle, dl_msg)
                remaining = deadline - loop.time()
                data = b""
                if remaining > 0:
                    try:
                        data = await asyncio.wait_for(reader.read(READ_CHUNK), remaining)
                    except TimeoutError:
                        remaining = 0
                    except (ConnectionError, OSError):
                        break
                if remaining <= 0:
                    msg_first = dl_msg is not None and dl_msg < dl_idle
                    self._stats.inc("message_timeouts" if msg_first else "idle_timeouts")
                    break
                if not data:
                    break
                last_rx = loop.time()
                self._stats.inc("bytes_in", len(data))
                before = (getattr(framer, "oversize", 0), getattr(framer, "errors", 0))
                try:
                    frames = framer.feed(data)
                except ProtocolError:
                    self._account(framer, before, True)
                    break  # flusso non recuperabile: chiusura pulita
                except Exception:  # noqa: BLE001 - framer personalizzato difettoso: mai fatale al server
                    self._stats.inc("framing_errors")
                    break
                self._account(framer, before, False)
                mid_frame = getattr(framer, "bytes_since_frame", getattr(framer, "pending", 0))
                if mid_frame > 0:
                    keep = partial_since is not None and not frames
                    partial_since = partial_since if keep else last_rx
                else:
                    partial_since = None
                stop = False
                for f in frames:
                    if not self._limiter.allow(ip):
                        self._stats.inc("rate_limited")
                        violations += 1
                        if violations >= cfg.rate_disconnect_after:
                            stop = True
                            break
                        continue
                    violations = 0
                    self._enqueue(peer, f)
                if stop:
                    break
        finally:
            self._conns.pop(peer, None)
            self._stats.inc("disconnects")
            writer.close()
            with contextlib.suppress(Exception, asyncio.CancelledError):
                await asyncio.wait_for(writer.wait_closed(), 1.0)

    async def send(self, data: bytes, peer: str | None = None) -> None:
        if self._closing:
            raise TransportClosed("trasporto chiuso")
        if len(data) > self.cfg.max_message_bytes:
            self._stats.inc("oversize")
            raise LimitExceeded(f"messaggio di {len(data)} byte oltre il limite")
        if peer is None:
            if len(self._conns) != 1:
                raise TransportClosed("peer non specificato e connessioni != 1")
            peer = next(iter(self._conns))
        writer = self._conns.get(peer)
        if writer is None:
            raise TransportClosed("peer non connesso")
        try:
            wire = self._encoder.encode(data)
        except FramingError as e:
            raise LimitExceeded(str(e)) from None
        try:
            writer.write(wire)
            await asyncio.wait_for(writer.drain(), self.cfg.idle_timeout_s)
        except (ConnectionError, OSError, TimeoutError):
            writer.close()  # lettore lento o connessione persa: non si accumula memoria
            raise TransportClosed("scrittura fallita o peer troppo lento") from None
        self._stats.inc("sent")
        self._stats.inc("bytes_out", len(data))

    async def _shutdown_conns(self) -> None:
        for w in list(self._conns.values()):
            w.close()
        for t in list(self._tasks):
            t.cancel()
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)
        self._queue.close()


class TcpServerTransport(_TcpBase):
    """Server TCP asincrono. Messaggi delimitati dal framer (default: prefisso di lunghezza
    big-endian a 2/4 byte con massimo `max_message_bytes`). Connessioni oltre `max_connections`
    chiuse subito; idle e frame parziali con timeout; rate limit per IP; coda con scarto."""

    def __init__(
        self,
        cfg: ListenerConfig,
        framer_factory: FramerFactory | None = None,
        clock: Clock | None = None,
    ) -> None:
        if cfg.kind != "tcp_server":
            raise ValueError("kind deve essere tcp_server")
        super().__init__(cfg, framer_factory, clock)
        self._server: asyncio.Server | None = None

    async def start(self) -> None:
        if self._server is not None:
            return
        try:
            self._server = await asyncio.start_server(
                self._on_client, self.cfg.host, self.cfg.port, limit=2 * READ_CHUNK
            )
        except OSError as e:
            raise TransportClosed(f"bind {self.cfg.host}:{self.cfg.port} fallito: {e}") from e
        self.bound_address = _addr2(self._server.sockets[0].getsockname())

    async def _on_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        if task is not None:
            self._tasks.add(task)
        try:
            ip = normalize_peer_key(_fmt_peer(writer.get_extra_info("peername")).rpartition(":")[0])
            same_ip = sum(1 for k in self._conns if normalize_peer_key(k.rpartition(":")[0]) == ip)
            reject = None
            if self._closing or len(self._conns) >= self.cfg.max_connections:
                reject = "rejected_connections"
            elif same_ip >= self.cfg.max_connections_per_ip:
                reject = "rejected_per_ip"
            if reject is not None:
                self._stats.inc(reject)
                writer.close()
                with contextlib.suppress(Exception, asyncio.CancelledError):
                    await asyncio.wait_for(writer.wait_closed(), 1.0)
                return
            await self._serve(reader, writer)
        finally:
            if task is not None:
                self._tasks.discard(task)

    async def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        if self._server is not None:
            self._server.close()
        await self._shutdown_conns()
        if self._server is not None:
            with contextlib.suppress(Exception, asyncio.CancelledError):
                await asyncio.wait_for(self._server.wait_closed(), 2.0)


class TcpClientTransport(_TcpBase):
    """Client TCP verso `host:port` (connessione unica, nessuna riconnessione automatica)."""

    CONNECT_TIMEOUT_S = 5.0

    def __init__(
        self,
        cfg: ListenerConfig,
        framer_factory: FramerFactory | None = None,
        clock: Clock | None = None,
    ) -> None:
        if cfg.kind != "tcp_client":
            raise ValueError("kind deve essere tcp_client")
        super().__init__(cfg, framer_factory, clock)
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.cfg.host, self.cfg.port, limit=2 * READ_CHUNK),
                self.CONNECT_TIMEOUT_S,
            )
        except (OSError, TimeoutError) as e:
            raise TransportClosed(f"connessione a {self.cfg.host}:{self.cfg.port} fallita") from e
        self.bound_address = _addr2(writer.get_extra_info("sockname"))
        self._task = asyncio.get_running_loop().create_task(self._run(reader, writer))
        self._tasks.add(self._task)
        self._task.add_done_callback(self._tasks.discard)
        while not self._conns and not self._task.done():
            await asyncio.sleep(0)  # `_serve` registra la connessione al primo passo

    async def _run(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            await self._serve(reader, writer)
        finally:
            self._queue.close()

    async def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        await self._shutdown_conns()


class _UdpProtocol(asyncio.DatagramProtocol):
    def __init__(self, owner: "UdpTransport") -> None:
        self._owner = owner

    def datagram_received(self, data: bytes, addr: Any) -> None:
        self._owner._on_datagram(data, addr)

    def error_received(self, exc: Exception) -> None:
        self._owner._stats.inc("socket_errors")


class UdpTransport(_NetBase):
    """UDP unicast (`udp` = server legato, `udp_client` = connesso) e multicast (`udp_multicast`,
    gruppo e interfaccia espliciti). Un datagramma oltre `max_message_bytes` e' scartato e
    contato prima di qualsiasi copia/parsing; rate limit per IP; tabella peer limitata.
    UDP non ha connessione: nessun idle timeout (n/a). Nessun socket raw."""

    def __init__(self, cfg: ListenerConfig, clock: Clock | None = None) -> None:
        if cfg.kind not in ("udp", "udp_client", "udp_multicast"):
            raise ValueError("kind deve essere udp, udp_client o udp_multicast")
        super().__init__(cfg, clock)
        self._tr: asyncio.DatagramTransport | None = None

    def _multicast_socket(self) -> socket.socket:
        cfg = self.cfg
        assert cfg.group is not None and cfg.interface is not None
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((cfg.group, cfg.port))  # legato al gruppo, non a 0.0.0.0
            grp, ifc = socket.inet_aton(cfg.group), socket.inet_aton(cfg.interface)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, grp + ifc)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, ifc)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)  # non esce dalla subnet
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
            sock.setblocking(False)
        except OSError as e:
            sock.close()
            raise TransportClosed(f"setup multicast fallito: {e}") from e
        return sock

    async def start(self) -> None:
        if self._tr is not None:
            return
        loop = asyncio.get_running_loop()
        cfg = self.cfg
        try:
            if cfg.kind == "udp":
                tr, _ = await loop.create_datagram_endpoint(
                    lambda: _UdpProtocol(self), local_addr=(cfg.host, cfg.port)
                )
            elif cfg.kind == "udp_client":
                tr, _ = await loop.create_datagram_endpoint(
                    lambda: _UdpProtocol(self), remote_addr=(cfg.host, cfg.port)
                )
            else:
                tr, _ = await loop.create_datagram_endpoint(
                    lambda: _UdpProtocol(self), sock=self._multicast_socket()
                )
        except OSError as e:
            raise TransportClosed(f"avvio UDP fallito: {e}") from e
        self._tr = tr
        self.bound_address = _addr2(tr.get_extra_info("sockname"))

    def _on_datagram(self, data: bytes, addr: Any) -> None:
        if self._closing:
            return
        if len(data) > self.cfg.max_message_bytes:
            self._stats.inc("oversize")
            return
        self._stats.inc("bytes_in", len(data))
        if not self._limiter.allow(str(addr[0])):
            self._stats.inc("rate_limited")
            return
        self._enqueue(_fmt_peer(addr), bytes(data))

    async def send(self, data: bytes, peer: str | None = None) -> None:
        if self._closing or self._tr is None:
            raise TransportClosed("trasporto chiuso o non avviato")
        if len(data) > self.cfg.max_message_bytes:
            self._stats.inc("oversize")
            raise LimitExceeded(f"datagramma di {len(data)} byte oltre il limite")
        kind = self.cfg.kind
        try:
            if kind == "udp_client":
                self._tr.sendto(data)
            elif kind == "udp_multicast":
                self._tr.sendto(data, (self.cfg.group, self.cfg.port))
            else:
                if peer is None:
                    raise TransportError("peer richiesto per un server UDP")
                self._tr.sendto(data, _parse_peer(peer))
        except OSError as e:
            self._stats.inc("socket_errors")
            raise TransportError(f"invio UDP fallito: {e}") from e
        self._stats.inc("sent")
        self._stats.inc("bytes_out", len(data))

    async def close(self) -> None:
        if self._closing:
            return
        self._closing = True
        if self._tr is not None:
            self._tr.close()
        self._queue.close()


def build_transport(
    cfg: ListenerConfig, clock: Clock | None = None
) -> TcpServerTransport | TcpClientTransport | UdpTransport:
    if cfg.kind == "tcp_server":
        return TcpServerTransport(cfg, clock=clock)
    if cfg.kind == "tcp_client":
        return TcpClientTransport(cfg, clock=clock)
    return UdpTransport(cfg, clock=clock)


async def start_listeners(
    configs: list[ListenerConfig], clock: Clock | None = None
) -> list[TcpServerTransport | TcpClientTransport | UdpTransport]:
    """Avvia SOLO i listener configurati (lista vuota -> nessun socket). Se uno fallisce, chiude
    quelli gia' avviati e rilancia: mai uno stato parzialmente aperto."""
    started: list[TcpServerTransport | TcpClientTransport | UdpTransport] = []
    try:
        for cfg in configs:
            t = build_transport(cfg, clock)
            await t.start()
            started.append(t)
    except BaseException:
        for t in started:
            await t.close()
        raise
    return started
