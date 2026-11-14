# SPDX-License-Identifier: Apache-2.0
"""Endpoint della pipeline dati (spec 14): metriche JSON e interrogazioni predefinite.

GET /api/pipeline/metrics            stato per livello/sorgente/job (`{"enabled": false}` senza pipeline)
GET /api/pipeline/query/{name}       solo query predefinite; parametri validati; mai SQL dal client

Questo modulo NON importa pyarrow/duckdb: il servizio si crea solo con PIPELINE_DIR e gli extra [data].
"""

import asyncio
import logging
import os
import re
from typing import Any

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from backend.envconf import env_positive_int
from backend.pipeline.query_spec import QUERY_MODELS, QUERY_NAME_PATTERN, QueryError

log = logging.getLogger(__name__)
DEFAULT_MAX_QUERIES = 4
_NAME_RE = re.compile(QUERY_NAME_PATTERN)


def _service(request: Request) -> Any:
    return getattr(request.app.state, "pipeline", None)


def _error(status: int, detail: str) -> JSONResponse:
    return JSONResponse({"detail": detail}, status_code=status)


def build_pipeline_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/pipeline/metrics")
    async def metrics(request: Request) -> JSONResponse:
        svc = _service(request)
        if svc is None:
            return JSONResponse({"enabled": False})
        return JSONResponse(await asyncio.to_thread(svc.snapshot))  # stats SQLite: fuori dal loop

    @router.get("/api/pipeline/query/{name}")
    async def query(name: str, request: Request) -> JSONResponse:
        model_cls = QUERY_MODELS.get(name) if _NAME_RE.fullmatch(name) else None
        if model_cls is None:
            return _error(404, "interrogazione sconosciuta")
        svc = _service(request)
        if svc is None:
            return _error(503, "pipeline non configurata")
        items = request.query_params.multi_items()
        params = dict(items)
        if len(params) != len(items):
            return _error(422, "parametro ripetuto")
        try:
            model_cls.model_validate(params)
        except ValidationError as e:
            # niente 'input'/'ctx': non si rimanda al client cio' che ha inviato
            detail = [
                {"loc": [str(p) for p in x["loc"]], "msg": x["msg"], "type": x["type"]}
                for x in e.errors()
            ]
            return JSONResponse({"detail": detail}, status_code=422)
        sem: asyncio.Semaphore = request.app.state.pipeline_query_sem
        if sem.locked():  # troppe query DuckDB in corso: rifiuto pulito invece di accodare
            resp = _error(503, "troppe interrogazioni in corso")
            resp.headers["Retry-After"] = "1"
            return resp
        try:
            async with sem:
                rows = await asyncio.to_thread(svc.engine.query, name, params)
        except QueryError:
            return _error(500, "interrogazione non riuscita")
        return JSONResponse({"name": name, "row_count": len(rows), "rows": rows})

    return router


def include_pipeline_routes(app: FastAPI) -> None:
    """Registra le rotte; crea il servizio da PIPELINE_DIR (se impostata e se gli extra ci sono)
    e ne lega lo scheduler al ciclo di vita dell'app. Senza pipeline l'app funziona comunque."""
    if getattr(app.state, "pipeline", None) is None:
        app.state.pipeline = _service_from_env()
    max_queries = env_positive_int("PIPELINE_MAX_QUERIES", DEFAULT_MAX_QUERIES)
    app.state.pipeline_max_queries = max_queries
    app.state.pipeline_query_sem = asyncio.Semaphore(max_queries)
    app.include_router(build_pipeline_router())

    async def start(a: FastAPI) -> None:
        svc = getattr(a.state, "pipeline", None)  # letto all'avvio: i test possono sostituirlo
        if svc is not None:
            await svc.scheduler.start()

    async def stop(a: FastAPI) -> None:
        svc = getattr(a.state, "pipeline", None)
        if svc is not None:
            await svc.aclose()

    app.state.lifecycle.register("pipeline", start=start, stop=stop)


def _service_from_env() -> Any:
    if not os.environ.get("PIPELINE_DIR"):
        return None
    try:
        from backend.pipeline.service import build_service_from_env
    except ImportError:
        log.error(
            "PIPELINE_DIR impostata ma gli extra [data] (pyarrow, duckdb) mancano: pipeline disabilitata"
        )
        return None
    return build_service_from_env()
