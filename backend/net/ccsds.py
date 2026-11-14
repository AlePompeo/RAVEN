# SPDX-License-Identifier: Apache-2.0
"""CCSDS Space Packet Protocol (CCSDS 133.0-B-2, Blue Book, giugno 2020).

Layout verificato sul documento primario (https://public.ccsds.org/Pubs/133x0b2e2.pdf, letto il
2026-10-13), sezioni 4.1.2-4.1.3: intestazione primaria di 6 ottetti big-endian:

    bit 0-2   versione (000)                       4.1.3.2
    bit 3     tipo (0 TM, 1 TC)                    4.1.3.3.2
    bit 4     flag intestazione secondaria         4.1.3.3.3
    bit 5-15  APID (11 bit; 0x7FF = idle)          4.1.3.3.4
    bit 16-17 flag di sequenza                     4.1.3.4.2
    bit 18-31 conteggio di sequenza (mod 16384)    4.1.3.4.3
    bit 32-47 lunghezza dati C = ottetti - 1       4.1.3.5

Campo dati: 1..65536 ottetti (4.1.4.1.2, 4.1.2.1). Sottoinsieme implementato: solo il Packet
Primary Header e il campo dati opaco; intestazione secondaria, servizio Octet String e gestione
dei percorsi dati NON sono interpretati (spec 15.5: conformita' completa non e' un obiettivo).
Scelte NON dettate dallo standard: i pacchetti idle creati da `SpacePacket.idle` usano flag di
sequenza '11' e riempimento 0x00 (lo standard lascia il pattern al progetto, 4.1.4.3.4 nota).

Dati NON fidati: ogni errore e' `ProtocolError`; la lunghezza dichiarata e' confrontata con il
tetto configurato prima di toccare il corpo.
"""

from dataclasses import dataclass

from backend.net.errors import FramingError, OversizeError, ProtocolError

PRIMARY_HEADER_LEN = 6
MAX_DATA_LENGTH = 65536
MAX_APID = 0x7FF
IDLE_APID = 0x7FF
MAX_SEQUENCE_COUNT = 0x3FFF

_SEQ_MODULO = MAX_SEQUENCE_COUNT + 1


def _is_int(v: object) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def next_sequence_count(count: int) -> int:
    """Conteggio successivo, continuo modulo 16384 (4.1.3.4.3.4)."""
    return (count + 1) % _SEQ_MODULO


@dataclass(frozen=True)
class SpacePacket:
    apid: int
    data: bytes
    packet_type: int = 0  # 0 = telemetria, 1 = telecomando
    secondary_header: bool = False
    sequence_flags: int = 3  # 0 continuazione, 1 primo, 2 ultimo, 3 non segmentato
    sequence_count: int = 0
    version: int = 0

    def __post_init__(self) -> None:
        if not _is_int(self.apid) or not 0 <= self.apid <= MAX_APID:
            raise ProtocolError("apid: intero 0..2047")
        if not _is_int(self.packet_type) or self.packet_type not in (0, 1):
            raise ProtocolError("packet_type: 0 (TM) o 1 (TC)")
        if not isinstance(self.secondary_header, bool):
            raise ProtocolError("secondary_header: bool")
        if not _is_int(self.sequence_flags) or not 0 <= self.sequence_flags <= 3:
            raise ProtocolError("sequence_flags: intero 0..3")
        if not _is_int(self.sequence_count) or not 0 <= self.sequence_count <= MAX_SEQUENCE_COUNT:
            raise ProtocolError("sequence_count: intero 0..16383")
        if not _is_int(self.version) or self.version != 0:
            raise ProtocolError("version: solo 0 (Version 1 CCSDS Packet)")
        if not isinstance(self.data, bytes):
            raise ProtocolError("data: bytes")
        if not 1 <= len(self.data) <= MAX_DATA_LENGTH:
            raise ProtocolError("data: 1..65536 ottetti")
        if self.apid == IDLE_APID and self.secondary_header:
            raise ProtocolError("un pacchetto idle (APID 0x7FF) non ha intestazione secondaria")

    @property
    def is_idle(self) -> bool:
        return self.apid == IDLE_APID

    @classmethod
    def idle(cls, data_length: int, sequence_count: int = 0) -> "SpacePacket":
        return cls(apid=IDLE_APID, data=b"\x00" * data_length, sequence_count=sequence_count)


def _parse_header(buf: bytes, max_data_length: int) -> tuple[int, int, int, int, int, int, int]:
    """(version, type, sec, apid, flags, count, data_len) da >= 6 ottetti, con controlli."""
    w1 = (buf[0] << 8) | buf[1]
    w2 = (buf[2] << 8) | buf[3]
    data_len = ((buf[4] << 8) | buf[5]) + 1
    version = w1 >> 13
    if version != 0:
        raise ProtocolError(f"version {version} non supportata")
    if data_len > max_data_length:
        raise OversizeError(f"lunghezza dati dichiarata {data_len} oltre il max {max_data_length}")
    return version, (w1 >> 12) & 1, (w1 >> 11) & 1, w1 & 0x7FF, w2 >> 14, w2 & 0x3FFF, data_len


class SpacePacketCodec:
    """Codec Space Packet (implementa `ProtocolCodec`). `max_data_length` e' il tetto locale."""

    def __init__(self, max_data_length: int = MAX_DATA_LENGTH) -> None:
        if not 1 <= max_data_length <= MAX_DATA_LENGTH:
            raise ValueError("max_data_length deve stare in 1..65536")
        self.max_data_length = max_data_length

    def encode(self, message: SpacePacket) -> bytes:
        if not isinstance(message, SpacePacket):
            raise ProtocolError("encode accetta solo SpacePacket")
        if len(message.data) > self.max_data_length:
            raise ProtocolError(f"dati oltre il max {self.max_data_length}")
        w1 = (message.packet_type << 12) | (int(message.secondary_header) << 11) | message.apid
        w2 = (message.sequence_flags << 14) | message.sequence_count
        return (
            w1.to_bytes(2, "big")
            + w2.to_bytes(2, "big")
            + (len(message.data) - 1).to_bytes(2, "big")
            + message.data
        )

    def decode_prefix(self, data: bytes | bytearray | memoryview) -> tuple[SpacePacket, int]:
        """Decodifica un pacchetto all'inizio di `data`; restituisce (pacchetto, ottetti usati)."""
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise ProtocolError("decode accetta bytes, bytearray o memoryview")
        buf = bytes(data[: PRIMARY_HEADER_LEN + MAX_DATA_LENGTH])
        if len(buf) < PRIMARY_HEADER_LEN:
            raise ProtocolError("intestazione troncata (meno di 6 ottetti)")
        _, ptype, sec, apid, flags, count, dlen = _parse_header(buf, self.max_data_length)
        total = PRIMARY_HEADER_LEN + dlen
        if len(buf) < total:
            raise ProtocolError(f"pacchetto troncato: {len(buf)} di {total} ottetti")
        packet = SpacePacket(
            apid=apid,
            data=buf[PRIMARY_HEADER_LEN:total],
            packet_type=ptype,
            secondary_header=bool(sec),
            sequence_flags=flags,
            sequence_count=count,
        )
        return packet, total

    def decode(self, data: bytes | bytearray | memoryview) -> SpacePacket:
        packet, used = self.decode_prefix(data)
        if used != len(data):
            raise ProtocolError(f"{len(data) - used} ottetti trailing dopo il pacchetto")
        return packet


class SpacePacketFramer:
    """Framer a flusso con lunghezza letta dall'intestazione (spec 15.2). Restituisce i pacchetti
    completi (intestazione inclusa) da passare a `SpacePacketCodec.decode`. Versione non zero o
    lunghezza oltre `max_data_length` sull'intestazione -> `FramingError` (il flusso non e'
    risincronizzabile senza delimitatori: il chiamante chiude); il framer resta rotto fino a
    `reset()`. Il buffer non supera 6 + max_data_length ottetti."""

    def __init__(self, max_data_length: int = MAX_DATA_LENGTH) -> None:
        if not 1 <= max_data_length <= MAX_DATA_LENGTH:
            raise ValueError("max_data_length deve stare in 1..65536")
        self._max = max_data_length
        self._buf = bytearray()
        self._broken = False
        self.errors = 0
        self.oversize = 0
        self.frames = 0

    @property
    def pending(self) -> int:
        return len(self._buf)

    @property
    def bytes_since_frame(self) -> int:
        return len(self._buf)

    @property
    def in_frame(self) -> bool:
        return len(self._buf) > 0

    def reset(self) -> None:
        self._buf.clear()
        self._broken = False

    def encode(self, payload: bytes) -> bytes:
        # il payload e' gia' un Space Packet codificato: nessuna cornice aggiuntiva
        return bytes(payload)

    def feed(self, data: bytes) -> list[bytes]:
        if self._broken:
            raise FramingError("flusso non recuperabile: reset() necessario")
        buf = self._buf
        buf.extend(data)
        out: list[bytes] = []
        pos = 0
        while len(buf) - pos >= PRIMARY_HEADER_LEN:
            try:
                *_, dlen = _parse_header(bytes(buf[pos : pos + PRIMARY_HEADER_LEN]), self._max)
            except ProtocolError as e:
                self.errors += 1
                if isinstance(e, OversizeError):
                    self.oversize += 1
                self._broken = True
                buf.clear()
                raise FramingError(str(e)) from None
            total = PRIMARY_HEADER_LEN + dlen
            if len(buf) - pos < total:
                break
            out.append(bytes(buf[pos : pos + total]))
            pos += total
        del buf[:pos]
        self.frames += len(out)
        return out
