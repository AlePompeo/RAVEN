# SPDX-License-Identifier: Apache-2.0
"""RAVEN estimates for the Fresnel parameters the model needs but a site never provides (regolith permittivity, roughness).

Honesty rules: an interval is returned only where a public source gives the numbers behind it; otherwise the value is
unknown (None), never a guess. Tag I = estimate, not a measurement at the site. The sources below come from search
snippets (NASA NTRS 19780005009; Carrier, Olhoeft & Mendell 1991 as cited by others) and were NOT checked against the
primary documents. Stdlib only.
"""

from __future__ import annotations

import math
from typing import Final

MODEL_ID: Final = "raven.fresnel_estimates.v1"
SOURCE: Final = (
    "NASA NTRS 19780005009 (K = (1.93 +/- 0.17)^density, density in g/cm3); Carrier, Olhoeft & Mendell 1991, "
    "Lunar Sourcebook ch. 9 (as cited, not read); loss tangent < 0.005 for typical soils, 0.005-0.03 for rocks"
)
DENSITY_G_CM3: Final = (1.38, 1.80)  # range of the lunar samples named in the cited summary
COEFF: Final = (1.93 - 0.17, 1.93 + 0.17)
TAN_DELTA_SOIL_MAX: Final = 0.005


def estimate() -> dict[str, object]:
    eps_lo = COEFF[0] ** DENSITY_G_CM3[0]
    eps_hi = COEFF[1] ** DENSITY_G_CM3[1]
    eps_mid = 1.93 ** (sum(DENSITY_G_CM3) / 2)
    imag_hi = TAN_DELTA_SOIL_MAX * eps_hi
    return {
        "model": MODEL_ID,
        "tag": "I",
        "eps_real": {
            "min": round(eps_lo, 2),
            "typical": round(eps_mid, 2),
            "max": round(eps_hi, 2),
            "source": SOURCE,
        },
        "eps_imag": {
            "min": 0.0,
            "typical": None,
            "max": round(imag_hi, 3),
            "source": SOURCE,
            "note": "upper bound = soil loss tangent maximum x eps_real max; no typical value is given by the source",
        },
        "roughness_rms_m": {
            "min": None,
            "typical": None,
            "max": None,
            "source": None,
            "note": "no public measurement found for the reflection scale; the JPL 42-226 value 0.25 m is a simulation input",
        },
        "limits": "bulk regolith at radio wavelengths from Apollo samples; not the local surface, not wet, not a measurement at the site",
        "finite": all(math.isfinite(x) for x in (eps_lo, eps_hi, eps_mid, imag_hi)),
    }
