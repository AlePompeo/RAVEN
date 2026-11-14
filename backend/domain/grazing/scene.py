# SPDX-License-Identifier: Apache-2.0
"""Data of the lander scene for ONE instant (`/lander`, docs/domain/grazinglink-plan.md, scena lander).

Everything shown in 3D comes from here, nothing is invented: the terrain patch is sampled from the cached LOLA
tiles (or, with a user profile, only the profile is given), the numbers come from the same engine as `analyze`
(`analysis.analyze` on a one-step window), the Fresnel radius is the CB79 eq. (2) formula.

Local frame (metres, origin on the ground under the antenna, `e` forward along the Earth azimuth, `n` to the LEFT of
`e` seen from above, `u` up from the local horizontal plane through the ground point, lunar curvature included):
for a terrain post at horizontal arc s with height z over the reference sphere
    e = (R + z) sin(s / R) ~ s,    u = (R + z) cos(s / R) - (R + z0)
so the line of sight (antenna at u = mast height, direction (cos el, sin el)) and the ridge numbers of the
engine are exactly consistent with the drawn terrain. The patch heights are POINT samples (bilinear) of the 20 m
product on a coarser grid: a smaller rock or a crest narrower than the post spacing can be hidden (declared).
"""

import math
from datetime import datetime
from typing import Any

import numpy as np
from numpy.typing import NDArray

from backend.domain.grazing import antenna as ant
from backend.domain.grazing.analysis import (
    DECLARED_LIMITS,
    OUT_OF_COVERAGE_MESSAGE,
    AnalysisWindow,
    GrazingParamError,
    LinkInputs,
    ProfileCache,
    analyze,
)
from backend.domain.grazing.dem import DemOutOfCoverage, LolaDem
from backend.domain.grazing.geometry import earth_geometry
from backend.domain.grazing.model import MOON_RADIUS_M, PARAMS
from backend.domain.grazing.snapshot import link_state
from backend.domain.grazing.terrain import (
    TerrainProfile,
    dominant_ridge,
    profile_from_dem,
)

__all__ = ["PATCH_POSTS", "fresnel_radius_m", "scene"]

Arr = NDArray[np.float64]
PATCH_POSTS = 96
PATCH_MIN_HALF_M = 2500.0
PATCH_MAX_HALF_M = 5000.0  # the prefetched tiles cover a disc of 10.5 km: corners stay at 7.1 km
FRESNEL_SAMPLES = 48
MAX_PROFILE_OUT = 600
POINTING_DB_PER_X2 = ant.GAUSSIAN_DB_PER_X2
STATE_LABELS = {
    "open": "aperto",
    "transition": "transizione (chiude per diffrazione)",
    "blocked": "bloccato",
}


def fresnel_radius_m(n: int, wavelength_m: float, d1_m: float, d2_m: float) -> float:
    """n-th Fresnel zone radius r_n = sqrt(n lambda d1 d2 / (d1 + d2)) (CB79 sec. 2.3 eq. (2), p. 43)."""
    if d1_m <= 0.0 or d2_m <= 0.0 or wavelength_m <= 0.0 or n < 1:
        return 0.0
    return math.sqrt(n * wavelength_m * d1_m * d2_m / (d1_m + d2_m))


def _local(d: Arr, z: Arr, z0: float) -> tuple[Arr, Arr]:
    r = MOON_RADIUS_M + z
    phi = d / MOON_RADIUS_M
    return r * np.sin(phi), r * np.cos(phi) - (MOON_RADIUS_M + z0)


def _patch(
    dem: LolaDem, site: tuple[float, float], az_deg: float, half_m: float, z0: float
) -> dict[str, Any]:
    n = PATCH_POSTS
    ax = np.linspace(-half_m, half_m, n)
    ee, nn = np.meshgrid(ax, ax)  # ee: forward, nn: to the left
    dist = np.hypot(ee, nn)
    brg = math.radians(az_deg) - np.arctan2(nn, ee)
    R = dem.spec.radius_km * 1000.0
    la, lo = math.radians(site[0]), math.radians(site[1])
    ang = dist / R
    lat2 = np.arcsin(
        np.clip(math.sin(la) * np.cos(ang) + math.cos(la) * np.sin(ang) * np.cos(brg), -1, 1)
    )
    lon2 = lo + np.arctan2(
        np.sin(brg) * np.sin(ang) * math.cos(la), np.cos(ang) - math.sin(la) * np.sin(lat2)
    )
    rows = np.empty(n * n)
    cols = np.empty(n * n)
    lat_d, lon_d = np.degrees(lat2).ravel(), np.degrees(lon2).ravel()
    for i in range(n * n):
        rows[i], cols[i] = dem.pixel(float(lat_d[i]), float(lon_d[i]))
    z = dem.heights_m_at_pixels(rows, cols).reshape(n, n)
    _e, u = _local(dist, z, z0)
    return {
        "n": n,
        "size_m": 2.0 * half_m,
        "spacing_m": 2.0 * half_m / (n - 1),
        "native_resolution_m": dem.spec.scale_m,
        "layout": "righe: n da -S/2 (destra) a +S/2 (sinistra); colonne: e da -S/2 (dietro) a +S/2 (avanti)",
        "height_m": np.round(u, 1).ravel().tolist(),
        "min_m": round(float(u.min()), 1),
        "max_m": round(float(u.max()), 1),
        "sampling": f"campionamento puntuale (bilineare) del prodotto a {dem.spec.scale_m:g} m: rocce e creste piu' strette "
        "della spaziatura possono non comparire",
    }


def scene(
    *,
    t: datetime,
    site: tuple[float, float],
    site_id: str | None,
    inputs: LinkInputs,
    engine: Any,
    dem: LolaDem | None,
    cache: ProfileCache,
    profile: TerrainProfile | None = None,
) -> dict[str, Any]:
    """One-instant scene. `profile` = user profile (no height field); else LOLA (site must be in coverage)."""
    if profile is None:
        if dem is None:
            raise GrazingParamError("terrain")
        if not dem.spec.covers(site[0]):
            raise DemOutOfCoverage(OUT_OF_COVERAGE_MESSAGE)
    g = earth_geometry(site[0], site[1], [t], engine=engine)
    az, el, rng_km = float(g.az_deg[0]), float(g.el_deg[0]), float(g.range_km[0])
    lam = inputs.wavelength_m
    if profile is None:
        assert dem is not None
        azq = round(az / 0.1) * 0.1 % 360.0
        key = (dem.spec.id, round(site[0], 5), round(site[1], 5), azq, inputs.profile_length_m)
        prof = cache.get(
            key, lambda: profile_from_dem(dem, site[0], site[1], azq, inputs.profile_length_m)
        )
    else:
        prof = profile
    ridge = dominant_ridge(
        prof,
        el,
        lam,
        earth_range_m=rng_km * 1000.0,
        antenna_height_m=inputs.antenna_height_m,
    )
    res = analyze(
        window=AnalysisWindow(t, _ONE_STEP[0], _ONE_STEP[1]),
        inputs=inputs,
        site=site,
        site_id=site_id,
        dem=dem if profile is None else None,
        profile=profile,
        engine=engine,
        cache=cache,
    )
    s = res["series"]
    flags = res["flags"]

    def first(key: str) -> float:
        v = s[key][0]
        return float(v) if v is not None else math.nan

    margin = first("margin_chosen_rate_db")
    if math.isnan(margin):
        raise GrazingParamError("margin")
    geo = bool(first("geometric_visible") > 0.5)
    state = link_state(margin, geo)
    j_db, corr = first("knife_edge_loss_db"), first("ridge_correction_db")
    mp_ok = bool(first("multipath_applicable") > 0.5)
    mp_db = first("multipath_gain_db") if mp_ok else 0.0
    # local-frame profile and ridge
    z0 = float(prof.height_m[0])
    pe, pu = _local(prof.distance_m, prof.height_m, z0)
    step = max(1, -(-prof.distance_m.size // MAX_PROFILE_OUT))
    k = ridge.index
    ridge_e, ridge_u = float(pe[k]), float(pu[k])
    d1_end = min(max(ridge.d1_m * 1.6, ridge.d1_m + 500.0), 20_000.0)
    fz = [
        {
            "d_m": round(d, 2),
            "r_m": round(fresnel_radius_m(1, lam, d, rng_km * 1000.0 - d), 3),
        }
        for d in np.linspace(0.0, d1_end, FRESNEL_SAMPLES).tolist()
    ]
    half = 0.0
    patch: dict[str, Any] | None = None
    if profile is None:
        assert dem is not None
        half = float(
            min(
                PATCH_MAX_HALF_M,
                max(PATCH_MIN_HALF_M, math.ceil(1.3 * ridge.ridge_distance_m / 100.0) * 100.0),
            )
        )
        patch = _patch(dem, site, az, half, z0)
    d_m = ant.diameter_for_gain_m(inputs.tx_gain_dbi, inputs.frequency_hz, inputs.antenna_eta)
    hpbw = float(ant.hpbw_deg(d_m, inputs.frequency_hz, "script_70"))
    radius = ridge.radius_of_curvature_m
    synthetic = prof.synthetic
    a = math.radians(az)
    # Scene axes are forward along the Earth azimuth, up, and right.
    enu_to_scene = np.array(
        [[math.sin(a), math.cos(a), 0.0], [0.0, 0.0, 1.0], [math.cos(a), -math.sin(a), 0.0]]
    )
    icrf_to_scene = enu_to_scene @ engine.icrf_to_enu("moon", site[0], site[1], t)
    return {
        "label": "potential under stated assumptions",
        "t_utc": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "site": {"id": site_id, "lat_deg": site[0], "lon_deg_east": site[1]},
        "sky": {"icrf_to_scene": icrf_to_scene.tolist()},
        "earth": {
            "az_deg": round(az, 3),
            "el_deg": round(el, 3),
            "el_geocentric_deg": round(float(g.el_geocentric_deg[0]), 3),
            "parallax_deg": round(float(g.parallax_deg[0]), 3),
            "range_km": round(rng_km, 1),
            "angular_diameter_deg": round(float(g.angular_diameter_deg[0]), 4),
            "tag": "D (efemeridi Skyfield + NAIF: librazione fisica e parallasse topocentrica)",
        },
        "terrain": {
            "source": prof.source,
            "synthetic": synthetic,
            "label": prof.label,
            "product_id": None if profile is not None or dem is None else dem.spec.id,
            "native_resolution_m": None if dem is None or profile is not None else dem.spec.scale_m,
            "profile_spacing_m": prof.spacing_m,
            "profile_length_m": float(prof.distance_m[-1]),
            "azimuth_deg": round(az, 3),
            "radius_resolved": bool(ridge.radius_resolved),
            "coverage": "LOLA LDEM 85S 20 m: latitudine <= -85 gradi; tile in cache (build/lola)"
            if profile is None
            else "profilo fornito dall'utente; nessun campo di quote",
            "frame": "origine sul suolo sotto l'antenna; e avanti lungo l'azimut della Terra, n a sinistra, "
            "u in alto sul piano orizzontale locale (curvatura lunare inclusa)",
            "patch": patch,
            "patch_half_size_m": half if patch else None,
            "profile": {
                "e_m": np.round(pe[::step], 1).tolist(),
                "u_m": np.round(pu[::step], 2).tolist(),
                "arc_m": np.round(prof.distance_m[::step], 1).tolist(),
            },
        },
        "antenna": {
            "station": inputs.station,
            "mast_height_m": inputs.antenna_height_m,
            "mast_tag": PARAMS["antenna_height_m"].status,
            "gain_dbi": inputs.tx_gain_dbi,
            "gain_tag": PARAMS["tx_gain_dbi"].status,
            "diameter_m": round(d_m, 4),
            "hpbw_deg": round(hpbw, 3),
            "hpbw_model": "script_70 (70 lambda/D); a apertura uniforme "
            + f"{float(ant.hpbw_deg(d_m, inputs.frequency_hz, 'uniform')):.3f} gradi",
            "pointing_db_per_hpbw2": POINTING_DB_PER_X2,
            "pointing_rule": "perdita = 12.04 (errore/HPBW)^2 dB (gaussiana esatta); stato del cono rosso oltre HPBW/2",
            "frequency_ghz": inputs.frequency_ghz,
            "wavelength_m": round(lam, 6),
        },
        "ridge": {
            "e_m": round(ridge_e, 1),
            "u_m": round(ridge_u, 2),
            "arc_distance_m": round(ridge.ridge_distance_m, 1),
            "height_m": round(ridge.ridge_height_m, 1),
            "d1_m": round(ridge.d1_m, 1),
            "d2_m": round(ridge.d2_m, 1),
            "height_above_los_m": round(ridge.height_above_los_m, 2),
            "tip_elevation_deg": round(ridge.tip_elevation_deg, 3),
            "angle_above_los_deg": round(ridge.angle_above_los_deg, 3),
            "radius_of_curvature_m": None if math.isnan(radius) else round(radius, 1),
            "radius_resolved": bool(ridge.radius_resolved),
            "blocks_los": bool(ridge.blocks_los),
            "nu": round(ridge.nu, 3),
        },
        "fresnel": {
            "formula": "r_n = sqrt(n lambda d1 d2 / (d1 + d2)), CB79 sez. 2.3 eq. (2) p. 43",
            "wavelength_m": round(lam, 6),
            "range_m": round(rng_km * 1000.0, 0),
            "r1_at_ridge_m": round(fresnel_radius_m(1, lam, ridge.d1_m, ridge.d2_m), 3),
            "samples": fz,
            "near_field_only": "la Terra e' a circa 384 000 km: il tubo vale per il solo tratto vicino all'antenna "
            "(la zona si allarga come sqrt(lambda d1), non come un cono)",
            "tag": "D",
        },
        "diffraction": {
            "knife_edge_db": round(j_db, 3),
            "correction_db": round(corr, 3),
            "correction_uncertainty_db": round(first("ridge_correction_uncertainty_db"), 3),
            "correction_label": flags["correction"]["label"],
            "correction_status": flags["correction"]["status"],
            "diffraction_loss_db": round(j_db + corr, 3),
            "multipath_applicable": mp_ok,
            "multipath_gain_db": round(mp_db, 3) if mp_ok else None,
            "multipath_status": "applicato" if mp_ok else "non applicabile",
            "multipath_reason": None if mp_ok else flags["multipath"]["reason_not_applicable"],
            "total_loss_db": round(j_db + corr - mp_db, 3),
            "total_rule": "perdita totale = bordo a lama + correzione cresta - termine multipath",
            "p526": "ITU-R P.526-9 par. 4.1-4.2 verificate sul testo; correzione cresta = T(m,n), non misurata",
        },
        "link": {
            "rate_bps": inputs.rate_bps,
            "station": inputs.station,
            "margin_db": round(margin, 2),
            "state": state,
            "state_label": STATE_LABELS[state],
            "geometric_visible": geo,
            "fspl_db": round(first("fspl_db"), 3),
            "pointing_loss_db": round(first("pointing_loss_db"), 3),
            "rule": "aperto: margine >= 0 e centro della Terra sopra il crinale; transizione: margine >= 0 ma il "
            "crinale blocca la linea di vista geometrica; bloccato: margine < 0 al bit-rate scelto",
        },
        "flags": {
            "terrain": flags["terrain"],
            "synthetic": synthetic,
            "radius_resolved": bool(ridge.radius_resolved),
            "multipath": flags["multipath"],
            "correction": {k2: v for k2, v in flags["correction"].items() if k2 != "table"},
            "earth_below_horizon": bool(el <= 0.0),
        },
        "parameters": res["parameters"],
        "tags": {
            "geometry": "D",
            "terrain": "V (LOLA)" if prof.source == "lola" else "utente",
            "fresnel": "D",
            "knife_edge": "V (JPL 42-226 eq. 38)",
            "correction": "V formula (ITU-R P.526-9 eq. 28-32), banda split-step; non misurata",
            "multipath": "D",
            "radio": "I",
            "mast_height": PARAMS["antenna_height_m"].status,
        },
        "declared_limits": [
            *DECLARED_LIMITS,
            "Risoluzione del terreno 20 m (campo di quote piu' grossolano): rocce piu' piccole possono non comparire.",
        ],
    }


_ONE_STEP = (1.5 / 1440.0, 1.0)
