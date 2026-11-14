# SPDX-License-Identifier: Apache-2.0
"""S4 power and battery (docs/domain/raven-model.md, 2.7; migration step M6).

Generation = irradiance x area x efficiency x packing x (1 - degradation) x cos(incidence) x the
visible solar-disc fraction of S3 (`terrain_energy.terrain_generation_w`); the battery has three
modes (`energy.simulate_energy`); the communication load follows the link availability that the
pipeline derives from S5 and S6. The battery has memory: the first step with an unknown generation
or an unknown link makes that step and ALL later steps unknown (same rule as `coupled.couple`).
Parameters are the legacy `EnergyParams` (illustrative, tag I) until the unification of M8.
"""

import math
from dataclasses import dataclass

import numpy as np

from backend.domain.lunar.energy import MODE_ACTIVE, MODE_COMMS_ONLY, simulate_energy
from backend.domain.lunar.model import EnergyParams
from backend.domain.lunar.terrain_energy import terrain_generation_w
from backend.domain.raven import params as reg
from backend.domain.raven.known import Known, Reason
from backend.domain.raven.s1_geometry import Geometry
from backend.domain.raven.s3_illumination import Illumination

__all__ = ["Power", "power"]


@dataclass(frozen=True)
class Power:
    gen_w: list[Known[float]]
    soc: list[Known[float]]
    state: list[str]  # operational | comms_only | survival | dark | unknown
    min_soc: Known[float]  # initial state and known intervals; None without a known interval
    unmet_wh: Known[float]
    harvested_wh: Known[float]
    known_steps: int
    first_unknown_index: int | None
    reason: list[Reason]


def power(
    geo: Geometry,
    illum: Illumination,
    link_available: list[Known[bool]],
    energy: EnergyParams,
    tx_power_w: float,
    step_min: float,
) -> Power:
    n = geo.sun_az_deg.size
    if len(link_available) != n or len(illum.disc_fraction) != n or n == 0:
        raise ValueError("power inputs do not match")
    sun_au = geo.sun_range_km / reg.value("common.au_km")
    gen = terrain_generation_w(geo.sun_az_deg, geo.sun_el_deg, sun_au, illum.disc_fraction, energy)
    known_input = np.isfinite(gen) & np.array([v is not None for v in link_available], dtype=bool)
    prefix = n if known_input.all() else int(np.argmin(known_input))
    res = simulate_energy(
        gen[:prefix],
        gen[:prefix] > 0.0,
        np.array([bool(v) for v in link_available[:prefix]], dtype=bool),
        step_min / 60.0,
        energy,
        tx_power_w,
        comms_only=True,
    )
    assert res.mode is not None and res.unmet_step_wh is not None
    state: list[str] = []
    soc: list[Known[float]] = []
    reason: list[Reason] = []
    for k in range(n):
        if k >= prefix:
            state.append("unknown")
            soc.append(None)
            reason.append(Reason.UPSTREAM_UNKNOWN)
            continue
        soc.append(float(res.soc[k]))
        reason.append(Reason.OK)
        if res.unmet_step_wh[k] > 1e-9:
            state.append("dark")
        elif res.mode[k] == MODE_ACTIVE:
            state.append("operational")
        elif res.mode[k] == MODE_COMMS_ONLY:
            state.append("comms_only")
        else:
            state.append("survival")
    return Power(
        gen_w=[float(g) if math.isfinite(g) else None for g in gen],
        soc=soc,
        state=state,
        min_soc=min(energy.initial_soc, float(res.soc.min())) if prefix else None,
        unmet_wh=float(res.unmet_wh) if prefix else None,
        harvested_wh=float(res.harvested_wh) if prefix else None,
        known_steps=prefix,
        first_unknown_index=None if prefix == n else prefix,
        reason=reason,
    )
