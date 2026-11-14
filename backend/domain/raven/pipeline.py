# SPDX-License-Identifier: Apache-2.0
"""The evaluation pipeline: one entry point from a scenario to the stage outputs.

`evaluate` runs S0 to S7 in dependency order: S0, S1, S2, S3, S5, S6, then S4 (which needs the link
availability of S5 and S6) and S7. `Evaluation.implemented_stages` lists the stages that ran. A
missing input never becomes a default: it is unknown in every value that depends on it
(docs/domain/raven-model.md, principle 3).

Until the unification of M8 the radio and energy parameters are the legacy typed inputs
(`LinkInputs` for the RF link, `EnergyParams` for power and battery); the scenario carries them
explicitly and the response lists the registry hash.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from backend.domain.grazing.analysis import LinkInputs
from backend.domain.lunar.model import EnergyParams
from backend.domain.raven import params as reg
from backend.domain.raven.known import Known
from backend.domain.raven.meta import MODEL_VERSION, STAGE_ORDER, registry_sha256
from backend.domain.raven.s0_context import SiteRecord, TimeGrid, TimeWindow, build_grid
from backend.domain.raven.s1_geometry import Geometry, geometry
from backend.domain.raven.s2_terrain import Terrain, terrain
from backend.domain.raven.s3_illumination import Illumination, illumination
from backend.domain.raven.s4_power import Power, power
from backend.domain.raven.s5_rf import RfLink, rf_link, terrain_params, unified_link_inputs
from backend.domain.raven.s6_dsn import Dsn, dsn
from backend.domain.raven.s7_mission import Mission, link_usable_series, mission
from backend.domain.raven.windows import Predicate, find_windows

__all__ = [
    "MODEL_VERSION",
    "STAGE_ORDER",
    "Evaluation",
    "Scenario",
    "evaluate",
    "instant_predicates",
    "legacy_scenario",
    "refined_windows",
    "registry_sha256",
]


@dataclass(frozen=True)
class Scenario:
    """Inputs of one evaluation. Defaults are the UNIFIED set of M8 (D2, D3, D8): one radio set, a 3 dB
    usable-link threshold, two heights. `legacy_scenario` gives the pre-unification numbers."""

    site: SiteRecord
    window: TimeWindow
    energy: EnergyParams = field(default_factory=lambda: EnergyParams.from_overrides({}))
    rf: LinkInputs = field(default_factory=unified_link_inputs)
    panel_height_m: float = field(default_factory=lambda: reg.value("rf.panel_height_m"))
    dsn_min_elevation_deg: float = field(
        default_factory=lambda: reg.value("lunar.ground_station_min_elevation_deg")
    )
    required_margin_db: float = field(default_factory=lambda: reg.value("rf.required_margin_db"))


def legacy_scenario(site: SiteRecord, window: TimeWindow, **over: Any) -> Scenario:
    """The pre-M8 parameter set (GrazingLink radio, margin >= 0, 2 m): for regression against the
    golden outputs of the legacy endpoints. Not for new results."""
    base: dict[str, Any] = {
        "rf": LinkInputs(),
        "panel_height_m": reg.value("common.observer_height_default_m"),
        "required_margin_db": 0.0,
    }
    return Scenario(site, window, **{**base, **over})


@dataclass(frozen=True)
class Evaluation:
    model_version: str
    registry_sha256: str
    site: SiteRecord
    grid: TimeGrid
    geometry: Geometry | None
    terrain: Terrain | None
    illumination: Illumination | None
    power: Power | None
    rf: RfLink | None
    dsn: Dsn | None
    mission: Mission | None
    implemented_stages: tuple[str, ...]


def evaluate(
    sc: Scenario,
    engine: Any,
    *,
    mask_for: Any = None,
    profile_for: Any = None,
    injected: bool | None = None,
    limits: Any = None,
) -> Evaluation:
    """Run the whole chain for one site. Raises `EphemerisUnavailable` without kernels."""
    grid = build_grid(sc.window, limits)
    geo = geometry(engine, sc.site, grid)
    tp = terrain_params(sc.rf)
    tp = type(tp)(
        sc.panel_height_m,
        tp.antenna_height_m,
        tp.profile_length_m,
        tp.wavelength_m,
        tp.moon_radius_m,
    )
    terr = terrain(sc.site, geo, tp, mask_for=mask_for, profile_for=profile_for, injected=injected)
    ill = illumination(geo, terr)
    rf = rf_link(geo, terr, sc.rf, sc.window.step_min)
    ds = dsn(geo, sc.rf.station, sc.dsn_min_elevation_deg)
    tx_w = 10.0 ** (sc.rf.tx_power_dbw / 10.0)
    avail = link_usable_series(rf, ds, sc.required_margin_db)
    pw = power(geo, ill, avail, sc.energy, tx_w, sc.window.step_min)
    ms = mission(pw, rf, ds, sc.window.step_min, sc.required_margin_db)
    return Evaluation(
        MODEL_VERSION,
        registry_sha256(),
        sc.site,
        grid,
        geo,
        terr,
        ill,
        pw,
        rf,
        ds,
        ms,
        ("s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7"),
    )


def instant_predicates(
    sc: Scenario,
    engine: Any,
    *,
    mask_for: Any = None,
    profile_for: Any = None,
    injected: bool | None = None,
) -> dict[str, Predicate]:
    """Criteria at an EXACT instant (unix seconds), from S1-S3, S5 and S6 on a one-step grid.

    `lit` is S3 (`disc_fraction > 0`); `link_usable` is S5 and S6 with the scenario threshold. The
    battery has memory, so `useful` has no instant form and its windows stay at the step.
    """
    tp = terrain_params(sc.rf)
    tp = type(tp)(
        sc.panel_height_m,
        tp.antenna_height_m,
        tp.profile_length_m,
        tp.wavelength_m,
        tp.moon_radius_m,
    )

    def chain(t: float) -> tuple[Any, Any]:
        inst = datetime.fromtimestamp(t, UTC)
        grid = TimeGrid(inst, sc.window.step_min, 1, (inst,), (t,))
        geo = geometry(engine, sc.site, grid)
        return geo, terrain(
            sc.site, geo, tp, mask_for=mask_for, profile_for=profile_for, injected=injected
        )

    def lit_at(t: float) -> Known[bool]:
        geo, terr = chain(t)
        return illumination(geo, terr).lit[0]

    def link_at(t: float) -> Known[bool]:
        geo, terr = chain(t)
        rf = rf_link(geo, terr, sc.rf, sc.window.step_min)
        ds = dsn(geo, sc.rf.station, sc.dsn_min_elevation_deg)
        return link_usable_series(rf, ds, sc.required_margin_db)[0]

    return {"lit": lit_at, "link_usable": link_at}


# Each refinement step evaluates S1-S3 (and S5, S6) at one instant, about 15 ms: a year of windows needs
# hundreds of them. Beyond this budget the remaining edges stay at the step boundary and are flagged
# unresolved (the predicate answers unknown), so a long period costs seconds, never minutes.
MAX_INSTANT_CALLS = 200


def _budgeted(preds: dict[str, Predicate], budget: int) -> dict[str, Predicate]:
    left = [budget]

    def limit(pred: Predicate) -> Predicate:
        def call(t: float) -> Known[bool]:
            if left[0] <= 0:
                return None
            left[0] -= 1
            return pred(t)

        return call

    return {k: limit(v) for k, v in preds.items()}


def refined_windows(
    ev: Evaluation,
    sc: Scenario,
    engine: Any,
    *,
    tol_s: float = 1.0,
    max_instant_calls: int = MAX_INSTANT_CALLS,
    **kw: Any,
) -> dict[str, list[dict[str, Any]]]:
    """Windows of `lit`, `link_usable` and `useful` of an evaluation; the first two have their edges
    bisected to `tol_s`, `useful` stays at the step resolution (`*_resolved` False)."""
    assert ev.illumination is not None and ev.mission is not None
    preds = _budgeted(instant_predicates(sc, engine, **kw), max_instant_calls)
    t = ev.grid.t_unix
    step_s = ev.grid.step_min * 60.0
    return {
        "lit": find_windows(t, ev.illumination.lit, step_s, preds["lit"], tol_s),
        "link_usable": find_windows(t, ev.mission.link_usable, step_s, preds["link_usable"], tol_s),
        "useful": find_windows(t, ev.mission.useful, step_s, None, tol_s),
    }
