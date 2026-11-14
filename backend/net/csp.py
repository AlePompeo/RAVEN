# SPDX-License-Identifier: Apache-2.0
"""CubeSat Space Protocol (CSP) v1: intestazione a 32 bit e CRC32 opzionale. Codec minimale.

Layout letto (non copiato) dal sorgente di riferimento libcsp tag v1.6 (LGPL-2.1,
https://github.com/libcsp/libcsp): `include/csp/csp_types.h`, `src/interfaces/csp_if_kiss.c`,
`src/csp_crc32.c`, `src/csp_io.c`. NON esiste un Blue Book equivalente; l'interoperabilita' con
un nodo CSP reale NON e' stata verificata.

    bit 30-31 priorita' (0 critical, 1 high, 2 norm, 3 low)
    bit 25-29 sorgente (5 bit)       bit 20-24 destinazione (5 bit)
    bit 14-19 porta destinazione     bit 8-13  porta sorgente (6 bit ciascuna)
    bit 0-7   flag: HMAC 0x08, XTEA 0x04, RDP 0x02, CRC32 0x01 (bit 4-7 riservati)

Intestazione in ordine di rete (big-endian). Con il flag CRC32 in coda ai dati ci sono 4 byte:
CRC-32C (Castagnoli, riflesso, init/xorout 0xFFFFFFFF) big-endian, calcolato sui SOLI dati (come
csp1.x): una corruzione dell'intestazione non e' rilevata da questo CRC (limite dichiarato).
HMAC e XTEA non sono implementati e i pacchetti che li usano sono rifiutati (non si
interpretano dati cifrati/autenticati come in chiaro). RDP e' un flag passato in modo opaco.
"""

from dataclasses import dataclass

from backend.net.errors import CrcError, OversizeError, ProtocolError

CSP_FCRC32 = 0x01
CSP_FRDP = 0x02
CSP_FXTEA = 0x04
CSP_FHMAC = 0x08
_KNOWN_FLAGS = CSP_FCRC32 | CSP_FRDP | CSP_FXTEA | CSP_FHMAC
HEADER_LEN = 4


def _make_table() -> tuple[int, ...]:
    table = []
    for i in range(256):
        crc = i
        for _ in range(8):
            crc = (crc >> 1) ^ 0x82F63B78 if crc & 1 else crc >> 1
        table.append(crc)
    return tuple(table)


_TABLE = _make_table()


def crc32c(data: bytes) -> int:
    """CRC-32C (CRC-32/ISCSI): check("123456789") = 0xE3069283."""
    crc = 0xFFFFFFFF
    for b in data:
        crc = _TABLE[(crc ^ b) & 0xFF] ^ (crc >> 8)
    return crc ^ 0xFFFFFFFF


def _int_in(v: object, hi: int, name: str) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= hi:
        raise ProtocolError(f"{name}: intero 0..{hi}")
    return v


@dataclass(frozen=True)
class CspPacket:
    priority: int
    source: int
    destination: int
    destination_port: int
    source_port: int
    flags: int = 0
    data: bytes = b""

    def __post_init__(self) -> None:
        _int_in(self.priority, 3, "priority")
        _int_in(self.source, 31, "source")
        _int_in(self.destination, 31, "destination")
        _int_in(self.destination_port, 63, "destination_port")
        _int_in(self.source_port, 63, "source_port")
        _int_in(self.flags, 255, "flags")
        if self.flags & ~_KNOWN_FLAGS:
            raise ProtocolError("flags: bit riservati (0xF0) non ammessi")
        if not isinstance(self.data, bytes):
            raise ProtocolError("data: bytes")


class CspCodec:
    """Codec CSP v1 (implementa `ProtocolCodec`). `crc_errors`/`rejected` sono contatori."""

    def __init__(self, max_data_length: int = 1024) -> None:
        if max_data_length < 0:
            raise ValueError("max_data_length >= 0")
        self.max_data_length = max_data_length
        self.crc_errors = 0
        self.rejected = 0

    def encode(self, message: CspPacket) -> bytes:
        if not isinstance(message, CspPacket):
            raise ProtocolError("encode accetta solo CspPacket")
        if message.flags & (CSP_FHMAC | CSP_FXTEA):
            raise ProtocolError("flag HMAC/XTEA non supportati")
        if len(message.data) > self.max_data_length:
            raise OversizeError(f"dati oltre il max {self.max_data_length}")
        header = (
            (message.priority << 30)
            | (message.source << 25)
            | (message.destination << 20)
            | (message.destination_port << 14)
            | (message.source_port << 8)
            | message.flags
        )
        out = header.to_bytes(4, "big") + message.data
        if message.flags & CSP_FCRC32:
            out += crc32c(message.data).to_bytes(4, "big")
        return out

    def decode(self, data: bytes | bytearray | memoryview) -> CspPacket:
        try:
            return self._decode(data)
        except CrcError:
            self.crc_errors += 1
            raise
        except ProtocolError:
            self.rejected += 1
            raise

    def _decode(self, data: bytes | bytearray | memoryview) -> CspPacket:
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise ProtocolError("decode accetta bytes, bytearray o memoryview")
        if len(data) > HEADER_LEN + self.max_data_length + 4:  # prima di copiare
            raise OversizeError(f"pacchetto oltre il max {self.max_data_length}")
        raw = bytes(data)
        if len(raw) < HEADER_LEN:
            raise ProtocolError("pacchetto troncato (meno di 4 byte)")
        h = int.from_bytes(raw[:4], "big")
        flags = h & 0xFF
        if flags & ~_KNOWN_FLAGS:
            raise ProtocolError("flag riservati impostati")
        if flags & (CSP_FHMAC | CSP_FXTEA):
            raise ProtocolError("flag HMAC/XTEA non supportati")
        body = raw[HEADER_LEN:]
        trailer = 4 if flags & CSP_FCRC32 else 0
        if len(body) > self.max_data_length + trailer:
            raise OversizeError(f"dati oltre il max {self.max_data_length}")
        if trailer:
            if len(body) < 4:
                raise ProtocolError("CRC32 dichiarato ma assente (pacchetto troncato)")
            payload, crc = body[:-4], int.from_bytes(body[-4:], "big")
            if crc32c(payload) != crc:
                raise CrcError("CRC32 non valido")
            body = payload
        return CspPacket(
            priority=h >> 30,
            source=(h >> 25) & 0x1F,
            destination=(h >> 20) & 0x1F,
            destination_port=(h >> 14) & 0x3F,
            source_port=(h >> 8) & 0x3F,
            flags=flags,
            data=body,
        )
