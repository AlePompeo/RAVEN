# SPDX-License-Identifier: Apache-2.0
"""Solar generation under the terrain horizon mask, and the battery what-if of `/solar-terrain`.

    P_array = S(r) A eta packing (1 - degradation) cos(inc) * f_disc

`f_disc` is the visible fraction of the solar disc against the horizon mask (`horizon.py`), so
a partly hidden Sun gives proportionally less power (uniform disc: no limb darkening). The flat
elevation mask of the baseline timeline is NOT applied: the terrain mask replaces it (a summit can
see the Sun slightly below the astronomical horizon). An unknown `f_disc` gives unknown power.
"""

from typing import Any

import numpy as np
from numpy.typing import NDArray

from backend.domain.lunar.energy import (
    array_power_w,
    cos_incidence,
    irradiance_w_m2,
    simulate_energy,
)
from backend.domain.lunar.model import EnergyParams, LinkParams

Arr = NDArray[np.float64]
KNOWN_STATES = {"upper_above_profile", "upper_below_profile"}
UNKNOWN_STATES = {"missing_dem", "outside_coverage", "invalid_geometry"}


def terrain_generation_w(
    sun_az_deg: Any, sun_el_deg: Any, sun_au: Any, disc_fraction: Any, p: EnergyParams
) -> Arr:
    """Array power (W) per step; NaN where the disc fraction (or the geometry) is unknown."""
    frac = np.array([np.nan if v is None else v for v in disc_fraction], dtype=np.float64)
    az = np.array([np.nan if v is None else v for v in sun_az_deg], dtype=np.float64)
    el = np.array([np.nan if v is None else v for v in sun_el_deg], dtype=np.float64)
    au = np.asarray(sun_au, dtype=np.float64)
    if not (frac.size == az.size == el.size == au.size):
        raise ValueError("generation inputs do not match")
    ok = np.isfinite(frac) & np.isfinite(az) & np.isfinite(el) & np.isfinite(au)
    safe = np.where(ok, 1.0, 0.0)
    cosi = cos_incidence(np.where(ok, az, 0.0), np.where(ok, el, 0.0), p)
    irr = irradiance_w_m2(np.where(ok, au, 1.0))
    gen = array_power_w(irr, cosi, np.ones(az.size, dtype=bool), p) * np.where(ok, frac, 0.0)
    return np.asarray(np.where(safe > 0, gen, np.nan), dtype=np.float64)


def terrain_energy_sensitivity(
    timeline: dict[str, Any],
    solar: dict[str, Any],
    overrides: dict[str, Any],
    sun_au: Any,
) -> None:
    """Attach an optional what-if to each solar row; never substitute for the baseline."""
    if timeline["series_time_unix"] != solar["series_time_unix"]:
        raise ValueError("solar and energy timelines do not match")
    energy = EnergyParams.from_overrides(overrides)
    link = LinkParams.from_overrides(overrides)
    dt_h = float(timeline["window"]["step_min"]) / 60.0
    n = len(timeline["series_time_unix"])
    for base, row in zip(timeline["sites"], solar["sites"], strict=True):
        if base["site"]["id"] != row["site_id"] or len(row["state"]) != n:
            raise ValueError("solar and energy sites do not match")
        if any(state not in KNOWN_STATES | UNKNOWN_STATES for state in row["state"]):
            raise ValueError("unrecognised solar terrain state")
        series = base["series"]
        if any(len(series[key]) != n for key in ("sun_az_deg", "sun_el_deg", "link_ok")):
            raise ValueError("energy series length mismatch")
        gen = terrain_generation_w(
            series["sun_az_deg"], series["sun_el_deg"], sun_au, row["disc_fraction"], energy
        )
        if not np.all(np.isfinite(gen)):
            row["energy_sensitivity"] = {"status": "unknown_terrain"}
            continue
        lit = np.asarray([f > 0.0 for f in row["disc_fraction"]], dtype=bool)
        link_ok = np.asarray(series["link_ok"], dtype=bool)
        result = simulate_energy(gen, lit, link_ok, dt_h, energy, link.tx_power_w)
        row["energy_sensitivity"] = {
            "status": "available",
            "gen_w": result.gen_w.tolist(),
            "soc": result.soc.tolist(),
            "harvested_wh": result.harvested_wh,
            "min_soc": result.min_soc,
            "generation_rule": "array power x visible solar-disc fraction (terrain mask)",
        }
