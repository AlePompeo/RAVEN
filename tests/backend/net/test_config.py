# SPDX-License-Identifier: Apache-2.0
"""Configurazione listener: default chiuso, bind pubblico rifiutato salvo opt-in esplicito."""

import json

import pytest

from backend.net.config import ListenerConfig, load_listeners, parse_listeners
from backend.net.errors import NetConfigError


def one(**kw):
    base = {"name": "l1", "kind": "tcp_server", "host": "127.0.0.1", "port": 0}
    base.update(kw)
    return base


def test_empty_or_missing_env_means_no_listeners(monkeypatch):
    monkeypatch.delenv("NET_LISTENERS", raising=False)
    assert load_listeners() == []
    monkeypatch.setenv("NET_LISTENERS", "")
    assert load_listeners() == []
    monkeypatch.setenv("NET_LISTENERS", "[]")
    assert load_listeners() == []


def test_valid_listener_defaults_are_conservative():
    [cfg] = parse_listeners([one()], allow_public=False)
    assert isinstance(cfg, ListenerConfig)
    assert cfg.host == "127.0.0.1"
    assert 0 < cfg.max_message_bytes <= 65536
    assert cfg.max_connections >= 1
    assert cfg.idle_timeout_s > 0
    assert cfg.rate_msgs_per_s > 0
    assert cfg.drop_policy in ("drop_oldest", "drop_newest")


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.5", "10.0.0.1"])
def test_public_bind_refused_without_opt_in(host):
    with pytest.raises(NetConfigError, match="NET_ALLOW_PUBLIC_BIND"):
        parse_listeners([one(host=host)], allow_public=False)


def test_public_bind_allowed_with_opt_in():
    [cfg] = parse_listeners([one(host="0.0.0.0")], allow_public=True)
    assert cfg.host == "0.0.0.0"


def test_env_opt_in_only_exact_1(monkeypatch):
    monkeypatch.setenv("NET_LISTENERS", json.dumps([one(host="0.0.0.0")]))
    monkeypatch.setenv("NET_ALLOW_PUBLIC_BIND", "true")
    with pytest.raises(NetConfigError):
        load_listeners()
    monkeypatch.setenv("NET_ALLOW_PUBLIC_BIND", "1")
    assert load_listeners()[0].host == "0.0.0.0"


def test_hostnames_refused_for_bind():
    with pytest.raises(NetConfigError):
        parse_listeners([one(host="localhost")], allow_public=False)


@pytest.mark.parametrize(
    "bad",
    [
        {"kind": "raw"},
        {"kind": "tcp_server", "port": -1},
        {"port": 70000},
        {"port": "80"},
        {"max_message_bytes": 0},
        {"max_message_bytes": 10**9},
        {"max_connections": 0},
        {"idle_timeout_s": 0},
        {"idle_timeout_s": float("nan")},
        {"rate_msgs_per_s": -1},
        {"drop_policy": "explode"},
        {"unknown_key": 1},
        {"name": ""},
    ],
)
def test_invalid_values_rejected(bad):
    with pytest.raises(NetConfigError):
        parse_listeners([one(**bad)], allow_public=False)


def test_duplicate_names_rejected():
    with pytest.raises(NetConfigError):
        parse_listeners([one(), one()], allow_public=False)


def test_malformed_json_and_shape(monkeypatch):
    monkeypatch.setenv("NET_LISTENERS", "{not json")
    with pytest.raises(NetConfigError):
        load_listeners()
    monkeypatch.setenv("NET_LISTENERS", '{"a": 1}')
    with pytest.raises(NetConfigError):
        load_listeners()


def test_multicast_requires_explicit_group_and_interface():
    mc = {"kind": "udp_multicast", "host": "127.0.0.1", "port": 5000}
    with pytest.raises(NetConfigError):
        parse_listeners([one(**mc)], allow_public=False)  # niente gruppo
    with pytest.raises(NetConfigError):
        parse_listeners([one(**mc, group="224.0.0.1")], allow_public=False)  # niente interfaccia
    with pytest.raises(NetConfigError):
        parse_listeners(
            [one(**mc, group="10.0.0.1", interface="127.0.0.1")], allow_public=False
        )  # non e' multicast
    [cfg] = parse_listeners(
        [one(**mc, group="239.1.2.3", interface="127.0.0.1")], allow_public=False
    )
    assert cfg.group == "239.1.2.3" and cfg.interface == "127.0.0.1"


def test_client_kind_needs_nonzero_port():
    with pytest.raises(NetConfigError):
        parse_listeners([one(kind="tcp_client", port=0)], allow_public=False)
