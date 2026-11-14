# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("imufusion")

from backend.core.manifest import load_manifest
from backend.plugins.estimator_imu.plugin import ImuEstimator

ROOT = Path(__file__).resolve().parents[2]
GYRO = {"gyro_x_dps": 0.0, "gyro_y_dps": 0.0, "gyro_z_dps": 30.0}


class Exploding:
    def set_sample_period(self, dt: float) -> None: ...

    def update_no_magnetometer(self, *a: Any) -> None:
        raise RuntimeError("libreria fallita")


def test_dt_not_committed_when_ahrs_update_fails() -> None:
    est = ImuEstimator(load_manifest(ROOT / "backend/plugins/estimator_imu/manifest.toml"))
    est.predict(0.01)
    real = est._ahrs
    est._ahrs = Exploding()  # type: ignore[assignment]
    with pytest.raises(RuntimeError):
        est.update(GYRO, dt_s=0.5)
    assert est._dt_s == 0.01  # il passo 0.5 non e' stato salvato
    est._ahrs = real
    out = est.update(GYRO)
    assert abs(out["yaw_deg"] - 0.3) < 0.01
