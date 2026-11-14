# SPDX-License-Identifier: Apache-2.0
"""AX.25 UI frame + FCS (CRC-16/X.25) + KISS (Task 19 step 5).

Fonti primarie lette il 2026-10-13:
- AX.25 Link Access Protocol v2.2 (rev. 10 settembre 2017),
  https://wiki.oarc.uk/_media/packet:ax25.2.2.10.pdf : sez. 3.12 codifica degli indirizzi
  (carattere << 1, SSID ottetto "CRRSSSS0"/"HRRSSSS1", bit di estensione LSB), Figura 3.4 (esempio
  NJ7P -> N7LEM), SSID 0xE0 / 0x61 come in figura. ERRATA TROVATA NEL DOCUMENTO: la figura 3.4 stampa
  0x98 (10011000) per la lettera 'N' (A1 e A8), ma 'N' = 0x4E e la regola di 3.12 (carattere
  spostato di 1 bit a sinistra) da' 0x9C; tutti gli altri ottetti della figura sono coerenti con la
  regola. Qui si usa 0x9C (regola), non il valore stampato,
  Figura (repeater) SSID 0xE3 = H=1 RR=11 SSID=1 ext=1, sez. 4.3.3.6 e tabella dei controlli: UI =
  000P/F0011 (0x03, 0x13 con P/F), sez. 3.4 PID 0xF0 = nessun layer 3, sez. 3.5 info 256 ottetti
  predefiniti, sez. 3.9 frame < 136 bit invalido, sez. 3.7 FCS secondo ISO 3309 (HDLC), 4.4.6 frame
  con FCS errato scartato.
- CRC-16/IBM-SDLC (X-25): catalogo RevEng, check("123456789") = 0x906E, residuo 0xF0B8.
- Ordine dei byte dell'FCS (byte basso per primo): RFC 1662 Appendice C (HDLC/PPP). NON verificato
  contro una cattura reale AX.25.
- KISS: https://www.ax25.net/kiss.aspx (i frame KISS trasportano l'AX.25 SENZA FCS).
"""

import itertools

import pytest

from backend.core.ports import ProtocolCodec
from backend.net.ax25 import (
    Ax25Address,
    Ax25Codec,
    Ax25UiFrame,
    crc16_x25,
    kiss_decode_frames,
    kiss_encode,
)
from backend.net.errors import CrcError, FramingError, ProtocolError
from backend.net.framing import FEND, FESC, KissFramer


def ref_crc16_x25(data: bytes) -> int:
    """Riferimento bit a bit INDIPENDENTE (poly riflesso 0x8408, init/xorout 0xFFFF)."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
    return crc ^ 0xFFFF


def test_crc16_x25_check_value_and_matches_reference():
    assert crc16_x25(b"123456789") == 0x906E  # catalogo RevEng CRC-16/IBM-SDLC
    assert ref_crc16_x25(b"123456789") == 0x906E
    assert crc16_x25(b"") == 0x0000
    for data in (b"\x00", b"\xff" * 5, bytes(range(256))):
        assert crc16_x25(data) == ref_crc16_x25(data)


def test_fcs_residue_property_low_byte_first():
    msg = b"\x01\x02hello"
    fcs = crc16_x25(msg)
    wire = msg + bytes([fcs & 0xFF, fcs >> 8])
    # registro (senza xorout) dopo un codeword valido = 0xF0B8 (residuo del catalogo / RFC 1662)
    assert crc16_x25(wire) ^ 0xFFFF == 0xF0B8


# --- Indirizzi ---


def test_address_vectors_from_spec_figure_3_4():
    dest = Ax25Address("NJ7P", 0)
    src = Ax25Address("N7LEM", 0)
    assert dest.encode(flag=True, last=False) == bytes.fromhex("9C 94 6E A0 40 40 E0")
    assert src.encode(flag=False, last=True) == bytes.fromhex("9C 6E 98 8A 9A 40 61")


def test_address_repeater_ssid_octet_0xe3():
    # N7OO-1 con H=1 (gia' ripetuto), ultimo indirizzo: 0xE3 = 1 11 0001 1
    raw = Ax25Address("N7OO", 1).encode(flag=True, last=True)
    assert raw[-1] == 0xE3
    assert raw[:4] == bytes([ord("N") << 1, ord("7") << 1, ord("O") << 1, ord("O") << 1])


@pytest.mark.parametrize(
    "call", ["", "TOOLONG1", "n7lem", "N7 EM", "N7-EM", "N7\x00", "ÀB", "A" * 7]
)
def test_invalid_callsigns_rejected(call):
    with pytest.raises(ProtocolError):
        Ax25Address(call, 0)


@pytest.mark.parametrize("ssid", [-1, 16, 255, "1", 1.5, True, None])
def test_invalid_ssid_rejected(ssid):
    with pytest.raises(ProtocolError):
        Ax25Address("N7LEM", ssid)


def test_address_parse_text_form():
    assert Ax25Address.parse("N7LEM-15") == Ax25Address("N7LEM", 15)
    assert Ax25Address.parse("NJ7P") == Ax25Address("NJ7P", 0)
    for bad in ["N7LEM-16", "N7LEM-", "-1", "N7LEM-A", "", "N7LEM-1-2", "n7lem"]:
        with pytest.raises(ProtocolError):
            Ax25Address.parse(bad)


def test_address_boundaries():
    Ax25Address("A", 0)
    Ax25Address("ABCDEF", 15)
    Ax25Address("123456", 7)


# --- Frame UI ---


def frame(**kw):
    base = {
        "destination": Ax25Address("NJ7P", 0),
        "source": Ax25Address("N7LEM", 0),
        "info": b"hi",
    }
    base.update(kw)
    return Ax25UiFrame(**base)


def test_ui_frame_vector_with_fcs():
    body = bytes.fromhex("9C 94 6E A0 40 40 E0 9C 6E 98 8A 9A 40 61 03 F0") + b"hi"
    fcs = ref_crc16_x25(body)
    expected = body + bytes([fcs & 0xFF, fcs >> 8])
    codec = Ax25Codec()
    assert isinstance(codec, ProtocolCodec)
    assert codec.encode(frame()) == expected
    assert codec.decode(expected) == frame()


def test_ui_frame_pf_bit_and_response_and_pid():
    codec = Ax25Codec()
    f = frame(poll_final=True, command=False, pid=0xCC)
    raw = codec.encode(f)
    assert raw[14] == 0x13  # UI con P/F
    assert raw[6] & 0x80 == 0 and raw[13] & 0x80 == 0x80  # risposta: C dest=0, C src=1
    assert codec.decode(raw) == f
    cmd = codec.encode(frame())
    assert cmd[6] & 0x80 == 0x80 and cmd[13] & 0x80 == 0  # comando: dest C=1, src C=0


def test_digipeaters_up_to_eight_and_h_bit_roundtrip():
    codec = Ax25Codec()
    digis = tuple(Ax25Address(f"RPT{i}", i) for i in range(8))
    f = frame(digipeaters=digis, repeated=(True, False) * 4)
    assert codec.decode(codec.encode(f)) == f
    with pytest.raises(ProtocolError):
        frame(digipeaters=digis + (Ax25Address("RPT9", 0),), repeated=(False,) * 9)
    with pytest.raises(ProtocolError):
        frame(digipeaters=digis[:2], repeated=(True,))  # lunghezza incoerente


def test_info_limits():
    codec = Ax25Codec()
    assert codec.decode(codec.encode(frame(info=b"x" * 256))).info == b"x" * 256
    assert codec.decode(codec.encode(frame(info=b""))).info == b""
    with pytest.raises(ProtocolError):
        codec.encode(frame(info=b"x" * 257))  # oltre il default 256, sez. 3.5
    big = Ax25Codec(max_info=512)
    assert big.decode(big.encode(frame(info=b"x" * 512))).info == b"x" * 512
    with pytest.raises(ProtocolError):
        codec.decode(big.encode(frame(info=b"x" * 300)))
    with pytest.raises(ValueError):
        Ax25Codec(max_info=0)


def test_truncated_and_garbage_inputs_only_protocolerror():
    codec = Ax25Codec()
    raw = codec.encode(frame())
    for n in range(len(raw)):
        with pytest.raises(ProtocolError):
            codec.decode(raw[:n])
    for bad in (None, "x", 3, [1]):
        with pytest.raises(ProtocolError):
            codec.decode(bad)
    with pytest.raises(ProtocolError):
        codec.encode("not a frame")


def fix_fcs(body: bytes) -> bytes:
    f = ref_crc16_x25(body)
    return body + bytes([f & 0xFF, f >> 8])


def test_structural_rejections_with_valid_fcs():
    codec = Ax25Codec()
    ok = bytes.fromhex("9C 94 6E A0 40 40 E0 9C 6E 98 8A 9A 40 61 03 F0") + b"hi"
    assert codec.decode(fix_fcs(ok)).info == b"hi"
    non_ui = bytearray(ok)
    non_ui[14] = 0x3E  # I-frame, non supportato
    with pytest.raises(ProtocolError, match="UI"):
        codec.decode(fix_fcs(bytes(non_ui)))
    no_end = bytearray(ok)
    no_end[13] &= 0xFE  # nessun bit di estensione: indirizzi che non finiscono
    with pytest.raises(ProtocolError):
        codec.decode(fix_fcs(bytes(no_end)))
    early_end = bytearray(ok)
    early_end[6] |= 1  # estensione gia' nella destinazione: manca la sorgente
    with pytest.raises(ProtocolError):
        codec.decode(fix_fcs(bytes(early_end)))
    low_bit = bytearray(ok)
    low_bit[2] |= 1  # bit di estensione dentro un carattere
    with pytest.raises(ProtocolError):
        codec.decode(fix_fcs(bytes(low_bit)))
    bad_char = bytearray(ok)
    bad_char[0] = ord("a") << 1  # minuscola
    with pytest.raises(ProtocolError):
        codec.decode(fix_fcs(bytes(bad_char)))
    space_mid = bytearray(ok)
    space_mid[1] = 0x40  # N, spazio, 7... -> spazio in mezzo
    with pytest.raises(ProtocolError):
        codec.decode(fix_fcs(bytes(space_mid)))
    blank = bytearray(ok)
    blank[0:6] = b"\x40" * 6  # nominativo vuoto
    with pytest.raises(ProtocolError):
        codec.decode(fix_fcs(bytes(blank)))
    # 9+ indirizzi di ripetitori: nessun fine indirizzo entro il massimo di 10
    too_many = b"\x98" * 6 + b"\xe0" + (b"\x98" * 6 + b"\x60") * 10 + b"\x03\xf0"
    with pytest.raises(ProtocolError):
        codec.decode(fix_fcs(too_many))


# --- CRC: corruzione bit per bit (esaustiva) ---


def test_every_single_bit_flip_detected_and_counted():
    codec = Ax25Codec()
    raw = codec.encode(frame(info=b"\x00\x01"))
    nbits = len(raw) * 8
    for bit in range(nbits):
        m = bytearray(raw)
        m[bit // 8] ^= 1 << (bit % 8)
        with pytest.raises(CrcError):
            codec.decode(bytes(m))
    assert codec.crc_errors == nbits
    assert codec.decode(raw) == frame(info=b"\x00\x01")  # il frame integro passa ancora


def test_every_double_bit_flip_detected_on_short_frame():
    codec = Ax25Codec()
    raw = codec.encode(frame(info=b"\x00"))
    nbits = len(raw) * 8
    for a, b in itertools.combinations(range(nbits), 2):
        m = bytearray(raw)
        m[a // 8] ^= 1 << (a % 8)
        m[b // 8] ^= 1 << (b % 8)
        with pytest.raises(CrcError):
            codec.decode(bytes(m))


def test_burst_errors_up_to_16_bits_detected():
    codec = Ax25Codec()
    raw = codec.encode(frame(info=b"burst"))
    for start in range(0, len(raw) * 8 - 16, 3):
        for width in (2, 5, 9, 16):
            m = bytearray(raw)
            for i in range(start, start + width):
                m[i // 8] ^= 1 << (i % 8)
            with pytest.raises(CrcError):
                codec.decode(bytes(m))


# --- KISS + AX.25 ---


def test_kiss_roundtrip_carries_frame_without_fcs():
    codec = Ax25Codec(with_fcs=False)
    f = frame(info=bytes([FEND, FESC, 0x00, 0xFF]))
    wire = kiss_encode(f)
    assert wire[0] == FEND and wire[-1] == FEND and wire[1] == 0x00  # comando dati porta 0
    assert kiss_decode_frames(wire)[0] == f
    assert Ax25Codec(with_fcs=False).decode(codec.encode(f)) == f


def test_kiss_stream_with_invalid_escape_drops_only_bad_frame():
    good = kiss_encode(frame(info=b"one"))
    bad = bytes([FEND, 0x00, 0x98, FESC, 0x41, 0x6E, FEND])  # FESC + 0x41: escape non valido
    framer = KissFramer(max_payload=400)
    payloads = framer.feed(good + bad + kiss_encode(frame(info=b"two")))
    assert framer.errors == 1
    assert [Ax25Codec(with_fcs=False).decode(p).info for p in payloads] == [b"one", b"two"]
    codec = Ax25Codec(with_fcs=False)
    frames = kiss_decode_frames(good + bad + good, codec=codec)
    assert len(frames) == 2


def test_kiss_decode_frames_counts_and_skips_undecodable_frames():
    codec = Ax25Codec(with_fcs=False)
    junk = bytes([FEND, 0x00]) + b"\x01\x02\x03" + bytes([FEND])
    frames = kiss_decode_frames(junk + kiss_encode(frame()), codec=codec)
    assert frames == [frame()]
    assert codec.rejected == 1


def test_kiss_encode_validates():
    with pytest.raises(FramingError):
        kiss_encode(frame(info=b"x" * 256), max_payload=10)
