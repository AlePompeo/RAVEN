# SPDX-License-Identifier: Apache-2.0
"""Fix round 1: classificazione oversize per tipo, controllo dimensione prima della copia, bit
riservati AX.25 (spec 3.12.1/3.12.2: 'se non implementati, posti a uno')."""

import pytest

from backend.net.ax25 import Ax25Address, Ax25Codec, Ax25UiFrame, crc16_x25
from backend.net.ccsds import SpacePacket, SpacePacketCodec, SpacePacketFramer
from backend.net.csp import CspCodec
from backend.net.errors import FramingError, OversizeError, ProtocolError


def test_ccsds_oversize_is_classified_by_exception_type():
    small = SpacePacketCodec(max_data_length=4)
    big = SpacePacketCodec().encode(SpacePacket(apid=1, data=b"x" * 5))
    with pytest.raises(OversizeError):
        small.decode(big)
    with pytest.raises(ProtocolError) as ei:
        small.decode(bytes.fromhex("2000 0000 0000 00"))  # versione 1
    assert not isinstance(ei.value, OversizeError)
    f = SpacePacketFramer(max_data_length=4)
    with pytest.raises(FramingError):
        f.feed(big)
    assert f.oversize == 1
    f.reset()
    with pytest.raises(FramingError):
        f.feed(bytes.fromhex("2000 0000 0000 00"))
    assert f.oversize == 1  # la versione errata non e' oversize, anche se il testo contiene "max"


def test_csp_size_checked_before_copy():
    codec = CspCodec(max_data_length=8)

    big = memoryview(bytes(64))  # 64 > 4 + 8 + 4
    with pytest.raises(OversizeError):
        codec.decode(big)


def test_ax25_size_checked_before_copy_and_reserved_bits_policy():
    codec = Ax25Codec(max_info=8)
    with pytest.raises(OversizeError):
        codec.decode(memoryview(bytes(200)))
    good = Ax25Codec().encode(Ax25UiFrame(Ax25Address("N0CALL"), Ax25Address("N7LEM"), info=b"x"))
    body = bytearray(good[:-2])
    body[6] &= ~0x60  # bit R della destinazione a zero (uso "concordato")
    fcs = crc16_x25(bytes(body))
    raw = bytes(body) + bytes([fcs & 0xFF, fcs >> 8])
    tolerant = Ax25Codec()
    assert tolerant.decode(raw).info == b"x"  # accettato (uso concordato lecito)
    assert tolerant.nonstandard_reserved == 1
    assert Ax25Codec().decode(good).info == b"x"
    strict = Ax25Codec(strict_reserved=True)
    with pytest.raises(ProtocolError, match="riservati"):
        strict.decode(raw)
    assert strict.decode(good).info == b"x"
    assert good[6] & 0x60 == 0x60 and good[13] & 0x60 == 0x60  # l'encoder pone sempre R=11
