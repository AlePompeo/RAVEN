# SPDX-License-Identifier: Apache-2.0
"""Circuit breaker per candidato: chiuso -> aperto (dopo N guasti consecutivi o un 429) -> mezzo aperto.

Dopo il tempo di raffreddamento passa UNA sola richiesta di prova (half-open); se riesce il
breaker si chiude, se fallisce si riapre per un nuovo raffreddamento. Nessun sleep: il tempo e'
un orologio iniettato, cosi' i test sono deterministici e non c'e' alcuna tempesta di retry.
"""

import time
from collections.abc import Callable, Hashable
from dataclasses import dataclass

IMMEDIATE_OPEN = ("http_429",)


@dataclass
class _State:
    failures: int = 0
    open_until: float | None = None
    probing_since: float | None = None
    last_error: str | None = None


class CircuitBreakers:
    def __init__(
        self,
        failures: int = 3,
        cooldown_s: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.threshold, self.cooldown_s, self._clock = failures, cooldown_s, clock
        self._states: dict[Hashable, _State] = {}

    def _st(self, key: Hashable) -> _State:
        return self._states.setdefault(key, _State())

    def is_open(self, key: Hashable) -> bool:
        """Sola lettura: True se le richieste sono sospese (aperto e raffreddamento non scaduto)."""
        st = self._states.get(key)
        return bool(st and st.open_until is not None and self._clock() < st.open_until)

    def allow(self, key: Hashable) -> bool:
        """Chiede il permesso di inviare una richiesta (consuma l'unica prova in half-open)."""
        st = self._st(key)
        if st.open_until is None:
            return True
        now = self._clock()
        if now < st.open_until:
            return False
        if st.probing_since is not None and now - st.probing_since < self.cooldown_s:
            return False  # una prova e' gia' in corso
        st.probing_since = now
        return True

    def success(self, key: Hashable) -> None:
        self._states[key] = _State()

    def failure(self, key: Hashable, code: str) -> None:
        st = self._st(key)
        st.last_error = code
        st.failures += 1
        was_probe = st.probing_since is not None
        st.probing_since = None
        if was_probe or code in IMMEDIATE_OPEN or st.failures >= self.threshold:
            st.open_until = self._clock() + self.cooldown_s

    def last_error(self, key: Hashable) -> str | None:
        st = self._states.get(key)
        return st.last_error if st else None

    def state(self, key: Hashable) -> str:
        st = self._states.get(key)
        if st is None or st.open_until is None:
            return "closed"
        return "open" if self._clock() < st.open_until else "half_open"
