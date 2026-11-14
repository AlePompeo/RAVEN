# SPDX-License-Identifier: Apache-2.0
"""S0 site and time (RAVEN M4): catalogue with provenance, one grid, no decimation."""

import dataclasses
import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.domain.lunar import model as lm
from backend.domain.raven import s0_context as s0

T0 = datetime(2027, 1, 1, tzinfo=UTC)


def test_catalogue_keeps_provenance_and_matches_the_legacy_loader() -> None:
    cat = s0.load_catalog()
    legacy = {s.id: s for s in lm.load_sites()}
    assert set(cat) == set(legacy) and len(cat) == 51
    for sid, rec in cat.items():
        old = legacy[sid]
        assert (rec.lat_deg, rec.lon_deg_east, rec.name, rec.verified) == (
            old.lat_deg,
            old.lon_deg_east,
            old.name,
            old.verified,
        )
        assert rec.source_url and rec.source_accessed and rec.source_note, sid
        assert rec.coordinate_basis == old.coordinate_basis


def test_dem_coverage_follows_the_locked_product() -> None:
    cat = s0.load_catalog()
    assert cat["shackleton"].dem_coverage is True
    assert cat["mons-mouton"].dem_coverage is False  # -84.6 is north of the 85S product
    assert cat["apollo11"].dem_coverage is False


def test_unknown_site_and_bad_coordinates_are_errors_without_echo() -> None:
    with pytest.raises(s0.S0Error) as e:
        s0.resolve_site("nowhere-zz")
    assert "nowhere" not in str(e.value) and e.value.key == "site_id"
    for lat, lon in ((91.0, 0.0), (0.0, 181.0), (float("nan"), 0.0), (0.0, float("inf"))):
        with pytest.raises(s0.S0Error):
            s0.custom_site("x", lat, lon)


def test_custom_site_is_never_verified() -> None:
    r = s0.custom_site("mine", -88.0, 10.0)
    assert r.verified is False and r.kind == "user" and "not verified" in r.source_note
    assert r.dem_coverage is True


def test_catalogue_rejects_duplicates_and_missing_coordinates(tmp_path: Path) -> None:
    base = json.loads(s0.CATALOG_PATH.read_text(encoding="utf-8"))
    dup = {**base, "sites": [base["sites"][0], base["sites"][0]]}
    p = tmp_path / "dup.json"
    p.write_text(json.dumps(dup), encoding="utf-8")
    with pytest.raises(s0.S0Error):
        s0.load_catalog(p)
    bad = {**base, "sites": [{**base["sites"][0], "lat_deg": 123.0}]}
    p.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(s0.S0Error):
        s0.load_catalog(p)


def test_grid_is_exact_and_matches_the_legacy_window() -> None:
    # the legacy default (29.53 d at 10 min = 4252 steps) is over the D9 cap of 1500: the cap is explicit here
    wide = dataclasses.replace(s0.default_limits(), max_steps_per_site=20_000)
    g = s0.build_grid(s0.TimeWindow(T0, 29.53, 10.0), wide)
    old = lm.AnalysisWindow.build("2027-01-01T00:00:00Z", 29.53, 10.0)
    assert g.n_steps == old.n_steps == 4252  # floor(29.53 * 144)
    assert list(g.instants) == old.instants()
    assert g.t_unix[1] - g.t_unix[0] == 600.0 and len(g.t_unix) == g.n_steps
    assert g.instants[0] == T0 and g.instants[-1] == T0 + (g.n_steps - 1) * timedelta(minutes=10)


def test_step_count_formula_edges() -> None:
    assert s0.n_steps(1.0, 60.0) == 24
    assert s0.n_steps(0.01, 1440.0) == 1  # never zero
    assert s0.n_steps(30.0, 15.0) == 2880
    assert s0.n_steps(0.3, 1.0) == 432  # 0.3 * 1440 = 431.99999999999994 without the 1e-9


def test_legacy_default_window_is_over_the_d9_cap() -> None:
    with pytest.raises(s0.StepCapExceeded):
        s0.build_grid(s0.TimeWindow(T0, 29.53, 10.0))


def test_cap_is_an_error_not_a_decimation() -> None:
    lim = s0.default_limits()
    assert (lim.max_steps_per_site, lim.max_steps_total) == (1500, 6000)
    ok = s0.build_grid(s0.TimeWindow(T0, 1500 * 10 / 1440, 10.0))
    assert ok.n_steps == 1500
    with pytest.raises(s0.StepCapExceeded):
        s0.build_grid(s0.TimeWindow(T0, 1501 * 10 / 1440, 10.0))
    s0.check_total_steps(4, 1500)
    with pytest.raises(s0.StepCapExceeded):
        s0.check_total_steps(5, 1500)


def test_window_validation_is_generic() -> None:
    bad = [
        s0.TimeWindow(datetime(2027, 1, 1), 1.0, 60.0),  # naive
        s0.TimeWindow(datetime(2027, 1, 1, tzinfo=timezone(timedelta(hours=2))), 1.0, 60.0),
        s0.TimeWindow(T0, 0.0, 60.0),
        s0.TimeWindow(T0, -1.0, 60.0),
        s0.TimeWindow(T0, float("nan"), 60.0),
        s0.TimeWindow(T0, 367.0, 1440.0),
        s0.TimeWindow(T0, 1.0, 0.5),
        s0.TimeWindow(T0, 1.0, 1441.0),
        s0.TimeWindow(T0, 1.0, float("inf")),
    ]
    for w in bad:
        with pytest.raises(s0.S0Error):
            s0.build_grid(w)


def test_grid_is_deterministic() -> None:
    w = s0.TimeWindow(T0, 3.0, 30.0)
    assert s0.build_grid(w) == s0.build_grid(w)
