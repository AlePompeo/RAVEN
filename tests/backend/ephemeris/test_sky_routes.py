# SPDX-License-Identifier: Apache-2.0
"""Rotte /api/sky: con un motore finto (sempre eseguiti) e con i kernel reali (se presenti)."""

import asyncio
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

np = pytest.importorskip("numpy")

from backend.api.sky_routes import SkyService
from backend.bootstrap import build_app
from backend.ephemeris import kernels
from backend.ephemeris.timeutil import parse_utc

LO = datetime(1972, 1, 1, tzinfo=UTC)
HI = datetime(2150, 1, 1, tzinfo=UTC)


class _OutOfRange(ValueError):
    pass


@dataclass
class _LL:
    lat_deg: Any
    lon_deg_east: Any


class FakeEngine:
    """Motore finto deterministico: lon = secondi/240 (gradi), lat = 1.5."""

    def __init__(self) -> None:
        self.calls = 0
        self.gate: threading.Event | None = None
        self.entered = threading.Event()

    def _secs(self, t: Any) -> Any:
        items = [t] if isinstance(t, datetime | str) else list(t)
        out = []
        for x in items:
            d = parse_utc(x)
            if not LO <= d <= HI:
                raise _OutOfRange
            out.append(d.timestamp())
        return np.array(out)

    def subsolar_point(self, body: str, t: Any) -> _LL:
        self.calls += 1
        self.entered.set()
        if self.gate is not None:
            self.gate.wait(5)
        s = self._secs(t)
        return _LL(np.full_like(s, 1.5), ((s / 240.0 + 180) % 360) - 180)

    def sub_earth_point(self, body: str, t: Any) -> _LL:
        s = self._secs(t)
        return _LL(np.full_like(s, -2.0), np.full_like(s, 3.0))

    def sun_distance_au(self, body: str, t: Any) -> Any:
        return np.full_like(self._secs(t), 1.0)

    def solar_direction_body_fixed(self, body: str, t: Any) -> Any:
        s = self._secs(t)
        return np.tile(np.array([0.0, 0.0, 1.0]), (len(s), 1))

    def supported_range(self) -> tuple[datetime, datetime]:
        return LO, HI

    def info(self) -> dict[str, Any]:
        return {"versions": {"skyfield": "fake", "jplephem": "fake"}}


def make(monkeypatch: pytest.MonkeyPatch, engine: Any = None, **env: str) -> tuple[Any, TestClient]:
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    app = build_app()
    svc: SkyService = app.state.sky
    if engine is not None:
        svc._factory = lambda: engine
    return app, TestClient(app)


T = "2027-03-03T03:03:03Z"


def test_status_available_and_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    _, c = make(monkeypatch, FakeEngine())
    j = c.get("/api/raven/sky/status").json()
    assert j["available"] is True and j["supported_range"]["start_utc"] == "1972-01-01T00:00:00Z"
    assert j["limits"]["max_points"] == 2000 and len(j["kernels"]) == 4

    def boom() -> Any:
        raise kernels.EphemerisUnavailable("x")

    app, c2 = make(monkeypatch)
    app.state.sky._factory = boom
    j2 = c2.get("/api/raven/sky/status").json()
    assert j2["available"] is False and j2["supported_range"] is None and len(j2["kernels"]) == 4
    r = c2.get(f"/api/raven/sky/subsolar?body=moon&t={T}")
    assert r.status_code == 503 and r.json() == {"detail": "efemeridi non disponibili"}
    assert r.headers["retry-after"] == "30"


def test_subsolar_shape_and_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeEngine()
    _, c = make(monkeypatch, fake)
    j = c.get(f"/api/raven/sky/subsolar?body=moon&t={T}").json()
    assert j["body"] == "moon" and j["t_utc"] == T and j["frame"] == "viewer"
    assert set(j["subsolar"]) == {"lat_deg", "lon_deg_east"} and j["sub_earth"] == {
        "lat_deg": -2.0,
        "lon_deg_east": 3.0,
    }
    assert j["sun_direction_body_fixed"] == [0.0, 0.0, 1.0] and j["sun_distance_au"] == 1.0
    n = fake.calls
    c.get(f"/api/raven/sky/subsolar?body=moon&t={T}")
    c.get(
        "/api/raven/sky/subsolar?body=moon&t=2027-03-03T03:03:03.300000Z"
    )  # stesso secondo arrotondato
    assert fake.calls == n  # servite dalla cache
    j2 = c.get(f"/api/raven/sky/subsolar?body=mars&t={T}").json()
    assert "sub_earth" not in j2 and fake.calls == n + 1


def test_cache_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    _, c = make(monkeypatch, FakeEngine(), SKY_CACHE_SIZE="2")
    for s in range(5):
        c.get(f"/api/raven/sky/subsolar?body=earth&t=2027-03-03T03:03:0{s}Z")
    assert len(c.app.state.sky._cache) == 2  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "qs",
    [
        "body=sun&t=" + T,
        "body=moon&t=2027-03-03T03:03:03",
        "body=moon&t=2027-03-03T03:03:03+00:00",
        "body=moon&t=" + "9" * 500,
        "body=moon&t=1900-01-01T00:00:00Z",
        "body=moon&t=2999-01-01T00:00:00Z",
        "body=moon",
        "t=" + T,
    ],
)
def test_subsolar_rejects_bad_input_without_echo(monkeypatch: pytest.MonkeyPatch, qs: str) -> None:
    _, c = make(monkeypatch, FakeEngine())
    r = c.get(f"/api/raven/sky/subsolar?{qs}")
    assert r.status_code == 422
    for echoed in ("9" * 20, "1900-01-01", "2999-01-01", "+00:00", "03:03:03"):
        assert echoed not in r.text  # nessun eco del valore ricevuto


def test_series_ok_and_caps(monkeypatch: pytest.MonkeyPatch) -> None:
    _, c = make(
        monkeypatch, FakeEngine(), SKY_MAX_POINTS="50", SKY_MIN_STEP_S="60", SKY_MAX_SPAN_DAYS="2"
    )
    base = "/api/raven/sky/series?body=moon&t0=2027-03-03T00:00:00Z"
    j = c.get(f"{base}&t1=2027-03-03T01:00:00Z&step_s=600").json()
    assert j["body"] == "moon" and len(j["t_utc"]) == 7 == len(j["lat_deg"]) == len(
        j["sun_direction_body_fixed"]
    )
    assert j["t_utc"][1] == "2027-03-03T00:10:00Z" and "sub_earth_lat_deg" in j
    assert (
        "sub_earth_lat_deg"
        not in c.get(base.replace("moon", "mars") + "&t1=2027-03-03T00:10:00Z&step_s=600").json()
    )
    for bad in (
        "&t1=2027-03-03T01:00:00Z&step_s=59",  # sotto il passo minimo
        "&t1=2027-03-03T10:00:00Z&step_s=60",  # 601 punti > 50
        "&t1=2027-03-10T00:00:00Z&step_s=3600",  # oltre 2 giorni
        "&t1=2027-03-02T00:00:00Z&step_s=600",  # invertito
        "&t1=2027-03-03T01:00:00Z&step_s=0",
        "&t1=2027-03-03T01:00:00Z&step_s=nan",
        "&t1=2027-03-03T01:00:00Z&step_s=inf",
        "&t1=oggi&step_s=600",
    ):
        r = c.get(base + bad)
        assert r.status_code == 422, bad
        assert "oggi" not in r.text


def test_env_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKY_MAX_POINTS", "0")
    with pytest.raises(SystemExit):
        build_app()


async def test_concurrency_cap_returns_503_then_recovers(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeEngine()
    fake.gate = threading.Event()
    app, _ = make(monkeypatch, fake, SKY_MAX_CONCURRENT="1")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        first = asyncio.create_task(c.get(f"/api/raven/sky/subsolar?body=moon&t={T}"))
        while not fake.entered.is_set():
            await asyncio.sleep(0.01)
        r = await c.get("/api/raven/sky/subsolar?body=earth&t=2027-03-03T03:03:04Z")
        assert r.status_code == 503 and r.headers["retry-after"] == "1"
        fake.gate.set()
        assert (await first).status_code == 200
        r2 = await c.get("/api/raven/sky/subsolar?body=earth&t=2027-03-03T03:03:05Z")
        assert r2.status_code == 200


def test_security_headers_present(monkeypatch: pytest.MonkeyPatch) -> None:
    _, c = make(monkeypatch, FakeEngine())
    r = c.get("/api/raven/sky/status")
    assert r.headers.get("x-content-type-options") == "nosniff"


def test_rate_limit_applies(monkeypatch: pytest.MonkeyPatch) -> None:
    _, c = make(monkeypatch, FakeEngine(), RATE_LIMIT_PER_MIN="3")
    codes = [c.get("/api/raven/sky/status").status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200] and 429 in codes[3:]


# --------------------------------------------------------------------------- kernel reali


def _real() -> bool:
    try:
        import skyfield  # noqa: F401
    except ImportError:
        return False
    return not kernels.problems(kernels.ephemeris_dir())


@pytest.mark.skipif(not _real(), reason="kernel NAIF assenti: make ephemeris")
def test_real_engine_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.ephemeris.engine import Engine

    eng = Engine()
    _, c = make(monkeypatch, eng)
    j = c.get("/api/raven/sky/status").json()
    assert j["available"] and j["engine"]["skyfield"] == "1.55"
    r = c.get("/api/raven/sky/subsolar?body=moon&t=2026-12-24T00:00:00Z").json()
    assert r["subsolar"]["lon_deg_east"] == pytest.approx(0.2252, abs=1e-3)  # Horizons: 0.225218
    assert r["sub_earth"]["lon_deg_east"] == pytest.approx(-0.5906, abs=1e-3)  # 359.409356
    v = r["sun_direction_body_fixed"]
    assert sum(x * x for x in v) == pytest.approx(1.0, abs=1e-6)
    assert 0.98 < r["sun_distance_au"] < 1.02
    s = c.get(
        "/api/raven/sky/series?body=mars&t0=2027-01-01T00:00:00Z&t1=2027-01-02T00:00:00Z&step_s=3600"
    ).json()
    assert len(s["lat_deg"]) == 25
    assert c.get("/api/raven/sky/subsolar?body=earth&t=1960-01-01T00:00:00Z").status_code == 422
