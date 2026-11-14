# SPDX-License-Identifier: Apache-2.0
"""Framer incrementali: dal flusso di byte ai messaggi (spec 15.2). Dati NON fidati.

Regole comuni (testate):
- ogni framer ha un `max_payload` e non conserva mai piu' di (max_payload + intestazione) byte
  tra una `feed` e l'altra; nessuna allocazione dipende da una lunghezza dichiarata dal peer;
- `feed` accetta frammenti arbitrari (anche un byte alla volta) e restituisce i messaggi completi;
- gli errori di flusso irrecuperabili (prefisso di lunghezza oltre il massimo) sollevano
  `FramingError` e il framer resta "rotto" fino a `reset()`; i framer con delimitatore
  (delimiter/SLIP/KISS) invece scartano il frame difettoso, incrementano i contatori
  (`errors`, `oversize`) e si risincronizzano sul delimitatore successivo.

SLIP: RFC 1055. KISS: Chepponis & Karn 1987 (https://www.ax25.net/kiss.aspx). Il prefisso di
lunghezza e il delimitatore sono definizioni locali del template (non standard).
"""

from backend.net.errors import FramingError

FEND = 0xC0  # SLIP "END"
FESC = 0xDB  # SLIP "ESC"
TFEND = 0xDC  # SLIP "ESC_END"
TFESC = 0xDD  # SLIP "ESC_ESC"

_FEND_B = bytes([FEND])


def default_discard_cap(max_payload: int) -> int:
    """Tetto predefinito dei byte consumati senza produrre un frame (rumore/frame scartati)."""
    return 4 * max_payload + 1024


class LengthPrefixFramer:
    """Prefisso di lunghezza big-endian di 1, 2 o 4 byte seguito dal payload.

    Una lunghezza dichiarata > `max_payload` solleva `FramingError` senza leggere ne' allocare
    altro (il flusso non e' risincronizzabile: il chiamante chiude la connessione). Politica dei
    frame vuoti: lunghezza 0 e' RIFIUTATA (FramingError) salvo `allow_empty=True`, cosi' 16 KiB
    di zeri non generano 16384 messaggi."""

    def __init__(self, width: int, *, max_payload: int, allow_empty: bool = False) -> None:
        if width not in (1, 2, 4):
            raise ValueError("width deve essere 1, 2 o 4")
        if max_payload < 0 or max_payload > (1 << (8 * width)) - 1:
            raise ValueError("max_payload non rappresentabile con questa larghezza")
        self._w = width
        self._max = max_payload
        self._allow_empty = allow_empty
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
        if len(payload) > self._max:
            raise FramingError(f"payload di {len(payload)} byte oltre il limite {self._max}")
        if not payload and not self._allow_empty:
            raise FramingError("payload vuoto non ammesso (allow_empty=False)")
        return len(payload).to_bytes(self._w, "big") + bytes(payload)

    def feed(self, data: bytes) -> list[bytes]:
        if self._broken:
            raise FramingError("flusso non recuperabile: reset() necessario")
        self._buf.extend(data)
        out: list[bytes] = []
        pos = 0
        w = self._w
        buf = self._buf
        while len(buf) - pos >= w:
            n = int.from_bytes(buf[pos : pos + w], "big")
            if n > self._max:
                self.errors += 1
                self.oversize += 1
                self._broken = True
                buf.clear()
                raise FramingError(f"lunghezza dichiarata {n} oltre il limite {self._max}")
            if n == 0 and not self._allow_empty:
                self.errors += 1
                self._broken = True
                buf.clear()
                raise FramingError("lunghezza dichiarata zero: frame vuoto non ammesso")
            if len(buf) - pos - w < n:
                break
            out.append(bytes(buf[pos + w : pos + w + n]))
            pos += w + n
        del buf[:pos]
        self.frames += len(out)
        return out


class DelimiterFramer:
    """Messaggi terminati da un delimitatore (es. `b"\\n"`). Il payload non puo' contenerlo
    (`encode` solleva). Frame vuoti ignorati; frame oltre `max_payload` scartati e contati, poi
    risincronizzazione sul delimitatore successivo."""

    def __init__(
        self, delimiter: bytes, *, max_payload: int, max_discard_bytes: int | None = None
    ) -> None:
        if not delimiter:
            raise ValueError("delimitatore vuoto")
        if max_payload < 1:
            raise ValueError("max_payload >= 1")
        self._d = bytes(delimiter)
        self._max = max_payload
        self._cap = max_discard_bytes or default_discard_cap(max_payload)
        self._buf = bytearray()
        self._skipping = False
        self._broken = False
        self._since = 0
        self.errors = 0
        self.oversize = 0
        self.empty_frames = 0
        self.frames = 0

    @property
    def pending(self) -> int:
        return len(self._buf)

    @property
    def bytes_since_frame(self) -> int:
        """Byte ricevuti dopo l'ultimo frame emesso (frame parziali, rumore, frame vuoti)."""
        return self._since

    @property
    def in_frame(self) -> bool:
        return self._since > 0

    def reset(self) -> None:
        self._buf.clear()
        self._skipping = False
        self._broken = False
        self._since = 0

    def encode(self, payload: bytes) -> bytes:
        if len(payload) > self._max:
            raise FramingError(f"payload di {len(payload)} byte oltre il limite {self._max}")
        if self._d in payload:
            raise FramingError("il payload contiene il delimitatore")
        return bytes(payload) + self._d

    def feed(self, data: bytes) -> list[bytes]:
        if self._broken:
            raise FramingError("flusso non recuperabile: reset() necessario")
        buf = self._buf
        buf.extend(data)
        self._since += len(data)
        d, dl = self._d, len(self._d)
        out: list[bytes] = []
        while True:
            idx = buf.find(d)
            if self._skipping:
                if idx < 0:
                    del buf[: max(0, len(buf) - (dl - 1))]
                    break
                del buf[: idx + dl]
                self._skipping = False
                continue
            if idx < 0:
                if len(buf) > self._max + dl - 1:
                    self.errors += 1
                    self.oversize += 1
                    self._skipping = True
                    del buf[: max(0, len(buf) - (dl - 1))]
                    continue
                break
            payload = bytes(buf[:idx])
            del buf[: idx + dl]
            if len(payload) > self._max:
                self.errors += 1
                self.oversize += 1
            elif payload:
                out.append(payload)
                self._since = len(buf)
            else:
                self.empty_frames += 1  # vuoti ignorati ma NON azzerano il contatore di rumore
        self.frames += len(out)
        if not out and self._since > self._cap:
            self._broken = True
            buf.clear()
            raise FramingError(f"oltre {self._cap} byte scartati senza produrre un frame")
        return out


class SlipFramer:
    """SLIP (RFC 1055). Frame delimitati da END (0xC0); END/ESC nei dati sono sostituiti da
    ESC ESC_END / ESC ESC_ESC. Scelte difensive rispetto al testo RFC: ESC seguito da un byte
    diverso da ESC_END/ESC_ESC (o da END) e' una violazione e il frame viene SCARTATO e contato
    (l'RFC suggerisce invece di inserire il byte); END consecutivi non producono frame vuoti.
    Il rumore prima del primo END forma un frame "sporco" che i livelli superiori (CRC)
    devono rifiutare."""

    def __init__(self, *, max_payload: int, max_discard_bytes: int | None = None) -> None:
        if max_payload < 1:
            raise ValueError("max_payload >= 1")
        self._max = max_payload
        self._limit = max_payload  # byte decodificati ammessi per frame (KISS: +1 comando)
        self._cap = max_discard_bytes or default_discard_cap(max_payload)
        self._cur = bytearray()
        self._esc = False
        self._discard = False
        self._broken = False
        self._since = 0
        self.errors = 0
        self.oversize = 0
        self.empty_frames = 0
        self.frames = 0

    @property
    def pending(self) -> int:
        return len(self._cur) + (1 if self._esc else 0)

    @property
    def bytes_since_frame(self) -> int:
        """Byte ricevuti dopo l'ultimo frame emesso (anche in stato di scarto, dove pending=0)."""
        return self._since

    @property
    def in_frame(self) -> bool:
        return self._since > 0

    def reset(self) -> None:
        self._cur.clear()
        self._esc = False
        self._discard = False
        self._broken = False
        self._since = 0

    @staticmethod
    def _escape(body: bytes) -> bytes:
        return body.replace(b"\xdb", b"\xdb\xdd").replace(b"\xc0", b"\xdb\xdc")

    def encode(self, payload: bytes) -> bytes:
        if len(payload) > self._max:
            raise FramingError(f"payload di {len(payload)} byte oltre il limite {self._max}")
        return _FEND_B + self._escape(bytes(payload)) + _FEND_B

    def _emit(self, frame: bytes) -> bytes | None:
        return frame

    def _overflow(self) -> None:
        self.errors += 1
        self.oversize += 1
        self._discard = True
        self._cur.clear()
        self._esc = False

    def _append_part(self, part: bytes) -> None:
        if self._discard or not part:
            return
        cur = self._cur
        if FESC not in part and not self._esc:
            if len(cur) + len(part) > self._limit:
                self._overflow()
                return
            cur.extend(part)
            return
        for b in part:
            if self._esc:
                self._esc = False
                if b == TFEND:
                    cur.append(FEND)
                elif b == TFESC:
                    cur.append(FESC)
                else:
                    self.errors += 1  # escape non valido: scarta il frame fino al prossimo END
                    self._discard = True
                    cur.clear()
                    return
            elif b == FESC:
                self._esc = True
            else:
                cur.append(b)
            if len(cur) > self._limit:
                self._overflow()
                return

    def _end_of_frame(self, out: list[bytes]) -> bool:
        emitted = False
        if not self._discard:
            if self._esc:
                self.errors += 1  # ESC subito prima dell'END
            elif self._cur:
                frame = self._emit(bytes(self._cur))
                if frame is not None:
                    out.append(frame)
                    emitted = True
            else:
                self.empty_frames += 1  # END consecutivi: ignorati, ma contano come rumore
        self._cur.clear()
        self._esc = False
        self._discard = False
        return emitted

    def feed(self, data: bytes) -> list[bytes]:
        if self._broken:
            raise FramingError("flusso non recuperabile: reset() necessario")
        out: list[bytes] = []
        raw = bytes(data)
        self._since += len(raw)
        parts = raw.split(_FEND_B)
        last = len(parts) - 1
        pos = 0
        for i, part in enumerate(parts):
            self._append_part(part)
            pos += len(part) + 1
            if i < last and self._end_of_frame(out):
                self._since = len(raw) - pos
        self.frames += len(out)
        if not out and self._since > self._cap:
            self._broken = True
            self.reset_state_after_break()
            raise FramingError(f"oltre {self._cap} byte scartati senza produrre un frame")
        return out

    def reset_state_after_break(self) -> None:
        self._cur.clear()
        self._esc = False
        self._discard = False


class KissFramer(SlipFramer):
    """KISS (TNC): come SLIP con FEND/FESC/TFEND/TFESC, ma il primo byte decodificato di ogni
    frame e' il byte di comando (porta nel nibble alto, comando nel basso). `feed` restituisce
    il payload dei soli frame DATI (comando 0, qualunque porta); gli altri comandi sono
    ignorati e contati in `ignored_commands`. KISS non ha CRC: sopra serve AX.25 FCS o simile."""

    def __init__(self, *, max_payload: int, max_discard_bytes: int | None = None) -> None:
        super().__init__(max_payload=max_payload, max_discard_bytes=max_discard_bytes)
        self._limit = max_payload + 1
        self.ignored_commands = 0

    def encode(self, payload: bytes, port: int = 0, command: int = 0) -> bytes:
        if not 0 <= port <= 15 or not 0 <= command <= 15:
            raise ValueError("port e command devono stare in 0..15")
        if len(payload) > self._max:
            raise FramingError(f"payload di {len(payload)} byte oltre il limite {self._max}")
        body = bytes([(port << 4) | command]) + bytes(payload)
        return _FEND_B + self._escape(body) + _FEND_B

    def _emit(self, frame: bytes) -> bytes | None:
        if frame[0] & 0x0F != 0:
            self.ignored_commands += 1
            return None
        return frame[1:] or None
