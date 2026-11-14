# SPDX-License-Identifier: Apache-2.0
"""Test dell'estimatore IMU con dati sintetici a rotazione nota.

Verita': rotazione costante di RATE_DPS attorno a z (convenzione NWU, asse z in alto),
assetto iniziale = identita'. Lo yaw vero al passo k e' RATE_DPS * k * DT_S.
Si salta il modulo se l'extra `[fusion]` (imufusion) non e' installato.
"""

import math
from pathlib import Path

import pytest

pytest.importorskip("imufusion")

from backend.bootstrap import make_loader
from backend.core.manifest import load_manifest
from backend.core.ports import Estimator
from backend.core.registry import Registry
from backend.plugins.estimator_imu.plugin import ImuEstimator

PLUGIN_DIR = Path(__file__).resolve().parents[2] / "backend" / "plugins" / "estimator_imu"
RATE_DPS = 30.0
DT_S = 0.01
STEPS = 1000  # 10 s -> rotazione vera di 300 gradi
MAG_NORTH_UT, MAG_UP_UT = (
    20.0,
    -40.0,
)  # campo terrestre in NWU (componente verticale verso il basso)


def make() -> ImuEstimator:
    return ImuEstimator(load_manifest(PLUGIN_DIR / "manifest.toml"))


def angle_err_deg(a: float, b: float) -> float:
    """Differenza angolare con wrap in [-180, 180]."""
    return abs((a - b + 180.0) % 360.0 - 180.0)


def gyro(rate: float = RATE_DPS, bias: float = 0.0) -> dict[str, float]:
    return {"gyro_x_dps": 0.0, "gyro_y_dps": 0.0, "gyro_z_dps": rate + bias}


def accel() -> dict[str, float]:
    # Rotazione attorno a z: la gravita' nel corpo resta (0, 0, 1) g.
    return {"accel_x_g": 0.0, "accel_y_g": 0.0, "accel_z_g": 1.0}


def mag(yaw_deg: float) -> dict[str, float]:
    y = math.radians(yaw_deg)
    return {
        "mag_x_ut": MAG_NORTH_UT * math.cos(y),
        "mag_y_ut": -MAG_NORTH_UT * math.sin(y),
        "mag_z_ut": MAG_UP_UT,
    }


def run(
    est: ImuEstimator, *, with_accel: bool, with_mag: bool, bias: float = 0.0, yaw0: float = 0.0
) -> dict[str, float]:
    out: dict[str, float] = {}
    est.predict(DT_S)
    for k in range(1, STEPS + 1):
        true_yaw = yaw0 + RATE_DPS * k * DT_S
        m = gyro(bias=bias)
        if with_accel:
            m |= accel()
        if with_mag:
            m |= mag(true_yaw)
        out = dict(est.update(m))
    return out


def test_is_estimator_and_loadable_via_registry() -> None:
    assert isinstance(make(), Estimator)
    reg = Registry()
    errors = reg.discover(PLUGIN_DIR.parent, make_loader())
    assert not [p for p, _ in errors if p.name == "estimator_imu"]
    assert reg.create("estimator", "estimator-imu") is not None


def test_manifest_fields() -> None:
    m = load_manifest(PLUGIN_DIR / "manifest.toml")
    assert m.kind == "estimator"
    assert m.license == "Apache-2.0"
    assert m.entry == "python:backend.plugins.estimator_imu.plugin:ImuEstimator"


def test_gyro_only_constant_rate() -> None:
    # Solo giroscopio, nessuna correzione: l'errore e' solo integrazione numerica in float32
    # (misurato ~7e-4 deg dopo 300 deg di rotazione). Soglia 0.01 deg, ~14x di margine.
    out = run(make(), with_accel=False, with_mag=False)
    assert angle_err_deg(out["yaw_deg"], RATE_DPS * STEPS * DT_S) < 0.01
    assert abs(out["roll_deg"]) < 0.01 and abs(out["pitch_deg"]) < 0.01


def test_accel_and_mag_consistent() -> None:
    # Con accel+mag coerenti il filtro segue lo yaw vero; l'errore residuo e' il ritardo
    # del feedback magnetico (misurato ~0.3 deg a 30 dps). Soglia 1 deg.
    out = run(make(), with_accel=True, with_mag=True)
    assert angle_err_deg(out["yaw_deg"], RATE_DPS * STEPS * DT_S) < 1.0
    assert abs(out["roll_deg"]) < 0.1 and abs(out["pitch_deg"]) < 0.1


def test_mag_corrects_gyro_bias() -> None:
    # Bias giroscopio 1 dps: senza correzione, errore 10 deg dopo 10 s. Il magnetometro
    # lo limita; soglia 4 deg (< meta' dell'errore non corretto).
    out = run(make(), with_accel=True, with_mag=True, bias=1.0)
    assert angle_err_deg(out["yaw_deg"], RATE_DPS * STEPS * DT_S) < 4.0
    uncorrected = run(make(), with_accel=False, with_mag=False, bias=1.0)
    assert angle_err_deg(uncorrected["yaw_deg"], RATE_DPS * STEPS * DT_S) > 9.0


def test_mag_converges_from_wrong_initial_heading() -> None:
    # Assetto iniziale (identita') sbagliato di 90 deg rispetto al campo magnetico,
    # corpo fermo: dopo 10 s lo yaw stimato deve essere entro 2 deg dal vero (90).
    est = make()
    est.predict(DT_S)
    out: dict[str, float] = {}
    for _ in range(STEPS):
        out = dict(est.update(gyro(0.0) | accel() | mag(90.0)))
    assert angle_err_deg(out["yaw_deg"], 90.0) < 2.0


def test_output_keys_and_unit_quaternion() -> None:
    out = run(make(), with_accel=True, with_mag=True)
    assert set(out) == {"qw", "qx", "qy", "qz", "roll_deg", "pitch_deg", "yaw_deg"}
    assert math.isclose(sum(out[k] ** 2 for k in ("qw", "qx", "qy", "qz")), 1.0, abs_tol=1e-4)


@pytest.mark.parametrize("dt", [0.0, -0.01, math.nan, math.inf, -math.inf])
def test_predict_rejects_bad_dt(dt: float) -> None:
    with pytest.raises(ValueError, match="dt_s"):
        make().predict(dt)


def test_update_requires_predict_first() -> None:
    with pytest.raises(ValueError, match="predict"):
        make().update(gyro())


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
@pytest.mark.parametrize("key", ["gyro_z_dps", "accel_z_g", "mag_x_ut"])
def test_update_rejects_non_finite(key: str, bad: float) -> None:
    est = make()
    est.predict(DT_S)
    m = gyro() | accel() | mag(0.0)
    m[key] = bad
    with pytest.raises(ValueError, match=key):
        est.update(m)


def test_update_rejects_missing_or_partial_keys() -> None:
    est = make()
    est.predict(DT_S)
    with pytest.raises(ValueError, match="gyro_y_dps"):
        est.update({"gyro_x_dps": 0.0, "gyro_z_dps": 0.0})
    with pytest.raises(ValueError, match="accel"):
        est.update(gyro() | {"accel_x_g": 0.0})
    with pytest.raises(ValueError, match="mag"):
        est.update(gyro() | accel() | {"mag_x_ut": 1.0})
    with pytest.raises(ValueError, match="accel"):
        est.update(gyro() | mag(0.0))  # magnetometro senza accelerometro


def test_rejected_update_does_not_corrupt_state() -> None:
    est = make()
    est.predict(DT_S)
    est.update(gyro())
    before = est.update(gyro())
    with pytest.raises(ValueError):
        est.update(gyro() | {"accel_x_g": math.nan, "accel_y_g": 0.0, "accel_z_g": 1.0})
    after = est.update(gyro(0.0))
    assert abs(after["yaw_deg"] - before["yaw_deg"]) < 0.1


def test_reset_restores_identity() -> None:
    est = make()
    run(est, with_accel=False, with_mag=False)
    est.reset()
    est.predict(DT_S)
    out = est.update(gyro(0.0))
    assert angle_err_deg(out["yaw_deg"], 0.0) < 1e-3
