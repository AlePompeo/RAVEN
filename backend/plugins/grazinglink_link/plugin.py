# SPDX-License-Identifier: Apache-2.0
"""RAVEN simulation on an explicitly synthetic test ridge, never a site prediction."""

import asyncio
import math
from collections.abc import Mapping
from datetime import UTC, datetime

from backend.core.errors import PluginError, SimulationTimeout
from backend.core.manifest import Manifest

_REQUIRED = {"earth_el_deg", "ridge_radius_m"}
_ALLOWED = _REQUIRED | {"ridge_height_m", "rate_bps", "frequency_ghz"}


def _run(inputs: Mapping[str, float]) -> dict[str, float]:
    try:
        from backend.domain.grazing.analysis import (
            AnalysisWindow,
            EarthSweep,
            GrazingParamError,
            LinkInputs,
            analyze,
        )
        from backend.domain.grazing.terrain import synthetic_ridge_profile
    except ImportError as exc:
        raise PluginError("RAVEN richiede gli extra [sky]") from exc

    if not _REQUIRED <= inputs.keys() or inputs.keys() - _ALLOWED:
        raise PluginError("ingressi RAVEN non validi")
    if any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in inputs.values()):
        raise PluginError("ingressi RAVEN non finiti")
    el = inputs["earth_el_deg"]
    radius = inputs["ridge_radius_m"]
    height = inputs.get("ridge_height_m", 33.0)
    if not (-30 <= el <= 60 and 10 <= radius <= 5000 and 1 <= height <= 100):
        raise PluginError("ingressi RAVEN fuori intervallo")
    overrides = {key: inputs[key] for key in ("rate_bps", "frequency_ghz") if key in inputs}
    try:
        params = LinkInputs.from_overrides(overrides)
        profile = synthetic_ridge_profile(2000.0, height, ridge_radius_m=radius, step_m=5.0)
        report = analyze(
            window=AnalysisWindow(datetime(2026, 1, 1, tzinfo=UTC), 1.5 / 1440, 1.0),
            inputs=params,
            profile=profile,
            sweep=EarthSweep(el, el),
        )
    except GrazingParamError as exc:
        raise PluginError("parametri RAVEN non validi") from exc
    series = report["series"]
    return {
        "margin_db": float(series["margin_chosen_rate_db"][0]),
        "nu": float(series["nu"][0]),
        "knife_edge_loss_db": float(series["knife_edge_loss_db"][0]),
        "ridge_correction_db": float(series["ridge_correction_db"][0]),
        "fspl_db": float(series["fspl_db"][0]),
        "frequency_ghz": params.frequency_ghz,
        "distance_km": 384_400.0,
        "profile_synthetic": 1.0,
        "radius_resolved": float(report["flags"]["radius_resolved"]),
        "earth_below_horizon": float(el <= 0),
        "correction_clamped": float(report["flags"]["correction"]["clamped_steps"] > 0),
    }


class GrazingLinkSimulation:
    def __init__(self, manifest: Manifest) -> None:
        self.manifest = manifest

    async def run(self, inputs: Mapping[str, float], *, timeout_s: float) -> Mapping[str, float]:
        try:
            return await asyncio.wait_for(asyncio.to_thread(_run, inputs), timeout=timeout_s)
        except TimeoutError as exc:
            raise SimulationTimeout("simulazione RAVEN scaduta") from exc
