# SPDX-License-Identifier: Apache-2.0
import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.bootstrap import build_app
from backend.core.errors import PluginError

MSG = {"messages": [{"role": "user", "content": "ciao mondo"}]}


def _events(text: str) -> list[str]:
    return [line[len("data: ") :] for line in text.splitlines() if line.startswith("data: ")]


def test_chat_streams_sse_tokens() -> None:
    r = TestClient(build_app()).post("/api/chat", json=MSG)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    ev = _events(r.text)
    tokens = [json.loads(e)["token"] for e in ev if e != "[DONE]"]
    assert "".join(tokens).strip() == "ciao mondo"
    assert ev[-1] == "[DONE]"


@pytest.mark.parametrize(
    "body",
    [
        {"messages": []},
        {"messages": [{"role": "user", "content": "x" * 4001}]},
        {"messages": [{"role": "user", "content": "x"}] * 51},
        {"messages": [{"role": "root", "content": "x"}]},
        {"messages": [{"role": "system", "content": "x"}]},
    ],
)
def test_chat_caps_and_validation(body: dict[str, Any]) -> None:
    assert TestClient(build_app()).post("/api/chat", json=body).status_code == 422


def test_chat_unknown_provider_is_404() -> None:
    r = TestClient(build_app()).post("/api/chat", json={**MSG, "provider": "nope"})
    assert r.status_code == 404


def test_chat_respects_body_size_cap(monkeypatch: Any) -> None:
    monkeypatch.setenv("MAX_BODY_BYTES", "100")
    big = {"messages": [{"role": "user", "content": "x" * 500}]}
    assert TestClient(build_app()).post("/api/chat", json=big).status_code == 413


def test_chat_provider_failure_mid_stream_does_not_leak() -> None:
    class Boom:
        async def stream(self, messages: Any) -> AsyncIterator[str]:
            yield "a"
            raise RuntimeError("SECRET-internal")

    app = build_app()
    app.state.registry.create = lambda kind, id: Boom()
    r = TestClient(app).post("/api/chat", json=MSG)
    assert "SECRET" not in r.text and "event: error" in r.text


def test_data_fixture_served() -> None:
    r = TestClient(build_app()).get("/api/data/example-data")
    assert r.status_code == 200
    assert r.headers["x-cache"] == "fresh"
    assert r.json()["data"]["sample"]["name"]


def test_data_unknown_is_404() -> None:
    assert TestClient(build_app()).get("/api/data/nope").status_code == 404


class _Down:
    async def fetch(self, query: Any) -> Any:
        raise ConnectionError("upstream http://internal:9/secret")


def test_data_upstream_down_with_stale_cache_serves_stale() -> None:
    import asyncio

    app = build_app()
    asyncio.run(app.state.cache.set("data:example-data", b'{"v": 1}', ttl_s=-1))  # scaduto
    app.state.registry.create = lambda kind, id: _Down()
    r = TestClient(app).get("/api/data/example-data")
    assert r.status_code == 200
    assert r.headers["x-cache"] == "stale"
    assert r.json()["data"] == {"v": 1}


def test_data_upstream_down_without_cache_is_503_no_internals() -> None:
    app = build_app()
    app.state.registry.create = lambda kind, id: _Down()
    r = TestClient(app).get("/api/data/example-data")
    assert r.status_code == 503
    assert set(r.json()) == {"detail"}
    assert "internal" not in r.text and "secret" not in r.text.lower()
    assert "set-cookie" not in r.headers


def test_manifests_have_in_repo_terms() -> None:
    from pathlib import Path

    for m in TestClient(build_app()).app.state.registry.manifests():  # type: ignore[attr-defined]
        if m.kind in ("llm", "data_source"):
            assert (Path(__file__).parents[3] / m.terms_url).is_file(), m.id


def _fast_timeouts(app: Any, timeout_s: float = 0.1) -> None:
    from dataclasses import replace

    reg = app.state.registry
    original = reg.manifests()
    reg.manifests = lambda: [replace(m, timeout_s=timeout_s) for m in original]


class _SlowSource:
    async def fetch(self, query: Any) -> Any:
        await asyncio.sleep(5)
        return {}


def test_data_slow_upstream_with_stale_serves_stale() -> None:
    app = build_app()
    asyncio.run(app.state.cache.set("data:example-data", b'{"v": 2}', ttl_s=-1))
    app.state.registry.create = lambda kind, id: _SlowSource()
    _fast_timeouts(app)
    r = TestClient(app).get("/api/data/example-data")
    assert r.status_code == 200 and r.headers["x-cache"] == "stale"
    assert r.json()["data"] == {"v": 2}


def test_data_slow_upstream_without_cache_is_504_clean() -> None:
    app = build_app()
    app.state.registry.create = lambda kind, id: _SlowSource()
    _fast_timeouts(app)
    r = TestClient(app).get("/api/data/example-data")
    assert r.status_code == 504
    assert set(r.json()) == {"detail"}


def test_chat_slow_first_token_gets_generic_error() -> None:
    class Slow:
        async def stream(self, messages: Any) -> AsyncIterator[str]:
            await asyncio.sleep(5)
            yield "never"

    app = build_app()
    app.state.registry.create = lambda kind, id: Slow()
    _fast_timeouts(app)
    r = TestClient(app).post("/api/chat", json=MSG)
    assert "event: error" in r.text and "never" not in r.text


def test_chat_total_timeout_even_if_tokens_keep_coming() -> None:
    class Drip:
        async def stream(self, messages: Any) -> AsyncIterator[str]:
            while True:
                await asyncio.sleep(0.03)
                yield "t "

    app = build_app()
    app.state.registry.create = lambda kind, id: Drip()
    _fast_timeouts(app, 0.2)
    r = TestClient(app).post("/api/chat", json=MSG)
    assert '"token": "t "' in r.text  # i token precedenti al timeout sono arrivati
    assert r.text.count("event: error") == 1
    assert "[DONE]" not in r.text
    assert r.text.rstrip().endswith("}")  # l'errore è l'ultimo evento


def test_chat_normal_stream_ends_with_done_and_no_error() -> None:
    r = TestClient(build_app()).post("/api/chat", json=MSG)
    assert "event: error" not in r.text
    assert r.text.rstrip().endswith("data: [DONE]")


async def test_slow_consumer_does_not_trip_total_deadline() -> None:
    from backend.api.routes import chat_events

    class Fast:
        async def stream(self, messages: Any) -> AsyncIterator[str]:
            for t in ("a", "b", "c"):
                yield t

    out = []
    async for ev in chat_events(Fast(), [], timeout_s=0.2):
        out.append(ev)
        await asyncio.sleep(0.3)  # backpressure del client: oltre il budget totale
    assert out[-1] == "data: [DONE]\n\n"
    assert not any("error" in e for e in out)


async def test_stalling_producer_trips_deadline() -> None:
    from backend.api.routes import chat_events

    class Stall:
        async def stream(self, messages: Any) -> AsyncIterator[str]:
            yield "a"
            await asyncio.sleep(5)
            yield "b"

    out = [ev async for ev in chat_events(Stall(), [], timeout_s=0.2)]
    assert out[0].startswith("data: ") and out[-1].startswith("event: error")


async def test_sync_exception_from_provider_stream_is_generic_error() -> None:
    from backend.api.routes import chat_events

    class Boom:
        def stream(self, messages: Any) -> AsyncIterator[str]:
            raise RuntimeError("SECRET-sync")

    out = [ev async for ev in chat_events(Boom(), [])]
    assert len(out) == 1 and out[0].startswith("event: error")
    assert "SECRET" not in out[0]


async def test_wall_clock_cap_stops_progressing_stream() -> None:
    from backend.api.routes import chat_events

    closed = False

    class Endless:
        async def stream(self, messages: Any) -> AsyncIterator[str]:
            nonlocal closed
            try:
                while True:
                    await asyncio.sleep(0.01)
                    yield "t "
            finally:
                closed = True

    out = [ev async for ev in chat_events(Endless(), [], timeout_s=5, max_stream_s=0.2)]
    assert out[-1].startswith("event: error") and closed


async def test_stalled_consumer_beyond_cap_closes_provider(monkeypatch: Any) -> None:
    monkeypatch.setenv("CHAT_MAX_STREAM_SECONDS", "1")
    closed = asyncio.Event()

    class Endless:
        async def stream(self, messages: Any) -> AsyncIterator[str]:
            try:
                while True:
                    yield "t "
            finally:
                closed.set()

    app = build_app()
    app.state.registry.create = lambda kind, id: Endless()
    body = json.dumps(MSG).encode()
    sent = False

    async def receive() -> dict[str, Any]:
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        await asyncio.sleep(3600)  # nessuna disconnessione: il client è fermo
        return {"type": "http.disconnect"}

    async def send(msg: dict[str, Any]) -> None:
        if msg["type"] == "http.response.body" and msg.get("body"):
            await asyncio.sleep(3600)  # il client smette di leggere

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "path": "/api/chat",
        "raw_path": b"/api/chat",
        "query_string": b"",
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
        ],
        "client": ("testclient", 1),
        "server": ("test", 80),
        "scheme": "http",
    }
    await asyncio.wait_for(app(scope, receive, send), timeout=10)
    assert closed.is_set()


def test_cache_timeout_error_is_not_reported_as_upstream_504() -> None:
    class BadCache:
        async def get(self, key: str, *, allow_stale: bool = False) -> bytes | None:
            raise TimeoutError("cache backend")

        async def set(self, key: str, value: bytes, ttl_s: float) -> None: ...

    app = build_app()
    app.state.cache = BadCache()
    r = TestClient(app).get("/api/data/example-data")
    assert r.status_code == 503


def test_registry_create_unexpected_error_is_502() -> None:
    def boom(kind: str, id: str) -> Any:
        raise PluginError("internal /secret/path")

    app = build_app()
    app.state.registry.create = boom
    c = TestClient(app, raise_server_exceptions=False)
    for r in (c.post("/api/chat", json=MSG), c.get("/api/data/example-data")):
        assert r.status_code == 502
        assert "secret" not in r.text


def test_stream_construction_failure_releases_subscription(monkeypatch: Any) -> None:
    from backend.api import routes

    def broken(*a: Any, **k: Any) -> Any:
        raise RuntimeError("ctor")

    monkeypatch.setattr(routes, "_LeasedStreamingResponse", broken)
    app = build_app()
    r = TestClient(app, raise_server_exceptions=False).get("/api/telemetry/stream")
    assert r.status_code == 500
    assert app.state.hub.subscriber_count == 0
