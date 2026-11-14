# SPDX-License-Identifier: Apache-2.0
"""S2 terrain and S3 illumination (RAVEN M4): synthetic cases with analytic answers (marked as
synthetic: never a prediction), unknown propagation, determinism and bounds."""

import math
from typing import Any

import numpy as np
import pytest

from backend.domain.grazing.dem import DemOutOfCoverage, DemUnavailable
from backend.domain.grazing.horizon import HorizonMask, MaskConfig, disc_criteria
from backend.domain.grazing.terrain import (
    TerrainProfile,
    dominant_ridge,
    synthetic_ridge_profile,
)
from backend.domain.raven import params as reg
from backend.domain.raven import s0_context as s0
from backend.domain.raven import s2_terrain as s2
from backend.domain.raven import s3_illumination as s3
from backend.domain.raven.known import Reason
from backend.domain.raven.s1_geometry import Geometry

SITE = s0.custom_site(
    "synthetic-site", -89.0, 10.0
)  # synthetic: marked by the id and never verified
N = 4


def _mask(
    elev: float | np.ndarray = 1.0,
    dist: float = 50_000.0,
    complete: bool | np.ndarray = True,
    height: float = 2.0,
) -> HorizonMask:
    cfg = MaskConfig()
    n = cfg.n_azimuths
    return HorizonMask(
        lat_deg=SITE.lat_deg,
        lon_deg_east=SITE.lon_deg_east,
        observer_height_m=height,
        site_height_m=0.0,
        elevation_deg=np.broadcast_to(np.asarray(elev, dtype=np.float64), (n,)).copy(),
        distance_m=np.full(n, dist),
        complete=np.broadcast_to(np.asarray(complete, dtype=bool), (n,)).copy(),
        unknown_fraction=0.0,
        config=cfg,
    )


def _geo(
    earth_el: float = 3.0, sun_el: float = 10.0, sun_semi: float = 0.2665, n: int = N
) -> Geometry:
    f = np.float64
    z = np.zeros(n, dtype=f)
    return Geometry(
        sun_az_deg=np.linspace(0.0, 90.0, n),
        sun_el_deg=np.full(n, sun_el, dtype=f),
        sun_range_km=np.full(n, 1.496e8),
        sun_semidiameter_deg=np.full(n, sun_semi, dtype=f),
        earth_az_deg=np.full(n, 180.0, dtype=f),
        earth_el_deg=np.full(n, earth_el, dtype=f),
        earth_range_km=np.full(n, 384_400.0),
        earth_semidiameter_deg=np.full(n, 0.95, dtype=f),
        earth_el_geocentric_deg=z,
        parallax_deg=z,
        sub_earth_lat_deg=z,
        sub_earth_lon_deg_east=z,
        dsn_complexes=("a", "b", "c"),
        dsn_moon_el_deg=np.zeros((3, n), dtype=f),
    )


def _ridge() -> TerrainProfile:
    return synthetic_ridge_profile(2000.0, 40.0)  # 40 m crest, R = 100 m, at 2 km (synthetic)


def _run(geo: Geometry, mask: HorizonMask | None, **kw: Any) -> s2.Terrain:
    def mask_for(lat: float, lon: float, h: float) -> HorizonMask:
        if mask is None:
            raise DemUnavailable("no tiles")
        return mask

    return s2.terrain(SITE, geo, s2.TerrainParams.from_registry(), mask_for=mask_for, **kw)


# --------------------------------------------------------------------------- S2
def test_horizon_is_read_towards_sun_and_earth() -> None:
    t = _run(_geo(), _mask(1.25), profile_for=lambda az: _ridge())
    assert t.mask_state is Reason.OK and t.mask_meta is not None
    assert all(h == pytest.approx(1.25) for h in t.sun_horizon_deg)
    assert all(h == pytest.approx(1.25) for h in t.earth_horizon_deg)
    assert t.params.panel_height_m == 2.0 and t.params.antenna_height_m == 2.0


def test_far_terrain_above_the_earth_is_outside_model() -> None:
    far = _run(_geo(earth_el=0.5), _mask(1.0, dist=50_000.0), profile_for=lambda az: _ridge())
    assert all(v is True for v in far.far_terrain_hides_earth)
    assert all(r in (Reason.OUTSIDE_MODEL, Reason.BLOCKED_FAR_TERRAIN) for r in far.terrain_reason)


def test_far_terrain_far_above_the_earth_is_a_known_block() -> None:
    """D4 ruling: single knife-edge loss >= 30 dB (registry, tag I) = KNOWN blocked_far_terrain."""
    t = _run(_geo(earth_el=0.5), _mask(10.0, dist=40_000.0), profile_for=lambda az: _ridge())
    assert all(v is True for v in t.far_terrain_hides_earth)
    assert all(r is Reason.BLOCKED_FAR_TERRAIN for r in t.terrain_reason)
    assert all(x is not None and x >= 30.0 for x in t.far_terrain_loss_db)
    # a slight exceedance stays unknown (outside the single-obstacle model) with a loss below 30 dB
    mid = _run(_geo(earth_el=0.5), _mask(1.0, dist=40_000.0), profile_for=lambda az: _ridge())
    assert all(r is Reason.OUTSIDE_MODEL for r in mid.terrain_reason)
    assert all(x is not None and x < 30.0 for x in mid.far_terrain_loss_db)
    # nothing above the Earth: no loss, no change
    clear = _run(_geo(earth_el=3.0), _mask(1.0, dist=40_000.0), profile_for=lambda az: _ridge())
    assert all(x is None for x in clear.far_terrain_loss_db)
    assert reg.value("common.far_terrain_blocked_loss_db") == 30.0
    assert reg.get("common.far_terrain_blocked_loss_db").tag == "I"


def test_far_loss_matches_the_knife_edge_formula() -> None:
    import math as m

    from backend.domain.grazing.diffraction import knife_edge_loss_db

    geo = _geo(earth_el=0.5)
    t = _run(geo, _mask(3.0, dist=40_000.0), profile_for=lambda az: _ridge())
    theta = m.radians(3.0 - (0.5 + 0.95))
    d1, d2 = 40_000.0, 384_400_000.0 - 40_000.0
    nu = theta * m.sqrt(2 * d1 * d2 / (t.params.wavelength_m * (d1 + d2)))
    assert t.far_terrain_loss_db[0] == pytest.approx(float(knife_edge_loss_db(nu)), rel=1e-9)


def test_near_terrain_is_left_to_the_rf_profile() -> None:
    near = _run(_geo(earth_el=0.5), _mask(1.0, dist=5_000.0), profile_for=lambda az: _ridge())
    assert all(v is False for v in near.far_terrain_hides_earth)
    assert all(r is Reason.OK for r in near.terrain_reason)


def test_earth_above_far_terrain_is_clear() -> None:
    t = _run(_geo(earth_el=3.0), _mask(1.0, dist=50_000.0), profile_for=lambda az: _ridge())
    assert all(v is False for v in t.far_terrain_hides_earth)
    assert all(r is Reason.OK for r in t.terrain_reason)


def test_rf_obstacle_is_the_dominant_ridge_with_explicit_heights() -> None:
    prof = _ridge()
    geo = _geo(earth_el=0.0)
    t = _run(geo, _mask(-5.0), profile_for=lambda az: prof)
    ref = dominant_ridge(prof, 0.0, t.params.wavelength_m, earth_range_m=384_400_000.0)
    ob = t.rf_obstacle[0]
    assert ob is not None and ob.nu == ref.nu and ob.ridge_distance_m == pytest.approx(2000.0)
    # a higher antenna lowers the Fresnel-Kirchhoff parameter: the height is a real input
    high = s2.terrain(
        SITE,
        geo,
        s2.TerrainParams.from_registry(antenna_height_m=10.0),
        mask_for=lambda lat, lon, h: _mask(-5.0, height=h),
        profile_for=lambda az: prof,
    )
    assert high.rf_obstacle[0] is not None and high.rf_obstacle[0].nu < ob.nu
    assert high.params.antenna_height_m == 10.0 and high.params.panel_height_m == 2.0


def test_missing_tiles_are_unknown_never_clear_sky() -> None:
    t = _run(_geo(), None)  # DemUnavailable from the mask
    assert t.mask is None and t.mask_state is Reason.MISSING_DEM
    assert all(h is None for h in t.sun_horizon_deg + t.earth_horizon_deg)
    assert all(v is None for v in t.far_terrain_hides_earth)
    # without an injected profile the default reader is used: the site is outside the DEM
    t2 = s2.terrain(
        s0.custom_site("flat", 0.0, 0.0),
        _geo(),
        mask_for=lambda *a: (_ for _ in ()).throw(DemOutOfCoverage("x")),
    )
    assert t2.mask_state is Reason.OUTSIDE_COVERAGE
    assert all(r is Reason.OUTSIDE_COVERAGE for r in t2.terrain_reason)
    assert all(o is None for o in t2.rf_obstacle)


def test_incomplete_azimuth_known_lower_bound_still_hides() -> None:
    # unknown samples at the Earth azimuth: a clear lower bound is NOT a clear sky ...
    unk = _run(_geo(earth_el=3.0), _mask(1.0, complete=False), profile_for=lambda az: _ridge())
    assert all(v is None for v in unk.far_terrain_hides_earth)
    assert all(h is None for h in unk.earth_horizon_deg)
    # ... but a lower bound already above the Earth is a known "hidden"
    hid = _run(_geo(earth_el=0.5), _mask(1.0, complete=False), profile_for=lambda az: _ridge())
    assert all(v is True for v in hid.far_terrain_hides_earth)


def test_injected_profile_without_mask_stays_ok_but_far_terrain_unknown() -> None:
    t = _run(_geo(), None, profile_for=lambda az: _ridge())
    assert all(
        r is Reason.OK for r in t.terrain_reason
    )  # the user/synthetic profile is the terrain
    assert all(v is None for v in t.far_terrain_hides_earth)


def test_s2_is_deterministic() -> None:
    a = _run(_geo(), _mask(0.7), profile_for=lambda az: _ridge())
    b = _run(_geo(), _mask(0.7), profile_for=lambda az: _ridge())
    assert a.sun_horizon_deg == b.sun_horizon_deg and a.terrain_reason == b.terrain_reason
    assert [o and o.nu for o in a.rf_obstacle] == [o and o.nu for o in b.rf_obstacle]


def test_synthetic_profile_helper_is_marked() -> None:
    p = synthetic_ridge_profile(2000.0, 40.0)
    assert p.synthetic is True and p.source == "synthetic"


# --------------------------------------------------------------------------- S3
def test_flat_mask_gives_analytic_disc_fraction() -> None:
    geo = _geo(sun_el=10.0)
    ill = s3.illumination(geo, _run(geo, _mask(-2.0), profile_for=lambda az: _ridge()))
    assert all(f == pytest.approx(1.0) for f in ill.disc_fraction)  # whole disc above the mask
    assert all(v is True for v in ill.lit + ill.centre_visible + ill.upper_limb_visible)
    # centre exactly on the mask: half of the disc (symmetric chord)
    geo2 = _geo(sun_el=1.0, sun_semi=0.27)
    half = s3.illumination(geo2, _run(geo2, _mask(1.0), profile_for=lambda az: _ridge()))
    assert all(f == pytest.approx(0.5, abs=1e-9) for f in half.disc_fraction)
    assert all(v is True for v in half.lit) and all(v is True for v in half.upper_limb_visible)
    assert all(v is True for v in half.centre_visible)  # el + 0 >= horizon
    assert all(v is False for v in half.lower_limb_visible)
    # fully below: known zero, not lit, still known
    geo3 = _geo(sun_el=-5.0)
    dark = s3.illumination(geo3, _run(geo3, _mask(1.0), profile_for=lambda az: _ridge()))
    assert all(f == 0.0 for f in dark.disc_fraction) and all(v is False for v in dark.lit)


def test_segment_area_matches_the_circular_segment_formula() -> None:
    """Disc centre at height c below the mask by dh: visible fraction = circular segment."""
    r, dh = 0.27, 0.1
    geo = _geo(sun_el=1.0 - dh, sun_semi=r)
    ill = s3.illumination(geo, _run(geo, _mask(1.0), profile_for=lambda az: _ridge()))
    # segment of height (r - dh) from the top of a circle of radius r
    h = r - dh
    seg = r * r * math.acos((r - h) / r) - (r - h) * math.sqrt(2 * r * h - h * h)
    assert ill.disc_fraction[0] == pytest.approx(seg / (math.pi * r * r), abs=2e-3)


def test_lit_rule_is_disc_fraction_positive() -> None:
    geo = _geo(sun_el=1.2, sun_semi=0.27)  # lower limb below the mask, upper limb above
    ill = s3.illumination(geo, _run(geo, _mask(1.0), profile_for=lambda az: _ridge()))
    for f, lit in zip(ill.disc_fraction, ill.lit, strict=True):
        assert f is not None and (lit is (f > 0.0))


def test_s3_matches_disc_criteria_exactly() -> None:
    m = _mask(0.4)
    geo = _geo(sun_el=0.5)
    ill = s3.illumination(geo, _run(geo, m, profile_for=lambda az: _ridge()))
    c = disc_criteria(m, geo.sun_az_deg, geo.sun_el_deg, geo.sun_semidiameter_deg)
    assert ill.disc_fraction == c["disc_fraction"] and ill.centre_visible == c["centre"]


def test_s3_unknown_propagation() -> None:
    geo = _geo()
    ill = s3.illumination(geo, _run(geo, None, profile_for=lambda az: _ridge()))
    assert all(v is None for v in ill.lit + ill.disc_fraction + ill.centre_visible)
    assert all(r is Reason.MISSING_DEM for r in ill.reason)
    # incomplete azimuth: a "visible" answer becomes unknown, a known hidden stays known
    inc = _run(geo, _mask(-2.0, complete=False), profile_for=lambda az: _ridge())
    ill2 = s3.illumination(geo, inc)
    assert all(v is None for v in ill2.lit) and all(r is not Reason.OK for r in ill2.reason)
    deep = _geo(sun_el=-30.0)
    ill3 = s3.illumination(
        deep, _run(deep, _mask(10.0, complete=False), profile_for=lambda az: _ridge())
    )
    assert all(
        f == 0.0 and lit is False for f, lit in zip(ill3.disc_fraction, ill3.lit, strict=True)
    )


def test_s3_nan_geometry_is_unknown_upstream() -> None:
    geo = _geo()
    bad = Geometry(**{**geo.__dict__, "sun_el_deg": np.array([np.nan] * N)})
    ill = s3.illumination(bad, _run(bad, _mask(1.0), profile_for=lambda az: _ridge()))
    assert all(v is None for v in ill.lit)
    assert all(r is Reason.UPSTREAM_UNKNOWN for r in ill.reason)


def test_s3_bounds_and_determinism() -> None:
    elevs = np.linspace(-3.0, 3.0, 25)
    geo = Geometry(**{**_geo(n=25).__dict__, "sun_el_deg": elevs})
    t = _run(geo, _mask(0.0), profile_for=lambda az: _ridge())
    a, b = s3.illumination(geo, t), s3.illumination(geo, t)
    assert a == b
    fr = [f for f in a.disc_fraction if f is not None]
    assert len(fr) == 25 and all(0.0 <= f <= 1.0 for f in fr)
    assert fr == sorted(fr)  # the higher the Sun, the larger the visible fraction
