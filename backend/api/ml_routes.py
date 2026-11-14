# SPDX-License-Identifier: Apache-2.0
"""Endpoint dei job di addestramento (spec 13.1): l'API serve solo stato; il lavoro e' nel subprocess.

POST /api/train, GET /api/jobs/{id}, POST /api/jobs/{id}/cancel. Gli errori sono generici.
La promozione dei modelli NON e' esposta qui (cancello umano, passo successivo).
"""

import os
from typing import Annotated, Any

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StringConstraints,
    field_validator,
)

from backend.api.security import RateLimitMiddleware
from backend.envconf import env_positive_int
from backend.ml.jobs import TooManyJobs, UnknownTrainer
from backend.ml.runner import TrainerRunner, default_runner

DEFAULT_TRAIN_PER_HOUR = 20
MAX_CONFIG_KEYS = 32
MAX_CONFIG_STR = 256
TrainerId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")]
ConfigKey = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,63}$")]
ConfigValue = (
    StrictBool
    | StrictInt
    | Annotated[float, Field(allow_inf_nan=False)]
    | Annotated[str, StringConstraints(max_length=MAX_CONFIG_STR)]
)


class TrainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trainer: TrainerId
    config: dict[ConfigKey, ConfigValue] = Field(default_factory=dict)

    @field_validator("config")
    @classmethod
    def _cap(cls, v: dict[str, Any]) -> dict[str, Any]:
        if len(v) > MAX_CONFIG_KEYS:
            raise ValueError("troppi parametri")
        return v


def _runner(request: Request) -> TrainerRunner:
    runner: TrainerRunner = request.app.state.trainer_runner
    return runner


def build_ml_router() -> APIRouter:
    router = APIRouter()

    @router.post("/api/train", status_code=202)
    async def train(body: TrainRequest, request: Request) -> JSONResponse:
        limiter: RateLimitMiddleware = request.app.state.train_limiter
        allowed, retry = limiter._allow(limiter._key(request.scope))
        if not allowed:
            return JSONResponse(
                {"detail": "too many requests"},
                status_code=429,
                headers={"Retry-After": str(retry)},
            )
        try:
            job = _runner(request).submit(body.trainer, body.config)
        except UnknownTrainer:
            raise HTTPException(status_code=404, detail="not found") from None
        except TooManyJobs:
            return JSONResponse(
                {"detail": "too many jobs"}, status_code=429, headers={"Retry-After": "5"}
            )
        except ValueError:
            raise HTTPException(status_code=422, detail="invalid config") from None
        return JSONResponse(job.public(), status_code=202)

    @router.get("/api/jobs/{job_id}")
    async def get_job(job_id: str, request: Request) -> dict[str, Any]:
        job = _runner(request).get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="not found")
        return job.public()

    @router.post("/api/jobs/{job_id}/cancel")
    async def cancel_job(job_id: str, request: Request) -> dict[str, Any]:
        job = await _runner(request).cancel(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="not found")
        return job.public()

    return router


def include_ml_routes(app: FastAPI) -> None:
    """Crea il runner dal registry dei plugin, aggiunge le rotte e chiude i job allo shutdown."""
    per_hour = env_positive_int("ML_TRAIN_PER_HOUR", DEFAULT_TRAIN_PER_HOUR)
    # stessa logica di chiave del rate limiter globale (IP del peer; XFF solo con TRUSTED_PROXY=1)
    app.state.train_limiter = RateLimitMiddleware(
        app, limit=per_hour, window_s=3600.0, trusted_proxy=os.environ.get("TRUSTED_PROXY") == "1"
    )
    runner = default_runner(app.state.registry)
    app.state.trainer_runner = runner
    app.include_router(build_ml_router())

    async def stop(a: FastAPI) -> None:
        await a.state.trainer_runner.shutdown()

    app.state.lifecycle.register("trainer", stop=stop)
