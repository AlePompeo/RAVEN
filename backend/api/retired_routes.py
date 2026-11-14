# SPDX-License-Identifier: Apache-2.0
"""Explicit retirement, never redirects or computes using obsolete mission rules."""

from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse


def include_retired_routes(app: FastAPI) -> None:
    router = APIRouter()

    async def retired() -> JSONResponse:
        return JSONResponse(
            {
                "detail": "endpoint retired; use /api/raven",
                "model": "/api/raven/model",
                "mission": "/api/raven/evaluate",
                "wave": "/api/raven/wave",
                "sky": "/api/raven/sky/status",
            },
            status_code=410,
        )

    for prefix in ("/api/lunar", "/api/grazing", "/api/sky"):
        for path in (prefix, prefix + "/{path:path}"):
            router.add_api_route(
                path,
                retired,
                methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
                include_in_schema=False,
            )
    app.include_router(router)
