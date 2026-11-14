# SPDX-License-Identifier: Apache-2.0
"""Parameter registry of the GrazingLink engine (V = from a source with page, D = derived, I = illustrative).

Values and tags come from docs/domain/grazinglink-model.md (section 3). Sources: JPL226 = IPN PR 42-226
(Sanchez Net, 2021); CB79 = Crane & Blood, ERT TR-1 (1979); P526 = ITU-R P.526-9 (2005).
Only the referenced P526 formulas were checked; the complete rounded-ridge model remains unvalidated.
Radio parameters are illustrative in the research scripts and stay `I`.
"""

from backend.domain.lunar.model import ParamSpec, legacy_view
from backend.domain.raven.params import CB79, JPL226, P526

__all__ = ["CB79", "JPL226", "MOON_RADIUS_M", "P526", "PARAMS", "get_spec"]

MOON_RADIUS_M = 1_737_400.0  # reference sphere of LOLA / Horizons (MOONFACT via assumptions.md)

_SPECS = legacy_view("grazing")
PARAMS: dict[str, ParamSpec] = {s.key: s for s in _SPECS}


def get_spec(key: str) -> ParamSpec:
    return PARAMS[key]
