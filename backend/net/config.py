# SPDX-License-Identifier: Apache-2.0
"""Configurazione dei listener di rete. Default chiuso: senza configurazione NON parte nulla.

Sorgenti: variabile d'ambiente `NET_LISTENERS` (array JSON) oppure oggetti `ListenerConfig`
passati dal codice. Il bind su indirizzi non loopback (0.0.0.0, interfacce reali) e' rifiutato
salvo `NET_ALLOW_PUBLIC_BIND=1` (esattamente "1"). Valori fuori limite sono rifiutati con
`NetConfigError`, mai corretti in silenzio.
"""

import ipaddress
import json
import math
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from backend.net.errors import NetConfigError

KINDS = ("tcp_server", "tcp_client", "udp", "udp_client", "udp_multicast")
SERVER_KINDS = ("tcp_server", "udp")
DROP_POLICIES = ("drop_oldest", "drop_newest")

# Tetti assoluti: nessuna configurazione puo' superarli (difesa contro config sbagliate).
MAX_MESSAGE_BYTES_CEILING = 1 << 20  # 1 MiB
MAX_CONNECTIONS_CEILING = 1024
MAX_QUEUE_CEILING = 100_000


@dataclass(frozen=True)
class ListenerConfig:
    name: str
    kind: str
    host: str = "127.0.0.1"
    port: int = 0
    max_connections: int = 8
    max_connections_per_ip: int = 2  # un solo IP non puo' occupare tutti gli slot
    max_message_bytes: int = 4096
    idle_timeout_s: float = 30.0
    message_timeout_s: float = 10.0  # tempo massimo per completare un frame iniziato
    rate_msgs_per_s: float = 100.0  # per peer (token bucket)
    rate_burst: int = 200
    global_rate_msgs_per_s: float = 1000.0  # tetto complessivo del listener (tutti i peer)
    global_rate_burst: int = 2000
    rate_disconnect_after: int = 1000  # violazioni consecutive oltre le quali si chiude (TCP)
    queue_size: int = 1024
    drop_policy: str = "drop_oldest"
    max_peers: int = 1024  # tabella dei rate limiter/peer UDP: limitata
    group: str | None = None  # multicast: gruppo IPv4 esplicito
    interface: str | None = None  # multicast: indirizzo IPv4 dell'interfaccia, esplicito
    allow_reserved_group: bool = False  # multicast: consente 224.0.0.0/24 (riservato, link-local)


_FIELDS = set(ListenerConfig.__dataclass_fields__)


def _num(
    d: Mapping[str, Any], key: str, default: Any, *, lo: float, hi: float, integer: bool
) -> Any:
    v = d.get(key, default)
    if isinstance(v, bool) or not isinstance(v, int if integer else (int, float)):
        raise NetConfigError(f"{key}: tipo non valido")
    if not math.isfinite(v) or not (lo <= v <= hi):
        raise NetConfigError(f"{key}: fuori intervallo [{lo}, {hi}]")
    return v


def _ip(value: Any, key: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    if not isinstance(value, str):
        raise NetConfigError(f"{key}: deve essere una stringa")
    try:
        return ipaddress.ip_address(value)
    except ValueError:
        raise NetConfigError(f"{key}: deve essere un indirizzo IP letterale") from None


def _parse_one(raw: Any, *, allow_public: bool) -> ListenerConfig:
    if not isinstance(raw, Mapping):
        raise NetConfigError("ogni listener deve essere un oggetto")
    unknown = set(raw) - _FIELDS
    if unknown:
        raise NetConfigError(f"chiavi sconosciute: {sorted(map(str, unknown))}")
    name = raw.get("name")
    if not isinstance(name, str) or not name or len(name) > 64 or not name.isprintable():
        raise NetConfigError("name: stringa non vuota (<=64 caratteri stampabili)")
    kind = raw.get("kind")
    if kind not in KINDS:
        raise NetConfigError(f"kind: uno tra {KINDS}")
    host = raw.get("host", "127.0.0.1")
    port = raw.get("port", 0)
    if isinstance(port, bool) or not isinstance(port, int) or not (0 <= port <= 65535):
        raise NetConfigError("port: intero 0..65535")
    group = raw.get("group")
    interface = raw.get("interface")
    if kind in SERVER_KINDS:
        addr = _ip(host, "host")  # niente nomi host: nessuna risoluzione DNS nel bind
        if not addr.is_loopback and not allow_public:
            raise NetConfigError(
                f"bind su {host} rifiutato: non e' loopback (impostare NET_ALLOW_PUBLIC_BIND=1 "
                "per consentirlo esplicitamente)"
            )
    else:
        if not isinstance(host, str) or not host or len(host) > 253 or not host.isprintable():
            raise NetConfigError("host: stringa non vuota")
        if port == 0:
            raise NetConfigError("port: i client e il multicast richiedono una porta esplicita")
    if kind == "udp_multicast":
        g = _ip(group, "group") if group is not None else None
        if g is None or g.version != 4 or not g.is_multicast:
            raise NetConfigError("group: indirizzo multicast IPv4 esplicito obbligatorio")
        reserved_ok = raw.get("allow_reserved_group", False)
        if not isinstance(reserved_ok, bool):
            raise NetConfigError("allow_reserved_group: bool")
        if g in ipaddress.ip_network("224.0.0.0/24") and not reserved_ok:
            raise NetConfigError(
                "group: 224.0.0.0/24 e' riservato (protocolli di rete locale); impostare "
                "allow_reserved_group=true per usarlo esplicitamente"
            )
        i = _ip(interface, "interface") if interface is not None else None
        if i is None or i.version != 4 or i.is_multicast or i.is_unspecified:
            raise NetConfigError("interface: indirizzo IPv4 esplicito obbligatorio (non 0.0.0.0)")
        if not (i.is_loopback or i.is_private or i.is_link_local) and not allow_public:
            raise NetConfigError(
                f"interface {interface} non e' loopback/privata/link-local (impostare "
                "NET_ALLOW_PUBLIC_BIND=1 per consentirla esplicitamente)"
            )
    elif group is not None or interface is not None:
        raise NetConfigError("group/interface solo per udp_multicast")
    policy = raw.get("drop_policy", "drop_oldest")
    if policy not in DROP_POLICIES:
        raise NetConfigError(f"drop_policy: uno tra {DROP_POLICIES}")
    d = raw
    return ListenerConfig(
        name=name,
        kind=kind,
        host=host,
        port=port,
        max_connections=_num(
            d, "max_connections", 8, lo=1, hi=MAX_CONNECTIONS_CEILING, integer=True
        ),
        max_connections_per_ip=_num(
            d, "max_connections_per_ip", 2, lo=1, hi=MAX_CONNECTIONS_CEILING, integer=True
        ),
        max_message_bytes=_num(
            d, "max_message_bytes", 4096, lo=1, hi=MAX_MESSAGE_BYTES_CEILING, integer=True
        ),
        idle_timeout_s=_num(d, "idle_timeout_s", 30.0, lo=0.001, hi=86400, integer=False),
        message_timeout_s=_num(d, "message_timeout_s", 10.0, lo=0.001, hi=86400, integer=False),
        rate_msgs_per_s=_num(d, "rate_msgs_per_s", 100.0, lo=0.001, hi=1e6, integer=False),
        global_rate_msgs_per_s=_num(
            d, "global_rate_msgs_per_s", 1000.0, lo=0.001, hi=1e7, integer=False
        ),
        global_rate_burst=_num(d, "global_rate_burst", 2000, lo=1, hi=10**7, integer=True),
        rate_burst=_num(d, "rate_burst", 200, lo=1, hi=10**6, integer=True),
        rate_disconnect_after=_num(d, "rate_disconnect_after", 1000, lo=1, hi=10**9, integer=True),
        queue_size=_num(d, "queue_size", 1024, lo=1, hi=MAX_QUEUE_CEILING, integer=True),
        drop_policy=policy,
        max_peers=_num(d, "max_peers", 1024, lo=1, hi=100_000, integer=True),
        group=group,
        interface=interface,
        allow_reserved_group=bool(raw.get("allow_reserved_group", False)),
    )


def parse_listeners(raw: Sequence[Any], *, allow_public: bool) -> list[ListenerConfig]:
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        raise NetConfigError("NET_LISTENERS deve essere un array JSON")
    out = [_parse_one(item, allow_public=allow_public) for item in raw]
    names = [c.name for c in out]
    if len(set(names)) != len(names):
        raise NetConfigError("nomi di listener duplicati")
    return out


def load_listeners() -> list[ListenerConfig]:
    """Legge `NET_LISTENERS`. Assente/vuoto/`[]` -> nessun listener (default sicuro)."""
    text = os.environ.get("NET_LISTENERS", "").strip()
    if not text:
        return []
    try:
        raw = json.loads(text)
    except ValueError:
        raise NetConfigError("NET_LISTENERS non e' JSON valido") from None
    allow = os.environ.get("NET_ALLOW_PUBLIC_BIND") == "1"
    return parse_listeners(raw, allow_public=allow)
