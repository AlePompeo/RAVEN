# SPDX-License-Identifier: Apache-2.0
import asyncio
from collections.abc import Mapping
from typing import Any

import httpx
import pytest

from backend.bootstrap import build_app
from backend.core.errors import SimulationTimeout

URL = "/api/simulations/example-sim/run"
BODY = {"inputs": {"x": 1.0}}


class SlowSim:
    """Simulazione finta: resta in corso finche' il test non la rilascia (nessun sleep)."""

    started = 0
    gate: asyncio.Event
    entered: asyncio.Event
    fail: Exception | None = None

    async def run(self, inputs: Mapping[str, float], timeout_s: float) -> Mapping[str, float]:
        SlowSim.started += 1
        SlowSim.entered.set()
        await SlowSim.gate.wait()
        if SlowSim.fail is not None:
            raise SlowSim.fail
        return {"y": 1.0}


@pytest.fixture(autouse=True)
def _fresh() -> None:
    SlowSim.started = 0
    SlowSim.gate = asyncio.Event()
    SlowSim.entered = asyncio.Event()
    SlowSim.fail = None


def make_app(monkeypatch: pytest.MonkeyPatch, cap: int) -> Any:
    monkeypatch.setenv("SIM_MAX_CONCURRENT", str(cap))
    app = build_app()
    app.state.registry.create = lambda kind, id: SlowSim()
    return app


async def wait_started(n: int) -> None:
    while SlowSim.started < n:
        SlowSim.entered.clear()
        await SlowSim.entered.wait()


async def test_default_cap_is_8(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SIM_MAX_CONCURRENT", raising=False)
    assert build_app().state.sim_max_concurrent == 8


async def test_saturated_returns_503_with_retry_after_then_recovers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = make_app(monkeypatch, 2)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        running = [asyncio.create_task(c.post(URL, json=BODY)) for _ in range(2)]
        await asyncio.wait_for(wait_started(2), 5)
        rejected = await c.post(URL, json=BODY)
        assert rejected.status_code == 503
        assert rejected.headers["retry-after"]
        assert SlowSim.started == 2  # la terza non ha avviato nulla
        SlowSim.gate.set()
        assert [r.status_code for r in await asyncio.gather(*running)] == [200, 200]
        assert (await c.post(URL, json=BODY)).status_code == 200


@pytest.mark.parametrize(
    ("exc", "status"), [(SimulationTimeout("t"), 504), (RuntimeError("boom"), 500)]
)
async def test_slot_released_on_failure(
    monkeypatch: pytest.MonkeyPatch, exc: Exception, status: int
) -> None:
    app = make_app(monkeypatch, 1)
    SlowSim.fail = exc
    SlowSim.gate.set()
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        assert (await c.post(URL, json=BODY)).status_code == status
        assert not app.state.sim_sem.locked()
        assert (await c.post(URL, json=BODY)).status_code == status  # non 503


async def test_slot_released_on_cancellation(monkeypatch: pytest.MonkeyPatch) -> None:
    app = make_app(monkeypatch, 1)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        task = asyncio.create_task(c.post(URL, json=BODY))
        await asyncio.wait_for(wait_started(1), 5)
        assert app.state.sim_sem.locked()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        for _ in range(50):  # lascia girare il loop finche' la cancellazione si propaga
            if not app.state.sim_sem.locked():
                break
            await asyncio.sleep(0)
        assert not app.state.sim_sem.locked()
