# SPDX-License-Identifier: Apache-2.0
"""Parameter registry (RAVEN M1): one definition per number, legacy views unchanged."""

import math

import pytest

from backend.domain.grazing import model as gm
from backend.domain.lunar import model as lm
from backend.domain.raven import params as reg


def test_every_entry_is_complete() -> None:
    for key, s in reg.REGISTRY.items():
        assert key == f"{s.scope}.{s.name}"
        assert s.scope in reg.SCOPES and s.stage in reg.STAGES and s.tag in reg.TAGS, key
        assert s.unit and s.source, key
        assert math.isfinite(s.default) and s.lo <= s.default <= s.hi, key


def test_legacy_tables_are_views_of_the_registry() -> None:
    for scope, params in (("lunar", lm.PARAMS), ("grazing", gm.PARAMS)):
        reg_specs = {s.name: s for s in reg.scope_specs(scope)}
        assert list(params) == list(reg_specs)  # same keys, same order
        for name, old in params.items():
            new = reg_specs[name]
            assert (old.default, old.unit, old.lo, old.hi, old.status, old.source, old.note) == (
                new.default,
                new.unit,
                new.lo,
                new.hi,
                new.tag,
                new.source,
                new.note,
            )
    assert len(reg.scope_specs("lunar")) == 32 and len(reg.scope_specs("grazing")) == 35


def test_known_values_did_not_move() -> None:
    """A few pins taken from the pre-migration code (the golden outputs pin all of them)."""
    assert reg.value("lunar.frequency_ghz") == 8.425
    assert reg.value("grazing.frequency_ghz") == 8.4
    assert reg.value("lunar.required_margin_db") == 3.0
    assert reg.get("lunar.required_margin_db").tag == "V"
    assert reg.value("lunar.ground_station_min_elevation_deg") == 6.0
    assert reg.value("grazing.antenna_height_m") == 2.0
    assert reg.value("common.sun_radius_km") == 695_700.0
    assert lm.SUN_SEMIDIAMETER_DEG == 0.27


def test_default_window_respects_the_d9_cap() -> None:
    """The registry default window (7 d at 10 min) fits the per-site cap; the legacy 29.53 d at 10 min
    (4252 steps) does not. The synodic month stays reachable at a coarser step."""
    cap = reg.value("common.max_steps_per_site")
    steps = reg.value("lunar.days") * 24 * 60 / reg.value("lunar.step_min")
    assert steps <= cap and steps == 1008
    assert 29.53 * 24 * 60 / 10 > cap and 29.53 * 24 * 60 / 30 <= cap


def test_duplicated_concepts_are_declared() -> None:
    assert reg.DUPLICATED_CONCEPTS == {
        "frequency_ghz": ("lunar.frequency_ghz", "grazing.frequency_ghz")
    }
    assert reg.value("lunar.frequency_ghz") != reg.value("grazing.frequency_ghz")


def test_resolve_validates_without_echo() -> None:
    d = reg.resolve("lunar")
    assert d["tx_power_w"] == 20.0 and set(d) == {s.name for s in reg.scope_specs("lunar")}
    assert reg.resolve("lunar", {"tx_power_w": 5})["tx_power_w"] == 5.0
    for bad in (
        {"nope": 1},
        {"tx_power_w": 1e9},
        {"tx_power_w": float("nan")},
        {"tx_power_w": True},
        {"tx_power_w": "5"},
    ):
        with pytest.raises(reg.ParamError) as e:
            reg.resolve("lunar", bad)
        assert "1000000000" not in str(e.value)
    assert reg.ParamError is lm.ParamError  # one exception class for the legacy code


def test_registry_rows_are_plain_data() -> None:
    rows = reg.registry_rows()
    assert len(rows) == len(reg.REGISTRY)
    assert all(isinstance(v, str | float | int) for r in rows for v in r.values())


def test_au_matches_the_ephemeris_engine_copy() -> None:
    from backend.ephemeris import engine

    assert reg.value("common.au_km") == engine.AU_KM
