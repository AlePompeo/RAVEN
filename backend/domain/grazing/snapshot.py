# SPDX-License-Identifier: Apache-2.0
"""Single-instant GrazingLink snapshot for ALL sites plus the DSN complexes (viewer, docs/domain/grazinglink-plan.md).

Per site: Earth az/el (topocentric: parallax + libration), distance, free-space-loss delta against the fixed
384 400 km. For sites inside the DEM coverage the link state comes from the existing `analyze` engine run
on ONE instant (one DEM profile read per site through the azimuth-quantised `ProfileCache`). Sites outside the
coverage get state 'fuori copertura DEM' and no number. Per DSN complex: elevation of the Moon from the
ephemeris engine, with the coordinates and citation of `backend.domain.lunar.visibility` (DSN 810-005 Table 5).

State rule (margin at the chosen rate, geometry from the dominant ridge):
    open        margin >= 0 and the Earth centre clears the ridge (geometric LOS)
    transition  margin >= 0 but the ridge blocks the geometric LOS (the link closes by diffraction)
    blocked     margin < 0 (the link does not close at this rate; includes Earth below the horizon)
"""

import math
from collections.abc import Callable
from datetime import datetime
from typing import Any

import numpy as np

from backend.domain.grazing import antenna as ant
from backend.domain.grazing.analysis import (
    AnalysisWindow,
    GrazingParamError,
    LinkInputs,
    ProfileCache,
    analyze,
)
from backend.domain.grazing.dem import DemUnavailable, LolaDem, load_lock
from backend.domain.grazing.geometry import earth_geometry
from backend.domain.lunar.model import Site, load_sites
from backend.domain.lunar.visibility import DSN_SOURCE, DSN_STATIONS
from backend.domain.raven import params as reg

__all__ = ["REFERENCE_RANGE_KM", "link_state", "snapshot"]

REFERENCE_RANGE_KM = 384_400.0
# DSN 810-005 Module 301 Rev. P sec. 2.2.2-2.2.3 (6 deg receive mechanical limit): the single
# definition is the registry entry `lunar.ground_station_min_elevation_deg` (tag V)
DSN_MIN_ELEVATION_DEG = reg.value("lunar.ground_station_min_elevation_deg")
OUT_OF_COVERAGE = "fuori copertura DEM"
# One-instant window: n_steps = int(1.5 * 1440 / (1440 * 1.0)) = 1 (AnalysisWindow is a plain dataclass).
_ONE_STEP = (1.5 / 1440.0, 1.0)


def link_state(margin_db: float, geometric_visible: bool) -> str:
    if margin_db < 0.0:
        return "blocked"
    return "open" if geometric_visible else "transition"


def _r(v: float, nd: int) -> float:
    return round(float(v), nd)


def _site_entry(
    site: Site,
    t: datetime,
    inputs: LinkInputs,
    engine: Any,
    dem: LolaDem | None,
    dem_error: bool,
    cache: ProfileCache,
    max_lat: float,
) -> dict[str, Any]:
    g = earth_geometry(site.lat_deg, site.lon_deg_east, [t], engine=engine)
    rng = float(g.range_km[0])
    out: dict[str, Any] = {
        "id": site.id,
        "name": site.name,
        "lat_deg": site.lat_deg,
        "lon_deg_east": site.lon_deg_east,
        "dem_covered": site.lat_deg <= -max_lat,
        "earth_az_deg": _r(g.az_deg[0], 3),
        "earth_el_deg": _r(g.el_deg[0], 3),
        "earth_el_geocentric_deg": _r(g.el_geocentric_deg[0], 3),
        "parallax_deg": _r(g.parallax_deg[0], 3),
        "earth_range_km": _r(rng, 1),
        "fspl_delta_db": _r(20.0 * math.log10(rng / REFERENCE_RANGE_KM), 3),
    }
    if not out["dem_covered"]:
        out.update(
            state="out_of_coverage", state_label=OUT_OF_COVERAGE, margin_db=None, ridge_el_deg=None
        )
        return out
    if dem is None or dem_error:
        out.update(
            state="unavailable",
            state_label="dati DEM non disponibili",
            margin_db=None,
            ridge_el_deg=None,
        )
        return out
    try:
        res = analyze(
            window=AnalysisWindow(t, _ONE_STEP[0], _ONE_STEP[1]),
            inputs=inputs,
            site=(site.lat_deg, site.lon_deg_east),
            site_id=site.id,
            dem=dem,
            engine=engine,
            cache=cache,
        )
    except DemUnavailable:
        # a terrain tile of THIS site is not cached: the site is reported as unavailable, the others are still answered
        out.update(
            state="unavailable",
            state_label="dati DEM non disponibili",
            margin_db=None,
            ridge_el_deg=None,
        )
        return out
    s = res["series"]
    margin = s["margin_chosen_rate_db"][0]
    geo = bool(s["geometric_visible"][0])
    angle = s["ridge_angle_above_los_deg"][0]
    if margin is None:
        raise GrazingParamError("margin")
    out.update(
        state=link_state(margin, geo),
        state_label=None,
        margin_db=_r(margin, 2),
        geometric_visible=geo,
        ridge_el_deg=None if angle is None else _r(float(out["earth_el_deg"]) + angle, 3),
        ridge_angle_above_los_deg=angle,
        terrain=res["flags"]["terrain"],
        correction=res["flags"]["correction"]["label"],
        correction_status=res["flags"]["correction"]["status"],
        multipath_status=res["flags"]["multipath"]["status"],
    )
    return out


def snapshot(
    t: datetime,
    inputs: LinkInputs,
    engine: Any,
    dem_getter: Callable[[], LolaDem],
    cache: ProfileCache,
) -> dict[str, Any]:
    max_lat = load_lock().max_lat_deg
    sites = load_sites()
    dem: LolaDem | None = None
    dem_error = False
    if any(s.lat_deg <= -max_lat for s in sites):
        try:
            dem = dem_getter()
        except DemUnavailable:
            dem_error = True
    entries = [_site_entry(s, t, inputs, engine, dem, dem_error, cache, max_lat) for s in sites]
    complexes: list[dict[str, Any]] = []
    for st in DSN_STATIONS:
        m = engine.topocentric_azel(
            "earth", st.lat_deg, st.lon_deg_east, "moon", [t], h_m=st.height_m
        )
        complexes.append(
            {
                "complex": st.complex,
                "lat_deg": st.lat_deg,
                "lon_deg_east": st.lon_deg_east,
                "height_m": st.height_m,
                "moon_az_deg": _r(m.az_deg[0], 3),
                "moon_el_deg": _r(m.el_deg[0], 3),
                "sees_moon": bool(m.el_deg[0] >= DSN_MIN_ELEVATION_DEG),
                "antennas": [
                    {
                        "id": "dsn34",
                        "name": st.name,
                        "diameter_m": 34.0,
                        "coordinates_verified": st.verified,
                        "gain_tag": ant.STATIONS["dsn34"].gain_tag,
                    },
                    {
                        "id": "dsn18",
                        "name": "stazione 18 m (ipotesi)",
                        "diameter_m": 18.0,
                        "coordinates_verified": False,
                        "gain_tag": ant.STATIONS["dsn18"].gain_tag,
                        "note": "nessuna fonte: ipotesi dello script della ricerca; coordinate del complesso",
                    },
                ],
            }
        )
    centre_km = float(np.asarray(engine.distance_km("moon", "earth", [t])).reshape(-1)[0])
    best = max(complexes, key=lambda c: c["moon_el_deg"])
    return {
        "label": "potential under stated assumptions",
        "t_utc": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rate_bps": inputs.rate_bps,
        "station": inputs.station,
        "reference_range_km": REFERENCE_RANGE_KM,
        "earth_moon_range_km": _r(centre_km, 1),
        "fspl_delta_db": _r(20.0 * math.log10(centre_km / REFERENCE_RANGE_KM), 3),
        "sites": entries,
        "dsn": {
            "min_elevation_deg": DSN_MIN_ELEVATION_DEG,
            "min_elevation_source": "DSN 810-005 Module 301 Rev. P sec. 2.2.2-2.2.3 (limite meccanico di ricezione 6 gradi)",
            "source": DSN_SOURCE,
            "complexes": complexes,
            "best_complex": best["complex"] if best["sees_moon"] else None,
            "sees_moon": [c["complex"] for c in complexes if c["sees_moon"]],
        },
        "state_rule": "aperto: margine >= 0 e centro della Terra sopra il crinale; transizione: margine >= 0 ma il "
        "crinale blocca la linea di vista geometrica (chiude per diffrazione); bloccato: margine < 0 al bit-rate scelto",
        "limits": [
            "Copertura DEM: latitudine <= -85 gradi.",
            "Ostacolo singolo dominante sul solo azimut del centro della Terra.",
            "Parametri radio illustrativi (tag I); cresta da ITU-R P.526-9 par. 4.2, modello non validato da misure.",
        ],
    }
