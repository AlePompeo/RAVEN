# SPDX-License-Identifier: Apache-2.0
import asyncio
from typing import Any

import pytest
from starlette.requests import ClientDisconnect

from backend.api.routes import TelemetryHub, TooManySubscribers, sse_events


async def test_unsubscribe_releases_queue() -> None:
    hub = TelemetryHub()
    q = hub.subscribe()
    assert hub.subscriber_count == 1
    hub.unsubscribe(q)
    assert hub.subscriber_count == 0
    hub.unsubscribe(q)  # idempotente


async def test_publish_reaches_subscribers() -> None:
    hub = TelemetryHub()
    q = hub.subscribe()
    hub.publish({"schema_version": "1.0.0", "power_w": 12.5})
    assert (await q.get())["power_w"] == 12.5


async def test_publish_drops_when_full_without_blocking() -> None:
    hub = TelemetryHub()
    q = hub.subscribe()
    for i in range(150):
        hub.publish({"i": i})
    assert q.qsize() == 100
    assert (await q.get())["i"] == 0


async def test_sse_generator_releases_on_close() -> None:
    hub = TelemetryHub()
    gen = sse_events(hub, hub.subscribe())
    task = asyncio.ensure_future(gen.__anext__())
    await asyncio.sleep(0.05)
    assert hub.subscriber_count == 1
    hub.publish({"power_w": 1.0})
    chunk = await task
    assert chunk.startswith("data: ") and '"power_w"' in chunk
    await gen.aclose()
    assert hub.subscriber_count == 0


async def test_sse_cancel_releases_subscription() -> None:
    """Disconnessione client: Starlette cancella il task del generatore."""
    hub = TelemetryHub()
    gen = sse_events(hub, hub.subscribe())
    task = asyncio.ensure_future(gen.__anext__())
    await asyncio.sleep(0.05)
    assert hub.subscriber_count == 1
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert hub.subscriber_count == 0


async def test_hub_subscribe_atomic_cap_concurrent() -> None:
    hub = TelemetryHub(max_subscribers=3)

    async def sub() -> bool:
        await asyncio.sleep(0)  # tutte le task arrivano interleaved al punto di sottoscrizione
        try:
            hub.subscribe()
        except TooManySubscribers:
            return False
        await asyncio.sleep(0)
        assert hub.subscriber_count <= 3
        return True

    results = await asyncio.gather(*(sub() for _ in range(8)))
    assert results.count(True) == 3
    assert hub.subscriber_count == 3


async def test_slot_reclaimed_when_response_fails_before_streaming(monkeypatch: Any) -> None:
    from backend.bootstrap import build_app

    app = build_app()
    hub: TelemetryHub = app.state.hub
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "path": "/api/telemetry/stream",
        "raw_path": b"/api/telemetry/stream",
        "query_string": b"",
        "headers": [],
        "client": ("testclient", 1),
        "server": ("test", 80),
        "scheme": "http",
    }

    async def receive() -> dict[str, str]:
        await asyncio.sleep(10)
        return {"type": "http.disconnect"}

    async def send(msg: dict[str, Any]) -> None:
        raise OSError("client gone")  # fallisce prima che il generatore parta

    with pytest.raises((OSError, ClientDisconnect)):
        await app(scope, receive, send)
    assert hub.subscriber_count == 0


@pytest.mark.parametrize("same_peer,accepted,rejected", [(False, 3, 503), (True, 2, 429)])
async def test_endpoint_concurrent_connects_exactly_n_succeed(
    monkeypatch: Any, same_peer: bool, accepted: int, rejected: int
) -> None:
    from backend.bootstrap import build_app

    monkeypatch.setenv("TELEMETRY_MAX_SUBSCRIBERS", "3")
    monkeypatch.setenv("TELEMETRY_MAX_SUBSCRIBERS_PER_CLIENT", "2")
    app = build_app()
    hub: TelemetryHub = app.state.hub
    release = asyncio.Event()
    statuses: list[int] = []
    peak = 0

    async def connect(index: int) -> None:
        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "path": "/api/telemetry/stream",
            "raw_path": b"/api/telemetry/stream",
            "query_string": b"",
            "headers": [],
            "client": ("shared-peer" if same_peer else f"peer-{index}", index),
            "server": ("test", 80),
            "scheme": "http",
        }

        async def receive() -> dict[str, str]:
            await release.wait()
            return {"type": "http.disconnect"}

        async def send(msg: dict[str, Any]) -> None:
            nonlocal peak
            peak = max(peak, hub.subscriber_count)
            if msg["type"] == "http.response.start":
                statuses.append(int(msg["status"]))

        await app(scope, receive, send)

    tasks = [asyncio.create_task(connect(i)) for i in range(7)]
    await asyncio.sleep(0.3)
    assert sorted(statuses) == [200] * accepted + [rejected] * (7 - accepted)
    assert hub.subscriber_count == accepted and peak <= accepted
    release.set()
    await asyncio.gather(*tasks)
    assert hub.subscriber_count == 0


async def test_per_client_quota_is_reclaimed_on_unsubscribe() -> None:
    from backend.api.routes import TooManyClientSubscribers

    hub = TelemetryHub(max_subscribers=4, max_per_client=1)
    q = hub.subscribe("a")
    with pytest.raises(TooManyClientSubscribers):
        hub.subscribe("a")
    other = hub.subscribe("b")
    hub.unsubscribe(q)
    hub.subscribe("a")
    hub.unsubscribe(other)
    assert hub.subscriber_count == 1


async def test_telemetry_lease_expires_even_with_send_backpressure(monkeypatch: Any) -> None:
    from backend.api.routes import _LeasedStreamingResponse

    monkeypatch.setenv("TELEMETRY_MAX_STREAM_SECONDS", "1")
    hub = TelemetryHub(max_per_client=1)
    q = hub.subscribe("a")
    hub.publish({"power_w": 1.0})
    gen = sse_events(hub, q)
    response = _LeasedStreamingResponse(hub, q, gen)

    async def send(message: dict[str, Any]) -> None:
        if message["type"] == "http.response.body":
            await asyncio.Future()

    async def receive() -> dict[str, str]:
        await asyncio.Future()
        return {"type": "http.disconnect"}

    await asyncio.wait_for(
        response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send), timeout=3
    )
    assert hub.subscriber_count == 0
    hub.subscribe("a")
    await gen.aclose()
