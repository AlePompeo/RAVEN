# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from typing import Annotated
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, RootModel


class CovarianceItem(RootModel[list[float]]):
    root: Annotated[list[float], Field(min_length=1)]


class StateOrderItem(RootModel[str]):
    root: Annotated[str, Field(min_length=1)]


class StateEstimate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    covariance: Annotated[
        list[CovarianceItem] | None,
        Field(
            description="Optional row-major square matrix, n x n for n = number of state entries.",
            min_length=1,
        ),
    ] = None
    schema_version: Annotated[
        str, Field(pattern="^(0|[1-9]\\d*)\\.(0|[1-9]\\d*)\\.(0|[1-9]\\d*)$")
    ]
    state: Annotated[
        dict[str, float],
        Field(
            description="Map name (with unit suffix, e.g. yaw_deg) to finite number.",
            min_length=1,
        ),
    ]
    state_order: Annotated[
        list[StateOrderItem] | None,
        Field(
            description="Names of state entries giving the row/column order of covariance.",
            min_length=1,
        ),
    ] = None
    t_utc: AwareDatetime


class AzEl(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    az_deg: float
    el_deg: float


class Telemetry(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    earth: AzEl | None = None
    link_margin_db: float | None = None
    power_w: float
    schema_version: Annotated[
        str, Field(pattern="^(0|[1-9]\\d*)\\.(0|[1-9]\\d*)\\.(0|[1-9]\\d*)$")
    ]
    site_id: Annotated[str, Field(min_length=1)]
    sun: AzEl | None = None
    t_utc: AwareDatetime
