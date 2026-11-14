# SPDX-License-Identifier: Apache-2.0
"""Independent arbiter for the RAVEN Sun-terrain comparison (`/api/lunar/solar-terrain`).

Separate code path from `backend.domain.grazing.terrain` / `solar_terrain`: it shares only the
tile reader `LolaDem` (data access and integrity checks) and the ephemeris engine (Sun azimuth
and elevation, already compared with JPL Horizons). Everything else is re-implemented here:

* stereographic projection and bilinear interpolation on locally assembled numpy windows;
* rays built by rotating 3D unit vectors (not the lat/lon great-circle formula of `terrain.py`);
* elevation angles from 3D Cartesian differences on the 1737.4 km sphere (curvature included);
* a full azimuthal mask (default 3600 azimuths) with nested grids: LDEM_85S_20M up to
  `near_m`, LDEM_75S_240M from `near_m` to `far_m`;
* disc-aware Sun criteria: upper limb, centre, lower limb at the centre azimuth, and the visible
  fraction of the solar disc integrated column by column against the mask.

Not modelled: refraction (none on the Moon), limb darkening, terrain beyond `far_m`, DEM
uncertainty, sub-pixel relief. The stereographic orientation convention is taken from
`dem.lock.json`, so an error there would be common to both implementations; the comparison with
the observational LROC WAC map (see `docs/domain/validation.md`) is what tests it.

Usage: `.venv/bin/python -m scripts.solar_horizon_arbiter --help`.
"""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

Arr = NDArray[np.float64]
Sampler = Callable[[Arr, Arr], Arr]  # (lat_deg, lon_deg_east) -> height over sphere (m), NaN

MOON_R_M = 1_737_400.0
SUN_RADIUS_KM = 695_700.0  # IAU 2015 nominal solar radius
API_SEMIDIAMETER_DEG = 0.27  # fixed value used by the RAVEN API

# LDEM_75S_240M, values read from the PDS label on 2026-11-04 (label SHA-256 below). The whole
# image is never downloaded: only 128x128 tiles via `LolaDem`, each hashed on first use.
LDEM_240M: dict[str, Any] = {
    "id": "ldem_75s_240m_float",
    "url": "https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/polar/float_img/ldem_75s_240m_float.img",
    "label_url": "https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/polar/float_img/ldem_75s_240m_float.lbl",
    "size": 58_125_376,
    "etag": '"89f3b64badbd21:0"',
    "sha256": "82f40337cf42b3d478b255f22e6fce06d7273ff3bd4ac879b0f1ea4712dc280c",  # 2026-11-04
    "label_sha256": "8ad7ed746f0944762d249281db50667d4e1e9a0059eb836b4003909c1a5b336a",
    "lines": 3812,
    "samples": 3812,
    "scale_m": 240.0,
    "center_px": 1905.5,
    "radius_km": 1737.4,
    "min_km": -7.765,
    "max_km": 7.025,
    "max_lat_deg": 75.0,
    "retrieved": "2026-11-04",
    "credit": "LRO LOLA Gridded Data Record LDEM_75S_240M (NASA/GSFC), PDS Geosciences Node",
}


# --------------------------------------------------------------------------------------------
# geometry helpers
# --------------------------------------------------------------------------------------------
def unit_vector(lat_deg: Arr | float, lon_deg: Arr | float) -> Arr:
    la, lo = np.radians(lat_deg), np.radians(lon_deg)
    return np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)], axis=-1)


def local_basis(lat_deg: float, lon_deg: float) -> tuple[Arr, Arr, Arr]:
    """Up, East, North unit vectors at a point of the sphere."""
    la, lo = math.radians(lat_deg), math.radians(lon_deg)
    up = np.array([math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo), math.sin(la)])
    east = np.array([-math.sin(lo), math.cos(lo), 0.0])
    north = np.cross(up, east)
    return up, east, north


def horizon_mask(
    segments: Sequence[tuple[Sampler, Arr]],
    lat_deg: float,
    lon_deg: float,
    observer_height_m: float,
    azimuths_deg: Arr,
    *,
    radius_m: float = MOON_R_M,
    site_sampler: Sampler | None = None,
    chunk: int = 60,
) -> dict[str, Arr]:
    """Maximum terrain elevation angle (deg) seen from the site for each azimuth.

    `segments` = [(sampler, distances_m), ...]: each sampler is evaluated at the points of the
    great circles leaving the site at the listed ground distances. NaN heights are unknown and
    are counted in `unknown_fraction`; they are excluded from the maximum (never 'free sky' by
    construction: the caller must check `unknown_fraction`).
    """
    up, east, north = local_basis(lat_deg, lon_deg)
    base = site_sampler if site_sampler is not None else segments[0][0]
    z0 = float(base(np.array([lat_deg]), np.array([lon_deg]))[0])
    if not math.isfinite(z0):
        raise ValueError("site height unknown")
    obs = (radius_m + z0 + observer_height_m) * up
    az = np.radians(np.asarray(azimuths_deg, dtype=np.float64))
    best = np.full(az.size, -np.inf)
    best_d = np.full(az.size, np.nan)
    n_unknown = 0
    n_total = 0
    for k0 in range(0, az.size, chunk):
        a = az[k0 : k0 + chunk]
        t = np.cos(a)[:, None] * north[None, :] + np.sin(a)[:, None] * east[None, :]
        for sampler, dist in segments:
            ang = np.asarray(dist, dtype=np.float64) / radius_m
            p = (
                np.cos(ang)[None, :, None] * up[None, None, :]
                + np.sin(ang)[None, :, None] * t[:, None, :]
            )
            lat = np.degrees(np.arcsin(np.clip(p[..., 2], -1.0, 1.0)))
            lon = np.degrees(np.arctan2(p[..., 1], p[..., 0]))
            z = sampler(lat.ravel(), lon.ravel()).reshape(lat.shape)
            v = (radius_m + z)[..., None] * p - obs[None, None, :]
            el = np.degrees(np.arcsin(np.clip((v @ up) / np.linalg.norm(v, axis=-1), -1, 1)))
            n_unknown += int(np.count_nonzero(~np.isfinite(el)))
            n_total += el.size
            el = np.where(np.isfinite(el), el, -np.inf)
            i = np.argmax(el, axis=1)
            m = el[np.arange(el.shape[0]), i]
            better = m > best[k0 : k0 + a.size]
            best[k0 : k0 + a.size] = np.where(better, m, best[k0 : k0 + a.size])
            best_d[k0 : k0 + a.size] = np.where(better, dist[i], best_d[k0 : k0 + a.size])
    return {
        "azimuth_deg": np.asarray(azimuths_deg, dtype=np.float64),
        "elevation_deg": best,
        "distance_m": best_d,
        "unknown_fraction": np.array(n_unknown / max(n_total, 1)),
        "site_height_m": np.array(z0),
    }


def mask_at(mask_az: Arr, mask_el: Arr, az_deg: Arr) -> Arr:
    """Periodic linear interpolation of a mask sampled on a uniform azimuth grid from 0."""
    n = mask_az.size
    step = 360.0 / n
    x = np.mod(az_deg, 360.0) / step
    i0 = np.floor(x).astype(int) % n
    f = x - np.floor(x)
    return (1 - f) * mask_el[i0] + f * mask_el[(i0 + 1) % n]


def disc_fraction(
    sun_el: Arr, sun_az: Arr, radius_deg: Arr | float, mask_az: Arr, mask_el: Arr, cols: int = 64
) -> Arr:
    """Visible fraction of the solar disc: vertical strips, each compared with the mask.

    Each strip of the disc (offset x on the sky, half-chord c) is visible above the mask value
    at azimuth az + x / cos(el). Exact for a horizontal mask in the limit of many strips.
    """
    el = np.asarray(sun_el, dtype=np.float64)[:, None]
    az = np.asarray(sun_az, dtype=np.float64)[:, None]
    r = np.broadcast_to(np.asarray(radius_deg, dtype=np.float64), el.shape[:1])[:, None]
    u = ((np.arange(cols) + 0.5) / cols * 2.0 - 1.0)[None, :]
    x = u * r
    c = np.sqrt(np.maximum(r * r - x * x, 0.0))
    h = mask_at(mask_az, mask_el, az + x / np.cos(np.radians(el)))
    vis = np.clip(el + c - h, 0.0, 2.0 * c)
    out: Arr = vis.sum(axis=1) / (2.0 * c).sum(axis=1)
    return out


def segment_fraction(sun_el: Arr, radius_deg: Arr | float, horizon_deg: Arr) -> Arr:
    """Disc fraction above a horizontal line at `horizon_deg` (Barker et al. 2021 convention)."""
    d = np.clip((np.asarray(sun_el) - np.asarray(horizon_deg)) / radius_deg, -1.0, 1.0)
    # area of the part of the unit disc above the line y = -d, divided by pi
    out: Arr = (np.pi - np.arccos(d) + d * np.sqrt(1.0 - d * d)) / np.pi
    return out


def sun_criteria(
    sun_el: Arr, sun_az: Arr, radius_deg: Arr | float, mask_az: Arr, mask_el: Arr
) -> dict[str, Arr]:
    """Per-instant booleans and fractions for every illumination criterion used in the report."""
    h = mask_at(mask_az, mask_el, sun_az)
    r = np.asarray(radius_deg, dtype=np.float64)
    frac = disc_fraction(sun_el, sun_az, r, mask_az, mask_el)
    return {
        "horizon_at_centre_deg": h,
        "upper": sun_el + r >= h,
        "centre": sun_el >= h,
        "lower": sun_el - r >= h,
        "disc_fraction": frac,
        "any_part": frac > 0.0,
        "full_disc": frac >= 1.0 - 1e-9,
        "segment_fraction": segment_fraction(sun_el, r, h),
    }


# --------------------------------------------------------------------------------------------
# LOLA windows (real data)
# --------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Window:
    """Local window of a south polar stereographic DEM (heights in m over the sphere)."""

    heights_m: Arr
    row0: int
    col0: int
    scale_m: float
    center_px: float
    radius_m: float

    def sample(self, lat_deg: Arr, lon_deg: Arr) -> Arr:
        rho = 2.0 * self.radius_m * np.tan(np.radians(90.0 + np.asarray(lat_deg)) / 2.0)
        lon = np.radians(lon_deg)
        col = self.center_px + rho * np.sin(lon) / self.scale_m - self.col0
        row = self.center_px - rho * np.cos(lon) / self.scale_m - self.row0
        nr, nc = self.heights_m.shape
        ok = (row >= 0) & (row <= nr - 1) & (col >= 0) & (col <= nc - 1)
        r = np.clip(row, 0, nr - 1.000001)
        c = np.clip(col, 0, nc - 1.000001)
        r0, c0 = np.floor(r).astype(int), np.floor(c).astype(int)
        fr, fc = r - r0, c - c0
        hm = self.heights_m
        z = (
            (1 - fr) * (1 - fc) * hm[r0, c0]
            + (1 - fr) * fc * hm[r0, c0 + 1]
            + fr * (1 - fc) * hm[r0 + 1, c0]
            + fr * fc * hm[r0 + 1, c0 + 1]
        )
        out: Arr = np.where(ok, z, np.nan)
        return out


def load_window(dem: Any, lat_deg: float, lon_deg: float, half_m: float) -> Window:
    """Assemble the tiles of `dem` (a `LolaDem`) covering a square of half side `half_m`."""
    from backend.domain.grazing.dem import TILE, DemUnavailable

    s = dem.spec
    rad = s.radius_km * 1000.0
    rho = 2.0 * rad * math.tan(math.radians(90.0 + lat_deg) / 2.0)
    col = s.center_px + rho * math.sin(math.radians(lon_deg)) / s.scale_m
    row = s.center_px - rho * math.cos(math.radians(lon_deg)) / s.scale_m
    h = half_m / s.scale_m + 2
    t_r0, t_r1 = int(max(0, row - h)) // TILE, int(min(s.lines - 1, row + h)) // TILE
    t_c0, t_c1 = int(max(0, col - h)) // TILE, int(min(s.samples - 1, col + h)) // TILE
    out = np.full(((t_r1 - t_r0 + 1) * TILE, (t_c1 - t_c0 + 1) * TILE), np.nan)
    for ti in range(t_r0, t_r1 + 1):
        for tj in range(t_c0, t_c1 + 1):
            try:
                tile = dem.tile(ti, tj).astype(np.float64) * 1000.0
            except DemUnavailable:
                continue  # stays NaN: unknown, never free horizon
            out[
                (ti - t_r0) * TILE : (ti - t_r0 + 1) * TILE,
                (tj - t_c0) * TILE : (tj - t_c0 + 1) * TILE,
            ] = tile
    # pixels beyond the product edge (zero padding of edge tiles) are unknown
    rr = np.arange(out.shape[0]) + t_r0 * TILE
    cc = np.arange(out.shape[1]) + t_c0 * TILE
    out[rr >= s.lines, :] = np.nan
    out[:, cc >= s.samples] = np.nan
    return Window(out, t_r0 * TILE, t_c0 * TILE, s.scale_m, s.center_px, rad)


def dem_240m(allow_download: bool = True) -> Any:
    from backend.domain.grazing.dem import DemSpec, LolaDem, load_lock

    base = load_lock()
    spec = DemSpec(**{**LDEM_240M, "orientation": base.orientation})  # type: ignore[arg-type]
    return LolaDem(spec=spec, allow_download=allow_download)


@dataclass(frozen=True)
class MaskConfig:
    near_m: float = 10_000.0
    far_m: float = 200_000.0
    near_step_m: float = 10.0
    far_step_m: float = 120.0
    n_azimuths: int = 3600


def site_mask(
    lat_deg: float,
    lon_deg: float,
    observer_height_m: float,
    cfg: MaskConfig,
    *,
    near_dem: Any = None,
    far_dem: Any = None,
) -> dict[str, Arr]:
    from backend.domain.grazing.dem import LolaDem

    near = load_window(near_dem or LolaDem(), lat_deg, lon_deg, cfg.near_m + 200)
    segments: list[tuple[Sampler, Arr]] = [
        (near.sample, np.arange(cfg.near_step_m, cfg.near_m + 1e-6, cfg.near_step_m))
    ]
    if cfg.far_m > cfg.near_m:
        far = load_window(far_dem or dem_240m(), lat_deg, lon_deg, cfg.far_m + 1000)
        segments.append(
            (far.sample, np.arange(cfg.near_m + cfg.far_step_m, cfg.far_m + 1e-6, cfg.far_step_m))
        )
    az = np.arange(cfg.n_azimuths) * (360.0 / cfg.n_azimuths)
    return horizon_mask(segments, lat_deg, lon_deg, observer_height_m, az, site_sampler=near.sample)


def sun_track(lat_deg: float, lon_deg: float, instants: list[datetime]) -> dict[str, Arr]:
    from backend.ephemeris.engine import Engine

    eng = Engine()
    out = {"az": [], "el": [], "r": []}  # type: dict[str, list[Any]]
    for k in range(0, len(instants), 20_000):
        part = instants[k : k + 20_000]
        s = eng.topocentric_azel("moon", lat_deg, lon_deg, "sun", part)
        out["az"].append(s.az_deg)
        out["el"].append(s.el_deg)
        out["r"].append(np.degrees(np.arcsin(SUN_RADIUS_KM / np.asarray(s.range_km))))
    return {k: np.concatenate(v) for k, v in out.items()}


def grid(start: datetime, end: datetime, step: timedelta) -> list[datetime]:
    n = int((end - start) / step)
    return [start + i * step for i in range(n)]


# --------------------------------------------------------------------------------------------
# CLI: comparison with the RAVEN API
# --------------------------------------------------------------------------------------------
API_FIELDS = ("state", "horizon_deg", "disc_fraction", "centre_visible", "lower_limb_visible")


def api_states(
    site_ids: list[str],
    start: datetime,
    days: float,
    step_min: int,
    observer_height_m: float | None = None,
) -> dict[str, Any]:
    """Call the historical test oracle in windows of <=240 steps, two sites per request.

    `observer_height_m` is sent only when given (the endpoint gained it on 2026-11-04); fields
    absent from older responses stay empty lists.
    """
    from fastapi.testclient import TestClient

    from scripts.raven_reference import build_reference_app

    client = TestClient(build_reference_app())
    window_days = 240 * step_min / 1440.0
    out: dict[str, dict[str, list[Any]]] = {s: {f: [] for f in API_FIELDS} for s in site_ids}
    times: list[int] = []
    t, end = start, start + timedelta(days=days)
    while t < end:
        d = min(window_days, (end - t).total_seconds() / 86400.0)
        first = True
        for k in range(0, len(site_ids), 2):
            req = {
                "site_ids": site_ids[k : k + 2],
                "start_utc": t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "days": d,
                "step_min": step_min,
            }
            if observer_height_m is not None:
                req["observer_height_m"] = observer_height_m
            r = client.post("/api/lunar/solar-terrain", json=req)
            if r.status_code != 200:
                raise RuntimeError(f"API {r.status_code}: {r.text[:200]}")
            body = r.json()
            if first:
                times.extend(body["series_time_unix"])
                first = False
            for row in body["sites"]:
                for f in API_FIELDS:
                    out[row["site_id"]][f].extend(row.get(f, []))
        t += timedelta(days=d)
    return {"time_unix": times, "sites": out}


DEFAULT_SITES = ["malapert-massif", "haworth", "nobile-rim", "de-gerlache", "shackleton"]


def _frac(x: Arr) -> float:
    return float(np.mean(x))


def compare_api(args: argparse.Namespace) -> dict[str, Any]:
    from backend.domain.lunar.model import load_sites

    catalog = {s.id: {"lat_deg": s.lat_deg, "lon_deg_east": s.lon_deg_east} for s in load_sites()}
    start = datetime.fromisoformat(args.start).replace(tzinfo=UTC)
    api = api_states(args.sites, start, args.days, args.step_min)
    instants = [datetime.fromtimestamp(t, UTC) for t in api["time_unix"]]
    step_min = args.step_min
    report: dict[str, Any] = {
        "window": {
            "start": args.start,
            "days": args.days,
            "step_min": step_min,
            "n": len(instants),
        },
        "sites": {},
    }
    full_cfg = MaskConfig(n_azimuths=args.n_azimuths)
    near_cfg = replace(full_cfg, far_m=full_cfg.near_m)
    for sid in args.sites:
        site = catalog[sid]
        lat, lon = site["lat_deg"], site["lon_deg_east"]
        sun = sun_track(lat, lon, instants)
        states = np.array(api["sites"][sid]["state"])
        known = np.isin(states, ["upper_above_profile", "upper_below_profile"])
        api_up = states == "upper_above_profile"
        api_h = np.array([np.nan if h is None else h for h in api["sites"][sid]["horizon_deg"]])
        row: dict[str, Any] = {"lat_deg": lat, "lon_deg_east": lon, "api_known": int(known.sum())}
        m10 = site_mask(lat, lon, 0.0, near_cfg)
        c10 = sun_criteria(
            sun["el"], sun["az"], API_SEMIDIAMETER_DEG, m10["azimuth_deg"], m10["elevation_deg"]
        )
        diff_h = c10["horizon_at_centre_deg"][known] - api_h[known]
        dis10 = known & (c10["upper"] != api_up)
        row["same_criterion_10km"] = {
            "api_upper_fraction": _frac(api_up[known]),
            "arbiter_upper_fraction": _frac(c10["upper"][known]),
            "disagreeing_steps": int(dis10.sum()),
            "disagreeing_minutes": int(dis10.sum()) * step_min,
            "horizon_diff_deg_max_abs": float(np.max(np.abs(diff_h))),
            "horizon_diff_deg_mean": float(np.mean(diff_h)),
            "unknown_fraction": float(m10["unknown_fraction"]),
        }
        # same geometry as the API (exact Sun azimuth, 20 m step, 10 km): isolates the code
        from backend.domain.grazing.dem import LolaDem

        win = load_window(LolaDem(), lat, lon, near_cfg.near_m + 200)
        exact = np.full(len(instants), np.nan)
        for k0 in range(0, len(instants), 240):
            sl = slice(k0, k0 + 240)
            e = horizon_mask(
                [(win.sample, np.arange(20.0, 10_000.0 + 1e-6, 20.0))],
                lat,
                lon,
                0.0,
                sun["az"][sl],
                site_sampler=win.sample,
            )
            exact[sl] = e["elevation_deg"]
        up_exact = sun["el"] + API_SEMIDIAMETER_DEG >= exact
        dx = exact[known] - api_h[known]
        row["same_geometry_exact"] = {
            "horizon_diff_deg_max_abs": float(np.max(np.abs(dx))),
            "disagreeing_steps": int((known & (up_exact != api_up)).sum()),
        }
        for h_obs in args.heights:
            m = site_mask(lat, lon, h_obs, full_cfg)
            c = sun_criteria(sun["el"], sun["az"], sun["r"], m["azimuth_deg"], m["elevation_deg"])
            entry = {
                k: _frac(c[k][known])
                for k in ("upper", "centre", "lower", "any_part", "full_disc", "disc_fraction")
            }
            entry["unknown_fraction"] = float(m["unknown_fraction"])
            entry["max_mask_deg"] = float(np.max(m["elevation_deg"]))
            if h_obs == 0.0:
                dis = known & (c["upper"] != api_up)
                entry["upper_vs_api_disagreeing_minutes"] = int(dis.sum()) * step_min
                entry["upper_vs_api_api_lit_arbiter_dark_minutes"] = (
                    int((dis & api_up).sum()) * step_min
                )
                far = m["distance_m"] > full_cfg.near_m
                entry["azimuth_fraction_far_terrain_dominant"] = _frac(far)
            row[f"full_mask_h{h_obs:g}m"] = entry
        report["sites"][sid] = row
        print(sid, json.dumps(row, indent=1), flush=True)
    return report


# --------------------------------------------------------------------------------------------
# CLI: comparison with published / observed illumination
# --------------------------------------------------------------------------------------------
LROC_TWI: dict[str, Any] = {
    "url": "https://pds.mcp.nasa.gov/data/store/img/lunar_reconnaissance_orbiter/pds4/lroc/lro-l-lroc-5-rdr/LROLRC_2001/DATA/BDR/WAC_POLE/WAC_POLE_ILL_TWI_SOUTH/WAC_POLE_ILL_TWI_SOUTH_100M.IMG",
    "sha256": "dfecc026012fe24f67ca70ed21a09a1723ca0750bf3ec120f1a4ed2c4604717b",
    "size": 5_904_896,
    "offset": 2 * 4856,  # LABEL_RECORDS = 2, RECORD_BYTES = 4856 (attached PDS3 label)
    "lines": 1214,
    "scale_m": 100.0,
    "center_px": 606.5,  # LINE/SAMPLE_PROJECTION_OFFSET; 1214 / 2 - 0.5 zero-based
    "period": ("2010-02-15T00:00:00", "2011-02-05T00:00:00"),
}

# Barker et al., Planetary and Space Science, doi:10.1016/j.pss.2020.105119 (NTRS 20205009660
# accepted manuscript), Table 2: Site 1 RoI centroids, stereographic X/Y (km),
# 1st percentile of the RoI-averaged average illumination over 100 clones (row A), 2024-2026.
BARKER_T2: dict[str, Any] = {
    "x_km": [11.5825, 11.4875, 11.3525, 11.2875, 11.1025, 10.8025, 10.2275],
    "y_km": [12.4625, 12.5575, 12.5025, 12.1675, 11.9425, 11.7375, 11.5525],
    "avg_ill_1pct_A_dz1": [68.03, 70.32, 67.51, 69.61, 70.38, 71.15, 67.36],
    "avg_ill_1pct_C_dz1": [85.84, 85.75, 77.31, 86.81, 84.47, 86.74, 83.44],
    "avg_ill_1pct_A_dz5": [89.26, 88.51, 84.53, 88.12, 85.71, 87.35, 82.79],
    "period": ("2024-01-01T00:00:00", "2026-01-01T00:00:00"),
}


def lroc_map(directory: Path) -> Arr:
    import hashlib
    import urllib.request

    p = directory / "WAC_POLE_ILL_TWI_SOUTH_100M.IMG"
    if not p.is_file():
        directory.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(LROC_TWI["url"], timeout=120) as r:
            p.write_bytes(r.read(LROC_TWI["size"] + 1))
    raw = p.read_bytes()
    if hashlib.sha256(raw).hexdigest() != LROC_TWI["sha256"]:
        raise RuntimeError("LROC map SHA-256 differs from the pinned value")
    n = LROC_TWI["lines"]
    a = np.frombuffer(raw, dtype="<f4", count=n * n, offset=LROC_TWI["offset"]).reshape(n, n)
    return np.where(a > -1e30, a.astype(np.float64), np.nan)


def xy_to_latlon(x_m: float, y_m: float) -> tuple[float, float]:
    """Inverse of the convention x = rho sin(lon), y = rho cos(lon) (dem.lock orientation)."""
    rho = math.hypot(x_m, y_m)
    return -90.0 + 2.0 * math.degrees(math.atan(rho / (2.0 * MOON_R_M))), math.degrees(
        math.atan2(x_m, y_m)
    )


def lroc_value(a: Arr, x_m: float, y_m: float) -> tuple[float, float]:
    c = LROC_TWI["center_px"]
    r, k = round(c - y_m / LROC_TWI["scale_m"]), round(c + x_m / LROC_TWI["scale_m"])
    return float(a[r, k]), float(np.nanmean(a[r - 1 : r + 2, k - 1 : k + 2]))


def point_stats(
    lat: float, lon: float, h_obs: float, cfg: MaskConfig, instants: list[datetime]
) -> dict[str, float]:
    m = site_mask(lat, lon, h_obs, cfg)
    sun = sun_track(lat, lon, instants)
    c = sun_criteria(sun["el"], sun["az"], sun["r"], m["azimuth_deg"], m["elevation_deg"])
    out = {k: 100.0 * _frac(c[k]) for k in ("upper", "centre", "lower", "any_part", "full_disc")}
    out["disc_fraction"] = 100.0 * _frac(c["disc_fraction"])
    out["segment_fraction"] = 100.0 * _frac(c["segment_fraction"])
    out["unknown_fraction"] = float(m["unknown_fraction"])
    out["site_height_m"] = float(m["site_height_m"])
    return out


def compare_references(args: argparse.Namespace) -> dict[str, Any]:
    cfg = MaskConfig(near_m=5_000.0, n_azimuths=720)
    a = lroc_map(args.lroc_dir)
    t0, t1 = (datetime.fromisoformat(s).replace(tzinfo=UTC) for s in LROC_TWI["period"])
    inst = grid(t0, t1, timedelta(hours=1))
    pts = []
    step = args.grid_km * 1000.0
    n = int(args.grid_radius_km * 1000.0 // step)
    for i in range(-n, n + 1):
        for j in range(-n, n + 1):
            x, y = i * step, j * step
            if math.hypot(x, y) <= args.grid_radius_km * 1000.0:
                pts.append(("grid", x, y))
    lroc_rows = []
    for name, x, y in pts:
        lat, lon = xy_to_latlon(x, y)
        v1, v3 = lroc_value(a, x, y)
        if not math.isfinite(v1):
            continue
        s = point_stats(lat, lon, 0.0, cfg, inst)
        # same point read with a 180-degree rotation: an orientation check of both products
        v_rot = lroc_value(a, -x, -y)[1]
        lroc_rows.append(
            {
                "name": name,
                "x_km": x / 1000,
                "y_km": y / 1000,
                "lat": lat,
                "lon": lon,
                "lroc_px": v1,
                "lroc_3x3": v3,
                "lroc_3x3_rot180": v_rot,
                **s,
            }
        )
        print(json.dumps(lroc_rows[-1]), flush=True)
    b0, b1 = (datetime.fromisoformat(s).replace(tzinfo=UTC) for s in BARKER_T2["period"])
    binst = grid(b0, b1, timedelta(hours=1))
    barker_rows = []
    for k, (xk, yk) in enumerate(zip(BARKER_T2["x_km"], BARKER_T2["y_km"], strict=True)):
        # Barker's X/Y axes are opposite to the dem.lock convention: only (-X, -Y) falls on a
        # ridge crest (+1.95 km in LDEM_75S_240M, lon -137.15); the other 3 sign choices fall
        # at -0.6 to -1.1 km. Inferred from topography, not stated in the paper.
        xk, yk = -xk, -yk
        lat, lon = xy_to_latlon(xk * 1000.0, yk * 1000.0)
        row: dict[str, Any] = {"roi": k + 1, "lat": lat, "lon": lon}
        for h in (1.0, 5.0):
            s = point_stats(lat, lon, h, cfg, binst)
            row[f"dz{h:g}"] = {
                "disc_fraction": s["disc_fraction"],
                "segment_fraction": s["segment_fraction"],
                "any_part": s["any_part"],
                "unknown": s["unknown_fraction"],
            }
        row["lroc_px"] = lroc_value(a, xk * 1000.0, yk * 1000.0)[0]
        barker_rows.append(row)
        print(json.dumps(row), flush=True)
    return {"lroc": lroc_rows, "barker": barker_rows, "config": cfg.__dict__}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--mode", choices=["api", "references"], default="api")
    p.add_argument("--lroc-dir", type=Path, default=Path("build/lroc"))
    p.add_argument("--grid-km", type=float, default=5.0)
    p.add_argument("--grid-radius-km", type=float, default=20.0)
    p.add_argument("--sites", nargs="+", default=DEFAULT_SITES)
    p.add_argument("--start", default="2027-01-01T00:00:00")
    p.add_argument("--days", type=float, default=365.0)
    p.add_argument("--step-min", type=int, default=120)
    p.add_argument("--n-azimuths", type=int, default=3600)
    p.add_argument("--heights", type=float, nargs="+", default=[0.0, 2.0, 10.0])
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args(argv)
    report = compare_api(args) if args.mode == "api" else compare_references(args)
    if args.out:
        args.out.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
