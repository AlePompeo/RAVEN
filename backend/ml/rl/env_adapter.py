# SPDX-License-Identifier: Apache-2.0
"""Ambiente RL `SimulationEnv`: posizionamento di un servo con impianto di riferimento in Python.

Scelta di progetto (giustificata)
---------------------------------
La simulazione `servo_ctrl_c` e' un *episodio chiuso* (processo C con il proprio PI interno):
usarla per passo significherebbe un `exec` per ogni `step` (millisecondi) e nessuno stato
intermedio, quindi non e' un MDP a passi. L'ambiente avvolge perche' un **impianto di
riferimento puro Python** (`ServoPlant`) che ricalca la stessa fisica (angolo che integra una
velocita' limitata a `rate_dps`, con ritardo del primo ordine `tau_s`): niente processi, centinaia
di migliaia di passi/s, deterministico e senza numpy ne' gymnasium. Il confronto numerico con il
binario C NON e' stato fatto (vedi docs/ml.md): l'impianto e' un modello, non il firmware.

Contratto (porta `backend.core.ports.Environment`)
--------------------------------------------------
* Azione: 1 componente in [-1, 1] = frazione del comando di velocita' massimo. Valori finiti fuori
  limite sono *clippati* (e penalizzati, vedi sotto); NaN/inf/tipi errati sollevano `ValueError`
  PRIMA di toccare lo stato (mai propagati).
* Osservazione (3 componenti in [-1, 1], clippate): errore misurato / 180 deg (con rumore del
  sensore gaussiano `sensor_noise_deg`), velocita' / `rate_dps`, setpoint / `setpoint_range_deg`.
* Ricompensa: ``r = -|errore_vero_deg| / reward_scale_deg - SAT_PENALTY * [azione fuori limite]``.
  Limiti: ``-(max_abs_error_deg / reward_scale_deg) - SAT_PENALTY <= r <= 0``.
* `terminated`: errore <= `success_tol_deg` e velocita' <= `settle_rate_dps` (assestato). Con
  ricompensa sempre negativa terminare prima e' meglio: premia l'assestamento rapido.
* `truncated`: dopo `max_steps` passi senza terminare.
* Determinismo: `reset(seed)` riavvia un `random.Random` dedicato; `reset()` senza seme continua lo
  stesso flusso (riproducibile da un seme iniziale; il seme di default e' 0).
"""

import math
import random
from collections.abc import Sequence
from typing import Any

from backend.core.ports import BoxSpace

SAT_PENALTY = 0.05
MAX_SEED = 2**32 - 1
MAX_STEPS_LIMIT = 100_000
ERROR_NORM_DEG = 180.0


def _finite(name: str, value: object, lo: float, hi: float) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not math.isfinite(value)
        or not lo <= value <= hi
    ):
        raise ValueError(f"{name}: numero finito in [{lo}, {hi}] richiesto")
    return float(value)


class ServoPlant:
    """Servo: velocita' con ritardo del primo ordine verso `u * rate_dps`, angolo integrato.

    Discretizzazione esatta del ritardo (`1 - exp(-dt/tau)`): stabile per ogni `dt_s`. L'angolo
    e' limitato a +-`angle_limit_deg` (finecorsa: la velocita' si azzera).

    Non linearita' OPZIONALI (default 0 = spente; valori illustrativi, NON misurati; unita' nel nome):

    * `deadband_deg`: banda morta sul comando. Il comando `u` richiede uno spostamento
      `|u| * rate_dps * dt_s` per periodo; se e' < `deadband_deg` il comando e' ignorato (target 0).
      Motivazione: i servo hobby hanno una banda morta di ~0.5-2 deg (il driver non reagisce a
      variazioni piccole; qui espressa come spostamento comandato per periodo di controllo).
    * `stiction_dps`: attrito statico espresso come velocita' equivalente. Se il target e' <=
      soglia e la velocita' risultante e' <= soglia, il giunto si "incolla" (velocita' = 0) e
      si stacca solo con un target maggiore (stick-slip a bassa velocita').
    * `backlash_deg`: gioco meccanico totale negli ingranaggi. L'angolo di uscita (misurato) segue
      il motore solo dopo aver preso il gioco (+-`backlash_deg`/2): all'inversione l'uscita resta
      ferma finche' il gioco non e' attraversato.
    """

    def __init__(
        self,
        *,
        dt_s: float,
        tau_s: float,
        rate_dps: float,
        angle_limit_deg: float,
        deadband_deg: float = 0.0,
        stiction_dps: float = 0.0,
        backlash_deg: float = 0.0,
    ) -> None:
        self.dt_s = dt_s
        self.rate_dps = rate_dps
        self.angle_limit_deg = angle_limit_deg
        self.deadband_deg = deadband_deg
        self.stiction_dps = stiction_dps
        self.backlash_deg = backlash_deg
        self._alpha = 1.0 - math.exp(-dt_s / tau_s)
        self._motor_deg = 0.0
        self.angle_deg = 0.0
        self.velocity_dps = 0.0

    def reset(self) -> None:
        self._motor_deg = 0.0
        self.angle_deg = 0.0
        self.velocity_dps = 0.0

    def advance(self, command: float) -> None:
        target = command * self.rate_dps
        if self.deadband_deg and abs(target) * self.dt_s < self.deadband_deg:
            target = 0.0
        v = self.velocity_dps + (target - self.velocity_dps) * self._alpha
        if self.stiction_dps and abs(target) <= self.stiction_dps and abs(v) <= self.stiction_dps:
            v = 0.0
        self.velocity_dps = v
        self._motor_deg += v * self.dt_s
        if abs(self._motor_deg) >= self.angle_limit_deg:
            self._motor_deg = math.copysign(self.angle_limit_deg, self._motor_deg)
            self.velocity_dps = 0.0
        if self.backlash_deg:
            half = self.backlash_deg / 2.0
            if self._motor_deg - self.angle_deg > half:
                self.angle_deg = self._motor_deg - half
            elif self.angle_deg - self._motor_deg > half:
                self.angle_deg = self._motor_deg + half
        else:
            self.angle_deg = self._motor_deg
        self.angle_deg = max(-self.angle_limit_deg, min(self.angle_limit_deg, self.angle_deg))


# Profili con nome. `servo_realistic`: valori scelti PRIMA di qualunque confronto con i baseline,
# da un criterio dichiarato (banda morta tipica di un servo hobby 0.5-2 deg -> punto medio 1.0;
# gioco ingranaggi tipico 0.5-2 deg -> 1.0; attrito statico ~5% della velocita' massima, 90 dps ->
# 5 dps). Sono ILLUSTRATIVI, non misurati su hardware.
PROFILES: dict[str, dict[str, Any]] = {
    "nominal": {},
    "servo_realistic": {"deadband_deg": 1.0, "stiction_dps": 5.0, "backlash_deg": 1.0},
}


def profile_kwargs(name: str) -> dict[str, Any]:
    if name not in PROFILES:
        raise ValueError(f"profilo sconosciuto: {name!r} (ammessi: {sorted(PROFILES)})")
    return dict(PROFILES[name])


class SimulationEnv:
    def __init__(
        self,
        *,
        max_steps: int = 100,
        dt_s: float = 0.1,
        tau_s: float = 0.3,
        rate_dps: float = 90.0,
        setpoint_range_deg: float = 90.0,
        angle_limit_deg: float = 180.0,
        sensor_noise_deg: float = 0.2,
        success_tol_deg: float = 1.0,
        settle_rate_dps: float = 5.0,
        reward_scale_deg: float = 90.0,
        deadband_deg: float = 0.0,
        stiction_dps: float = 0.0,
        backlash_deg: float = 0.0,
    ) -> None:
        if (
            isinstance(max_steps, bool)
            or not isinstance(max_steps, int)
            or not 1 <= max_steps <= MAX_STEPS_LIMIT
        ):
            raise ValueError(f"max_steps: intero in [1, {MAX_STEPS_LIMIT}] richiesto")
        self.max_steps = max_steps
        self.dt_s = _finite("dt_s", dt_s, 1e-3, 1.0)
        self.tau_s = _finite("tau_s", tau_s, self.dt_s, 100.0)
        tau = self.tau_s
        self.rate_dps = _finite("rate_dps", rate_dps, 1e-3, 1000.0)
        self.setpoint_range_deg = _finite("setpoint_range_deg", setpoint_range_deg, 0.0, 180.0)
        self.angle_limit_deg = _finite("angle_limit_deg", angle_limit_deg, 1.0, 720.0)
        self.sensor_noise_deg = _finite("sensor_noise_deg", sensor_noise_deg, 0.0, 10.0)
        self.success_tol_deg = _finite("success_tol_deg", success_tol_deg, 0.0, 90.0)
        self.settle_rate_dps = _finite("settle_rate_dps", settle_rate_dps, 0.0, 1000.0)
        self.reward_scale_deg = _finite("reward_scale_deg", reward_scale_deg, 1e-3, 1e6)
        self.deadband_deg = _finite("deadband_deg", deadband_deg, 0.0, 10.0)
        self.stiction_dps = _finite("stiction_dps", stiction_dps, 0.0, 100.0)
        self.backlash_deg = _finite("backlash_deg", backlash_deg, 0.0, 10.0)
        self.max_abs_error_deg = self.setpoint_range_deg + self.angle_limit_deg
        self._plant = ServoPlant(
            dt_s=self.dt_s,
            tau_s=tau,
            rate_dps=self.rate_dps,
            angle_limit_deg=self.angle_limit_deg,
            deadband_deg=self.deadband_deg,
            stiction_dps=self.stiction_dps,
            backlash_deg=self.backlash_deg,
        )
        self.observation_space = BoxSpace(low=(-1.0,) * 3, high=(1.0,) * 3, shape=(3,))
        self.action_space = BoxSpace(low=(-1.0,), high=(1.0,), shape=(1,))
        self._rng = random.Random(0)
        self._setpoint_deg = 0.0
        self._t = 0
        self._active = False

    def _observe(self) -> tuple[float, float, float]:
        noise = self._rng.gauss(0.0, self.sensor_noise_deg) if self.sensor_noise_deg else 0.0
        err = (self._setpoint_deg - self._plant.angle_deg + noise) / ERROR_NORM_DEG
        vel = self._plant.velocity_dps / self.rate_dps
        sp = self._setpoint_deg / self.setpoint_range_deg if self.setpoint_range_deg else 0.0
        return (_clip1(err), _clip1(vel), _clip1(sp))

    def reset(self, seed: int | None = None) -> tuple[tuple[float, ...], dict[str, Any]]:
        if seed is not None:
            if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= MAX_SEED:
                raise ValueError(f"seed: intero in [0, {MAX_SEED}] richiesto")
            self._rng = random.Random(seed)
        r = self.setpoint_range_deg
        self._setpoint_deg = self._rng.uniform(-r, r) if r else 0.0
        self._plant.reset()
        self._t = 0
        self._active = True
        return self._observe(), {"setpoint_deg": self._setpoint_deg}

    @staticmethod
    def _parse_action(action: object) -> float:
        """Accetta una sequenza/array di 1 numero reale; tutto il resto e' ValueError."""
        try:
            if isinstance(action, str | bytes) or len(action) != 1:  # type: ignore[arg-type]
                raise ValueError
            raw = action[0]  # type: ignore[index]
            if isinstance(raw, bool | str | bytes):
                raise TypeError
            a = float(raw)
        except (TypeError, ValueError, IndexError, KeyError):
            raise ValueError("azione: sequenza di 1 numero reale richiesta") from None
        if not math.isfinite(a):
            raise ValueError("azione non finita")
        return a

    def step(
        self, action: Sequence[float]
    ) -> tuple[tuple[float, ...], float, bool, bool, dict[str, Any]]:
        if not self._active:
            raise RuntimeError("step senza reset o dopo la fine dell'episodio")
        raw = self._parse_action(action)  # nessuna modifica di stato prima della validazione
        applied = max(-1.0, min(1.0, raw))
        clipped = applied != raw
        self._plant.advance(applied)
        self._t += 1
        error = self._setpoint_deg - self._plant.angle_deg
        reward = -abs(error) / self.reward_scale_deg - (SAT_PENALTY if clipped else 0.0)
        settled = (
            abs(error) <= self.success_tol_deg
            and abs(self._plant.velocity_dps) <= self.settle_rate_dps
        )
        truncated = (not settled) and self._t >= self.max_steps
        self._active = not (settled or truncated)
        info = {
            "setpoint_deg": self._setpoint_deg,
            "error_deg": error,
            "action_clipped": clipped,
            "applied_action": applied,
            "settled": settled,
        }
        return self._observe(), float(reward), settled, truncated, info


def _clip1(x: float) -> float:
    return max(-1.0, min(1.0, x))
