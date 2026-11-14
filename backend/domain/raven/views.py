# SPDX-License-Identifier: Apache-2.0
"""Read-only views on the single model: snapshot, scene, horizon (docs/domain/raven-model.md, 2.13).

No physics of their own. `snapshot` runs S1, S2 and S5 (and the DSN elevations of S1) on a one-step
grid for every catalogue site; `scene` returns the 3D scene of `grazing.scene` (patch, Fresnel zones,
ridge: the same numbers for the same inputs) and adds the model block of the unified chain (terrain
reason, far-terrain loss, the S5 state with the D4 rule); `horizon` gives the horizon mask and its
metadata. With the legacy radio set (`LinkInputs()`), geometry, margins and DSN elevations equal
`/api/grazing/snapshot`; the only intended difference is the D4 state of sites whose far terrain hides
the Earth (docs/domain/raven-changes.md).
"""

import dataclasses
import math
from datetime import UTC, datetime
from typing import Any

from backend.domain.grazing import antenna as ant
from backend.domain.grazing.analysis import LinkInputs, ProfileCache
from backend.domain.grazing.dem import DemOutOfCoverage, DemUnavailable, LolaDem
from backend.domain.grazing.dem_select import plan_site
from backend.domain.grazing.horizon import default_store
from backend.domain.lunar.visibility import DSN_SOURCE, DSN_STATIONS
from backend.domain.raven import params as reg
from backend.domain.raven import s0_context as s0
from backend.domain.raven.known import Reason
from backend.domain.raven.s1_geometry import geometry
from backend.domain.raven.s2_terrain import terrain
from backend.domain.raven.s5_rf import rf_link, terrain_params

__all__ = ["horizon", "scene", "snapshot"]

REFERENCE_RANGE_KM = 384_400.0
LIMITS = (
    "DEM coverage: latitude <= -85 degrees.",
    "Single dominant obstacle on the Earth-centre azimuth; far terrain beyond the RF profile is a single-obstacle estimate (decision D4).",
    "Radio parameters are illustrative where tagged I; ridge from ITU-R P.526-9 4.2, not validated by measurement.",
)


def _r(v: float, nd: int) -> float:
    return round(float(v), nd)


def _one(t: datetime, step_min: float = 1.0) -> s0.TimeGrid:
    t = t.astimezone(UTC)
    return s0.TimeGrid(t, step_min, 1, (t,), (t.timestamp(),))


def _state(rf: Any, terr: Any) -> tuple[str, str | None]:
    """(state, label) of the first step: open | transition | blocked | unknown."""
    if rf.rf_state[0] is not None:
        label = (
            "far terrain closes the link (known)"
            if rf.reason[0] is Reason.BLOCKED_FAR_TERRAIN
            else None
        )
        return str(rf.rf_state[0]), label
    return "unknown", f"unknown: {rf.reason[0].value}"


def _promote(site: s0.SiteRecord) -> s0.SiteRecord:
    if site.custom or site.dem_coverage is True:
        return site
    try:
        ok: bool | None = plan_site(site.lat_deg, site.lon_deg_east).status == "ok"
    except (OSError, KeyError, ValueError):
        ok = None
    return dataclasses.replace(site, custom=True, dem_coverage=ok)


def snapshot(
    t: datetime,
    rf_inputs: LinkInputs,
    engine: Any,
    *,
    site_ids: list[str] | None = None,
    extra_sites: list[s0.SiteRecord] | None = None,
    terrain_kw_for: Any = None,
    cached: Any = None,
) -> dict[str, Any]:
    """One instant, all catalogue sites plus the three DSN complexes.

    `extra_sites` are custom sites: `terrain_kw_for(site)` gives their terrain hooks and
    `cached(site)` tells whether their tiles are all in the cache (no download here): else the entry is
    `needs_download` (or `out_of_coverage` when the point has no terrain), margin unknown."""
    catalog = s0.load_catalog()
    sites = [catalog[i] for i in site_ids] if site_ids else list(catalog.values())
    if terrain_kw_for is not None and cached is not None:
        # a catalogue site outside the 20 m polar product is read like a user site: the global 237 m terrain, if its tiles are
        # already cached (no download here); otherwise `needs_download`, never an invented value
        sites = [_promote(x) for x in sites]
    sites = sites + list(extra_sites or [])
    grid = _one(t)
    tp = terrain_params(rf_inputs)
    entries: list[dict[str, Any]] = []
    for site in sites:
        geo = geometry(engine, site, grid)
        rng = float(geo.earth_range_km[0])
        e: dict[str, Any] = {
            "id": site.id,
            "name": site.name,
            "lat_deg": site.lat_deg,
            "lon_deg_east": site.lon_deg_east,
            "dem_covered": site.dem_coverage is True,
            "custom": site.custom and site.id.startswith(s0.CUSTOM_PREFIX),
            "earth_az_deg": _r(geo.earth_az_deg[0], 3),
            "earth_el_deg": _r(geo.earth_el_deg[0], 3),
            "earth_el_geocentric_deg": _r(geo.earth_el_geocentric_deg[0], 3),
            "parallax_deg": _r(geo.parallax_deg[0], 3),
            "earth_range_km": _r(rng, 1),
            "fspl_delta_db": _r(20.0 * math.log10(rng / REFERENCE_RANGE_KM), 3),
        }
        if site.dem_coverage is not True:
            e.update(state="out_of_coverage", margin_db=None, ridge_el_deg=None)
            entries.append(e)
            continue
        if site.custom and cached is not None and not cached(site):
            e.update(state="needs_download", margin_db=None, ridge_el_deg=None)
            entries.append(e)
            continue
        try:
            kw = terrain_kw_for(site) if site.custom and terrain_kw_for is not None else {}
            terr = terrain(site, geo, tp, **kw)
            rf = rf_link(geo, terr, rf_inputs, grid.step_min)
        except (DemUnavailable, DemOutOfCoverage):
            # a catalogue site whose horizon is not computed yet is unknown (open it once, or install the catalogue terrain)
            pending = site.custom and not site.id.startswith(s0.CUSTOM_PREFIX)
            e.update(
                state="unknown" if pending else "unavailable", margin_db=None, ridge_el_deg=None
            )
            entries.append(e)
            continue
        state, label = _state(rf, terr)
        ob = terr.rf_obstacle[0]
        m = rf.margin_db[0]
        e.update(
            state=state,
            state_label=label,
            rf_reason=rf.reason[0].value,
            terrain_reason=terr.terrain_reason[0].value,
            terrain_resolution_m=(
                terr.mask_meta["products"][0]["scale_m"]
                if terr.mask_meta and terr.mask_meta.get("products")
                else None
            ),
            far_terrain_loss_db=None
            if terr.far_terrain_loss_db[0] is None
            else _r(terr.far_terrain_loss_db[0], 2),
            margin_db=None if m is None else _r(m, 2),
            geometric_visible=rf.geometric_visible[0],
            ridge_el_deg=None
            if ob is None
            else _r(float(e["earth_el_deg"]) + ob.angle_above_los_deg, 3),
            ridge_angle_above_los_deg=None if ob is None else ob.angle_above_los_deg,
        )
        entries.append(e)
    thr = reg.value("lunar.ground_station_min_elevation_deg")
    complexes: list[dict[str, Any]] = []
    for st in DSN_STATIONS:
        mo = engine.topocentric_azel(
            "earth", st.lat_deg, st.lon_deg_east, "moon", [grid.instants[0]], h_m=st.height_m
        )
        complexes.append(
            {
                "complex": st.complex,
                "lat_deg": st.lat_deg,
                "lon_deg_east": st.lon_deg_east,
                "height_m": st.height_m,
                "moon_az_deg": _r(mo.az_deg[0], 3),
                "moon_el_deg": _r(mo.el_deg[0], 3),
                "sees_moon": bool(mo.el_deg[0] >= thr),
                "antenna_34m_coordinates_verified": st.verified,
                "antenna_18m": "no verified station list: visibility unknown",
                "gain_tag_34m": ant.STATIONS["dsn34"].gain_tag,
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
                        "name": "18 m station (assumption)",
                        "diameter_m": 18.0,
                        "coordinates_verified": False,
                        "gain_tag": ant.STATIONS["dsn18"].gain_tag,
                        "note": "no source: assumption of the research script; coordinates of the complex",
                    },
                ],
            }
        )
    best = max(complexes, key=lambda c: c["moon_el_deg"])
    # true Earth-Moon centre range at this instant (S1 geometry) and its FSPL delta vs the reference range
    centre_km = float(engine.distance_km("moon", "earth", [grid.instants[0]])[0])
    return {
        "label": "potential under stated assumptions",
        "t_utc": grid.instants[0].strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rate_bps": rf_inputs.rate_bps,
        "station": rf_inputs.station,
        "reference_range_km": REFERENCE_RANGE_KM,
        "earth_moon_range_km": _r(centre_km, 1),
        "fspl_delta_db": _r(20.0 * math.log10(centre_km / REFERENCE_RANGE_KM), 3),
        "sites": entries,
        "dsn": {
            "min_elevation_deg": thr,
            "min_elevation_source": "DSN 810-005 Module 301 Rev. P sec. 2.2.2-2.2.3 (registry lunar.ground_station_min_elevation_deg)",
            "source": DSN_SOURCE,
            "complexes": complexes,
            "best_complex": best["complex"] if best["sees_moon"] else None,
            "sees_moon": [c["complex"] for c in complexes if c["sees_moon"]],
        },
        "state_rule": "open: margin >= 0 and the Earth centre clears the ridge; transition: margin >= 0 but "
        "the ridge blocks the line of sight; blocked: margin < 0, or far terrain closes the link (known); "
        "unknown: an input is missing or the far terrain is outside the model",
        "limits": list(LIMITS),
    }


def scene(
    t: datetime,
    site: s0.SiteRecord,
    rf_inputs: LinkInputs,
    engine: Any,
    dem: LolaDem,
    cache: ProfileCache,
    *,
    terrain_kw: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The legacy 3D scene (same numbers for the same inputs) plus the model block of the chain.
    `terrain_kw`: the per-site terrain hooks of a custom site (its own product)."""
    from backend.domain.grazing.scene import scene as legacy_scene

    out = legacy_scene(
        t=t.astimezone(UTC),
        site=(site.lat_deg, site.lon_deg_east),
        site_id=site.id,
        inputs=rf_inputs,
        engine=engine,
        dem=dem,
        cache=cache,
    )
    grid = _one(t)
    geo = geometry(engine, site, grid)
    terr = terrain(site, geo, terrain_params(rf_inputs), cache=cache, **(terrain_kw or {}))
    rf = rf_link(geo, terr, rf_inputs, grid.step_min)
    state, label = _state(rf, terr)
    out["model"] = {
        "state": state,
        "state_label": label,
        "margin_db": rf.margin_db[0],
        "rf_reason": rf.reason[0].value,
        "terrain_reason": terr.terrain_reason[0].value,
        "far_terrain_hides_earth": terr.far_terrain_hides_earth[0],
        "far_terrain_loss_db": terr.far_terrain_loss_db[0],
        "earth_horizon_deg": terr.earth_horizon_deg[0],
        "heights": {
            "panel_height_m": terr.params.panel_height_m,
            "antenna_height_m": terr.params.antenna_height_m,
        },
    }
    if rf.margin_db[0] is None:
        out["link"].update(margin_db=None, state=state, state_label=label)
        out["link"]["state_label"] = label or "far terrain closes the link (known)"
        for key in (
            "correction_db",
            "correction_uncertainty_db",
            "diffraction_loss_db",
            "total_loss_db",
        ):
            out["diffraction"][key] = None
        out["diffraction"].update(
            correction_status="outside_model",
            multipath_applicable=False,
            multipath_gain_db=None,
            multipath_status="non applicabile",
            multipath_reason=f"RF result unavailable: {rf.reason[0].value}",
        )
    return out


def horizon(
    site: s0.SiteRecord, height_m: float, *, terrain_kw: dict[str, Any] | None = None
) -> dict[str, Any]:
    """The horizon mask of a site at an eye height: elevation and distance per azimuth bin.

    `terrain_kw` (custom sites): the `mask_for` of the site's own product; the mask metadata then
    names the product and its resolution."""
    base: dict[str, Any] = {
        "site": site.to_dict(),
        "height_m": height_m,
        "limit": "terrain beyond the horizon range (meta.far_range_m) not modelled; missing tiles are "
        "unknown, never a clear horizon",
    }
    try:
        if terrain_kw is not None:
            mask = terrain_kw["mask_for"](site.lat_deg, site.lon_deg_east, height_m)
        else:
            mask = default_store().get(site.lat_deg, site.lon_deg_east, height_m)
    except DemOutOfCoverage:
        return {**base, "state": Reason.OUTSIDE_COVERAGE.value, "mask": None}
    except DemUnavailable:
        return {**base, "state": Reason.MISSING_DEM.value, "mask": None}

    def fin(v: float) -> float | None:
        return float(v) if math.isfinite(float(v)) else None

    return {
        **base,
        "state": "ok",
        "meta": mask.metadata(),
        "azimuth_step_deg": 360.0 / mask.config.n_azimuths,
        "elevation_deg": [fin(v) for v in mask.elevation_deg],
        "distance_m": [fin(v) for v in mask.distance_m],
        "complete": [bool(v) for v in mask.complete],
    }
