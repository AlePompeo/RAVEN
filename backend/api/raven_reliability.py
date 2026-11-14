# SPDX-License-Identifier: Apache-2.0
"""Strict, bounded inputs for the optional RAVEN engine reliability study."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from backend.domain.raven.reliability import Component, Profile, Window, reliability_summary

Probability = Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]
Rate = Annotated[float, Field(strict=True, ge=0, le=1000, allow_inf_nan=False)]
Hours = Annotated[float, Field(strict=True, ge=0, le=1e6, allow_inf_nan=False)]
Temperature = Annotated[float, Field(strict=True, ge=-273.15, le=1000, allow_inf_nan=False)]


class ComponentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: Literal["power", "battery", "radio", "computer", "thermal"]
    protection: Literal["unspecified", "none", "passive", "active", "both"] = "unspecified"
    launch_failure_probability: Probability | None = None
    landing_failure_probability: Probability | None = None
    launch_loss_fraction: Probability | None = None
    landing_loss_fraction: Probability | None = None
    failure_rate_per_hour: Rate | None = None
    upset_rate_per_hour: Rate | None = None
    restart_success_probability: Probability | None = None
    mean_recovery_hours: Hours | None = None
    degradation_rate_per_hour: Rate | None = None
    minimum_performance_fraction: Probability | None = None
    thermal_min_c: Temperature | None = None
    thermal_max_c: Temperature | None = None
    rated_min_c: Temperature | None = None
    rated_max_c: Temperature | None = None
    dose_rate_krad_h: Rate | None = None
    shield_transmission: Probability | None = None
    tid_limit_krad: (
        Annotated[float, Field(strict=True, ge=0, le=1e9, allow_inf_nan=False)] | None
    ) = None

    @model_validator(mode="after")
    def ordered(self) -> "ComponentInput":
        for low, high in (
            (self.thermal_min_c, self.thermal_max_c),
            (self.rated_min_c, self.rated_max_c),
        ):
            if low is not None and high is not None and low > high:
                raise ValueError("temperature interval is inverted")
        if self.mean_recovery_hours is not None and 0 < self.mean_recovery_hours < 1e-6:
            raise ValueError("recovery time is zero or at least one microhour")
        return self


class ProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    components: list[ComponentInput] = Field(min_length=1, max_length=5)
    enabled: StrictBool
    basis: str = Field(max_length=1000)
    launch_success_probability: Probability | None = None
    cruise_success_probability: Probability | None = None
    landing_success_probability: Probability | None = None
    cruise_hours: Hours | None = None
    apply_thermal_load: StrictBool = False
    thermal_load_w: (
        Annotated[float, Field(strict=True, ge=0, le=1000, allow_inf_nan=False)] | None
    ) = None

    @model_validator(mode="after")
    def attributed(self) -> "ProfileInput":
        if not self.enabled or not self.basis.strip():
            raise ValueError("an enabled study requires a source or explicit assumption basis")
        if len({c.id for c in self.components}) != len(self.components):
            raise ValueError("duplicate component")
        if self.apply_thermal_load and self.thermal_load_w is None:
            raise ValueError("applied thermal power must be declared")
        return self


class WindowInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: Literal["A", "B"]
    start_unix: Annotated[float, Field(strict=True, ge=0, le=1e11, allow_inf_nan=False)]
    step_hours: Annotated[float, Field(strict=True, gt=0, le=24, allow_inf_nan=False)]
    useful: list[StrictBool | None] = Field(min_length=1, max_length=1500)


class ReliabilityInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile: ProfileInput
    windows: list[WindowInput] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def unique_windows(self) -> "ReliabilityInput":
        if len({w.id for w in self.windows}) != len(self.windows):
            raise ValueError("duplicate scenario")
        return self


def calculate_reliability(body: ReliabilityInput) -> dict[str, object]:
    profile = Profile(
        **body.profile.model_dump(exclude={"components"}),
        components=tuple(Component(**c.model_dump()) for c in body.profile.components),
    )
    windows = [Window(w.id, w.start_unix, w.step_hours, tuple(w.useful)) for w in body.windows]
    return reliability_summary(profile, windows)
