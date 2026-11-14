# SPDX-License-Identifier: Apache-2.0
"""S4 power, S6 DSN, S7 mission and `evaluate` (RAVEN M6)."""

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from backend.domain.grazing.horizon import HorizonMask, MaskConfig, disc_criteria
from backend.domain.lunar.coupled import couple
from backend.domain.lunar.model import EnergyParams
from backend.domain.raven import params as reg
from backend.domain.raven import s0_context as s0
from backend.domain.raven import s4_power as s4
from backend.domain.raven import s6_dsn as s6
from backend.domain.raven import s7_mission as s7
from backend.domain.raven.known import Reason
from backend.domain.raven.meta import MODEL_VERSION
from backend.domain.raven.pipeline import evaluate, legacy_scenario
from backend.domain.raven.s1_geometry import Geometry
from backend.domain.raven.s3_illumination import Illumination
from backend.domain.raven.s5_rf import RfLink
from scripts import raven_golden as rg

N = 24


def _geo(dsn_el: np.ndarray | None = None, n: int = N) -> Geometry:
    z = np.zeros(n)
    el = 30.0 * np.sin(np.linspace(0.0, 2 * np.pi, n))
    return Geometry(
        sun_az_deg=np.linspace(0.0, 360.0, n, endpoint=False),
        sun_el_deg=el,
        sun_range_km=np.full(n, reg.value("common.au_km")),
        sun_semidiameter_deg=np.full(n, 0.2665),
        earth_az_deg=z,
        earth_el_deg=z,
        earth_range_km=np.full(n, 384_400.0),
        earth_semidiameter_deg=np.full(n, 0.95),
        earth_el_geocentric_deg=z,
        parallax_deg=z,
        sub_earth_lat_deg=z,
        sub_earth_lon_deg_east=z,
        dsn_complexes=("Goldstone", "Canberra", "Madrid"),
        dsn_moon_el_deg=np.zeros((3, n)) if dsn_el is None else dsn_el,
    )


def _ill(frac: list[float | None]) -> Illumination:
    n = len(frac)
    return Illumination(
        [None] * n, [None] * n, [None] * n, frac, [None if f is None else f > 0 for f in frac],
        [Reason.OK] * n,
    )  # fmt: skip


def _rf(margins: list[float | None], closes: list[bool | None] | None = None) -> RfLink:
    n = len(margins)
    nf: list[Any] = [None] * n
    cl = closes if closes is not None else [None if m is None else m >= 0 for m in margins]
    return RfLink(
        nf, nf, nf, nf, nf, nf, {}, margins, nf, nf, cl, nf, [Reason.OK] * n, 100_000
    )  # fmt: skip


@pytest.mark.parametrize("distance_au", [1.0, 2.0])
@pytest.mark.parametrize("visible_fraction", [0.5, 1.0])
def test_s4_generation_and_charge_against_closed_solution(
    distance_au: float, visible_fraction: float
) -> None:
    """Closed energy balance, without invoking shared generation/battery helpers as oracle."""
    geo = replace(_geo(n=1), sun_range_km=np.array([149597870.7 * distance_au]))
    energy = EnergyParams.from_overrides(
        {
            "orientation": "tracking",
            "array_area_m2": 1.0,
            "cell_efficiency": 0.1,
            "packing_factor": 1.0,
            "degradation_fraction": 0.0,
            "battery_capacity_wh": 100.0,
            "initial_soc": 0.2,
            "min_soc": 0.1,
            "active_load_w": 10.0,
            "charge_efficiency": 0.9,
            "comms_duty": 0.0,
        }
    )
    result = s4.power(geo, _ill([visible_fraction]), [False], energy, 10.0, 30.0)
    generation = 136.08 * visible_fraction / distance_au**2
    end_soc = (20.0 + (generation - 10.0) * 0.5 * 0.9) / 100.0
    assert result.gen_w == pytest.approx([generation], rel=1e-9)
    assert result.soc == pytest.approx([end_soc], rel=1e-9)
    assert result.harvested_wh == pytest.approx(generation * 0.5, rel=1e-9)
    assert result.min_soc == 0.2
    assert result.unmet_wh == 0.0


def test_s4_dark_discharge_against_closed_solution() -> None:
    energy = EnergyParams.from_overrides(
        {
            "battery_capacity_wh": 100.0,
            "initial_soc": 0.8,
            "min_soc": 0.1,
            "active_load_w": 10.0,
            "discharge_efficiency": 0.8,
            "comms_duty": 0.0,
        }
    )
    result = s4.power(_geo(n=3), _ill([0.0] * 3), [False] * 3, energy, 10.0, 60.0)
    assert result.soc == pytest.approx([0.675, 0.55, 0.425], rel=1e-9)
    assert result.harvested_wh == 0.0
    assert result.unmet_wh == 0.0
    assert result.state == ["operational"] * 3


def test_s4_preserves_energy_from_a_thin_solar_crescent() -> None:
    cfg = MaskConfig(n_azimuths=360)
    mask = HorizonMask(
        -89.0,
        0.0,
        2.0,
        0.0,
        np.zeros(360),
        np.ones(360),
        np.ones(360, dtype=bool),
        0.0,
        cfg,
    )
    radius, elevation = 0.27, -0.27 + 1e-5
    c = disc_criteria(mask, np.array([77.0]), np.array([elevation]), radius)
    u = elevation / radius
    expected_fraction = (np.arccos(-u) + u * np.sqrt(1.0 - u * u)) / np.pi
    energy = EnergyParams.from_overrides(
        {
            "orientation": "tracking",
            "array_area_m2": 1.0,
            "cell_efficiency": 0.1,
            "packing_factor": 1.0,
            "degradation_fraction": 0.0,
            "battery_capacity_wh": 100.0,
            "initial_soc": 0.2,
            "min_soc": 0.1,
            "active_load_w": 0.0,
            "comms_duty": 0.0,
            "charge_efficiency": 0.9,
        }
    )
    result = s4.power(_geo(n=1), _ill(c["disc_fraction"]), [False], energy, 10.0, 60.0)
    expected_generation = 136.08 * expected_fraction
    assert result.gen_w == pytest.approx([expected_generation], rel=1e-9)
    assert result.harvested_wh == pytest.approx(expected_generation, rel=1e-9)
    assert result.soc == pytest.approx([0.2 + expected_generation * 0.9 / 100.0], rel=1e-9)
    assert result.soc[0] is not None and result.soc[0] > 0.2


def test_s4_minimum_includes_initial_state_before_a_known_charging_prefix() -> None:
    energy = EnergyParams.from_overrides(
        {
            "orientation": "tracking",
            "initial_soc": 0.2,
            "battery_capacity_wh": 100.0,
            "active_load_w": 0.0,
            "comms_duty": 0.0,
        }
    )
    result = s4.power(_geo(n=2), _ill([1.0, None]), [False, False], energy, 10.0, 60.0)
    assert result.soc[0] is not None and result.soc[0] > 0.2
    assert result.soc[1] is None and result.known_steps == 1
    assert result.min_soc == 0.2
    unknown = s4.power(_geo(n=1), _ill([None]), [False], energy, 10.0, 60.0)
    assert unknown.min_soc is None


def test_s4_depletion_reports_unserved_energy_instead_of_negative_soc() -> None:
    energy = EnergyParams.from_overrides(
        {
            "battery_capacity_wh": 100.0,
            "initial_soc": 0.02,
            "min_soc": 0.1,
            "survival_load_w": 2.0,
            "discharge_efficiency": 0.8,
            "comms_duty": 0.0,
        }
    )
    result = s4.power(_geo(n=1), _ill([0.0]), [False], energy, 10.0, 60.0)
    assert result.soc == [0.0]
    assert result.unmet_wh == pytest.approx(0.4, rel=1e-9)
    assert result.state == ["dark"]


# ----------------------------------------------------------------------------- S6
def test_dsn_threshold_is_inclusive_and_from_the_registry() -> None:
    el = np.array([[5.99, 6.0, 20.0], [0.0, 0.0, 0.0], [-3.0, 5.0, 6.01]])
    d = s6.dsn(_geo(el, 3))
    assert d.min_elevation_deg == 6.0 == reg.value("lunar.ground_station_min_elevation_deg")
    assert d.any_visible == [False, True, True]
    assert d.complex_visible["Goldstone"] == [False, True, True]
    assert d.complex_visible["Madrid"] == [False, False, True]


def test_dsn_18m_class_is_unknown() -> None:
    d = s6.dsn(_geo(), station="dsn18")
    assert all(v is None for v in d.any_visible)
    assert all(r is Reason.UNKNOWN_STATION for r in d.reason)


# ----------------------------------------------------------------------------- S4 + S7 vs couple
def _oracle(
    gen_frac: list[float | None], margins: list[float | None], dsn_v: list[bool | None]
) -> tuple[Any, Any, dict[str, Any]]:
    geo = _geo()
    energy = EnergyParams.from_overrides({"battery_capacity_wh": 200.0, "initial_soc": 1.0})
    ill = _ill(gen_frac)
    rf = _rf(margins)
    ds = s6.Dsn({}, dsn_v, "dsn34", 6.0, [Reason.OK] * N)
    tx = 10.0
    avail = s7.link_usable_series(rf, ds, 0.0)
    pw = s4.power(geo, ill, avail, energy, tx, 60.0)
    ms = s7.mission(pw, rf, ds, 60.0, 0.0)
    from backend.domain.lunar.terrain_energy import terrain_generation_w

    gen = terrain_generation_w(
        geo.sun_az_deg,
        geo.sun_el_deg,
        geo.sun_range_km / reg.value("common.au_km"),
        gen_frac,
        energy,
    )
    ref = couple(60.0, [None if np.isnan(g) else float(g) for g in gen], margins, dsn_v, energy, tx)
    return pw, ms, ref


def test_s4_s7_equal_the_legacy_coupling_all_known() -> None:
    frac: list[float | None] = [min(1.0, max(0.0, 0.5 + 0.5 * np.sin(i / 3.0))) for i in range(N)]
    margins: list[float | None] = [(-1.0 if i % 5 == 0 else 4.0) for i in range(N)]
    dsn_v: list[bool | None] = [i % 7 != 0 for i in range(N)]
    pw, ms, ref = _oracle(frac, margins, dsn_v)
    s = ref["series"]
    assert ms.state == s["state"] and ms.useful == s["useful"] and ms.limiting == s["limiting"]
    assert ms.link_usable == s["link_usable"]
    assert pw.soc == s["soc"] and pw.gen_w == s["gen_w"]
    for k, v in ref["metrics"].items():
        assert ms.metrics[k] == pytest.approx(v), k


def test_unknown_input_makes_that_step_and_all_later_ones_unknown() -> None:
    frac: list[float | None] = [1.0] * N
    frac[10] = None  # unknown disc fraction at step 10
    margins: list[float | None] = [5.0] * N
    dsn_v: list[bool | None] = [True] * N
    pw, ms, ref = _oracle(frac, margins, dsn_v)
    assert pw.known_steps == 10 and pw.first_unknown_index == 10
    assert all(s == "unknown" for s in ms.state[10:]) and ms.state == ref["series"]["state"]
    assert all(u is None for u in ms.useful[10:])  # never "useful" by default
    assert ms.metrics["unknown_steps"] == N - 10 and ms.metrics["unknown_hours"] == (N - 10) * 1.0
    assert all(r is Reason.UPSTREAM_UNKNOWN for r in pw.reason[10:])


def test_known_far_terrain_block_is_a_known_no_unknown_rf_stops_the_chain() -> None:
    frac: list[float | None] = [1.0] * N
    ds = s6.Dsn({}, [True] * N, "dsn34", 6.0, [Reason.OK] * N)
    blocked = _rf([None] * N, [False] * N)
    assert s7.link_usable_series(blocked, ds, 0.0) == [False] * N  # known no
    unknown = _rf([None] * N, [None] * N)
    assert s7.link_usable_series(unknown, ds, 0.0) == [None] * N  # stays unknown
    energy = EnergyParams.from_overrides({})
    pw = s4.power(_geo(), _ill(frac), s7.link_usable_series(unknown, ds, 0.0), energy, 10.0, 60.0)
    assert pw.known_steps == 0 and set(pw.state) == {"unknown"}
    # a False with an unknown DSN stays False; a True with an unknown DSN is unknown
    unk_ds = s6.Dsn({}, [None] * N, "dsn18", 6.0, [Reason.UNKNOWN_STATION] * N)
    assert s7.link_usable_series(blocked, unk_ds, 0.0) == [False] * N
    assert s7.link_usable_series(_rf([5.0] * N), unk_ds, 0.0) == [None] * N


def test_required_margin_is_a_parameter_and_pipeline_is_deterministic() -> None:
    ds = s6.Dsn({}, [True] * 3, "dsn34", 6.0, [Reason.OK] * 3)
    rf = _rf([2.0, 3.0, 4.0])
    assert s7.link_usable_series(rf, ds, 0.0) == [True, True, True]
    assert s7.link_usable_series(rf, ds, 3.0) == [False, True, True]
    a = _oracle([1.0] * N, [4.0] * N, [True] * N)
    b = _oracle([1.0] * N, [4.0] * N, [True] * N)
    assert a[1] == b[1]


@pytest.mark.parametrize("radio", [True, False, None])
@pytest.mark.parametrize("visible", [True, False, None])
def test_s7_rules_against_independent_three_valued_truth_table(
    radio: bool | None, visible: bool | None
) -> None:
    expected_link = (
        False
        if radio is False or visible is False
        else None
        if radio is None or visible is None
        else True
    )
    margin = None if radio is None else 4.0 if radio else -1.0
    rf = _rf([margin])
    ds = s6.Dsn({}, [visible], "dsn34", 6.0, [Reason.OK])
    energy = EnergyParams.from_overrides({"orientation": "tracking"})
    availability = s7.link_usable_series(rf, ds, 3.0)
    pw = s4.power(_geo(n=1), _ill([1.0]), availability, energy, 10.0, 60.0)
    result = s7.mission(pw, rf, ds, 60.0, 3.0)
    assert result.link_usable == [expected_link]
    if expected_link is None:
        assert result.state == ["unknown"]
        assert result.useful == [None] and result.limiting == [None]
    else:
        assert result.state == ["operational"]
        assert result.useful == [expected_link]
        causes = []
        if radio is False:
            causes.append("link")
        if visible is False:
            causes.append("visibility")
        expected_cause = None if not causes else causes[0] if len(causes) == 1 else "multiple"
        assert result.limiting == [expected_cause]
        assert result.metrics["limiting_fraction"]["multiple"] == (1.0 if len(causes) > 1 else 0.0)


# ----------------------------------------------------------------------------- evaluate, real data
GOLD: dict[str, Any] = json.loads(
    (Path(__file__).parents[1] / "golden" / "real.json").read_text(encoding="utf-8")
)["outputs"]
needs_real = pytest.mark.skipif(
    not (rg.have_kernels() and rg.have_tiles()), reason="kernels or LOLA tiles missing"
)


def _evaluate(site_id: str) -> Any:
    from backend.ephemeris.engine import get_engine

    sc = legacy_scenario(
        s0.resolve_site(site_id),
        s0.TimeWindow(datetime.fromisoformat("2027-01-01T00:00:00Z").astimezone(UTC), 3.0, 60.0),
    )
    return evaluate(sc, get_engine())


@needs_real
def test_evaluate_malapert_equals_the_mission_golden() -> None:
    ev = _evaluate("malapert-massif")
    g = GOLD["lunar_mission_malapert"]["response"]
    s = g["series"]
    assert ev.implemented_stages[-1] == "s7" and ev.model_version == MODEL_VERSION
    assert ev.mission.state == s["state"] and ev.mission.useful == s["useful"]
    assert ev.mission.limiting == s["limiting"] and ev.mission.link_usable == s["link_usable"]
    np.testing.assert_allclose(
        [np.nan if v is None else v for v in ev.power.gen_w],
        [np.nan if v is None else v for v in s["gen_w"]],
        atol=1e-9,
        equal_nan=True,
    )
    for k, v in g["metrics"].items():
        if v is not None:
            assert ev.mission.metrics[k] == pytest.approx(v, abs=1e-9), k


@needs_real
def test_evaluate_haworth_states_equal_golden_rf_is_a_known_block() -> None:
    ev = _evaluate("haworth")
    g = GOLD["lunar_mission_haworth"]["response"]["series"]
    assert ev.mission.state == g["state"] and ev.mission.useful == g["useful"]
    # D4 ruling: far terrain over Haworth is a KNOWN no, not an unknown, in most steps
    assert any(c is False for c in ev.rf.closes)
    assert all(u is not True for u in ev.mission.useful)
    assert len(ev.registry_sha256) == 64
