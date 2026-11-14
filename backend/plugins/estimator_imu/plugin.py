# SPDX-License-Identifier: Apache-2.0
"""Estimatore di assetto IMU: wrapper di `imufusion` (xioTechnologies/Fusion, MIT).

Richiede l'extra opzionale `[fusion]`; senza, l'import fallisce e il loader riporta un
PluginError per questo solo plugin (gli altri partono comunque).

Convenzione: NWU (x nord, y ovest, z alto). Unita': giroscopio in deg/s, accelerometro in g,
magnetometro in uT. Fusion e' un filtro AHRS (Madgwick modificato): non produce covarianza,
quindi l'uscita e' una mappa nome->valore e non un messaggio `state_estimate` completo.
"""

import math
from collections.abc import Mapping

import imufusion
import numpy as np

from backend.core.errors import InvalidMeasurement

GYRO_KEYS = ("gyro_x_dps", "gyro_y_dps", "gyro_z_dps")
ACCEL_KEYS = ("accel_x_g", "accel_y_g", "accel_z_g")
MAG_KEYS = ("mag_x_ut", "mag_y_ut", "mag_z_ut")


def _vector(
    m: Mapping[str, float], keys: tuple[str, str, str], *, required: bool
) -> np.ndarray | None:
    present = [k for k in keys if k in m]
    if not present:
        if required:
            raise InvalidMeasurement(f"misura incompleta: mancano {list(keys)}")
        return None
    missing = [k for k in keys if k not in m]
    if missing:
        raise InvalidMeasurement(f"misura incompleta: mancano {missing}")
    values: list[float] = []
    for k in keys:
        try:
            v = float(m[k])
        except (TypeError, ValueError):  # float() della libreria: messaggio nostro
            raise InvalidMeasurement(f"{k} non numerico") from None
        if not math.isfinite(v):
            raise InvalidMeasurement(f"{k} non finito")
        values.append(v)
    return np.array(values, dtype=np.float64)


class ImuEstimator:
    """Porta `Estimator`: `predict(dt_s)` fissa il passo, `update(misura)` fa un passo AHRS.

    Misura: giroscopio obbligatorio; accelerometro opzionale (senza, solo integrazione del
    giroscopio); magnetometro opzionale e solo insieme all'accelerometro.
    """

    def __init__(self, manifest: object) -> None:
        self.manifest = manifest
        self._dt_s: float | None = None
        self._ahrs = self._new_ahrs()

    @staticmethod
    def _new_ahrs() -> "imufusion.Ahrs":
        ahrs = imufusion.Ahrs()
        ahrs.set_settings(imufusion.AhrsSettings(convention=imufusion.CONVENTION_NWU))
        # Fusion ignora il giroscopio durante i primi ~3 s di avvio: qui l'assetto iniziale e'
        # l'identita' dichiarata, quindi si salta la fase.
        ahrs.skip_startup()
        return ahrs

    def reset(self) -> None:
        """Stato iniziale: assetto identita' e nessun passo impostato."""
        self._ahrs = self._new_ahrs()
        self._dt_s = None

    @staticmethod
    def _check_dt(dt_s: float) -> float:
        try:
            dt = float(dt_s)
        except (TypeError, ValueError):  # float() della libreria: messaggio nostro
            raise InvalidMeasurement("dt_s non numerico") from None
        if not math.isfinite(dt) or dt <= 0:
            raise InvalidMeasurement(f"dt_s deve essere finito e > 0, ricevuto {dt_s!r}")
        return dt

    def predict(self, dt_s: float) -> None:
        """Imposta il passo di campionamento per i prossimi `update`."""
        self._dt_s = self._check_dt(dt_s)

    def update(
        self, measurement: Mapping[str, float], dt_s: float | None = None
    ) -> Mapping[str, float]:
        """Un passo AHRS. Valida tutto (misura e `dt_s`) prima di toccare lo stato: un
        rifiuto non cambia ne' il filtro ne' il passo; `dt_s` viene applicato solo a successo."""
        dt = self._check_dt(dt_s) if dt_s is not None else self._dt_s
        if dt is None:
            raise InvalidMeasurement("passo non impostato: chiamare predict(dt_s) o passare dt_s")
        gyro = _vector(measurement, GYRO_KEYS, required=True)
        accel = _vector(measurement, ACCEL_KEYS, required=False)
        mag = _vector(measurement, MAG_KEYS, required=False)
        if mag is not None and accel is None:
            raise InvalidMeasurement("il magnetometro richiede anche l'accelerometro (accel_*)")
        assert gyro is not None
        self._ahrs.set_sample_period(dt)  # idempotente: ripetuto a ogni update
        if accel is None:
            # Accelerometro nullo: Fusion salta la correzione e integra solo il giroscopio.
            self._ahrs.update_no_magnetometer(gyro, np.zeros(3))
        elif mag is None:
            self._ahrs.update_no_magnetometer(gyro, accel)
        else:
            self._ahrs.update(gyro, accel, mag)
        self._dt_s = dt  # impegnato solo dopo il successo dell'aggiornamento
        q = self._ahrs.get_quaternion()
        roll, pitch, yaw = (float(a) for a in imufusion.quaternion_to_euler(q))
        # Il quaternione di Fusion e' in ordine (w, x, y, z).
        return {
            "qw": float(q[0]),
            "qx": float(q[1]),
            "qy": float(q[2]),
            "qz": float(q[3]),
            "roll_deg": roll,
            "pitch_deg": pitch,
            "yaw_deg": yaw,
        }
