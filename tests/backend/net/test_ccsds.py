# SPDX-License-Identifier: Apache-2.0
"""Space Packet Protocol (Task 19 step 4).

Fonte primaria: CCSDS 133.0-B-2 "Space Packet Protocol", Blue Book, June 2020,
https://public.ccsds.org/Pubs/133x0b2e2.pdf (scaricato e letto il 2026-10-13). I numeri di sezione
citati sotto sono quelli del documento. I vettori sono costruiti A MANO dai campi, non generati
dal codice sotto test.

- 4.1.2.1/4.1.2.2: intestazione primaria 6 ottetti + campo dati 1..65536 ottetti; pacchetto 7..65542.
- 4.1.3.2: bit 0-2 versione, '000'.
- 4.1.3.3.2: bit 3 tipo (0 = TM, 1 = TC).
- 4.1.3.3.3: bit 4 flag intestazione secondaria; '0' per i pacchetti idle (4.1.3.3.3.4).
- 4.1.3.3.4: bit 5-15 APID; idle = '11111111111' (4.1.3.3.4.4).
- 4.1.3.4.2: bit 16-17 flag di sequenza ('01' primo, '00' continuazione, '10' ultimo, '11' non segmentato).
- 4.1.3.4.3: bit 18-31 conteggio di sequenza, modulo 16384 (4.1.3.4.3.4).
- 4.1.3.5: bit 32-47 lunghezza dati C = (ottetti del campo dati) - 1.
"""

import random

import pytest

from backend.core.ports import ProtocolCodec
from backend.net.ccsds import (
    IDLE_APID,
    MAX_APID,
    MAX_DATA_LENGTH,
    MAX_SEQUENCE_COUNT,
    PRIMARY_HEADER_LEN,
    SpacePacket,
    SpacePacketCodec,
    SpacePacketFramer,
    next_sequence_count,
)
from backend.net.errors import FramingError, ProtocolError

codec = SpacePacketCodec()


def test_constants_match_standard():
    assert PRIMARY_HEADER_LEN == 6  # 4.1.2.1 a)
    assert MAX_DATA_LENGTH == 65536  # 4.1.2.1 b)
    assert MAX_APID == 0x7FF == IDLE_APID  # 11 bit, 4.1.3.3.4.4
    assert MAX_SEQUENCE_COUNT == 16383  # 14 bit, 4.1.3.4.3.4
    assert isinstance(codec, ProtocolCodec)


# --- Vettori costruiti a mano ---


def test_vector_tm_minimal_one_octet_data():
    # versione 000, tipo 0, sec 0, APID 0x123 -> 0000 0001 0010 0011 = 0x0123
    # flag 11 (non segmentato) + conteggio 1 -> 1100 0000 0000 0001 = 0xC001
    # lunghezza dati: 1 ottetto -> C = 0 (4.1.3.5.3) = 0x0000
    p = SpacePacket(apid=0x123, packet_type=0, sequence_flags=3, sequence_count=1, data=b"\xaa")
    assert codec.encode(p) == bytes.fromhex("0123 C001 0000 AA")
    assert len(codec.encode(p)) == 7  # pacchetto minimo, 4.1.2.2


def test_vector_tc_with_secondary_header_flag_and_max_nonidle_apid():
    # tipo 1 (bit 3 -> 0x1000), flag sec (bit 4 -> 0x0800), APID 0x7FE -> 0x1FFE
    # flag di sequenza 01 (primo segmento), conteggio 0x2ABC -> 01 10 1010 1011 1100 = 0x6ABC
    # 4 ottetti di dati -> C = 3
    p = SpacePacket(
        apid=0x7FE,
        packet_type=1,
        secondary_header=True,
        sequence_flags=1,
        sequence_count=0x2ABC,
        data=b"\x01\x02\x03\x04",
    )
    raw = bytes.fromhex("1FFE 6ABC 0003 01020304")
    assert codec.encode(p) == raw
    assert codec.decode(raw) == p


def test_vector_idle_packet_apid_all_ones():
    # APID 0x7FF, sec 0 (4.1.3.3.3.4), TM: 0x07FF. Flag 11, conteggio 16383 -> 0xFFFF. 3 ottetti.
    p = SpacePacket(
        apid=0x7FF, packet_type=0, sequence_flags=3, sequence_count=16383, data=b"\x00\x00\x00"
    )
    assert p.is_idle
    assert codec.encode(p) == bytes.fromhex("07FF FFFF 0002 000000")
    assert codec.decode(bytes.fromhex("07FF FFFF 0002 000000")).is_idle


def test_idle_helper_builds_valid_idle_packet():
    p = SpacePacket.idle(data_length=10, sequence_count=5)
    assert p.is_idle and p.apid == 0x7FF and not p.secondary_header
    assert len(p.data) == 10
    assert codec.decode(codec.encode(p)) == p


def test_idle_packet_cannot_have_secondary_header():
    with pytest.raises(ProtocolError, match="idle"):
        SpacePacket(apid=0x7FF, secondary_header=True, data=b"x")
    with pytest.raises(ProtocolError, match="idle"):
        codec.decode(bytes.fromhex("0FFF C000 0000 00"))  # sec=1 + APID 0x7FF in ingresso


def test_vector_length_maximum_65536_octets():
    data = bytes(range(256)) * 256  # 65536 ottetti
    p = SpacePacket(apid=1, data=data)
    raw = codec.encode(p)
    assert raw[4:6] == b"\xff\xff"  # C = 65535
    assert len(raw) == 65542  # 4.1.2.2
    assert codec.decode(raw).data == data


def test_vector_apid_zero_and_count_zero():
    p = SpacePacket(apid=0, sequence_flags=0, sequence_count=0, data=b"z")
    assert codec.encode(p) == bytes.fromhex("0000 0000 0000 7A")


def test_sequence_flags_all_values():
    for flags, bits in [(0, 0x0000), (1, 0x4000), (2, 0x8000), (3, 0xC000)]:
        raw = codec.encode(SpacePacket(apid=5, sequence_flags=flags, data=b"a"))
        assert int.from_bytes(raw[2:4], "big") == bits


def test_sequence_count_wraparound_modulo_16384():
    assert next_sequence_count(0) == 1
    assert next_sequence_count(16382) == 16383
    assert next_sequence_count(16383) == 0  # 4.1.3.4.3.4
    p = SpacePacket(apid=1, sequence_count=16383, data=b"a")
    assert codec.decode(codec.encode(p)).sequence_count == 16383
    with pytest.raises(ProtocolError):
        SpacePacket(apid=1, sequence_count=16384, data=b"a")


# --- Validazione dei campi ---


@pytest.mark.parametrize(
    "kw",
    [
        {"apid": -1},
        {"apid": 0x800},
        {"apid": "1"},
        {"apid": True},
        {"apid": 1.0},
        {"packet_type": 2},
        {"sequence_flags": 4},
        {"sequence_flags": -1},
        {"sequence_count": -1},
        {"sequence_count": 1 << 14},
        {"data": b""},  # almeno 1 ottetto, 4.1.4.1.2
        {"data": b"x" * 65537},  # oltre 65536
        {"data": "str"},
        {"data": None},
        {"version": 1},
        {"secondary_header": 1},
    ],
)
def test_invalid_fields_raise_only_protocolerror(kw):
    base = {"apid": 1, "data": b"x"}
    base.update(kw)
    with pytest.raises(ProtocolError):
        SpacePacket(**base)


def test_packet_is_immutable_and_hashable():
    p = SpacePacket(apid=1, data=b"x")
    with pytest.raises(AttributeError):
        p.apid = 2  # type: ignore[misc]
    assert hash(p) == hash(SpacePacket(apid=1, data=b"x"))


# --- Ingresso ostile ---


def test_truncated_inputs_rejected():
    raw = codec.encode(SpacePacket(apid=3, data=b"abcdef"))
    for n in range(len(raw)):
        with pytest.raises(ProtocolError):
            codec.decode(raw[:n])


def test_trailing_bytes_rejected_by_strict_decode_but_reported_by_stream_api():
    raw = codec.encode(SpacePacket(apid=3, data=b"abc"))
    with pytest.raises(ProtocolError, match="trailing"):
        codec.decode(raw + b"\x00")
    pkt, used = codec.decode_prefix(raw + b"\x00\x01")
    assert used == len(raw) and pkt.data == b"abc"


def test_version_not_zero_rejected():
    raw = bytearray(codec.encode(SpacePacket(apid=3, data=b"a")))
    for v in range(1, 8):
        raw[0] = (raw[0] & 0x1F) | (v << 5)
        with pytest.raises(ProtocolError, match="version"):
            codec.decode(bytes(raw))


def test_oversize_declared_length_rejected_before_use_with_configured_cap():
    small = SpacePacketCodec(max_data_length=16)
    ok = codec.encode(SpacePacket(apid=1, data=b"x" * 16))
    assert small.decode(ok).data == b"x" * 16
    big = codec.encode(SpacePacket(apid=1, data=b"x" * 17))
    with pytest.raises(ProtocolError, match="max"):
        small.decode(big)
    # solo l'intestazione basta per rifiutare: nessun accesso al corpo
    with pytest.raises(ProtocolError, match="max"):
        small.decode(big[:6] + b"")
    with pytest.raises(ProtocolError):
        small.encode(SpacePacket(apid=1, data=b"x" * 17))
    with pytest.raises(ValueError):
        SpacePacketCodec(max_data_length=0)
    with pytest.raises(ValueError):
        SpacePacketCodec(max_data_length=65537)


@pytest.mark.parametrize("bad", [None, "abc", 12, [1, 2], 3.5, object()])
def test_decode_non_bytes_raises_protocolerror(bad):
    with pytest.raises(ProtocolError):
        codec.decode(bad)


def test_encode_wrong_type_raises_protocolerror():
    with pytest.raises(ProtocolError):
        codec.encode({"apid": 1})


def test_decode_accepts_bytearray_and_memoryview():
    raw = codec.encode(SpacePacket(apid=9, data=b"hi"))
    assert codec.decode(bytearray(raw)) == codec.decode(memoryview(raw))


# --- Proprieta': decode(encode(x)) == x e nessuna eccezione diversa da ProtocolError ---


def random_packet(rng):
    apid = rng.choice([0, 1, 0x7FE, 0x7FF, rng.randrange(0x800)])
    idle = apid == 0x7FF
    size = rng.choice([1, 2, 7, 255, 256, rng.randint(1, 3000)])
    return SpacePacket(
        apid=apid,
        packet_type=rng.randrange(2),
        secondary_header=False if idle else bool(rng.randrange(2)),
        sequence_flags=rng.randrange(4),
        sequence_count=rng.choice([0, 16383, rng.randrange(16384)]),
        data=bytes(rng.randrange(256) for _ in range(size)),
    )


def test_property_roundtrip_seeded():
    rng = random.Random(20261013)
    for _ in range(2000):
        p = random_packet(rng)
        raw = codec.encode(p)
        assert len(raw) == 6 + len(p.data)
        assert codec.decode(raw) == p
        assert codec.encode(codec.decode(raw)) == raw


def test_property_random_bytes_only_protocolerror():
    rng = random.Random(5)
    decoded = 0
    for _ in range(5000):
        raw = bytes(rng.randrange(256) for _ in range(rng.randint(0, 40)))
        try:
            p = codec.decode(raw)
        except ProtocolError:
            continue
        decoded += 1
        assert codec.encode(p) == raw  # se decodifica, e' canonico
    # sanity: la maggior parte dei byte casuali e' rifiutata (versione/lunghezza incoerenti)
    assert decoded < 500


def test_property_every_single_bit_flip_in_header_never_crashes():
    raw = codec.encode(SpacePacket(apid=0x155, sequence_count=77, data=b"payload!"))
    for bit in range(48):
        m = bytearray(raw)
        m[bit // 8] ^= 1 << (bit % 8)
        try:
            codec.decode(bytes(m))
        except ProtocolError:
            pass


# --- Framer con lunghezza dall'intestazione (spec 15.2) ---


def test_stream_framer_byte_at_a_time_and_many_in_one_chunk():
    rng = random.Random(11)
    pkts = [random_packet(rng) for _ in range(40)]
    wire = b"".join(codec.encode(p) for p in pkts)
    f = SpacePacketFramer(max_data_length=4096)
    assert [codec.decode(x) for x in f.feed(wire)] == pkts
    f.reset()
    got = []
    for i in range(len(wire)):
        got += f.feed(wire[i : i + 1])
    assert [codec.decode(x) for x in got] == pkts
    assert f.pending == 0


def test_stream_framer_rejects_bad_version_and_oversize_header_without_buffering():
    f = SpacePacketFramer(max_data_length=100)
    with pytest.raises(FramingError):
        f.feed(bytes.fromhex("2000 0000 0000 00"))  # versione 1
    f.reset()
    with pytest.raises(FramingError):
        f.feed(bytes.fromhex("0001 C000 FFFF"))  # dichiara 65536 > 100: rifiutato sull'intestazione
    assert f.pending == 0
    with pytest.raises(FramingError):
        f.feed(b"\x00")  # rotto finche' non c'e' reset()
    f.reset()
    assert f.feed(codec.encode(SpacePacket(apid=1, data=b"ok"))) != []


def test_stream_framer_truncated_stream_yields_nothing():
    f = SpacePacketFramer(max_data_length=100)
    raw = codec.encode(SpacePacket(apid=1, data=b"abcdef"))
    assert f.feed(raw[:-1]) == []
    assert f.pending == len(raw) - 1
