# SPDX-License-Identifier: Apache-2.0
"""Coupled mission evaluation for ONE site: Sun disc -> power -> battery -> RF link -> DSN -> state.

At every step t_i (each step stands for [t_i, t_i + dt)):

1. visible solar-disc fraction `f` against the cached LOLA horizon mask (`grazing/horizon.py`);
2. array power `P = S(r) A eta packing (1 - degradation) cos(inc) f` (`terrain_energy.py`);
3. battery state of charge with the existing model (`energy.simulate_energy`, three modes:
   active, comms-only, survival);
4. RF margin at the chosen bit rate from the GrazingLink engine (`grazing/analysis.py`: LOLA
   terrain along the Earth azimuth, dominant ridge, knife edge + ITU-R P.526-9 cylinder term);
5. DSN geometric visibility: Moon above the minimum elevation at any 34 m complex
   (`visibility.dsn_visibility`). The 18 m class has no verified station list here: its
   visibility is UNKNOWN, never assumed.

    link_usable = margin_db >= 0 AND dsn_visible
    useful      = state == operational AND link_usable

States: `operational` (active mode: the array covers the active load or the battery is above the
reserve), `comms_only` (active mode not available, link usable and the array alone covers survival
+ comms), `survival` (survival load only, served), `dark` (load not fully served: blackout),
`unknown` (an input of this step or of an earlier step is unknown: missing DEM, RF not computed,
unsynchronised series, 18 m station). Once the battery history depends on an unknown input, every
later state of charge is unknown too: nothing unknown is ever counted as OK.

`coupled_sensitivity` is the older input-driven variant kept for `/api/lunar/coupled-sensitivity`.
"""

import math
from collections.abc import Sequence
from typing import Any

import numpy as np
from numpy.typing import NDArray

from backend.domain.lunar.energy import (
    MODE_ACTIVE,
    MODE_COMMS_ONLY,
    simulate_energy,
)
from backend.domain.lunar.model import EnergyParams
from backend.domain.lunar.runs import longest_run
from backend.domain.raven.params import value as reg_value

Arr = NDArray[np.float64]
STATES = ("operational", "comms_only", "survival", "dark", "unknown")
LIMITING = ("energy", "link", "visibility", "multiple")


def coupled_sensitivity(
    samples: list[dict[str, Any]], step_min: float, energy: EnergyParams, tx_power_dbw: float
) -> dict[str, Any]:
    """Recompute battery and useful steps without changing the baseline timeline."""
    if any(s["solar_state"] not in ("upper_above_profile", "upper_below_profile") for s in samples):
        return {"status": "unknown_terrain"}
    solar = np.asarray(
        [s["sun_up"] and s["solar_state"] == "upper_above_profile" for s in samples],
        dtype=bool,
    )
    available = np.asarray(
        [s["earth_visible"] and s["dsn_visible"] and s["rf_ok"] for s in samples], dtype=bool
    )
    generation = np.asarray([s["gen_w"] for s in samples], dtype=np.float64)
    tx_power_w = 10.0 ** (tx_power_dbw / 10.0)
    result = simulate_energy(
        np.where(solar, generation, 0.0), solar, available, step_min / 60.0, energy, tx_power_w
    )
    useful = result.power_available & available
    return {
        "status": "available",
        "time_unix": [s["time_unix"] for s in samples],
        "gen_w": result.gen_w.tolist(),
        "soc": result.soc.tolist(),
        "link_available": available.tolist(),
        "useful": useful.tolist(),
        "harvested_wh": result.harvested_wh,
        "min_soc": result.min_soc,
        "unmet_wh": result.unmet_wh,
        "useful_hours": float(useful.sum()) * step_min / 60.0,
        "tx_power_w": tx_power_w,
    }


def _num(v: Any) -> float:
    return float("nan") if v is None else float(v)


def couple(
    step_min: float,
    gen_w: Sequence[float | None],
    margin_db: Sequence[float | None],
    dsn_visible: Sequence[bool | None],
    energy: EnergyParams,
    tx_power_w: float,
) -> dict[str, Any]:
    """Pure coupling of per-step inputs (None/NaN = unknown) into states and objectives."""
    n = len(gen_w)
    if not (len(margin_db) == len(dsn_visible) == n) or n == 0:
        raise ValueError("coupled inputs do not match")
    dt_h = step_min / 60.0
    gen = np.array([_num(v) for v in gen_w], dtype=np.float64)
    margin = np.array([_num(v) for v in margin_db], dtype=np.float64)
    if np.any(gen[np.isfinite(gen)] < 0):
        raise ValueError("negative generation")
    link: list[bool | None] = []
    for m, d in zip(margin, dsn_visible, strict=True):
        if d is None or not math.isfinite(m):
            link.append(None)
        else:
            link.append(bool(m >= 0.0) and bool(d))
    known_input = np.isfinite(gen) & np.array([v is not None for v in link], dtype=bool)
    prefix = n if known_input.all() else int(np.argmin(known_input))
    res = simulate_energy(
        gen[:prefix],
        gen[:prefix] > 0.0,
        np.array([bool(v) for v in link[:prefix]], dtype=bool),
        dt_h,
        energy,
        tx_power_w,
        comms_only=True,
    )
    assert res.mode is not None and res.unmet_step_wh is not None
    states: list[str] = []
    useful: list[bool | None] = []
    soc: list[float | None] = []
    limiting: list[str | None] = []
    for k in range(n):
        if k >= prefix:
            states.append("unknown")
            useful.append(None)
            soc.append(None)
            limiting.append(None)
            continue
        soc.append(float(res.soc[k]))
        if res.unmet_step_wh[k] > 1e-9:
            st = "dark"
        elif res.mode[k] == MODE_ACTIVE:
            st = "operational"
        elif res.mode[k] == MODE_COMMS_ONLY:
            st = "comms_only"
        else:
            st = "survival"
        states.append(st)
        u = st == "operational" and bool(link[k])
        useful.append(u)
        if u:
            limiting.append(None)
            continue
        causes = []
        if st != "operational":
            causes.append("energy")
        if not margin[k] >= 0.0:
            causes.append("link")
        if not dsn_visible[k]:
            causes.append("visibility")
        limiting.append(causes[0] if len(causes) == 1 else "multiple")
    known = np.arange(n) < prefix
    u_arr = np.array([bool(v) for v in useful], dtype=bool)
    dark = [k for k, s in enumerate(states) if s == "dark"]
    lim_counts = {c: sum(1 for v in limiting if v == c) for c in LIMITING}
    metrics: dict[str, Any] = {
        "n_steps": n,
        "known_steps": prefix,
        "unknown_steps": n - prefix,
        "useful_hours": float(u_arr.sum()) * dt_h,
        "useful_fraction": float(u_arr.sum()) / n,
        "useful_fraction_of_known": float(u_arr.sum()) / prefix if prefix else None,
        "unknown_hours": (n - prefix) * dt_h,
        "state_hours": {s: sum(1 for v in states if v == s) * dt_h for s in STATES},
        "limiting_fraction": {c: lim_counts[c] / n for c in LIMITING},
        "min_soc": float(res.soc.min()) if prefix else None,
        "min_soc_scope": "known steps only" if prefix < n else "all steps",
        "time_to_first_blackout_h": dark[0] * dt_h if dark else None,
        "blackout_within_known": bool(dark),
        "unmet_wh": res.unmet_wh,
        "harvested_wh": res.harvested_wh,
        "sun_hours": float(np.sum(gen[:prefix] > 0.0)) * dt_h,
        "longest_unuseful_h": longest_run(u_arr[known], False) * dt_h if prefix else None,
    }
    return {
        "series": {
            "gen_w": [None if not math.isfinite(g) else float(g) for g in gen],
            "soc": soc,
            "margin_db": [None if not math.isfinite(m) else float(m) for m in margin],
            "dsn_visible": list(dsn_visible),
            "link_usable": link,
            "state": states,
            "useful": useful,
            "limiting": limiting,
        },
        "metrics": metrics,
        "first_unknown_index": None if prefix == n else prefix,
    }


AU_KM = reg_value("common.au_km")  # IAU 2012 Resolution B2 (registry)
MISSION_LIMITS = (
    (
        "RF: GrazingLink single dominant obstacle along the Earth-centre azimuth (knife edge + "
        "ITU-R P.526-9 cylinder term, split-step band as uncertainty), no real radio measurement at "
        "the lunar south pole; illustrative radio parameters (tag I)."
    ),
    (
        "Shadows: LOLA horizon mask to 200 km (terrain beyond not modelled, DEM uncertainty and "
        "limb darkening not modelled); missing DEM = unknown."
    ),
    (
        "Energy: illustrative array, battery and loads (tag I); no thermal model, dust or ageing "
        "beyond the stated degradation."
    ),
    (
        "DSN: geometric visibility of the Moon centre from one 34 m antenna per complex; no "
        "scheduling, no antenna assignment; the 18 m class is a hypothesis with unknown visibility."
    ),
    "Potential under stated assumptions, not a mission forecast.",
)


def evaluate_mission(
    engine: Any,
    site: Any,
    window: Any,
    energy: EnergyParams,
    rf_inputs: Any,
    observer_height_m: float,
    *,
    dsn_min_elevation_deg: float,
    mask_for: Any = None,
    dem: Any = None,
) -> dict[str, Any]:
    """Run the coupled evaluation for one `Site` over a lunar `AnalysisWindow`."""
    from backend.domain.grazing import analysis as ga
    from backend.domain.grazing.dem import DemOutOfCoverage, DemUnavailable, LolaDem
    from backend.domain.grazing.horizon import LIMITS as SHADOW_LIMITS
    from backend.domain.grazing.horizon import sun_semidiameter_deg
    from backend.domain.grazing.solar_terrain import site_solar_terrain
    from backend.domain.lunar.model import defaults_table
    from backend.domain.lunar.terrain_energy import terrain_generation_w
    from backend.domain.lunar.visibility import dsn_visibility

    instants = window.instants()
    n = len(instants)
    t_unix = [int(t.timestamp()) for t in instants]
    sun = engine.topocentric_azel("moon", site.lat_deg, site.lon_deg_east, "sun", instants)
    sun_az = np.asarray(sun.az_deg, dtype=np.float64)
    sun_el = np.asarray(sun.el_deg, dtype=np.float64)
    sun_au = np.asarray(engine.sun_distance_au("moon", instants), dtype=np.float64)
    solar = site_solar_terrain(
        site.to_dict(),
        sun_az.tolist(),
        sun_el.tolist(),
        sun_semidiameter_deg(sun_au * AU_KM).tolist(),
        observer_height_m,
        mask_for,
    )
    gen = terrain_generation_w(sun_az, sun_el, sun_au, solar["disc_fraction"], energy)

    # RF margin at the chosen rate (GrazingLink), same instants or unknown
    rf_state = "ok"
    margin: list[float | None] = [None] * n
    rf_meta: dict[str, Any] = {}
    try:
        gw = ga.AnalysisWindow.build(window.start_utc, window.days, window.step_min)
        res = ga.analyze(
            window=gw,
            inputs=rf_inputs,
            site=(site.lat_deg, site.lon_deg_east),
            site_id=site.id,
            dem=dem if dem is not None else LolaDem(allow_download=False),
            engine=engine,
            include_window_samples=True,
        )
        samples = res["window_samples"]
        if [int(v) for v in samples["time_unix"]] != t_unix:
            rf_state = "unsynchronised"
        else:
            margin = list(samples["margin_db"])
        rf_meta = {
            "flags": res["flags"],
            "windows": {k: v for k, v in res["windows"].items() if not k.endswith("_unix")},
            "station": res["antenna"]["station"],
            "declared_limits": res["declared_limits"],
        }
    except DemOutOfCoverage:
        rf_state = "outside_coverage"
    except DemUnavailable:
        rf_state = "missing_dem"

    # DSN geometric visibility: 34 m verified, 18 m unknown
    station = rf_inputs.station
    if station == "dsn34":
        dsn = dsn_visibility(engine, instants, dsn_min_elevation_deg)
        dsn_vis: list[bool | None] = [bool(v) for v in dsn.visible]
        dsn_state = "geometric_34m"
    else:
        dsn_vis = [None] * n
        dsn_state = "unknown_18m_hypothesis"

    tx_power_w = 10.0 ** (rf_inputs.tx_power_dbw / 10.0)
    out = couple(window.step_min, gen.tolist(), margin, dsn_vis, energy, tx_power_w)
    out["series"] = {
        "time_unix": t_unix,
        "sun_az_deg": sun_az.tolist(),
        "sun_el_deg": sun_el.tolist(),
        "disc_fraction": solar["disc_fraction"],
        "solar_state": solar["state"],
        **out["series"],
    }
    energy_rows = [
        {**r, "value": getattr(energy, r["key"])}
        for r in defaults_table()
        if r.get("group") == "energy" and hasattr(energy, r["key"])
    ]
    reasons = {
        "shadow": solar["mask_state"],
        "rf": rf_state,
        "dsn": dsn_state,
    }
    out.update(
        {
            "label": "potential under stated assumptions",
            "site": site.to_dict(),
            "window": window.to_dict(),
            "inputs_state": reasons,
            "mask": solar["mask"],
            "rf": rf_meta,
            "rate_bps": rf_inputs.rate_bps,
            "station": station,
            "tx_power_w": tx_power_w,
            "parameters": {
                "energy": energy_rows,
                "rf": rf_inputs.used_parameters() if rf_state != "outside_coverage" else [],
                "observer_height": {
                    "key": "observer_height_m",
                    "value": observer_height_m,
                    "unit": "m",
                    "status": "I",
                    "source": "illustrative; sensitivity in docs/domain/validation.md",
                },
                "dsn_min_elevation": {
                    "key": "ground_station_min_elevation_deg",
                    "value": dsn_min_elevation_deg,
                    "unit": "deg",
                    "status": "V",
                    "source": "DSN 810-005 Module 301 Rev. P sec. 2.2.2-2.2.3",
                },
            },
            "rules": {
                "link_usable": "margin_db >= 0 at rate_bps AND DSN geometric visibility",
                "useful": "state == operational AND link_usable",
                "states": {
                    "operational": "array >= active load OR battery above the reserve",
                    "comms_only": "not operational, link usable, array >= survival + comms",
                    "survival": "survival load only, fully served",
                    "dark": "load not fully served (blackout)",
                    "unknown": "an input of this or an earlier step is unknown",
                },
                "generation": "array power x visible solar-disc fraction (horizon mask)",
                "limiting": (
                    "for known non-useful steps: energy (not operational), link (margin < 0), "
                    "visibility (DSN not visible); 'multiple' when more than one"
                ),
            },
            "declared_limits": [*MISSION_LIMITS, SHADOW_LIMITS],
        }
    )
    return out
