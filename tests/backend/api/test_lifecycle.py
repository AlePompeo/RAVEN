# SPDX-License-Identifier: Apache-2.0
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.api.app import LIFECYCLE_ORDER
from backend.bootstrap import build_app


class Recorder:
    def __init__(self, events: list[str], name: str, fail_stop: bool = False) -> None:
        self.events, self.name, self.fail_stop = events, name, fail_stop

    async def start(self) -> None:
        self.events.append(f"start:{self.name}")

    async def aclose(self) -> None:
        self.events.append(f"stop:{self.name}")
        if self.fail_stop:
            raise RuntimeError("boom")


class FakePipeline:
    def __init__(self, events: list[str]) -> None:
        self.scheduler = Recorder(events, "pipeline")
        self._rec = Recorder(events, "pipeline")

    async def aclose(self) -> None:
        await self._rec.aclose()


class FakeRunner:
    def __init__(self, events: list[str], fail: bool = False) -> None:
        self.events, self.fail = events, fail

    async def shutdown(self) -> None:
        self.events.append("stop:trainer")
        if self.fail:
            raise RuntimeError("boom")


def wire(app: Any, events: list[str], fail_trainer: bool = False) -> None:
    app.state.pipeline = FakePipeline(events)
    app.state.trainer_runner = FakeRunner(events, fail_trainer)
    entry = app.state.lifecycle.get("csv_replay")

    async def start(a: Any) -> None:
        events.append("start:csv_replay")

    async def stop(a: Any) -> None:
        events.append("stop:csv_replay")

    entry.start, entry.stop = start, stop


def test_order_is_documented() -> None:
    assert LIFECYCLE_ORDER == ("pipeline", "trainer", "csv_replay")


def test_start_in_order_and_shutdown_in_reverse() -> None:
    events: list[str] = []
    app = build_app()
    wire(app, events)
    with TestClient(app):
        assert events == ["start:pipeline", "start:csv_replay"]
    assert events == [
        "start:pipeline",
        "start:csv_replay",
        "stop:csv_replay",
        "stop:trainer",
        "stop:pipeline",
    ]


def test_failing_stop_does_not_skip_the_others() -> None:
    events: list[str] = []
    app = build_app()
    wire(app, events, fail_trainer=True)
    with TestClient(app):
        pass
    assert events[-3:] == ["stop:csv_replay", "stop:trainer", "stop:pipeline"]


def test_duplicate_registration_rejected() -> None:
    app = build_app()
    with pytest.raises(ValueError):
        app.state.lifecycle.register("pipeline")
