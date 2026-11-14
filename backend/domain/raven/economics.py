# SPDX-License-Identifier: Apache-2.0
"""RAVEN economics and sustainability: cost band and CO2e of a mission CLASS, computed in the core.

Honesty rules (docs/domain/raven-model.md): every number is read from a listed public source (tag D) or is an explicit
assumption (tag I); a quantity with no adequate source is returned as unknown, never as a guess. These are class
scenarios (CLPS and HLS award values, public vehicle data), NOT a quote, NOT an LCA and NOT a forecast of the user's mission.
Sources are secondary (Wikipedia pages, newspaceeconomy.ca, a calculator page quoting ICE v3) and were NOT checked against the
primary documents. Stdlib only: this module is pure.
"""

from __future__ import annotations

from typing import Any, Final, TypedDict

MODEL_ID: Final = "raven.economics.v1"
CLASS_IDS: Final = ("rover", "small_lander", "medium_lander", "large_lander")
DEFAULT_CLASS: Final = "small_lander"

Band = dict[str, float | None]


class _Class(TypedDict):
    cost_musd: tuple[float | None, float | None, float | None]  # min, typical, max
    years: tuple[float | None, float | None, float | None]
    mass_kg: tuple[float | None, float | None, float | None]
    mass_tag: str
    launch: str
    vehicle: str | None


def _b(t: tuple[float | None, float | None, float | None]) -> Band:
    return {"min": t[0], "typical": t[1], "max": t[2]}


_NONE: Final = (None, None, None)
CLASSES: Final[dict[str, _Class]] = {
    # no adequate public source for the cost and time of a rover; its mass is an illustrative assumption (tag I)
    "rover": {
        "cost_musd": _NONE,
        "years": _NONE,
        "mass_kg": (50, None, 150),
        "mass_tag": "I",
        "launch": "passenger of a lander (see small lander)",
        "vehicle": None,
    },
    # CLPS awards IM-1 118, IM-2 47, Blue Ghost 1 93.3, Peregrine 108, IM-3 77.5, Blue Ghost 2 112 (median 100.65)
    "small_lander": {
        "cost_musd": (47, 100.65, 118),
        "years": (3.92, 4.455, 4.71),
        "mass_kg": (1283, 1517, 1900),
        "mass_tag": "D",
        "launch": "Falcon 9 Block 5 or Vulcan",
        "vehicle": "falcon9",
    },
    # Griffin Mission One: one award value (199.5 M USD), more than 6.5 years in development
    "medium_lander": {
        "cost_musd": (None, 199.5, None),
        "years": (6.5, None, None),
        "mass_kg": (1265, None, 21350),
        "mass_tag": "D",
        "launch": "Falcon Heavy or New Glenn",
        "vehicle": "falconheavy",
    },
    # HLS awards about 2.89 to 3.4 billion USD (one source reports 7, unresolved); Blue Moon Mark 2 above 45 t at launch
    "large_lander": {
        "cost_musd": (2890, None, 3400),
        "years": _NONE,
        "mass_kg": (45000, None, None),
        "mass_tag": "D",
        "launch": "New Glenn (7 m fairing) or Starship class",
        "vehicle": "newglenn",
    },
}

_CO2_PER_C: Final = 44.01 / 12.011  # C + O2 -> CO2
_CO2_PER_CH4: Final = 44.01 / 16.04  # CH4 + 2 O2 -> CO2 + 2 H2O
# Tank capacities in tonnes (Wikipedia Falcon 9 Block 5 / Falcon Heavy, read 12 Nov 2026); New Glenn: 710 m3 x density
# (the methane density 0.40-0.43 t/m3 is an assumption, not read from a source). LOX and hydrogen emit no CO2.
_VEHICLES: Final[dict[str, dict[str, Any]]] = {
    "falcon9": {
        "name": "Falcon 9",
        "fuel": "RP-1",
        "fuel_t": (155.8, 155.8),
        "per_kg": (0.85 * _CO2_PER_C, 0.87 * _CO2_PER_C),
        "note": "RP-1 tank capacity 123.5 t (stage 1) + 32.3 t (stage 2)",
    },
    "falconheavy": {
        "name": "Falcon Heavy",
        "fuel": "RP-1",
        "fuel_t": (402.8, 402.8),
        "per_kg": (0.85 * _CO2_PER_C, 0.87 * _CO2_PER_C),
        "note": "RP-1 tank capacity 3 x 123.5 t (cores) + 32.3 t (stage 2)",
    },
    "newglenn": {
        "name": "New Glenn",
        "fuel": "liquid methane (stage 1; the hydrogen second stage emits no CO2)",
        "fuel_t": (710 * 0.40, 710 * 0.43),
        "per_kg": (_CO2_PER_CH4, _CO2_PER_CH4),
        "note": "methane tank volume 710 m3 x 0.40-0.43 t/m3 (density: assumption, tag I)",
    },
}
_BURNED_SHARE: Final = (
    0.85,
    1.00,
)  # tank capacity is not the loaded mass and a recovered booster keeps some (tag I)

# Production: launch mass x the emission factor of PRIMARY ALUMINIUM, as an order-of-magnitude stand-in for the whole vehicle.
# Factors read in a search result on 12 Nov 2026: 8.24 (ICE v3 via a calculator page), 8.6 (Europe average), 15.1 (global average).
_ALU_KG_CO2E_PER_KG: Final = (8.24, 15.1)

SOURCES: Final = {
    "cost": "NASA CLPS / HLS award values 2019-2023, nominal USD (Wikipedia pages of CLPS, Nova-C, Peregrine, Blue Ghost, Griffin, "
    "Blue Moon, read 9 Nov 2026); docs/domain/scenario-archetypes.md; not the provider's own cost",
    "launch_co2": "Wikipedia Falcon 9 Block 5, Falcon Heavy and New Glenn pages (tank capacities, 12 Nov 2026); stoichiometry "
    "C + O2 -> CO2 (44.01/12.011) and CH4 + 2 O2 -> CO2 + 2 H2O (44.01/16.04)",
    "production_co2e": "primary aluminium 8.24-15.1 kg CO2e/kg (ICE v3 via a calculator page; global average 15.1; web search, 12 Nov 2026); "
    "not read from the ICE tables",
}
UNKNOWN: Final = (
    "Cost of a rover or payload; development time of the rover and large classes",
    "Cost per line item (structure, propulsion, avionics, operations): no adequate public source",
    "Manufacturing CO2e per material and component: only an aluminium-equivalent order of magnitude is given",
    "Operations CO2e (ground stations, electricity): no source read",
    "Black carbon, NOx, water vapour and propellant production of the launch are not included",
)


def _r(v: float | None, n: int = 0) -> float | None:
    return None if v is None else round(v, n)


def launch_co2_t(vehicle: str) -> Band:
    """Tonnes of CO2 from the carbon of the burned propellant: min, typical, max (combustion only: a lower bound of CO2e)."""
    v = _VEHICLES[vehicle]
    (f_lo, f_hi), (k_lo, k_hi) = v["fuel_t"], v["per_kg"]
    lo = f_lo * _BURNED_SHARE[0] * k_lo
    hi = f_hi * _BURNED_SHARE[1] * k_hi
    ty = (f_lo + f_hi) / 2 * 0.95 * (k_lo + k_hi) / 2
    return {"min": round(lo), "typical": round(ty), "max": round(hi)}


def production_co2e_t(mass_kg: tuple[float | None, float | None, float | None]) -> Band:
    """Aluminium-equivalent of the launch mass (tag I). A bound with no mass behind it stays unknown."""
    lo = None if mass_kg[0] is None else mass_kg[0] * _ALU_KG_CO2E_PER_KG[0] / 1000
    hi = None if mass_kg[2] is None else mass_kg[2] * _ALU_KG_CO2E_PER_KG[1] / 1000
    ty = (
        None
        if mass_kg[1] is None
        else mass_kg[1] * (_ALU_KG_CO2E_PER_KG[0] + _ALU_KG_CO2E_PER_KG[1]) / 2 / 1000
    )
    return {"min": _r(lo), "typical": _r(ty), "max": _r(hi)}


def _sum(a: Band, b: Band) -> Band:
    """Sum of two ranges; a bound is known only when both parts have it (unknown stays unknown)."""
    out: Band = {}
    for k in ("min", "typical", "max"):
        x, y = a[k], b[k]
        out[k] = None if x is None or y is None else x + y
    return out


def estimate(mission_class: str = DEFAULT_CLASS) -> dict[str, Any]:
    """Cost band, development time, launch mass, launch CO2 and aluminium-equivalent production CO2e of one class."""
    if mission_class not in CLASSES:
        raise ValueError(f"unknown mission class: {mission_class}")
    d = CLASSES[mission_class]
    veh = d["vehicle"]
    vname = _VEHICLES[veh] if veh else None
    launch = launch_co2_t(veh) if veh else None
    production = production_co2e_t(d["mass_kg"])
    total = _sum(launch, production) if launch else None
    limits = [
        "Class scenario from public award values and vehicle data: not a quote, not an LCA, not a forecast of this mission.",
        "Secondary sources, not checked against the primary NASA documents.",
        "CO2 of combustion only: a lower bound of the launch CO2e.",
        "Production is an aluminium-equivalent of the launch mass (propellant included): an order of magnitude, tag I.",
        (
            "The aluminium factor was NOT confirmed against the ICE tables on 12 Nov 2026: a re-check found only a different ICE v3 "
            "entry (2.176 kg CO2e/kg, cradle to gate, general aluminium with recycled share, via Climatiq), so the factor depends on "
            "the recycled share and the range may be too high."
        ),
    ]
    return {
        "model": MODEL_ID,
        "mission_class": mission_class,
        "cost": {"unit": "M USD", "tag": "D", "source": SOURCES["cost"], **_b(d["cost_musd"])},
        "development_years": {"unit": "years", "tag": "D", **_b(d["years"])},
        "launch_mass": {"unit": "kg", "tag": d["mass_tag"], **_b(d["mass_kg"])},
        "launch_class": d["launch"],
        "co2e": {
            "unit": "t CO2e",
            "launch": None
            if launch is None
            else {
                "tag": "I",
                "vehicle": (vname or {})["name"],
                "propellant": (vname or {})["note"],
                "source": SOURCES["launch_co2"],
                **launch,
            },
            "production": {"tag": "I", "source": SOURCES["production_co2e"], **production},
            "total": total,
        },
        "limits": limits,
        "unknown": list(UNKNOWN),
        "context": [
            {
                "mission_class": c,
                "cost": _b(CLASSES[c]["cost_musd"]),
                "co2e_launch": launch_co2_t(v) if (v := CLASSES[c]["vehicle"]) else None,
            }
            for c in CLASS_IDS
        ],
    }
