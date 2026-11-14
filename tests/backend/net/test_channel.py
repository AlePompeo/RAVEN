# SPDX-License-Identifier: Apache-2.0
"""Canale simulato deterministico (Task 19 step 6): orologio virtuale, nessuno sleep reale."""

import math
import random

import pytest

from backend.core.ports import Channel
from backend.net.ax25 import Ax25Address, Ax25Codec, Ax25UiFrame
from backend.net.channel import ChannelConfig, SimChannel, VirtualClock
from backend.net.errors import CrcError

INF = math.inf


def make(**kw):
    clock = VirtualClock()
    return SimChannel(ChannelConfig(**kw), clock=clock), clock


def test_satisfies_channel_port():
    ch, _ = make()
    assert isinstance(ch, Channel)


def test_perfect_channel_zero_delay_delivers_immediately_in_order():
    ch, _ = make()
    for i in range(5):
        ch.send(bytes([i]), now_s=1.0)
    assert ch.deliver(1.0) == [bytes([i]) for i in range(5)]
    assert ch.stats()["sent"] == ch.stats()["delivered"] == 5


def test_loss_100_percent_delivers_nothing():
    ch, _ = make(loss_probability=1.0, seed=3)
    for i in range(100):
        ch.send(b"x" * 10, now_s=float(i))
    assert ch.deliver(INF) == []
    st = ch.stats()
    assert (st["sent"], st["delivered"], st["lost"]) == (100, 0, 100)


def test_loss_zero_percent_loses_nothing_and_statistical_loss_is_close():
    ch, _ = make(loss_probability=0.0)
    for i in range(500):
        ch.send(b"a", now_s=0.0)
    assert len(ch.deliver(INF)) == 500
    ch, _ = make(loss_probability=0.3, seed=42)
    for _ in range(10000):
        ch.send(b"a", now_s=0.0)
    delivered = len(ch.deliver(INF))
    assert 6700 < delivered < 7300  # ~7000 attesi, seme fisso -> deterministico


def test_constant_delay_measured_on_virtual_clock():
    ch, clock = make(delay_s=0.25)
    clock.advance(10.0)
    ch.send(b"ping")  # usa l'orologio iniettato
    assert ch.deliver(10.0) == []
    assert ch.deliver(10.24999) == []
    assert ch.next_arrival_s() == 10.25
    assert ch.deliver(10.25) == [b"ping"]
    assert ch.deliver(INF) == []  # consegnato una sola volta
    # con l'orologio: deliver_due() senza argomenti
    ch.send(b"pong")
    clock.advance(0.2)
    assert ch.deliver_due() == []
    clock.advance(0.05)
    assert ch.deliver_due() == [b"pong"]


def test_constant_delay_for_every_frame_without_jitter():
    ch, _ = make(delay_s=1.5)
    times = [0.0, 0.3, 7.0, 7.0, 100.0]
    for t in times:
        ch.send(b"f", now_s=t)
    got = ch.deliver_timed(INF)
    assert [a for a, _ in got] == [t + 1.5 for t in times]


def test_determinism_same_seed_same_result_different_seed_differs():
    def run(seed):
        ch, _ = make(
            delay_s=0.1, jitter_s=0.5, loss_probability=0.2, bit_error_rate=1e-3, seed=seed
        )
        for i in range(300):
            ch.send(bytes([i % 256]) * 20, now_s=i * 0.01)
        return ch.deliver_timed(INF), dict(ch.stats())

    assert run(1) == run(1)
    assert run(1) != run(2)


def test_bit_errors_cause_downstream_crc_failure():
    codec = Ax25Codec()
    frames = [
        Ax25UiFrame(Ax25Address("N0CALL", 1), Ax25Address("N7LEM", 2), info=bytes([i]) * 24)
        for i in range(200)
    ]
    originals = [codec.encode(f) for f in frames]
    ch, _ = make(bit_error_rate=2e-3, seed=11)
    for i, raw in enumerate(originals):
        ch.send(raw, now_s=float(i))
    got = ch.deliver(INF)
    assert len(got) == len(originals)  # nessun jitter: ordine conservato
    corrupted = [g != o for g, o in zip(got, originals, strict=True)]
    assert 0 < sum(corrupted) < len(originals)  # ne' tutti ne' nessuno
    dec = Ax25Codec()
    for g, o, bad in zip(got, originals, corrupted, strict=True):
        if bad:
            with pytest.raises(CrcError):
                dec.decode(g)
        else:
            assert dec.decode(g) == codec.decode(o)
    assert dec.crc_errors == sum(corrupted)
    assert ch.stats()["corrupted"] == sum(corrupted)
    assert ch.stats()["bits_flipped"] >= sum(corrupted)


def test_bit_error_rate_statistics_and_extremes():
    ch, _ = make(bit_error_rate=0.01, seed=5)
    ch.send(bytes(12500), now_s=0.0)  # 100000 bit
    (got,) = ch.deliver(INF)
    flips = sum(b.bit_count() for b in got)
    assert ch.stats()["bits_flipped"] == flips
    assert 850 < flips < 1150  # ~1000 attesi
    ch, _ = make(bit_error_rate=1.0)
    ch.send(b"\x00\xff", now_s=0.0)
    assert ch.deliver(INF) == [b"\xff\x00"]  # tutti i bit invertiti
    ch, _ = make(bit_error_rate=0.0)
    ch.send(b"\x12\x34", now_s=0.0)
    assert ch.deliver(INF) == [b"\x12\x34"]


def test_nothing_delivered_outside_contact_windows():
    ch, _ = make(delay_s=1.0, contact_windows=((10.0, 20.0), (30.0, 40.0)))
    send_times = [5.0, 10.0, 15.0, 18.9, 19.5, 25.0, 35.0, 39.5, 50.0]
    for t in send_times:
        ch.send(f"{t}".encode(), now_s=t)
    got = ch.deliver_timed(INF)
    windows = ((10.0, 20.0), (30.0, 40.0))
    assert got  # qualcosa passa
    for arrival, _ in got:
        assert any(s <= arrival < e for s, e in windows), arrival
    delivered = {d for _, d in got}
    assert delivered == {b"10.0", b"15.0", b"18.9", b"35.0"}
    # 5.0, 25.0, 50.0 trasmessi fuori finestra; 19.5 -> arriva a 20.5 fuori; 39.5 -> 40.5 fuori
    st = ch.stats()
    assert st["dropped_outside_window"] == 5
    assert st["sent"] == st["delivered"] + st["lost"] + st["dropped_outside_window"]


def test_window_end_is_exclusive_and_start_inclusive():
    ch, _ = make(contact_windows=((1.0, 2.0),))
    ch.send(b"a", now_s=1.0)
    ch.send(b"b", now_s=2.0)
    assert ch.deliver(INF) == [b"a"]


def test_jitter_is_nonnegative_bounded_and_can_reorder():
    ch, _ = make(delay_s=1.0, jitter_s=5.0, seed=9)
    send_t = {}
    for i in range(50):
        ch.send(bytes([i]), now_s=i * 0.1)
        send_t[i] = i * 0.1
    got = ch.deliver_timed(INF)
    arrivals = [a for a, _ in got]
    assert arrivals == sorted(arrivals)  # deliver restituisce in ordine di ARRIVO
    for a, d in got:
        lat = a - send_t[d[0]]
        assert 1.0 <= lat <= 6.0 + 1e-9  # delay + [0, jitter]: mai in anticipo
    order = [d[0] for _, d in got]
    assert order != sorted(order)  # con jitter > spaziatura i frame si riordinano
    ch2, _ = make(delay_s=1.0, jitter_s=0.0)
    for i in range(50):
        ch2.send(bytes([i]), now_s=i * 0.1)
    assert [d[0] for _, d in ch2.deliver_timed(INF)] == list(range(50))  # senza jitter: FIFO


def test_equal_arrival_ties_keep_send_order():
    ch, _ = make(delay_s=1.0)
    for i in range(10):
        ch.send(bytes([i]), now_s=0.0)
    assert ch.deliver(INF) == [bytes([i]) for i in range(10)]


def test_bandwidth_limit_serializes_frames():
    ch, _ = make(bandwidth_bps=1000.0, delay_s=0.5)
    for _ in range(3):
        ch.send(bytes(125), now_s=0.0)  # 1000 bit = 1 s ciascuno
    got = ch.deliver_timed(INF)
    assert [a for a, _ in got] == [1.5, 2.5, 3.5]
    ch.send(bytes(125), now_s=10.0)  # canale libero: nessun accodamento residuo
    assert ch.deliver_timed(INF)[0][0] == 11.5


def test_overflow_counts_as_lost():
    ch, _ = make(max_in_flight=3)
    for i in range(5):
        ch.send(
            bytes([i]),
            now_s=0.0,
        )
    assert ch.stats()["in_flight"] == 3
    assert ch.stats()["lost"] == 2
    assert ch.stats()["lost_overflow"] == 2
    assert len(ch.deliver(INF)) == 3


def test_accounting_invariant_property():
    for seed in range(200):
        rng = random.Random(seed)
        wins = ((5.0, 15.0), (20.0, 30.0)) if seed % 2 else None
        ch, _ = make(
            delay_s=rng.choice([0.0, 0.5, 2.0]),
            jitter_s=rng.choice([0.0, 1.0]),
            loss_probability=rng.choice([0.0, 0.3, 1.0]),
            bit_error_rate=rng.choice([0.0, 1e-3]),
            bandwidth_bps=rng.choice([None, 800.0]),
            contact_windows=wins,
            max_in_flight=rng.choice([5, 1000]),
            seed=seed,
        )
        n = rng.randint(0, 60)
        for _ in range(n):
            ch.send(
                bytes(rng.randrange(256) for _ in range(rng.randint(0, 40))),
                now_s=rng.uniform(0, 40),
            )
            if rng.random() < 0.3:
                ch.deliver(rng.uniform(0, 45))
            st = ch.stats()
            assert st["sent"] == (
                st["delivered"] + st["lost"] + st["dropped_outside_window"] + st["in_flight"]
            )
        ch.deliver(INF)
        st = ch.stats()
        assert st["in_flight"] == 0
        assert st["sent"] == n
        assert st["sent"] == st["delivered"] + st["lost"] + st["dropped_outside_window"]


@pytest.mark.parametrize(
    "kw",
    [
        {"delay_s": -1.0},
        {"delay_s": float("nan")},
        {"jitter_s": -0.1},
        {"loss_probability": 1.1},
        {"loss_probability": -0.1},
        {"bit_error_rate": 2.0},
        {"bandwidth_bps": 0.0},
        {"bandwidth_bps": -5.0},
        {"max_in_flight": 0},
        {"contact_windows": ((5.0, 5.0),)},
        {"contact_windows": ((5.0, 3.0),)},
        {"contact_windows": ((1.0, 5.0), (4.0, 8.0))},  # sovrapposte
        {"contact_windows": ((10.0, 20.0), (1.0, 2.0))},  # non ordinate
        {"contact_windows": ((float("nan"), 2.0),)},
    ],
)
def test_invalid_config_rejected(kw):
    with pytest.raises(ValueError):
        ChannelConfig(**kw)


def test_invalid_send_arguments():
    ch, _ = make()
    with pytest.raises(TypeError):
        ch.send("text", now_s=0.0)
    with pytest.raises(ValueError):
        ch.send(b"x", now_s=float("nan"))
    with pytest.raises(ValueError):
        ch.deliver(float("nan"))


def test_sent_data_is_copied_not_aliased():
    ch, _ = make()
    buf = bytearray(b"abc")
    ch.send(buf, now_s=0.0)
    buf[0] = 0
    assert ch.deliver(INF) == [b"abc"]


@pytest.mark.parametrize("ber", [1e-310, 5e-324, 1e-13, 1e-12 / 2])
def test_subnormal_or_tiny_ber_rejected(ber):
    with pytest.raises(ValueError, match="bit_error_rate"):
        ChannelConfig(bit_error_rate=ber)


def test_minimum_ber_accepted_and_send_is_exception_safe(monkeypatch):
    ch, _ = make(bit_error_rate=1e-12, seed=1)
    ch.send(b"abc", now_s=0.0)
    assert ch.deliver(INF) == [b"abc"]

    # un errore interno in send non deve rompere la contabilita'
    import backend.net.channel as chmod

    ch, _ = make(bit_error_rate=0.5, seed=1)
    ch.send(b"ok", now_s=0.0)

    def boom(self, data):
        raise OverflowError("simulato")

    monkeypatch.setattr(chmod.SimChannel, "_flip_bits", boom)
    with pytest.raises(OverflowError):
        ch.send(b"bad", now_s=1.0)
    st = ch.stats()
    assert st["sent"] == 1 and st["in_flight"] == 1
    ch.deliver(INF)
    st = ch.stats()
    assert st["sent"] == st["delivered"] + st["lost"] + st["dropped_outside_window"]
