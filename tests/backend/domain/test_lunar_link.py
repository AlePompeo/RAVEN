# SPDX-License-Identifier: Apache-2.0
import math
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from backend.domain.lunar.link import (
    BOLTZMANN_DBW_PER_K_HZ,
    cn0_dbhz,
    dish_gain_dbi,
    ebn0_db,
    eirp_dbw,
    fspl_db,
    fspl_db_rounded_constant,
    link_margin_db,
    wavelength_m,
)
from backend.domain.lunar.model import LinkParams

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    ("tx_gain", "received_dbw", "rate", "published_margin"),
    [(-3.0, -153.3, 960.0, 9.8), (17.0, -133.3, 122880.0, 8.7)],
)
def test_surveyor_published_absolute_design_budget(
    tx_gain: float, received_dbw: float, rate: float, published_margin: float
) -> None:
    """NASA CR-69102 Table 10-3, PDF p.215: design arithmetic, not measured performance.

    Supply the published 211.4 dB loss, not a distance inferred from its ambiguous "miles".
    The 8.3 dB threshold already includes the 1.5 dB detector loss.
    """
    received = 3.0 + tx_gain + 61.0 - 211.4 - 2.6 - 0.3
    assert received == pytest.approx(received_dbw, abs=1e-12)
    noise = BOLTZMANN_DBW_PER_K_HZ + 10 * math.log10(215.0)
    assert noise == pytest.approx(-205.3, abs=0.05)
    cno = cn0_dbhz(3.0 + tx_gain, 211.4, 2.6 + 0.3 + 4.1, 61.0 - 10 * math.log10(215.0))
    margin = ebn0_db(cno, rate, 0.0) - 8.3
    assert margin == pytest.approx(published_margin, abs=0.1)
    assert ebn0_db(cno, rate, 1.5) - 6.8 == pytest.approx(margin, abs=1e-12)


def test_known_example_384400_km_2_2_ghz() -> None:
    # docs/knowledge/fspl.md: 210.994 dB with the plugin constant 92.45
    assert fspl_db_rounded_constant(384400, 2.2) == pytest.approx(210.994, abs=5e-4)
    # exact constant: 210.9919 dB (0.0022 dB lower)
    assert fspl_db(384400, 2.2) == pytest.approx(210.9919, abs=5e-4)


def test_identity_with_fspl_c_formula_over_grid() -> None:
    d = np.geomspace(300_000, 450_000, 40)
    f = np.geomspace(0.4, 40, 30)
    diffs = [
        fspl_db_rounded_constant(float(x), float(y)) - float(fspl_db(float(x), float(y)))
        for x in d
        for y in f
    ]
    # constant rounding of 92.4478 -> 92.45: identical shape, offset 0.0022 dB (> 1e-3 dB!)
    assert max(diffs) - min(diffs) < 1e-9
    assert diffs[0] == pytest.approx(92.45 - 92.44778322, abs=1e-7)
    assert max(abs(x) for x in diffs) < 2.3e-3


def test_exact_constant() -> None:
    assert 20 * math.log10(4 * math.pi * 1e12 / 299792458.0) == pytest.approx(92.447783, abs=1e-6)


def test_matches_real_fspl_c_plugin(tmp_path: Path) -> None:
    if not shutil.which("gcc"):
        pytest.skip("gcc missing")
    exe = tmp_path / "fspl"
    subprocess.run(
        ["gcc", "-O2", "-o", str(exe), str(ROOT / "backend/plugins/fspl_c/fspl.c"), "-lm"],
        check=True,
    )
    for d, f in [(384400.0, 2.2), (355200.0, 8.425), (405500.0, 0.5)]:
        out = subprocess.run(
            [str(exe)],
            input=f"distance_km={d}\nfreq_ghz={f}\n",
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        plugin = float(out.split("=")[1])
        assert fspl_db_rounded_constant(d, f) == pytest.approx(plugin, abs=1e-6)
        assert fspl_db(d, f) == pytest.approx(plugin, abs=2.3e-3)


def test_independent_linear_domain_hand_calculation() -> None:
    """Same budget computed in linear units from SI constants (no dB helpers), 8.425 GHz case."""
    p = replace(
        LinkParams.from_overrides(),
        tx_power_w=20.0,
        tx_antenna_gain_dbi=20.0,
        pointing_loss_db=1.0,
        other_losses_db=1.0,
        ground_gt_dbk=54.1,
        data_rate_bps=4000.0,
        implementation_loss_db=2.0,
        required_ebn0_db=9.6,
        frequency_ghz=8.425,
    )
    c, k, d = 299792458.0, 1.380649e-23, 384400e3
    lam = c / 8.425e9
    pr_w = 20.0 * 10 ** (20 / 10) * (lam / (4 * math.pi * d)) ** 2  # isotropic receiver
    gt = 10 ** (54.1 / 10)  # linear G/T, 1/K
    ebn0 = pr_w * 10 ** (-2 / 10) * gt / (k * 4000.0) * 10 ** (-2 / 10)
    ebn0_db = 10 * math.log10(ebn0)
    assert link_margin_db(384400.0, p) == pytest.approx(ebn0_db - 9.6, abs=0.01)
    # k = -228.6 dBW/K/Hz rounding is the only difference (0.001 dB)
    assert BOLTZMANN_DBW_PER_K_HZ == pytest.approx(10 * math.log10(k), abs=2e-3)


@pytest.mark.parametrize(
    ("rate_18_mbps", "rate_34_mbps"),
    [(6.28, 22.72), (100.55, 363.53)],
)
def test_nasa_lunar_return_rate_scaling_with_ground_gt(
    rate_18_mbps: float, rate_34_mbps: float
) -> None:
    # NASA/TM-2019-220203, tables 4 and 10: 8.475 GHz lunar return, fixed power.
    # These are published extrema, not a fully specified or measured link budget.
    base = replace(LinkParams.from_overrides(), frequency_ghz=8.475)
    p18 = replace(base, ground_gt_dbk=33.48, data_rate_bps=rate_18_mbps * 1e6)
    p34 = replace(base, ground_gt_dbk=39.02, data_rate_bps=rate_34_mbps * 1e6)
    difference = float(link_margin_db(390_000.0, p34) - link_margin_db(390_000.0, p18))
    assert difference == pytest.approx(0.0, abs=0.1)


@pytest.mark.parametrize(
    ("gt", "rate_min_mbps", "rate_max_mbps"),
    [(29.20, 2.31, 36.96), (33.48, 6.28, 100.55), (39.02, 22.72, 363.53)],
)
def test_nasa_lunar_return_rate_scaling_with_lunar_dish(
    gt: float, rate_min_mbps: float, rate_max_mbps: float
) -> None:
    # NASA/TM-2019-220203 sec. 2.3, Table 10 (X band, 8.475 GHz): only the lunar dish changes, 6 -> 23.7 in.
    # Relative check only: Tx power, required Eb/N0 and the lunar-side losses are not published, so the
    # absolute margin cannot be reproduced. Residual 0.11 dB (16.0x published vs (23.7/6)^2 = 15.6x).
    base = replace(LinkParams.from_overrides(), frequency_ghz=8.475, ground_gt_dbk=gt)
    big = replace(base, tx_dish_diameter_m=23.7 * 0.0254, data_rate_bps=rate_max_mbps * 1e6)
    small = replace(base, tx_dish_diameter_m=6.0 * 0.0254, data_rate_bps=rate_min_mbps * 1e6)
    difference = float(link_margin_db(390_000.0, big) - link_margin_db(390_000.0, small))
    assert difference == pytest.approx(0.0, abs=0.15)


@pytest.mark.parametrize(
    ("eirp", "dish_gain", "published_output"),
    [(64.00, 58.10, -36.46), (63.30, 55.55, -39.71)],
)
def test_nasa_cadet_forward_power_budget(
    eirp: float, dish_gain: float, published_output: float
) -> None:
    # NASA/TM-2020-220472 Table V, 22.6795 GHz. T=100 K is arbitrary and cancels;
    # the measured-input column is a budget, not a measured Eb/N0 or lunar link.
    temperature_dbk = 10 * math.log10(100.0)
    cn0 = cn0_dbhz(eirp, 211.35, 0.50, dish_gain - temperature_dbk)
    output = cn0 + BOLTZMANN_DBW_PER_K_HZ + temperature_dbk + 53.29
    assert output == pytest.approx(published_output, abs=0.02)


def test_margin_6_02_db_when_distance_doubles_and_3_01_when_power_doubles() -> None:
    p = LinkParams.from_overrides()
    m1 = float(link_margin_db(200000.0, p))
    m2 = float(link_margin_db(400000.0, p))
    assert m1 - m2 == pytest.approx(6.0206, abs=1e-4)
    p2 = replace(p, tx_power_w=p.tx_power_w * 2)
    assert float(link_margin_db(300000.0, p2)) - float(link_margin_db(300000.0, p)) == (
        pytest.approx(3.0103, abs=1e-4)
    )
    p3 = replace(p, data_rate_bps=p.data_rate_bps * 2)
    assert float(link_margin_db(300000.0, p3)) - float(link_margin_db(300000.0, p)) == (
        pytest.approx(-3.0103, abs=1e-4)
    )


def test_vectorised_and_dish_gain() -> None:
    p = LinkParams.from_overrides()
    arr = np.array([355000.0, 384400.0, 405000.0])
    out = link_margin_db(arr, p)
    assert out.shape == (3,) and out[0] > out[1] > out[2]
    # 1 m dish, eta 0.55 at 8.425 GHz
    g = dish_gain_dbi(1.0, 8.425, 0.55)
    assert g == pytest.approx(10 * math.log10(0.55 * (math.pi / wavelength_m(8.425)) ** 2))
    assert 30 < g < 40
    pd = replace(p, tx_dish_diameter_m=1.0)
    assert float(link_margin_db(384400.0, pd)) > float(link_margin_db(384400.0, p))


def test_eirp_and_cn0() -> None:
    assert eirp_dbw(100.0, 10.0) == pytest.approx(30.0)
    assert cn0_dbhz(30.0, 200.0, 2.0, 50.0) == pytest.approx(30 - 200 - 2 + 50 + 228.6)
