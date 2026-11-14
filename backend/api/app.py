# SPDX-License-Identifier: Apache-2.0
import asyncio
import contextlib
import logging
import os
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api.assistant_routes import include_assistant_routes
from backend.api.lifecycle import Lifecycle
from backend.api.raven_experiments import include_raven_experiments
from backend.api.raven_routes import include_raven_routes
from backend.api.report_routes import MAX_PDF_BODY_BYTES, PDF_PATH, include_report_routes
from backend.api.retired_routes import include_retired_routes
from backend.api.routes import (
    DEFAULT_CHAT_MAX_STREAM_S,
    ESTIMATOR_OWNER_HEADER,
    MAX_SUBSCRIBERS_PER_CLIENT,
    TELEMETRY_MAX_STREAM_S,
    TelemetryHub,
    csv_replay,
    include_routes,
)
from backend.api.security import (
    BodySizeLimitMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
)
from backend.api.sky_routes import include_sky_routes
from backend.api.static import mount_static
from backend.core.ports import CachePort
from backend.core.registry import Registry
from backend.envconf import ConfigError, env_positive_int

# Registro dei modelli, trainer e pipeline dati usano API solo POSIX (dir_fd, fcntl, killpg): su Windows queste
# parti restano disattivate (il resto del sito funziona); per averle usare WSL o Docker.
if sys.platform != "win32":
    from backend.api.ml_routes import include_ml_routes
    from backend.api.pipeline_routes import include_pipeline_routes
    from backend.ml.registry import DEFAULT_MAX_CANDIDATES

DEFAULT_RATE_LIMIT_PER_MIN = 120
DEFAULT_MAX_BODY_BYTES = 64 * 1024
DEFAULT_MAX_SUBSCRIBERS = 100
log = logging.getLogger(__name__)
__all__ = ["ConfigError", "create_app", "env_positive_int"]

# Ordine di avvio dei componenti con ciclo di vita; l'arresto e' in ordine inverso.
#   1. pipeline    (scheduler di ingestione: pronta prima di ricevere/pubblicare dati)
#   2. trainer     (runner dei job ML: solo arresto, i job partono su richiesta)
#   3. csv_replay  (produttore di telemetria: parte per ultimo, si ferma per primo)
LIFECYCLE_ORDER = ("pipeline", "trainer", "csv_replay")


def create_app(
    registry: Registry,
    cache: CachePort,
    plugin_errors: list[tuple[Path, Exception]] | None = None,
    hub: TelemetryHub | None = None,
) -> FastAPI:
    limit = env_positive_int("RATE_LIMIT_PER_MIN", DEFAULT_RATE_LIMIT_PER_MIN)
    max_body = env_positive_int("MAX_BODY_BYTES", DEFAULT_MAX_BODY_BYTES)
    max_subs = env_positive_int("TELEMETRY_MAX_SUBSCRIBERS", DEFAULT_MAX_SUBSCRIBERS)
    max_per_client = env_positive_int(
        "TELEMETRY_MAX_SUBSCRIBERS_PER_CLIENT", MAX_SUBSCRIBERS_PER_CLIENT
    )
    env_positive_int("TELEMETRY_MAX_STREAM_SECONDS", TELEMETRY_MAX_STREAM_S)
    chat_max_s = env_positive_int("CHAT_MAX_STREAM_SECONDS", int(DEFAULT_CHAT_MAX_STREAM_S))
    if sys.platform != "win32":
        env_positive_int(
            "ML_MAX_CANDIDATES", DEFAULT_MAX_CANDIDATES
        )  # validata subito, usata a lazy
    hub = hub or TelemetryHub(max_subscribers=max_subs, max_per_client=max_per_client)
    replay_csv = os.environ.get("TELEMETRY_CSV")
    if replay_csv and not Path(replay_csv).is_file():
        log.error("TELEMETRY_CSV non è un file leggibile: replay disabilitato")
        replay_csv = None

    lifecycle = Lifecycle()
    replay_task: list[asyncio.Task[None]] = []

    async def start_replay(_: FastAPI) -> None:
        if replay_csv:
            replay_task.append(asyncio.create_task(csv_replay(hub, Path(replay_csv))))

    async def stop_replay(_: FastAPI) -> None:
        for task in replay_task:
            task.cancel()
        await asyncio.gather(*replay_task, return_exceptions=True)
        replay_task.clear()

    lifecycle.register("csv_replay", start=start_replay, stop=stop_replay)

    @contextlib.asynccontextmanager
    async def lifespan(a: FastAPI) -> AsyncIterator[None]:
        entries = [(n, lifecycle.get(n)) for n in LIFECYCLE_ORDER]
        started: list[tuple[str, Any]] = []
        try:
            for name, entry in entries:
                if entry is None:
                    continue
                if entry.start is not None:
                    await entry.start(a)
                started.append((name, entry))
            yield
        finally:
            for name, entry in reversed(started):
                if entry.stop is None:
                    continue
                try:
                    await entry.stop(a)
                except Exception:
                    log.exception("arresto di %s fallito", name)

    app = FastAPI(title="hackathon-base", lifespan=lifespan)
    app.state.lifecycle = lifecycle
    app.state.registry = registry
    app.state.cache = cache
    app.state.hub = hub
    app.state.chat_max_stream_s = float(chat_max_s)
    app.state.plugin_errors = [
        {"plugin": p.name, "error": type(e).__name__} for p, e in plugin_errors or []
    ]

    origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
    app.state.trusted_proxy = os.environ.get("TRUSTED_PROXY") == "1"
    # Ordine (ultimo aggiunto = più esterno): sicurezza > CORS > rate limit
    app.add_middleware(RateLimitMiddleware, limit=limit, trusted_proxy=app.state.trusted_proxy)
    if origins:
        cors: dict[str, Any] = {
            "allow_origins": origins,
            "allow_methods": ["GET", "POST"],
            "allow_headers": ["Content-Type", ESTIMATOR_OWNER_HEADER],
            "expose_headers": [ESTIMATOR_OWNER_HEADER],
            "allow_credentials": False,
        }
        app.add_middleware(CORSMiddleware, **cors)
    app.add_middleware(
        BodySizeLimitMiddleware, max_bytes=max_body, path_limits={PDF_PATH: MAX_PDF_BODY_BYTES}
    )
    app.add_middleware(SecurityHeadersMiddleware, hsts=os.environ.get("ENV") == "prod")

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # niente 'input'/'ctx': potrebbero contenere NaN/inf non serializzabili in JSON
        detail = [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return JSONResponse({"detail": detail}, status_code=422)

    include_routes(app)
    if sys.platform != "win32":
        include_ml_routes(app)
        include_pipeline_routes(app)
    else:
        log.warning(
            "registro modelli, trainer e pipeline dati disattivati su Windows (solo POSIX): usare WSL o Docker"
        )
    include_assistant_routes(app)
    include_sky_routes(app)
    include_raven_experiments(app)
    include_raven_routes(app)
    include_report_routes(app)
    include_retired_routes(app)
    mount_static(app)  # no-op senza STATIC_DIR; deve restare dopo le rotte API
    return app
