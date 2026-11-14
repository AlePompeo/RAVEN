# SPDX-License-Identifier: Apache-2.0
"""Fix round 1: stato "dentro un frame", tetto sui byte scartati, politica dei frame vuoti."""

import pytest

from backend.net.ccsds import SpacePacketFramer
from backend.net.errors import FramingError
from backend.net.framing import (
    FEND,
    DelimiterFramer,
    KissFramer,
    LengthPrefixFramer,
    SlipFramer,
)

JUNK_FACTORIES = {
    "slip": lambda cap: SlipFramer(max_payload=16, max_discard_bytes=cap),
    "kiss": lambda cap: KissFramer(max_payload=16, max_discard_bytes=cap),
    "delim1": lambda cap: DelimiterFramer(b"\n", max_payload=16, max_discard_bytes=cap),
    "delim2": lambda cap: DelimiterFramer(b"\r\n", max_payload=16, max_discard_bytes=cap),
}


@pytest.mark.parametrize("name", JUNK_FACTORIES)
def test_junk_trickle_keeps_in_frame_and_hits_discard_cap(name):
    f = JUNK_FACTORIES[name](64)
    assert not f.in_frame and f.bytes_since_frame == 0
    total = 0
    with pytest.raises(FramingError, match="scart"):
        for _ in range(10_000):
            f.feed(b"A")  # rumore: oltre max_payload entra in stato di scarto (pending ~ 0)
            total += 1
            assert f.in_frame  # il timer di messaggio resta armato
    assert total <= 70
    with pytest.raises(FramingError):
        f.feed(b"x")  # rotto fino al reset
    f.reset()
    assert f.bytes_since_frame == 0 and not f.in_frame
    assert f.feed(f.encode(b"ok")) == [b"ok"]


@pytest.mark.parametrize("name", JUNK_FACTORIES)
def test_in_frame_clears_after_completed_frame_and_counts_trailing_bytes(name):
    f = JUNK_FACTORIES[name](4096)
    wire = f.encode(b"abc")
    assert f.feed(wire) == [b"abc"]
    assert not f.in_frame and f.bytes_since_frame == 0
    assert f.feed(wire + b"zz") == [b"abc"]
    assert f.in_frame and f.bytes_since_frame == 2


@pytest.mark.parametrize("name", ["slip", "kiss", "delim1"])
def test_empty_frames_do_not_reset_junk_counter(name):
    f = JUNK_FACTORIES[name](50)
    sep = b"\n" if name == "delim1" else bytes([FEND])
    with pytest.raises(FramingError):
        for _ in range(1000):
            f.feed(sep)
    assert f.empty_frames > 0


def test_length_prefix_in_frame_and_zero_length_policy():
    f = LengthPrefixFramer(2, max_payload=16)
    assert not f.in_frame
    f.feed(b"\x00")
    assert f.in_frame and f.bytes_since_frame == 1
    f.reset()
    with pytest.raises(FramingError, match="vuot"):
        f.feed(b"\x00\x00")
    with pytest.raises(FramingError):
        LengthPrefixFramer(1, max_payload=16).feed(bytes(16384))
    ok = LengthPrefixFramer(1, max_payload=16, allow_empty=True)
    assert ok.feed(b"\x00\x00\x00") == [b"", b"", b""]
    with pytest.raises(FramingError):
        LengthPrefixFramer(1, max_payload=16).encode(b"")
    assert ok.encode(b"") == b"\x00"


def test_default_discard_cap_scales_with_max_payload():
    f = SlipFramer(max_payload=64)
    f.feed(bytes([FEND, 0]))
    with pytest.raises(FramingError):
        for _ in range(100_000):
            f.feed(b"B" * 100)


def test_spacepacket_framer_exposes_in_frame():
    f = SpacePacketFramer(max_data_length=100)
    assert not f.in_frame
    f.feed(b"\x00")
    assert f.in_frame and f.bytes_since_frame == 1
