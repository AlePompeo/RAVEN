# SPDX-License-Identifier: Apache-2.0
"""S3 illumination (docs/domain/raven-model.md, 2.6).

The Sun is a uniform disc of semidiameter `asin(R_sun / distance)` (S1) compared with the horizon
mask of S2 (`horizon.disc_criteria`: exact circular area against the piecewise-linear horizon,
no limb darkening). Outputs: upper limb,
centre and lower limb visible, and the visible fraction of the disc. The boolean "light" is ONE
rule (decision D7): `lit = disc_fraction > 0`; the power of S4 always uses `disc_fraction`.

Unknown stays unknown: without a mask (missing tile, outside the coverage) or with an incomplete
azimuth, a criterion is None, never "visible"; a known "hidden" (fraction 0) stays known. There is
no flat-horizon criterion here (the old flat model is an oracle for the tests only).

This stage wraps `horizon.disc_criteria`; the new rule is `lit`.
"""

from dataclasses import dataclass

import numpy as np

from backend.domain.grazing.horizon import disc_criteria
from backend.domain.raven.known import Known, Reason
from backend.domain.raven.s1_geometry import Geometry
from backend.domain.raven.s2_terrain import Terrain

__all__ = ["Illumination", "illumination"]


@dataclass(frozen=True)
class Illumination:
    """Solar disc against the horizon mask; every field is three-state (None = unknown)."""

    upper_limb_visible: list[Known[bool]]
    centre_visible: list[Known[bool]]
    lower_limb_visible: list[Known[bool]]
    disc_fraction: list[Known[float]]  # visible fraction of the uniform disc, 0..1
    lit: list[Known[bool]]  # disc_fraction > 0
    reason: list[Reason]


def illumination(geo: Geometry, terr: Terrain) -> Illumination:
    n = geo.sun_az_deg.size
    if terr.mask is None:
        none: list[Known[bool]] = [None] * n
        return Illumination(
            none, list(none), list(none), [None] * n, list(none), [terr.mask_state] * n
        )
    c = disc_criteria(terr.mask, geo.sun_az_deg, geo.sun_el_deg, geo.sun_semidiameter_deg)
    frac: list[Known[float]] = list(c["disc_fraction"])
    lit: list[Known[bool]] = [None if f is None else f > 0.0 for f in frac]
    finite = (
        np.isfinite(geo.sun_az_deg)
        & np.isfinite(geo.sun_el_deg)
        & np.isfinite(geo.sun_semidiameter_deg)
        & (geo.sun_semidiameter_deg > 0.0)
    )
    reason = [
        Reason.OK
        if frac[k] is not None
        else Reason.MISSING_DEM
        if finite[k] and c["complete"][k] is not None
        else Reason.OUTSIDE_MODEL
        if finite[k]
        else Reason.UPSTREAM_UNKNOWN
        for k in range(n)
    ]
    return Illumination(c["upper"], c["centre"], c["lower"], frac, lit, reason)
