# SPDX-License-Identifier: Apache-2.0
"""Conditional series-system RAM arithmetic, not hardware or environmental qualification."""

import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass

MODEL = "raven-reliability-1"


@dataclass(frozen=True)
class Component:
    id: str
    protection: str = "unspecified"
    launch_failure_probability: float | None = None
    landing_failure_probability: float | None = None
    launch_loss_fraction: float | None = None
    landing_loss_fraction: float | None = None
    failure_rate_per_hour: float | None = None
    upset_rate_per_hour: float | None = None
    restart_success_probability: float | None = None
    mean_recovery_hours: float | None = None
    degradation_rate_per_hour: float | None = None
    minimum_performance_fraction: float | None = None
    thermal_min_c: float | None = None
    thermal_max_c: float | None = None
    rated_min_c: float | None = None
    rated_max_c: float | None = None
    dose_rate_krad_h: float | None = None
    shield_transmission: float | None = None
    tid_limit_krad: float | None = None


@dataclass(frozen=True)
class Profile:
    components: tuple[Component, ...]
    enabled: bool = False
    basis: str = ""
    launch_success_probability: float | None = None
    cruise_success_probability: float | None = None
    landing_success_probability: float | None = None
    cruise_hours: float | None = None
    apply_thermal_load: bool = False
    thermal_load_w: float | None = None


@dataclass(frozen=True)
class Window:
    id: str
    start_unix: float
    step_hours: float
    useful: tuple[bool | None, ...]


def _integral(rate: float, start: float, end: float) -> float:
    return (
        end - start
        if rate == 0
        else math.exp(-rate * start) * -math.expm1(-rate * (end - start)) / rate
    )


def _component(c: Component, cruise: float | None, hours: float) -> dict[str, object]:
    hazard = (
        c.failure_rate_per_hour + c.upset_rate_per_hour * (1 - c.restart_success_probability)
        if c.failure_rate_per_hour is not None
        and c.upset_rate_per_hour is not None
        and c.restart_success_probability is not None
        else None
    )
    recovery = (
        c.upset_rate_per_hour * c.restart_success_probability
        if c.upset_rate_per_hour is not None and c.restart_success_probability is not None
        else None
    )
    retained = (
        (1 - c.launch_loss_fraction)
        * (1 - c.landing_loss_fraction)
        * math.exp(-c.degradation_rate_per_hour * cruise)
        if c.launch_loss_fraction is not None
        and c.landing_loss_fraction is not None
        and c.degradation_rate_per_hour is not None
        and cruise is not None
        else None
    )
    cutoff: float | None = None
    performance_known = retained is not None and c.minimum_performance_fraction is not None
    if retained is not None and c.minimum_performance_fraction is not None:
        if retained < c.minimum_performance_fraction:
            cutoff = 0.0
        elif c.minimum_performance_fraction > 0 and c.degradation_rate_per_hour:
            crossing = (
                math.log(retained) - math.log(c.minimum_performance_fraction)
            ) / c.degradation_rate_per_hour
            cutoff = crossing if crossing <= hours else None
    thermal = (
        min(c.thermal_min_c - c.rated_min_c, c.rated_max_c - c.thermal_max_c)
        if c.thermal_min_c is not None
        and c.thermal_max_c is not None
        and c.rated_min_c is not None
        and c.rated_max_c is not None
        else None
    )
    dose = (
        c.dose_rate_krad_h * c.shield_transmission * (cruise + hours)
        if c.dose_rate_krad_h is not None
        and c.shield_transmission is not None
        and cruise is not None
        else None
    )
    radiation = (
        c.tid_limit_krad - dose if c.tid_limit_krad is not None and dose is not None else None
    )
    shock = (
        (1 - c.launch_failure_probability) * (1 - c.landing_failure_probability)
        if c.launch_failure_probability is not None and c.landing_failure_probability is not None
        else None
    )
    return {
        "id": c.id,
        "missing": [k for k, v in asdict(c).items() if v is None],
        "permanent_hazard_per_hour": hazard,
        "recoverable_rate_per_hour": recovery,
        "shock_survival": shock,
        "failure_probability": 1 - shock * math.exp(-hazard * hours)
        if shock is not None and hazard is not None
        else None,
        "malfunction_probability": -math.expm1(-c.upset_rate_per_hour * hours)
        if c.upset_rate_per_hour is not None
        else None,
        "restart_probability": -math.expm1(-recovery * hours) if recovery is not None else None,
        "expected_restart_count_full_exposure": recovery * hours if recovery is not None else None,
        "mean_recovery_hours": c.mean_recovery_hours,
        "retained_at_landing": retained,
        "retained_at_end": retained * math.exp(-c.degradation_rate_per_hour * hours)
        if retained is not None and c.degradation_rate_per_hour is not None
        else None,
        "performance_known": performance_known,
        "performance_cutoff_hours": cutoff,
        "thermal_margin_c": thermal,
        "dose_krad": dose,
        "radiation_margin_krad": radiation,
        "environment_status": "outside_declared_envelope"
        if (thermal is not None and thermal < 0) or (radiation is not None and radiation < 0)
        else "unknown"
        if thermal is None or radiation is None
        else "within_declared_envelope",
    }


def _window(profile: Profile, window: Window) -> dict[str, object]:
    hours = len(window.useful) * window.step_hours
    components = [_component(c, profile.cruise_hours, hours) for c in profile.components]
    stage: float | None = 1.0
    stages: list[dict[str, object]] = []
    for name in ("launch", "cruise", "landing"):
        probability = getattr(profile, f"{name}_success_probability")
        shocks = (
            [getattr(c, f"{name}_failure_probability") for c in profile.components]
            if name != "cruise"
            else []
        )
        if stage is None or probability is None or any(p is None for p in shocks):
            stage = None
        else:
            stage *= probability * math.prod(1 - p for p in shocks)
        stages.append({"phase": name, "survival_probability": stage})

    hazard = 0.0
    terms = [(1.0, 0.0)]
    cutoff = hours
    known = stage is not None
    hazard_known = stage is not None
    for c, result in zip(profile.components, components, strict=True):
        h = result["permanent_hazard_per_hour"]
        k = result["recoverable_rate_per_hour"]
        if not isinstance(h, (int, float)):
            hazard_known = False
            known = False
        else:
            hazard += h
        if not isinstance(k, (int, float)) or c.mean_recovery_hours is None:
            known = False
        elif k and c.mean_recovery_hours:
            mu = 1 / c.mean_recovery_hours
            a, b, q = mu / (k + mu), k / (k + mu), k + mu
            terms = [(w * x, r + y) for w, r in terms for x, y in ((a, 0.0), (b, q))]
        if not result["performance_known"]:
            known = False
        crossing = result["performance_cutoff_hours"]
        if isinstance(crossing, (int, float)):
            cutoff = min(cutoff, crossing)

    def available(t: float) -> float | None:
        if not known or stage is None:
            return None
        if any(
            c.minimum_performance_fraction is not None
            and isinstance(r["retained_at_landing"], (int, float))
            and r["retained_at_landing"] < c.minimum_performance_fraction
            for c, r in zip(profile.components, components, strict=True)
        ):
            return 0.0
        return (
            stage * sum(w * math.exp(-(hazard + r) * t) for w, r in terms) if t <= cutoff else 0.0
        )

    def integrate(start: float, end: float) -> float:
        end = min(end, cutoff)
        if end <= start or stage is None:
            return 0.0
        return stage * sum(w * _integral(hazard + r, start, end) for w, r in terms)

    expected = integrate(0, hours) if known else None
    lower = (
        sum(
            integrate(i * window.step_hours, (i + 1) * window.step_hours)
            for i, useful in enumerate(window.useful)
            if useful is True
        )
        if known
        else None
    )
    unknown = (
        sum(
            integrate(i * window.step_hours, (i + 1) * window.step_hours)
            for i, useful in enumerate(window.useful)
            if useful is None
        )
        if known
        else None
    )
    timeline = []
    for i in range(129):
        t = hours * i / 128
        timeline.append(
            {
                "hours": t,
                "time_unix": window.start_unix + t * 3600,
                "hardware_survival": stage * math.exp(-hazard * t)
                if hazard_known and stage is not None
                else None,
                "conditional_operational": available(t),
                "retained_min": min(
                    float(r["retained_at_landing"]) * math.exp(-c.degradation_rate_per_hour * t)
                    for c, r in zip(profile.components, components, strict=True)
                    if c.degradation_rate_per_hour is not None
                    and isinstance(r["retained_at_landing"], (int, float))
                )
                if all(r["performance_known"] for r in components)
                else None,
            }
        )
    return {
        "id": window.id,
        "duration_hours": hours,
        "stages": stages,
        "components": components,
        "complete_probability_inputs": known,
        "hardware_survival_probability": timeline[-1]["hardware_survival"],
        "conditional_operational_probability": available(hours),
        "expected_available_hours": expected,
        "expected_unavailable_hours": max(0.0, hours - expected) if expected is not None else None,
        "expected_useful_hours": lower if unknown == 0 else None,
        "expected_useful_lower_hours": lower,
        "expected_useful_upper_hours": lower + unknown
        if lower is not None and unknown is not None
        else None,
        "timeline": timeline,
    }


def reliability_summary(profile: Profile, windows: Sequence[Window]) -> dict[str, object]:
    return {
        "model": MODEL,
        "source": "declared_assumptions",
        "qualification": "not_validated",
        "assumptions": asdict(profile),
        "scenarios": [_window(profile, w) for w in windows],
        "method": "Independent critical series components; constant Poisson permanent/upset hazards; "
        "restart success splits recoverable and absorbing hazards; exponential recovery; "
        "all-up initial state after shocks; exact exponential-mixture integration. "
        "Launch/cruise/landing vehicle probabilities exclude the separately declared component shocks. "
        "Exponential performance retention; a declared minimum gates conditional operation. "
        "Thermal bounds and linear shielded TID are envelope checks, not failure-rate predictions.",
        "limits": [
            "No flight qualification, FMEA/FMECA completeness, redundancy, common-cause failures or Monte Carlo event history.",
            (
                "Rates are surface-operation assumptions, not inferred from lunar temperature or radiation. "
                "Restart counts assume full exposure; unavailable time includes irreversible loss and pre-surface failures."
            ),
            (
                "Conditional operation assumes the environmental envelope is satisfied; unknown or exceeded margins "
                "do not establish a mission success probability. No heat-flow, vibration, landing dynamics, "
                "particle transport, displacement damage or calibrated single-event cross-section simulation."
            ),
            (
                "Thermal min/max are predicted component temperatures after protection across all mission phases, "
                "not external lunar temperatures. Shield transmission is declared, not derived from shield thickness."
            ),
            "Degradation is an aggregate performance proxy, not a recalculation of RF gain, solar efficiency or battery capacity.",
        ],
    }
