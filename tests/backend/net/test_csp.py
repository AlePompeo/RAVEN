# SPDX-License-Identifier: Apache-2.0
"""CubeSat Space Protocol v1 (Task 19 step 5).

Fonte: libcsp (LGPL-2.1, solo LETTA per verificare il layout: nessun codice copiato), tag v1.6:
- include/csp/csp_types.h: CSP_ID_PRIO_SIZE 2, HOST 5, PORT 6, FLAGS 8; maschere con shift:
  pri bit 30-31, src 25-29, dst 20-24, dport 14-19, sport 8-13, flags 0-7;
  flag: CSP_FHMAC 0x08, CSP_FXTEA 0x04, CSP_FRDP 0x02, CSP_FCRC32 0x01; priorita' 0 critical,
  1 high, 2 norm, 3 low.
- src/interfaces/csp_if_kiss.c: intestazione inviata in ordine di rete (csp_hton32, big-endian);
  CRC32 aggiunto in coda ai dati; KISS FEND/FESC/TFEND/TFESC = C0/DB/DC/DD.
- src/csp_crc32.c: CRC-32 riflesso init 0xFFFFFFFF xorout 0xFFFFFFFF con tabella Castagnoli
  (CRC-32C, poly 0x1EDC6F41), 4 byte big-endian in coda; calcolato sui soli dati per
  compatibilita' con csp1.x (csp_io.c: "does not include header").
- CRC-32/ISCSI nel catalogo RevEng: check("123456789") = 0xE3069283.
NON c'e' uno standard formale pubblico equivalente a un Blue Book: la fonte e' l'implementazione di
riferimento. Non verificato: interoperabilita' con un nodo CSP reale.
"""

import random

import pytest

from backend.core.ports import ProtocolCodec
from backend.net.csp import (
    CSP_FCRC32,
    CSP_FHMAC,
    CSP_FRDP,
    CSP_FXTEA,
    CspCodec,
    CspPacket,
    crc32c,
)
from backend.net.errors import CrcError, ProtocolError


def ref_crc32c(data: bytes) -> int:
    crc = 0xFFFFFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0x82F63B78 if crc & 1 else crc >> 1
    return crc ^ 0xFFFFFFFF


def test_flag_values_match_libcsp_v1():
    assert (CSP_FHMAC, CSP_FXTEA, CSP_FRDP, CSP_FCRC32) == (0x08, 0x04, 0x02, 0x01)


def test_crc32c_check_value_and_reference():
    assert crc32c(b"123456789") == 0xE3069283
    assert ref_crc32c(b"123456789") == 0xE3069283
    rng = random.Random(1)
    for _ in range(50):
        d = bytes(rng.randrange(256) for _ in range(rng.randint(0, 64)))
        assert crc32c(d) == ref_crc32c(d)


def test_header_vector_built_by_hand():
    # pri=2 -> 0x80000000 ; src=5 -> 5<<25 = 0x0A000000 ; dst=10 -> 10<<20 = 0x00A00000
    # dport=7 -> 7<<14 = 0x0001C000 ; sport=48 -> 48<<8 = 0x00003000 ; flags=0
    # somma 0x8AA1F000 -> byte di rete 8A A1 F0 00
    p = CspPacket(
        priority=2, source=5, destination=10, destination_port=7, source_port=48, data=b"\x01\x02"
    )
    codec = CspCodec()
    assert isinstance(codec, ProtocolCodec)
    assert codec.encode(p) == bytes.fromhex("8AA1F000 0102")
    assert codec.decode(bytes.fromhex("8AA1F000 0102")) == p


def test_header_field_extremes():
    p = CspPacket(
        priority=3,
        source=31,
        destination=31,
        destination_port=63,
        source_port=63,
        flags=0x00,
        data=b"",
    )
    # pri 3 -> C0000000 ; src 31<<25 = 3E000000 ; dst 31<<20 = 01F00000 ; dport 63<<14 = 000FC000
    # sport 63<<8 = 00003F00 -> FFFFFF00
    assert CspCodec().encode(p) == bytes.fromhex("FFFFFF00")
    assert CspCodec().decode(bytes.fromhex("FFFFFF00")) == p
    z = CspPacket(priority=0, source=0, destination=0, destination_port=0, source_port=0, data=b"")
    assert CspCodec().encode(z) == bytes(4)


def test_crc32_flag_appends_big_endian_crc32c_over_data_only():
    codec = CspCodec()
    p = CspPacket(
        priority=2,
        source=1,
        destination=2,
        destination_port=3,
        source_port=4,
        flags=CSP_FCRC32,
        data=b"123456789",
    )
    raw = codec.encode(p)
    assert raw[:4] == ((2 << 30) | (1 << 25) | (2 << 20) | (3 << 14) | (4 << 8) | 1).to_bytes(
        4, "big"
    )
    assert raw[4:13] == b"123456789"
    assert raw[13:] == bytes.fromhex("E3069283")  # big-endian, check value CRC-32C
    assert codec.decode(raw) == p


@pytest.mark.parametrize("flag", [CSP_FHMAC, CSP_FXTEA])
def test_unsupported_security_flags_rejected(flag):
    codec = CspCodec()
    with pytest.raises(ProtocolError, match="non supportat"):
        codec.encode(CspPacket(1, 1, 1, 1, 1, flag, b"x"))
    raw = bytes.fromhex("8AA1F000")[:3] + bytes([flag]) + b"data"
    with pytest.raises(ProtocolError, match="non supportat"):
        codec.decode(raw)


def test_reserved_flag_bits_rejected():
    codec = CspCodec()
    for bit in (0x10, 0x20, 0x40, 0x80):
        with pytest.raises(ProtocolError):
            CspPacket(1, 1, 1, 1, 1, bit, b"x")
        with pytest.raises(ProtocolError):
            codec.decode(bytes([0x00, 0x00, 0x00, bit]) + b"x")


def test_rdp_flag_is_passed_through_opaque():
    p = CspPacket(1, 1, 2, 3, 4, CSP_FRDP, b"rdp-header-and-data")
    assert CspCodec().decode(CspCodec().encode(p)) == p


@pytest.mark.parametrize(
    "kw",
    [
        {"priority": 4},
        {"priority": -1},
        {"source": 32},
        {"destination": 32},
        {"destination_port": 64},
        {"source_port": 64},
        {"flags": 256},
        {"priority": "1"},
        {"source": None},
        {"data": "x"},
        {"data": None},
        {"priority": True},
    ],
)
def test_invalid_fields_rejected(kw):
    base = {
        "priority": 1,
        "source": 1,
        "destination": 1,
        "destination_port": 1,
        "source_port": 1,
        "data": b"x",
    }
    base.update(kw)
    with pytest.raises(ProtocolError):
        CspPacket(**base)


def test_truncated_and_oversize_and_wrong_types():
    codec = CspCodec(max_data_length=8)
    for n in range(4):
        with pytest.raises(ProtocolError):
            codec.decode(bytes(n))
    with pytest.raises(ProtocolError, match="max"):
        codec.decode(bytes(4) + b"x" * 9)
    with pytest.raises(ProtocolError, match="max"):
        codec.encode(CspPacket(1, 1, 1, 1, 1, 0, b"x" * 9))
    for bad in (None, "s", 5, [1]):
        with pytest.raises(ProtocolError):
            codec.decode(bad)
    with pytest.raises(ProtocolError):
        codec.encode("x")
    with pytest.raises(ValueError):
        CspCodec(max_data_length=-1)


def test_crc32_trailer_missing_or_short_rejected():
    codec = CspCodec()
    hdr = bytes.fromhex("8AA1F001")
    for tail in (b"", b"\x01\x02\x03"):
        with pytest.raises(ProtocolError):
            codec.decode(hdr + tail)


def test_every_single_bit_flip_in_data_or_crc_detected_header_not_covered():
    codec = CspCodec()
    p = CspPacket(2, 1, 2, 3, 4, CSP_FCRC32, b"\x10\x20\x30")
    raw = codec.encode(p)
    detected = 0
    for bit in range(32, len(raw) * 8):  # dati + trailer CRC
        m = bytearray(raw)
        m[bit // 8] ^= 1 << (bit % 8)
        with pytest.raises(CrcError):
            codec.decode(bytes(m))
        detected += 1
    assert codec.crc_errors == detected
    # l'intestazione NON e' coperta dal CRC (compatibilita' csp1.x): limite dichiarato
    m = bytearray(raw)
    m[1] ^= 0x01  # cambia source/dst senza toccare i flag
    assert codec.decode(bytes(m)) != p


def test_property_roundtrip_seeded():
    rng = random.Random(77)
    codec = CspCodec()
    for _ in range(1000):
        p = CspPacket(
            priority=rng.randrange(4),
            source=rng.randrange(32),
            destination=rng.randrange(32),
            destination_port=rng.randrange(64),
            source_port=rng.randrange(64),
            flags=rng.choice([0, CSP_FCRC32, CSP_FRDP, CSP_FRDP | CSP_FCRC32]),
            data=bytes(rng.randrange(256) for _ in range(rng.randint(0, 100))),
        )
        assert codec.decode(codec.encode(p)) == p


def test_random_bytes_only_protocolerror():
    rng = random.Random(3)
    codec = CspCodec()
    for _ in range(3000):
        raw = bytes(rng.randrange(256) for _ in range(rng.randint(0, 30)))
        try:
            codec.decode(raw)
        except ProtocolError:
            pass
