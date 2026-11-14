# SPDX-License-Identifier: Apache-2.0
"""Worked examples of the lunar knowledge documents == real code output."""

from pathlib import Path

import numpy as np
import pytest

from backend.assistant.kb import KnowledgeBase
from backend.domain.lunar import energy as en
from backend.domain.lunar import link as lk
from backend.domain.lunar.mission import rank_sites
from backend.domain.lunar.model import EnergyParams, LinkParams
from backend.domain.lunar.runs import longest_run, n_runs

ROOT = Path(__file__).resolve().parents[3]
KB = KnowledgeBase(ROOT)


def _ex(doc_id: str) -> dict[str, dict[str, object]]:
    d = KB.get(doc_id)
    assert d is not None, doc_id
    assert d.kind == "formula" and d.variables and all(v.unit for v in d.variables)
    return d.worked_example  # type: ignore[no-any-return]


def test_documents_present_and_valid() -> None:
    assert KB.errors == []
    for i in (
        "lunar-link-budget",
        "lunar-energy-model",
        "lunar-mission-hours",
        "lunar-ranking-score",
        "lunar-analysis-method",
        "glossary-soc",
        "glossary-libration",
    ):
        assert KB.get(i) is not None, i


def test_link_budget_example() -> None:
    ex = _ex("lunar-link-budget")
    i, o = ex["inputs"], ex["outputs"]
    p = LinkParams.from_overrides(
        {
            "frequency_ghz": i["frequency_ghz"],
            "tx_power_w": i["tx_power_w"],
            "tx_antenna_gain_dbi": i["tx_antenna_gain_dbi"],
            "pointing_loss_db": i["pointing_loss_db"],
            "other_losses_db": i["other_losses_db"],
            "ground_gt_dbk": i["ground_gt_dbk"],
            "data_rate_bps": i["data_rate_bps"],
            "implementation_loss_db": i["implementation_loss_db"],
            "required_ebn0_db": i["required_ebn0_db"],
        }
    )
    d = float(i["distance_km"])  # type: ignore[arg-type]
    fspl = lk.fspl_db(d, p.frequency_ghz)
    eirp = lk.eirp_dbw(p.tx_power_w, p.tx_antenna_gain_dbi)
    cn0 = lk.cn0_dbhz(eirp, fspl, p.pointing_loss_db + p.other_losses_db, p.ground_gt_dbk)
    eb = lk.ebn0_db(cn0, p.data_rate_bps, p.implementation_loss_db)
    assert fspl == pytest.approx(float(o["fspl_db"]), abs=6e-4)  # type: ignore[arg-type]
    assert eirp == pytest.approx(float(o["eirp_dbw"]), abs=6e-4)  # type: ignore[arg-type]
    assert cn0 == pytest.approx(float(o["cn0_dbhz"]), abs=6e-4)  # type: ignore[arg-type]
    assert eb == pytest.approx(float(o["ebn0_db"]), abs=6e-4)  # type: ignore[arg-type]
    assert lk.link_margin_db(d, p) == pytest.approx(float(o["margin_db"]), abs=6e-4)  # type: ignore[arg-type]
    # the document defaults are the code defaults (no drift)
    dflt = LinkParams.from_overrides()
    assert (dflt.tx_power_w, dflt.tx_antenna_gain_dbi, dflt.ground_gt_dbk) == (20.0, 20.0, 54.1)
    assert (dflt.frequency_ghz, dflt.data_rate_bps, dflt.required_ebn0_db) == (8.425, 4000.0, 9.6)


def test_energy_example() -> None:
    ex = _ex("lunar-energy-model")
    i, o = ex["inputs"], ex["outputs"]
    p = EnergyParams.from_overrides(
        {
            "array_area_m2": i["array_area_m2"],
            "cell_efficiency": i["cell_efficiency"],
            "packing_factor": i["packing_factor"],
            "degradation_fraction": i["degradation_fraction"],
        }
    )
    s = en.irradiance_w_m2(np.array([float(i["sun_distance_au"])]))  # type: ignore[arg-type]
    c = en.cos_incidence(np.array([0.0]), np.array([float(i["sun_elevation_deg"])]), p)  # type: ignore[arg-type]
    pw = en.array_power_w(s, c, np.array([True]), p)
    assert s[0] == pytest.approx(float(o["irradiance_w_m2"]), abs=1e-3)  # type: ignore[arg-type]
    assert c[0] == pytest.approx(float(o["cos_incidence"]), abs=1e-9)  # type: ignore[arg-type]
    assert pw[0] == pytest.approx(float(o["array_power_w"]), abs=6e-4)  # type: ignore[arg-type]


def _bits(s: object) -> np.ndarray:
    return np.array([ch == "1" for ch in str(s)])


def test_mission_hours_example() -> None:
    ex = _ex("lunar-mission-hours")
    i, o = ex["inputs"], ex["outputs"]
    useful = _bits(i["power"]) & _bits(i["earth"]) & _bits(i["dsn"]) & _bits(i["margin_ok"])
    dt = float(i["dt_h"])  # type: ignore[arg-type]
    assert useful.sum() * dt == pytest.approx(float(o["useful_hours"]))  # type: ignore[arg-type]
    assert useful.mean() == pytest.approx(float(o["useful_fraction"]), abs=5e-5)  # type: ignore[arg-type]
    assert n_runs(useful) == o["n_windows"]
    assert longest_run(useful, False) * dt == pytest.approx(float(o["longest_gap_h"]))  # type: ignore[arg-type]


def test_ranking_example() -> None:
    ex = _ex("lunar-ranking-score")
    i, o = ex["inputs"], ex["outputs"]
    metrics = {
        k: {"useful_fraction": v["useful_fraction"], "energy": {"min_soc": v["min_soc"]}}  # type: ignore[index]
        for k, v in i.items()
    }
    r = rank_sites(metrics)
    by = {x["site_id"]: x["score"] for x in r}
    assert by["a"] == pytest.approx(float(o["score_a"]))  # type: ignore[arg-type]
    assert by["b"] == pytest.approx(float(o["score_b"]))  # type: ignore[arg-type]
    assert by["c"] == pytest.approx(float(o["score_c"]))  # type: ignore[arg-type]
    assert ", ".join(x["site_id"] for x in r) == o["ranking"]
