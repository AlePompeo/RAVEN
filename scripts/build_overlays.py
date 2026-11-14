# SPDX-License-Identifier: Apache-2.0
"""Build the shipped map overlays (height and regional slope of the south-polar disc) from the LOLA LDEM 75S 240 m product.

Needs every tile the disc touches: missing tiles are downloaded from the PDS (public NASA data, ~64 KB each, about 50 MB in all)
into the usual DEM cache. The result is two small JSON files under `backend/assets/overlays/` that the app serves without any
download. Usage: GRAZING_DEM_DIR=build/lola PYTHONPATH=. .venv/bin/python scripts/build_overlays.py
"""

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

from backend.domain.grazing.dem import FAR_DEM_ID, TILE, LolaDem, load_lock
from backend.domain.raven import overlays as ov
from backend.ephemeris.engine import Engine

OUT = Path(__file__).resolve().parents[1] / "backend" / "assets" / "overlays"
SIZE = ov.PRECOMPUTED_SIZE
LIMIT = ov.DEFAULT_LIMIT_LAT


def main() -> int:
    dem = LolaDem(spec=load_lock(dataset_id=FAR_DEM_ID), allow_download=True)
    lat, lon, inside = ov.disc(SIZE, LIMIT)
    rows, cols = dem.pixel_arrays(lat[inside], lon[inside])
    r = np.clip(rows, 0, dem.spec.lines - 1.000001)
    c = np.clip(cols, 0, dem.spec.samples - 1.000001)
    tiles = {
        (int(a) // TILE + da, int(b) // TILE + db)
        for a, b in zip(r.ravel(), c.ravel())
        for da in (0, 1)
        for db in (0, 1)
    }
    max_ti, max_tj = (dem.spec.lines - 1) // TILE, (dem.spec.samples - 1) // TILE
    tiles = {
        (a, b) for a, b in tiles if 0 <= a <= max_ti and 0 <= b <= max_tj
    }  # a neighbour past the product edge does not exist
    missing = [t for t in sorted(tiles) if not dem.has_tile(*t)]
    print(f"{len(tiles)} tiles needed, {len(missing)} to download", flush=True)
    for i, (ti, tj) in enumerate(missing):
        dem.tile(ti, tj)
        if i % 50 == 0:
            print(f"  {i}/{len(missing)}", flush=True)

    def sampler(la: np.ndarray, lo: np.ndarray) -> np.ndarray:
        rr, cc = dem.pixel_arrays(la, lo)
        return dem.heights_m_at_pixels(rr, cc)

    OUT.mkdir(parents=True, exist_ok=True)
    for layer in ("elevation", "slope"):
        o = ov.compute_overlay(layer, size=SIZE, limit_lat_deg=LIMIT, sampler=sampler)
        (OUT / f"{layer}.json").write_text(
            json.dumps(o, separators=(",", ":")) + "\n", encoding="utf-8"
        )
        print(
            layer,
            o["unit"],
            round(o["min"], 2),
            round(o["max"], 2),
            len(o["data_b64"]),
            "bytes b64",
            flush=True,
        )

    # regional illumination and Earth visibility: horizons from the height grid, Sun and Earth sub-points every 6 h over 2027
    h = np.full((SIZE, SIZE), np.nan)
    h[inside] = sampler(lat[inside], lon[inside])
    np.save(OUT / "polar-heights.npy", h.astype(np.float32))  # the height grid, for the horizons of the site search (window-specific Sun and Earth)
    print("horizons...", flush=True)
    horizons, trusted = ov.horizon_grid(h, LIMIT)
    start = datetime(2027, 1, 1, tzinfo=UTC)
    times = [start + timedelta(hours=6 * i) for i in range(365 * 4)]
    engine = Engine()
    sun = engine.subsolar_point("moon", times)
    earth = engine.sub_earth_point("moon", times)
    for layer, sp, what in (("sun", sun, "Sun"), ("earth", earth, "Earth")):
        print(f"{layer}...", flush=True)
        frac = ov.visibility_fraction(
            horizons, trusted, LIMIT, np.asarray(sp.lat_deg), np.asarray(sp.lon_deg_east)
        )
        o = ov.fraction_overlay(
            layer,
            frac,
            SIZE,
            LIMIT,
            f"derived: horizons marched over the LOLA LDEM 75S 240 m heights at {ov.HORIZON_CELLS} cells and {ov.HORIZON_AZIMUTHS} azimuths; "
            f"{what} direction from the JPL DE440 ephemerides every 6 h of 2027 (libration included)",
            f"Share of 2027 with the {what} above the regional horizon, at about 2.4 km per cell. The {what} is a point at infinity "
            "(Earth parallax of about 1 degree and the solar disc are neglected) and relief smaller than a cell is not resolved. "
            "Not validated against NASA illumination products. Cells within 72 km of the rim and cells with an unreadable height have no data.",
        )
        (OUT / f"{layer}.json").write_text(
            json.dumps(o, separators=(",", ":")) + "\n", encoding="utf-8"
        )
        valid = np.isfinite(frac)
        print(layer, f"{valid.sum()} cells, mean {np.nanmean(frac) * 100:.1f} %", flush=True)
    # joint availability (Sun and Earth together) and the longest gaps: same horizons, same instants
    from backend.domain.raven import overlays_global as og

    plat, plon, _inside = ov.disc(SIZE, LIMIT)
    m = og.joint_metrics(
        horizons,
        trusted,
        plat,
        plon,
        (np.asarray(sun.lat_deg), np.asarray(sun.lon_deg_east)),
        (np.asarray(earth.lat_deg), np.asarray(earth.lon_deg_east)),
        6.0,
    )
    src = (
        f"derived: horizons marched over the LOLA LDEM 75S 240 m heights at {ov.HORIZON_CELLS} cells and {ov.HORIZON_AZIMUTHS} azimuths; "
        "Sun and Earth directions from the JPL DE440 ephemerides every 6 h of 2027"
    )
    note = "At about 2.4 km per cell: relief smaller than a cell is not resolved. Not validated against NASA illumination products. Cells within 72 km of the rim have no data."
    for o in (
        og.both_overlay(m["both"], note, src),
        og.gap_overlay("sun_gap", m["sun_gap_h"], "Sun", src, note),
        og.gap_overlay("earth_gap", m["earth_gap_h"], "Earth", src, note),
    ):
        o.update({"scope": "polar", "size": SIZE, "limit_lat_deg": LIMIT})
        for k in ("projection", "width", "height"):
            o.pop(k, None)
        (OUT / f"{o['layer']}.json").write_text(
            json.dumps(o, separators=(",", ":")) + "\n", encoding="utf-8"
        )
        print(o["layer"], flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
