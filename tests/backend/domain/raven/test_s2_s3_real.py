# SPDX-License-Identifier: Apache-2.0
"""S0-S3 on the real engine and the cached LOLA tiles (RAVEN M4).

They skip without kernels or tiles. Checks: the stages reproduce the frozen outputs of the legacy
engines (golden), and S2 agrees with the independent arbiter at the EARTH azimuth too.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from backend.domain.raven import s0_context as s0
from backend.domain.raven import s1_geometry as s1
from backend.domain.raven import s2_terrain as s2
from backend.domain.raven import s3_illumination as s3
from backend.domain.raven.known import Reason
from scripts import raven_golden as rg

pytestmark = pytest.mark.skipif(
    not (rg.have_kernels() and rg.have_tiles()), reason="kernels or LOLA tiles missing"
)
GOLDEN: dict[str, Any] = json.loads(
    (Path(__file__).parents[1] / "golden" / "real.json").read_text(encoding="utf-8")
)["outputs"]


def _engine() -> Any:
    from backend.ephemeris.engine import get_engine

    return get_engine()


def _chain(site_id: str, start: str, days: float, step: float) -> tuple[Any, ...]:
    t0 = datetime.fromisoformat(start).astimezone(UTC)
    grid = s0.build_grid(s0.TimeWindow(t0, days, step))
    site = s0.resolve_site(site_id)
    geo = s1.geometry(_engine(), site, grid)
    terr = s2.terrain(site, geo)
    return grid, geo, terr, s3.illumination(geo, terr)


def test_s2_rf_obstacle_equals_the_grazing_analysis_golden() -> None:
    g = GOLDEN["grazing_analyze_shackleton"]["response"]["series"]
    _grid, geo, terr, _ = _chain("shackleton", "2027-04-07T00:00:00Z", 2, 60)
    nu = [o.nu if o else None for o in terr.rf_obstacle]
    assert len(nu) == len(g["nu"]) == 48
    # registry wavelength is rounded (0.035690 m vs c/8.4 GHz): nu differs by ~8e-6 relative
    np.testing.assert_allclose(nu, g["nu"], rtol=2e-5)
    np.testing.assert_allclose(geo.earth_el_deg, g["earth_el_deg"], atol=1e-3)
    ang = [o.angle_above_los_deg for o in terr.rf_obstacle if o]
    np.testing.assert_allclose(ang, g["ridge_angle_above_los_deg"], atol=1e-3)


@pytest.mark.parametrize("idx,site_id", [(0, "malapert-massif"), (1, "haworth")])
def test_s2_s3_equal_the_solar_terrain_golden(idx: int, site_id: str) -> None:
    ref = GOLDEN["lunar_solar_terrain"]["response"]["sites"][idx]
    assert ref["site_id"] == site_id
    _grid, _geo, terr, ill = _chain(site_id, "2027-01-01T00:00:00Z", 2, 60)
    assert terr.mask_state is Reason.OK
    # horizon at the Sun azimuth: same mask lookup; golden None = disc incomplete (never here)
    got = [h for h in terr.sun_horizon_deg]
    want = ref["horizon_deg"]
    assert all(w is not None for w in want) and len(got) == len(want)
    np.testing.assert_allclose(got, want, rtol=0, atol=1e-9)
    np.testing.assert_allclose(
        [f for f in ill.disc_fraction if f is not None], ref["disc_fraction"], atol=1e-9
    )
    assert ill.centre_visible == ref["centre_visible"]
    assert ill.upper_limb_visible == ref["upper_limb_visible"]
    assert ill.lower_limb_visible == ref["lower_limb_visible"]
    assert ill.lit == [f > 0.0 for f in ref["disc_fraction"]]
    assert terr.mask_meta is not None and terr.mask_meta["near_product"]


def test_s0_to_s3_is_deterministic_on_real_data() -> None:
    a = _chain("haworth", "2027-01-01T00:00:00Z", 1, 60)
    b = _chain("haworth", "2027-01-01T00:00:00Z", 1, 60)
    assert a[3] == b[3] and a[2].terrain_reason == b[2].terrain_reason
    assert [o and o.nu for o in a[2].rf_obstacle] == [o and o.nu for o in b[2].rf_obstacle]


def test_arbiter_and_s2_agree_at_the_earth_azimuth() -> None:
    """Design M4 acceptance: the independent mask implementation reads the same horizon towards
    the Earth as S2 (the Sun azimuth was already checked in validation.md)."""
    from scripts import solar_horizon_arbiter as arb

    site = s0.resolve_site("shackleton")
    _grid, geo, terr, _ = _chain("shackleton", "2027-04-07T00:00:00Z", 2, 60)
    cfg = arb.MaskConfig(n_azimuths=1440)
    m = arb.site_mask(site.lat_deg, site.lon_deg_east, terr.params.antenna_height_m, cfg)
    want = arb.mask_at(
        np.asarray(m["azimuth_deg"]), np.asarray(m["elevation_deg"]), geo.earth_az_deg
    )
    got = np.array([np.nan if h is None else h for h in terr.earth_horizon_deg])
    assert np.isfinite(got).all()
    diff = np.abs(got - want)
    # validation.md: horizon at the Sun azimuth agrees to 0.007-0.053 deg; the same tolerance here
    assert float(diff.max()) < 0.06, float(diff.max())


@pytest.mark.parametrize("site_id", ["malapert-massif", "nobile-rim"])
def test_current_solar_disc_against_refined_independent_integration(site_id: str) -> None:
    """Real cached terrain, same mask: isolate area integration from DEM/azimuth uncertainty."""
    from backend.domain.grazing.horizon import default_store, disc_criteria
    from scripts import solar_horizon_arbiter as arb

    site = s0.resolve_site(site_id)
    grid = s0.build_grid(s0.TimeWindow(datetime(2027, 1, 1, tzinfo=UTC), 365, 360))
    geo = s1.geometry(_engine(), site, grid)
    mask = default_store().get(site.lat_deg, site.lon_deg_east, 2.0)
    assert mask.complete.all()
    current = disc_criteria(mask, geo.sun_az_deg, geo.sun_el_deg, geo.sun_semidiameter_deg)
    refs = []
    for cols in (1024, 2048):
        parts = []
        for start in range(0, grid.n_steps, 128):
            ix = slice(start, start + 128)
            parts.append(
                arb.disc_fraction(
                    geo.sun_el_deg[ix],
                    geo.sun_az_deg[ix],
                    geo.sun_semidiameter_deg[ix],
                    mask.azimuth_deg,
                    mask.elevation_deg,
                    cols=cols,
                )
            )
        refs.append(np.concatenate(parts))
    np.testing.assert_allclose(refs[0], refs[1], atol=1e-5, rtol=0)
    np.testing.assert_allclose(current["disc_fraction"], refs[1], atol=2e-5, rtol=0)
    assert np.array_equal(np.asarray(current["disc_fraction"]) > 0, refs[1] > 0)
