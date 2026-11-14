# SPDX-License-Identifier: Apache-2.0
"""AX.25 v2.2: frame UI (Unnumbered Information) con FCS CRC-16/X.25, piu' trasporto KISS.

Verificato sul documento primario "AX.25 Link Access Protocol for Amateur Packet Radio v2.2"
(rev. 10 settembre 2017, https://wiki.oarc.uk/_media/packet:ax25.2.2.10.pdf, letto il 2026-10-13):
- 3.12 / Fig. 3.3-3.4: indirizzo = 7 ottetti; 6 caratteri ASCII maiuscoli/cifre, completati con
  spazi, ciascuno <<1; ottetto SSID `C R R S S S S E` (C/H = bit 7, riservati = bit 6-5, SSID =
  bit 4-1, E = bit di estensione LSB, 1 sull'ultimo indirizzo); destinazione + sorgente + fino a
  8 ripetitori.
- Controllo UI = `000P/F0011` (0x03; 0x13 con P/F); PID 0xF0 = nessun layer 3; campo info di
  default 256 ottetti (3.5); frame minimo 136 bit con flag (3.9); frame con FCS errato scartato
  senza altre azioni (4.4.6).
- FCS: 16 bit secondo ISO 3309 / HDLC (3.7) = CRC-16/IBM-SDLC (X-25: poly 0x1021 riflesso, init
  0xFFFF, xorout 0xFFFF; check("123456789") = 0x906E, catalogo RevEng).
NON verificato contro una cattura reale: l'ordine dei byte dell'FCS sul filo (qui: byte basso per
primo, come HDLC/RFC 1662 Appendice C). Non implementati: frame I/S/U diversi da UI, bit stuffing e
flag HDLC (livello fisico), segmentazione, AX.25 v2.0 con bit C entrambi uguali (rifiutato).

KISS (https://www.ax25.net/kiss.aspx): trasporta il frame AX.25 SENZA FCS (la calcola il TNC);
senza FCS non c'e' alcun controllo di integrita' fra host e TNC.
"""

import re
from dataclasses import dataclass

from backend.net.errors import CrcError, OversizeError, ProtocolError
from backend.net.framing import KissFramer

DEFAULT_MAX_INFO = 256
MAX_DIGIPEATERS = 8
_CALL_RE = re.compile(r"[A-Z0-9]{1,6}")
_UI_CONTROL = 0x03
_PF_BIT = 0x10


def _make_table() -> tuple[int, ...]:
    table = []
    for i in range(256):
        crc = i
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
        table.append(crc)
    return tuple(table)


_TABLE = _make_table()


def crc16_x25(data: bytes) -> int:
    """CRC-16/X-25 (IBM-SDLC): check("123456789") = 0x906E."""
    crc = 0xFFFF
    for b in data:
        crc = _TABLE[(crc ^ b) & 0xFF] ^ (crc >> 8)
    return crc ^ 0xFFFF


@dataclass(frozen=True)
class Ax25Address:
    callsign: str
    ssid: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.callsign, str) or not _CALL_RE.fullmatch(self.callsign):
            raise ProtocolError("callsign: 1-6 caratteri A-Z0-9 maiuscoli")
        if (
            isinstance(self.ssid, bool)
            or not isinstance(self.ssid, int)
            or not 0 <= self.ssid <= 15
        ):
            raise ProtocolError("ssid: intero 0..15")

    @classmethod
    def parse(cls, text: str) -> "Ax25Address":
        if not isinstance(text, str):
            raise ProtocolError("indirizzo: stringa")
        call, sep, ssid_s = text.partition("-")
        if not sep:
            return cls(call, 0)
        if not re.fullmatch(r"[0-9]{1,2}", ssid_s):
            raise ProtocolError("ssid: cifre decimali")
        return cls(call, int(ssid_s))

    def __str__(self) -> str:
        return self.callsign if self.ssid == 0 else f"{self.callsign}-{self.ssid}"

    def encode(self, *, flag: bool, last: bool) -> bytes:
        """7 ottetti. `flag` = bit C (destinazione/sorgente) o H (ripetitore); `last` = estensione."""
        chars = bytes((ord(c) << 1) for c in self.callsign.ljust(6))
        ssid_octet = (0x80 if flag else 0) | 0x60 | (self.ssid << 1) | (1 if last else 0)
        return chars + bytes([ssid_octet])


def _decode_address(raw: bytes) -> tuple[Ax25Address, bool, bool]:
    chars = []
    for b in raw[:6]:
        if b & 1:
            raise ProtocolError("bit di estensione dentro il nominativo")
        chars.append(chr(b >> 1))
    text = "".join(chars)
    call = text.rstrip(" ")
    if not call or " " in call or not _CALL_RE.fullmatch(call):
        raise ProtocolError("nominativo non valido")
    o = raw[6]
    return Ax25Address(call, (o >> 1) & 0x0F), bool(o & 0x80), bool(o & 1)


@dataclass(frozen=True)
class Ax25UiFrame:
    destination: Ax25Address
    source: Ax25Address
    info: bytes = b""
    digipeaters: tuple[Ax25Address, ...] = ()
    repeated: tuple[bool, ...] = ()  # bit H per ripetitore (vuoto = tutti falsi)
    pid: int = 0xF0
    poll_final: bool = False
    command: bool = True  # True: comando (C dest=1, src=0); False: risposta

    def __post_init__(self) -> None:
        if not isinstance(self.destination, Ax25Address) or not isinstance(
            self.source, Ax25Address
        ):
            raise ProtocolError("destination/source: Ax25Address")
        if not isinstance(self.info, bytes):
            raise ProtocolError("info: bytes")
        if not isinstance(self.digipeaters, tuple) or len(self.digipeaters) > MAX_DIGIPEATERS:
            raise ProtocolError("digipeaters: tupla di al massimo 8 indirizzi")
        if not all(isinstance(d, Ax25Address) for d in self.digipeaters):
            raise ProtocolError("digipeaters: Ax25Address")
        rep = self.repeated or (False,) * len(self.digipeaters)
        if not isinstance(rep, tuple) or len(rep) != len(self.digipeaters):
            raise ProtocolError("repeated: stessa lunghezza di digipeaters")
        object.__setattr__(self, "repeated", tuple(bool(x) for x in rep))
        if isinstance(self.pid, bool) or not isinstance(self.pid, int) or not 0 <= self.pid <= 255:
            raise ProtocolError("pid: intero 0..255")
        if not isinstance(self.poll_final, bool) or not isinstance(self.command, bool):
            raise ProtocolError("poll_final/command: bool")


class Ax25Codec:
    """Codec frame UI AX.25 (implementa `ProtocolCodec`).

    `with_fcs=True`: il frame include l'FCS (2 ottetti, byte basso per primo), verificata PRIMA di
    interpretare qualunque campo; un errore solleva `CrcError` e incrementa `crc_errors`.
    `with_fcs=False`: formato KISS (senza FCS). Gli altri rifiuti incrementano `rejected`.

    Bit riservati dell'SSID (sez. 3.12.1/3.12.2): "possono essere usati in modo concordato in reti
    individuali; quando non implementati, sono posti a uno". L'encoder li pone sempre a uno. Il
    decoder per default li ACCETTA qualunque valore (uso concordato lecito) e conta i frame con
    valori diversi da 11 in `nonstandard_reserved`; con `strict_reserved=True` li rifiuta."""

    def __init__(
        self,
        *,
        max_info: int = DEFAULT_MAX_INFO,
        with_fcs: bool = True,
        strict_reserved: bool = False,
    ) -> None:
        if max_info < 1:
            raise ValueError("max_info >= 1")
        self.strict_reserved = strict_reserved
        self.nonstandard_reserved = 0
        self.max_info = max_info
        self.with_fcs = with_fcs
        self.crc_errors = 0
        self.rejected = 0

    def encode(self, message: Ax25UiFrame) -> bytes:
        if not isinstance(message, Ax25UiFrame):
            raise ProtocolError("encode accetta solo Ax25UiFrame")
        if len(message.info) > self.max_info:
            raise ProtocolError(f"info oltre il max {self.max_info}")
        out = message.destination.encode(flag=message.command, last=False)
        out += message.source.encode(flag=not message.command, last=not message.digipeaters)
        n = len(message.digipeaters)
        for i, d in enumerate(message.digipeaters):
            out += d.encode(flag=message.repeated[i], last=i == n - 1)
        out += bytes([_UI_CONTROL | (_PF_BIT if message.poll_final else 0), message.pid])
        out += message.info
        if self.with_fcs:
            fcs = crc16_x25(out)
            out += bytes([fcs & 0xFF, fcs >> 8])
        return out

    def decode(self, data: bytes | bytearray | memoryview) -> Ax25UiFrame:
        try:
            return self._decode(data)
        except CrcError:
            self.crc_errors += 1
            raise
        except ProtocolError:
            self.rejected += 1
            raise

    def _decode(self, data: bytes | bytearray | memoryview) -> Ax25UiFrame:
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise ProtocolError("decode accetta bytes, bytearray o memoryview")
        fcs_len = 2 if self.with_fcs else 0
        if len(data) > 70 + self.max_info + fcs_len:  # prima di copiare
            raise OversizeError(f"frame oltre il max (info {self.max_info})")
        raw = bytes(data)
        if len(raw) < 14 + 2 + fcs_len:
            raise ProtocolError("frame troncato (indirizzi, controllo e PID non completi)")
        body = raw
        if self.with_fcs:
            body, fcs = raw[:-2], raw[-2] | (raw[-1] << 8)
            if crc16_x25(body) != fcs:
                raise CrcError("FCS non valido")
        addrs: list[tuple[Ax25Address, bool]] = []
        i = 0
        while True:
            if len(body) - i < 7 + 2:
                raise ProtocolError("indirizzi troncati")
            addr, flag, last = _decode_address(body[i : i + 7])
            if body[i + 6] & 0x60 != 0x60:  # bit R: "se non usati sono posti a uno" (3.12.1/2)
                if self.strict_reserved:
                    raise ProtocolError("bit riservati dell'SSID non posti a uno")
                self.nonstandard_reserved += 1
            addrs.append((addr, flag))
            i += 7
            if last:
                break
            if len(addrs) >= 2 + MAX_DIGIPEATERS:
                raise ProtocolError("troppi indirizzi (nessuna fine campo indirizzi)")
        if len(addrs) < 2:
            raise ProtocolError("manca l'indirizzo sorgente")
        if len(body) - i < 2:
            raise ProtocolError("controllo/PID mancanti")
        control, pid = body[i], body[i + 1]
        if control & ~_PF_BIT != _UI_CONTROL:
            raise ProtocolError("non e' un frame UI (controllo != 0x03/0x13)")
        info = body[i + 2 :]
        if len(info) > self.max_info:
            raise ProtocolError(f"info oltre il max {self.max_info}")
        (dest, dc), (src, sc) = addrs[0], addrs[1]
        if dc == sc:
            raise ProtocolError("bit C ambigui (AX.25 v2.0 non supportato)")
        digis = tuple(a for a, _ in addrs[2:])
        return Ax25UiFrame(
            destination=dest,
            source=src,
            info=info,
            digipeaters=digis,
            repeated=tuple(f for _, f in addrs[2:]),
            pid=pid,
            poll_final=bool(control & _PF_BIT),
            command=dc,
        )


def kiss_encode(frame: Ax25UiFrame, *, port: int = 0, max_payload: int = 512) -> bytes:
    """Frame UI AX.25 (senza FCS) incapsulato in un frame KISS dati."""
    inner = Ax25Codec(with_fcs=False, max_info=max(DEFAULT_MAX_INFO, len(frame.info))).encode(frame)
    return KissFramer(max_payload=max_payload).encode(inner, port=port)


def kiss_decode_frames(
    data: bytes, *, codec: Ax25Codec | None = None, max_payload: int = 512
) -> list[Ax25UiFrame]:
    """Decodifica un blocco di byte KISS; i frame non decodificabili sono scartati e contati
    sul `codec` (`rejected`), cosi' un frame cattivo non ferma gli altri."""
    codec = codec or Ax25Codec(with_fcs=False)
    out: list[Ax25UiFrame] = []
    for payload in KissFramer(max_payload=max_payload).feed(data):
        try:
            out.append(codec.decode(payload))
        except ProtocolError:
            continue
    return out
