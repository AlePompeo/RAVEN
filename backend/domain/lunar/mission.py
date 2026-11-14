# SPDX-License-Identifier: Apache-2.0
"""Useful mission hours per site and ranking across sites (potential under stated assumptions).

A time step is USEFUL when ALL of these hold:

    power_available         (energy.simulate_energy: array covers the active load OR SOC > reserve)
    earth_visible           (Earth centre above the lunar-site mask, flat horizon)
    ground_station_visible  (Moon above the DSN minimum elevation at ANY of 3 complexes)
    margin_db >= required   (simplified link budget, link.link_margin_db)

Ranking (never a single opaque number): for each site two components, each divided by the maximum
over the compared sites (so the best site scores 1 on that component, 0 stays 0):

    useful_fraction   = useful steps / steps
    energy_margin     = minimum battery SOC reached in the window (0..1; 0 if it browns out)
    score             = sum_k w_k * c_k / max_site(c_k) / sum_k w_k      (default w = 1, 1)
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from backend.domain.lunar.energy import (
    EnergyResult,
    array_power_w,
    cos_incidence,
    irradiance_w_m2,
    simulate_energy,
)
from backend.domain.lunar.link import link_margin_db
from backend.domain.lunar.model import AnalysisWindow, EnergyParams, LinkParams, ParamError, Site
from backend.domain.lunar.runs import longest_run, n_runs
from backend.domain.lunar.visibility import (
    DsnVisibility,
    SiteVisibility,
    dsn_visibility,
    site_visibility,
    sun_distance_au,
)

__all__ = [
    "RANK_COMPONENTS",
    "Analysis",
    "SiteAnalysis",
    "analyze",
    "analyze_site",
    "rank_sites",
]

Arr = NDArray[np.float64]
BoolArr = NDArray[np.bool_]
RANK_COMPONENTS = ("useful_fraction", "energy_margin")


@dataclass(frozen=True)
class SiteAnalysis:
    site: Site
    vis: SiteVisibility
    energy: EnergyResult
    margin_db: Arr
    link_ok: BoolArr
    useful: BoolArr
    metrics: dict[str, Any]


@dataclass(frozen=True)
class Analysis:
    window: AnalysisWindow
    instants_unix: Arr
    sun_au: Arr
    dsn: DsnVisibility
    sites: list[SiteAnalysis]
    ranking: list[dict[str, Any]]


def analyze_site(
    site: Site,
    vis: SiteVisibility,
    dsn: DsnVisibility,
    irradiance: Arr,
    window: AnalysisWindow,
    link: LinkParams,
    energy: EnergyParams,
) -> SiteAnalysis:
    dt = window.dt_h
    margin = np.asarray(link_margin_db(vis.earth_range_km, link), dtype=np.float64)
    link_ok = vis.earth_visible & dsn.visible & (margin >= link.required_margin_db)
    cosi = cos_incidence(vis.sun_az_deg, vis.sun_el_deg, energy)
    gen = array_power_w(irradiance, cosi, vis.sun_up, energy)
    en = simulate_energy(gen, vis.sun_up, link_ok, dt, energy, link.tx_power_w)
    useful = en.power_available & link_ok
    n = len(useful)
    seen = margin[vis.earth_visible]
    metrics: dict[str, Any] = {
        "useful_hours": float(useful.sum()) * dt,
        "useful_fraction": float(useful.mean()),
        "longest_gap_h": longest_run(useful, False) * dt,
        "n_windows": n_runs(useful),
        "mean_margin_db": float(seen.mean()) if seen.size else None,
        "min_margin_db": float(seen.min()) if seen.size else None,
        "sun_fraction": float(vis.sun_up.mean()),
        "earth_fraction": float(vis.earth_visible.mean()),
        "ground_station_fraction": float(dsn.visible.mean()),
        "link_fraction": float(link_ok.mean()),
        "power_available_fraction": float(en.power_available.mean()),
        "earth_el_min_deg": float(vis.earth_el_deg.min()),
        "earth_el_max_deg": float(vis.earth_el_deg.max()),
        "n_steps": n,
        "energy": {
            "harvested_wh": en.harvested_wh,
            "sun_hours": en.sun_hours,
            "longest_dark_h": en.longest_dark_h,
            "min_soc": en.min_soc,
            "hours_power_available": en.hours_power_available,
            "survived": en.survived,
            "unmet_wh": en.unmet_wh,
            "curtailed_wh": en.curtailed_wh,
            "load_served_wh": en.load_served_wh,
        },
    }
    return SiteAnalysis(site, vis, en, margin, link_ok, useful, metrics)


def rank_sites(
    metrics: Mapping[str, Mapping[str, Any]], weights: Mapping[str, float] | None = None
) -> list[dict[str, Any]]:
    """Rank sites by the documented rule; the components are returned with every entry."""
    w = {k: 1.0 for k in RANK_COMPONENTS}
    if weights:
        if set(weights) - set(RANK_COMPONENTS):
            raise ParamError("weights")
        w.update({k: float(v) for k, v in weights.items()})
    if any(not np.isfinite(v) or v < 0 for v in w.values()) or sum(w.values()) <= 0:
        raise ParamError("weights")
    raw = {
        sid: {
            "useful_fraction": float(m["useful_fraction"]),
            "energy_margin": float(m["energy"]["min_soc"]),
        }
        for sid, m in metrics.items()
    }
    peak = {k: max((r[k] for r in raw.values()), default=0.0) for k in RANK_COMPONENTS}
    total_w = sum(w.values())
    rows: list[dict[str, Any]] = []
    for sid, comp in raw.items():
        parts = {}
        score = 0.0
        for k in RANK_COMPONENTS:
            norm = comp[k] / peak[k] if peak[k] > 0 else 0.0
            parts[k] = {"value": comp[k], "normalised": norm, "weight": w[k]}
            score += w[k] * norm
        rows.append({"site_id": sid, "score": score / total_w, "components": parts})
    rows.sort(key=lambda r: (-r["score"], r["site_id"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


def analyze(
    engine: Any,
    sites: list[Site],
    window: AnalysisWindow,
    link: LinkParams,
    energy: EnergyParams,
    weights: Mapping[str, float] | None = None,
) -> Analysis:
    ts = window.instants()
    sun_au = sun_distance_au(engine, ts)
    irr = irradiance_w_m2(sun_au)
    dsn = dsn_visibility(engine, ts, link.ground_station_min_elevation_deg)
    out = []
    for s in sites:
        vis = site_visibility(
            engine,
            s,
            ts,
            sun_mask_deg=energy.sun_elevation_mask_deg,
            earth_mask_deg=link.earth_site_elevation_mask_deg,
        )
        out.append(analyze_site(s, vis, dsn, irr, window, link, energy))
    ranking = rank_sites({a.site.id: a.metrics for a in out}, weights)
    unix = np.array([t.timestamp() for t in ts], dtype=np.float64)
    return Analysis(window, unix, sun_au, dsn, out, ranking)
