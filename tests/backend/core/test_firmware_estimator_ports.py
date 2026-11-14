# SPDX-License-Identifier: Apache-2.0
from collections.abc import Mapping

import pytest

from backend.core.manifest import load_manifest
from backend.core.ports import Estimator, FirmwareSim, Simulation

MANIFEST = 'id="a"\nkind="{kind}"\nversion="0.1.0"\nentry="python:x:Y"\nlicense="Apache-2.0"\n'


class FakeFirmware:
    async def load(self, image: str) -> None: ...

    async def step(self, dt_s: float, inputs: Mapping[str, float]) -> Mapping[str, float]:
        return {"servo_deg": 0.0}

    async def reset(self) -> None: ...


class FakeEstimator:
    def predict(self, dt_s: float) -> None: ...

    def update(
        self, measurement: Mapping[str, float], dt_s: float | None = None
    ) -> Mapping[str, float]:
        return {"yaw_deg": 0.0}

    def reset(self) -> None: ...


class FakeSim:
    async def run(self, inputs: Mapping[str, float], *, timeout_s: float) -> Mapping[str, float]:
        return {}


def test_protocols_are_structural_and_distinct() -> None:
    assert isinstance(FakeFirmware(), FirmwareSim)
    assert isinstance(FakeEstimator(), Estimator)
    assert not isinstance(FakeEstimator(), FirmwareSim)
    assert not isinstance(FakeSim(), Estimator)
    assert not isinstance(FakeSim(), FirmwareSim)
    assert isinstance(FakeSim(), Simulation)


@pytest.mark.parametrize("kind", ["firmware", "estimator"])
def test_manifest_accepts_new_kinds(tmp_path, kind: str) -> None:  # type: ignore[no-untyped-def]
    (tmp_path / "manifest.toml").write_text(MANIFEST.format(kind=kind))
    assert load_manifest(tmp_path / "manifest.toml").kind == kind
