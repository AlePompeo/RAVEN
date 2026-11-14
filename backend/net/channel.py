# SPDX-License-Identifier: Apache-2.0
"""Canale simulato (spec 15.2) - modello SEMPLIFICATO, deterministico, senza sleep reali.

Il tempo e' esplicito (`now_s`, secondi su un orologio virtuale iniettato): i test avanzano un
`VirtualClock`. Con lo stesso `seed` e la stessa sequenza di `send`/`deliver` l'esito e' identico.

Pipeline di un frame in `send` (ordine fisso, quindi riproducibile):
1. finestra di contatto: se `contact_windows` e' impostato e `now_s` non e' in una finestra
   -> `dropped_outside_window` (nessuna estrazione casuale);
2. capienza: oltre `max_in_flight` frame in volo -> `lost` (+ `lost_overflow`);
3. banda: il canale trasmette un frame alla volta, `len*8/bandwidth_bps` secondi ciascuno
   (i frame successivi si accodano dietro quello in corso);
4. perdita: con probabilita' `loss_probability` -> `lost` (+ `lost_random`); consuma comunque banda;
5. arrivo = fine trasmissione + `delay_s` + jitter uniforme in [0, `jitter_s`] (mai in anticipo
   rispetto a `delay_s`); se l'ISTANTE DI ARRIVO cade fuori da ogni finestra -> `dropped_outside_window`;
6. errori sui bit: ogni bit invertito indipendentemente con probabilita' `bit_error_rate`
   (`corrupted`, `bits_flipped`); i livelli superiori (CRC) devono accorgersene.

Finestre: intervalli [inizio, fine), ordinati e disgiunti. Ordine: `deliver` restituisce i frame
in ordine di ARRIVO (a parita', ordine di invio): con jitter maggiore della spaziatura degli invii
i frame si RIORDINANO rispetto all'invio, come su un collegamento reale; senza jitter e' FIFO.

Invariante di contabilita' (testata): `sent == delivered + lost + dropped_outside_window +
in_flight`; a canale drenato (`in_flight == 0`) `sent == delivered + lost + dropped_outside_window`.

NON modellati: Doppler, fading, correlazione degli errori (burst), perdita dipendente dalla
distanza. Non sostituisce una verifica sul collegamento reale (spec 15.5).
"""

import heapq
import math
import random
from bisect import bisect_right
from collections.abc import Callable, Mapping
from dataclasses import dataclass

MIN_BIT_ERROR_RATE = 1e-12  # sotto questa soglia un BER non ha effetto pratico: rifiutato


def _finite_nonneg(v: float, name: str) -> None:
    if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or v < 0:
        raise ValueError(f"{name}: numero finito >= 0")


@dataclass(frozen=True)
class ChannelConfig:
    delay_s: float = 0.0
    jitter_s: float = 0.0
    loss_probability: float = 0.0
    bit_error_rate: float = 0.0
    bandwidth_bps: float | None = None
    contact_windows: tuple[tuple[float, float], ...] | None = None
    max_in_flight: int = 10_000
    seed: int = 0

    def __post_init__(self) -> None:
        _finite_nonneg(self.delay_s, "delay_s")
        _finite_nonneg(self.jitter_s, "jitter_s")
        _finite_nonneg(self.loss_probability, "loss_probability")
        if self.loss_probability > 1.0:
            raise ValueError("loss_probability: probabilita' in [0, 1]")
        _finite_nonneg(self.bit_error_rate, "bit_error_rate")
        if self.bit_error_rate > 1.0 or 0.0 < self.bit_error_rate < MIN_BIT_ERROR_RATE:
            raise ValueError(
                f"bit_error_rate: 0 oppure in [{MIN_BIT_ERROR_RATE}, 1] (valori minori, anche "
                "subnormali, sono rifiutati)"
            )
        if self.bandwidth_bps is not None:
            _finite_nonneg(self.bandwidth_bps, "bandwidth_bps")
            if self.bandwidth_bps == 0:
                raise ValueError("bandwidth_bps: > 0 oppure None (illimitata)")
        if isinstance(self.max_in_flight, bool) or not isinstance(self.max_in_flight, int):
            raise TypeError("max_in_flight: intero >= 1")
        if self.max_in_flight < 1:
            raise ValueError("max_in_flight: intero >= 1")
        if self.contact_windows is not None:
            prev_end = -math.inf
            for w in self.contact_windows:
                if len(w) != 2 or not all(
                    isinstance(x, (int, float)) and math.isfinite(x) for x in w
                ):
                    raise ValueError("contact_windows: coppie (inizio, fine) finite")
                start, end = w
                if not start < end:
                    raise ValueError("contact_windows: inizio < fine")
                if start < prev_end:
                    raise ValueError("contact_windows: ordinate e non sovrapposte")
                prev_end = end


class VirtualClock:
    """Orologio virtuale iniettabile: avanza solo con `advance`/`set` (mai tempo reale)."""

    def __init__(self, start_s: float = 0.0) -> None:
        self._t = float(start_s)

    def __call__(self) -> float:
        return self._t

    def advance(self, dt_s: float) -> float:
        _finite_nonneg(dt_s, "dt_s")
        self._t += dt_s
        return self._t

    def set(self, t_s: float) -> None:
        if not math.isfinite(t_s):
            raise ValueError("t_s finito")
        self._t = float(t_s)


class SimChannel:
    """Canale simulato (implementa la porta `Channel`)."""

    def __init__(self, config: ChannelConfig, clock: Callable[[], float] | None = None) -> None:
        self.config = config
        self._clock = clock
        self._rng = random.Random(config.seed)
        self._heap: list[tuple[float, int, bytes]] = []
        self._seq = 0
        self._link_free_at = -math.inf
        w = config.contact_windows
        self._starts = [s for s, _ in w] if w is not None else None
        self._ends = [e for _, e in w] if w is not None else None
        self._c = dict.fromkeys(
            (
                "sent",
                "delivered",
                "lost",
                "dropped_outside_window",
                "lost_random",
                "lost_overflow",
                "corrupted",
                "bits_flipped",
            ),
            0,
        )

    # --- utilita' ---

    def _in_window(self, t: float) -> bool:
        if self._starts is None or self._ends is None:
            return True
        i = bisect_right(self._starts, t) - 1
        return i >= 0 and t < self._ends[i]

    def _flip_bits(self, data: bytes) -> tuple[bytes, int]:
        ber = self.config.bit_error_rate
        nbits = len(data) * 8
        if ber <= 0.0 or nbits == 0:
            return data, 0
        buf = bytearray(data)
        flips = 0
        if ber >= 1.0:
            buf = bytearray(b ^ 0xFF for b in buf)
            flips = nbits
        else:
            log_q = math.log1p(-ber)
            pos = 0
            while True:  # salto geometrico fra un errore e il successivo: O(errori), non O(bit)
                pos += int(math.log(1.0 - self._rng.random()) / log_q)
                if pos >= nbits:
                    break
                buf[pos >> 3] ^= 1 << (pos & 7)
                flips += 1
                pos += 1
        return bytes(buf), flips

    # --- porta Channel ---

    def send(self, data: bytes, *, now_s: float | None = None) -> None:
        """Transazionale: se solleva, contatori, banda e stato casuale tornano come prima."""
        saved = (dict(self._c), self._link_free_at, self._rng.getstate(), self._seq)
        try:
            self._send(data, now_s)
        except BaseException:
            self._c, self._link_free_at, rng_state, self._seq = saved
            self._rng.setstate(rng_state)
            raise

    def _send(self, data: bytes, now_s: float | None) -> None:
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError("data: bytes")
        if now_s is None:
            if self._clock is None:
                raise ValueError("now_s richiesto (nessun orologio iniettato)")
            now_s = self._clock()
        if not math.isfinite(now_s):
            raise ValueError("now_s finito")
        payload = bytes(data)
        cfg, c = self.config, self._c
        c["sent"] += 1
        if not self._in_window(now_s):
            c["dropped_outside_window"] += 1
            return
        if len(self._heap) >= cfg.max_in_flight:
            c["lost"] += 1
            c["lost_overflow"] += 1
            return
        tx_end = now_s
        if cfg.bandwidth_bps is not None:
            start = max(now_s, self._link_free_at)
            tx_end = start + len(payload) * 8 / cfg.bandwidth_bps
            self._link_free_at = tx_end
        p = cfg.loss_probability
        if p >= 1.0 or (p > 0.0 and self._rng.random() < p):
            c["lost"] += 1
            c["lost_random"] += 1
            return
        jitter = self._rng.uniform(0.0, cfg.jitter_s) if cfg.jitter_s > 0 else 0.0
        arrival = tx_end + cfg.delay_s + jitter
        if not self._in_window(arrival):
            c["dropped_outside_window"] += 1
            return
        payload, flips = self._flip_bits(payload)
        if flips:
            c["corrupted"] += 1
            c["bits_flipped"] += flips
        heapq.heappush(self._heap, (arrival, self._seq, payload))
        self._seq += 1

    def deliver_timed(self, now_s: float) -> list[tuple[float, bytes]]:
        """Come `deliver` ma con l'istante di arrivo di ogni frame."""
        if math.isnan(now_s):
            raise ValueError("now_s non puo' essere NaN")
        out: list[tuple[float, bytes]] = []
        while self._heap and self._heap[0][0] <= now_s:
            arrival, _, payload = heapq.heappop(self._heap)
            out.append((arrival, payload))
        self._c["delivered"] += len(out)
        return out

    def deliver(self, now_s: float) -> list[bytes]:
        return [p for _, p in self.deliver_timed(now_s)]

    def deliver_due(self) -> list[bytes]:
        """`deliver` all'istante dell'orologio iniettato."""
        if self._clock is None:
            raise ValueError("nessun orologio iniettato")
        return self.deliver(self._clock())

    def next_arrival_s(self) -> float | None:
        return self._heap[0][0] if self._heap else None

    def stats(self) -> Mapping[str, int]:
        s = dict(self._c)
        s["in_flight"] = len(self._heap)
        return s
