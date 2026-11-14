# SPDX-License-Identifier: Apache-2.0
"""Framer incrementali (Task 19 step 3). Riferimenti primari verificati il 2026-10-13:
- SLIP: RFC 1055 (END=0xC0, ESC=0xDB, ESC_END=0xDC, ESC_ESC=0xDD).
- KISS: Chepponis & Karn 1987, https://www.ax25.net/kiss.aspx (FEND/FESC/TFEND/TFESC = C0/DB/DC/DD,
  byte di comando con porta nel nibble alto e comando nel basso; comando 0 = dati; due FEND
  consecutivi non delimitano un frame vuoto; FESC seguito da altro = errore).
Lunghezza con prefisso e delimitatore non sono standard: definizioni locali (docs/net.md).
"""

import random
import tracemalloc

import pytest

from backend.core.ports import Framer
from backend.net.errors import FramingError, ProtocolError
from backend.net.framing import (
    FEND,
    FESC,
    TFEND,
    TFESC,
    DelimiterFramer,
    KissFramer,
    LengthPrefixFramer,
    SlipFramer,
)

MAXP = 64

FACTORIES = {
    "len1": lambda: LengthPrefixFramer(1, max_payload=MAXP),
    "len2": lambda: LengthPrefixFramer(2, max_payload=MAXP),
    "len4": lambda: LengthPrefixFramer(4, max_payload=MAXP),
    "delim": lambda: DelimiterFramer(b"\r\n", max_payload=MAXP),
    "slip": lambda: SlipFramer(max_payload=MAXP),
    "kiss": lambda: KissFramer(max_payload=MAXP),
}


def payloads(rng, n=30, delim_safe=False):
    out = []
    for _ in range(n):
        size = rng.randint(1, MAXP)
        p = bytes(rng.randrange(256) for _ in range(size))
        if delim_safe:
            p = p.replace(b"\r", b"x").replace(b"\n", b"y")
        out.append(p)
    return out


def corpus(name):
    return payloads(random.Random(1234), delim_safe=(name == "delim"))


@pytest.mark.parametrize("name", FACTORIES)
def test_satisfies_framer_port(name):
    assert isinstance(FACTORIES[name](), Framer)


@pytest.mark.parametrize("name", FACTORIES)
def test_roundtrip_whole_byte_at_a_time_and_random_chunks(name):
    msgs = corpus(name)
    f = FACTORIES[name]()
    wire = b"".join(f.encode(m) for m in msgs)
    assert f.feed(wire) == msgs  # tutto in un solo chunk (molti messaggi per segmento)
    f.reset()
    got = []
    for i in range(len(wire)):  # un byte alla volta
        got += f.feed(wire[i : i + 1])
    assert got == msgs
    assert f.pending == 0
    rng = random.Random(7)
    for _ in range(20):  # frammentazione arbitraria
        f.reset()
        got, i = [], 0
        while i < len(wire):
            n = rng.randint(1, 17)
            got += f.feed(wire[i : i + n])
            i += n
        assert got == msgs


@pytest.mark.parametrize("name", FACTORIES)
def test_truncated_stream_yields_nothing_and_reset_discards(name):
    f = FACTORIES[name]()
    wire = f.encode(b"abcdef")
    # per SLIP/KISS il terminatore e' l'ultimo byte: senza di esso il frame non e' completo
    cut = wire[:-1] if name in ("slip", "kiss", "delim") else wire[:-2]
    assert f.feed(cut) == []
    assert f.pending > 0
    f.reset()
    assert f.pending == 0
    assert f.feed(f.encode(b"ok")) == [b"ok"]


@pytest.mark.parametrize("width,huge", [(1, 255), (2, 65535), (4, 2**32 - 1), (4, 2**31)])
def test_declared_length_huge_rejected_without_allocating(width, huge):
    f = LengthPrefixFramer(width, max_payload=MAXP)
    header = huge.to_bytes(width, "big")
    tracemalloc.start()
    try:
        with pytest.raises(FramingError):
            f.feed(header)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 64 * 1024
    assert f.pending <= width
    # il flusso e' irrecuperabile: finche' non si fa reset() continua a rifiutare
    with pytest.raises(FramingError):
        f.feed(b"\x00")
    f.reset()
    assert f.feed(f.encode(b"x")) == [b"x"]


def test_length_prefix_boundaries_and_encode_limits():
    f = LengthPrefixFramer(1, max_payload=255, allow_empty=True)
    assert f.feed(f.encode(b"")) == [b""]
    assert f.feed(f.encode(b"a" * 255)) == [b"a" * 255]
    with pytest.raises(FramingError):
        f.encode(b"a" * 256)
    g = LengthPrefixFramer(2, max_payload=MAXP)
    with pytest.raises(FramingError):
        g.encode(b"a" * (MAXP + 1))
    with pytest.raises(ValueError):
        LengthPrefixFramer(3, max_payload=10)  # larghezze ammesse: 1, 2, 4
    with pytest.raises(ValueError):
        LengthPrefixFramer(1, max_payload=256)  # non rappresentabile in 1 byte


def test_length_prefix_exactly_at_limit_ok_and_one_over_rejected():
    f = LengthPrefixFramer(2, max_payload=10)
    assert f.feed((10).to_bytes(2, "big") + b"x" * 10) == [b"x" * 10]
    with pytest.raises(FramingError):
        f.feed((11).to_bytes(2, "big"))


def test_delimiter_overflow_discards_until_delimiter_and_resyncs():
    f = DelimiterFramer(b"\n", max_payload=8)
    out = f.feed(b"x" * 1000)
    assert out == [] and f.pending <= 9
    out = f.feed(b"y" * 1000 + b"\nok\n")
    assert out == [b"ok"]
    assert f.errors == 1 and f.oversize == 1


def test_delimiter_multibyte_split_across_chunks_and_empty_frames_skipped():
    f = DelimiterFramer(b"\r\n", max_payload=MAXP)
    assert f.feed(b"abc\r") == []
    assert f.feed(b"\n\r\n\r\ndef\r\n") == [b"abc", b"def"]  # frame vuoti ignorati


def test_delimiter_rejects_bad_config_and_payload_with_delimiter():
    with pytest.raises(ValueError):
        DelimiterFramer(b"", max_payload=5)
    f = DelimiterFramer(b"\n", max_payload=5)
    with pytest.raises(FramingError):
        f.encode(b"a\nb")


def test_slip_escape_vectors_rfc1055():
    f = SlipFramer(max_payload=MAXP)
    assert f.encode(b"\xc0") == bytes([FEND, FESC, TFEND, FEND])
    assert f.encode(b"\xdb") == bytes([FEND, FESC, TFESC, FEND])
    assert f.feed(bytes([FEND, 1, FESC, TFEND, FESC, TFESC, 2, FEND])) == [b"\x01\xc0\xdb\x02"]
    assert (FEND, FESC, TFEND, TFESC) == (0xC0, 0xDB, 0xDC, 0xDD)


@pytest.mark.parametrize("cls", [SlipFramer, KissFramer])
def test_invalid_escape_discards_frame_counts_and_resyncs(cls):
    f = cls(max_payload=MAXP)
    cmd = b"\x00" if cls is KissFramer else b""
    bad = bytes([FEND]) + cmd + b"a" + bytes([FESC, 0x41]) + b"b" + bytes([FEND])
    good = bytes([FEND]) + cmd + b"good" + bytes([FEND])
    assert f.feed(bad + good) == [b"good"]
    assert f.errors == 1
    # FESC subito prima della fine frame e' pure invalido
    f2 = cls(max_payload=MAXP)
    assert f2.feed(bytes([FEND]) + cmd + b"a" + bytes([FESC, FEND]) + good) == [b"good"]
    assert f2.errors == 1


@pytest.mark.parametrize("cls", [SlipFramer, KissFramer])
def test_resync_after_garbage_and_repeated_fend(cls):
    f = cls(max_payload=MAXP)
    wire = f.encode(b"payload")
    # i FEND consecutivi non sono frame vuoti; il rumore prima del primo FEND e' un frame sporco
    # che i livelli superiori (CRC) devono scartare: qui verifichiamo che il frame buono arrivi.
    out = f.feed(b"\x01\x02\x03" + bytes([FEND, FEND, FEND]) + wire + wire)
    assert out[-2:] == [b"payload", b"payload"]
    assert len(out) <= 3


@pytest.mark.parametrize("cls", [SlipFramer, KissFramer])
def test_oversize_frame_discarded_bounded_memory_then_resync(cls):
    f = cls(max_payload=16)
    cmd = b"\x00" if cls is KissFramer else b""
    out = []
    tracemalloc.start()
    try:
        out += f.feed(bytes([FEND]) + cmd)
        for _ in range(1):  # < tetto dei byte scartati (default 4*max+1024)
            out += f.feed(b"A" * 1000)
            assert f.pending <= 17
        out += f.feed(bytes([FEND]) + bytes([FEND]) + cmd + b"fine" + bytes([FEND]))
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert out == [b"fine"]
    assert f.oversize == 1
    assert peak < 256 * 1024


def test_kiss_command_byte_and_non_data_frames():
    f = KissFramer(max_payload=MAXP)
    assert f.encode(b"hi") == bytes([FEND, 0x00]) + b"hi" + bytes([FEND])
    assert f.encode(b"hi", port=3) == bytes([FEND, 0x30]) + b"hi" + bytes([FEND])
    # comando 1 (TXDELAY) non e' un frame dati: ignorato e contato; poi un frame dati porta 2
    wire = bytes([FEND, 0x01, 0x28, FEND, FEND, 0x20]) + b"data" + bytes([FEND])
    assert f.feed(wire) == [b"data"]
    assert f.ignored_commands == 1
    with pytest.raises(ValueError):
        f.encode(b"x", port=16)


def test_kiss_data_with_special_bytes_roundtrip():
    f = KissFramer(max_payload=MAXP)
    p = bytes([FEND, FESC, TFEND, TFESC, 0, 255])
    assert f.feed(f.encode(p)) == [p]


@pytest.mark.parametrize("name", FACTORIES)
def test_garbage_never_raises_other_than_protocolerror(name):
    rng = random.Random(99)
    f = FACTORIES[name]()
    for _ in range(300):
        chunk = bytes(rng.randrange(256) for _ in range(rng.randint(0, 40)))
        try:
            f.feed(chunk)
        except ProtocolError:
            f.reset()
        assert f.pending <= 4 + MAXP + 1
