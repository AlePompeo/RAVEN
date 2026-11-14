# SPDX-License-Identifier: Apache-2.0
"""Dump parity vectors for the browser link model (frontend/src/pages/simula/linkModel.ts).

The base scenario is the UNIFIED radio set of the registry (rf scope: 8.425 GHz, 68.29 dBi, Tsys 26.2 K, Eb/N0 9.6 dB), the same that /api/raven uses. Every number is computed with the backend engine (backend/domain/grazing): exact knife edge, ITU-R P.526-9 ridge term with the table as band,
two-ray multipath, antenna gain/HPBW/pointing, FSPL and the link sum of `analysis.analyze`. The geometry of the
manual scenario is the flat-ground limit (moon radius -> infinity) of `terrain.dominant_ridge`: tip at horizontal
distance e = d1 and height u = H - mast above the antenna, h = u cos(el) - e sin(el), d1_los = e cos(el) + u sin(el).

Run from the repository root:  .venv/bin/python -m scripts.dump_link_parity
Output: frontend/src/pages/simula/fixtures/link_parity.json (small, committed).
"""

import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from backend.domain.grazing import antenna as ant
from backend.domain.grazing.bitrate import DEFAULT_RATES_BPS
from backend.domain.grazing.compensation import load_table, ridge_correction
from backend.domain.grazing.diffraction import (
    itu_knife_edge_db,
    knife_edge_loss_db,
    nu_from_geometry,
)
from backend.domain.grazing.multipath import two_ray
from backend.domain.grazing.snapshot import link_state
from backend.domain.lunar.link import fspl_db
from backend.domain.raven import params as reg

OUT = (
    Path(__file__).resolve().parents[1]
    / "frontend"
    / "src"
    / "pages"
    / "simula"
    / "fixtures"
    / "link_parity.json"
)

BASE: dict[str, Any] = {
    "frequencyGhz": reg.value("rf.frequency_ghz"),
    "earthElDeg": 1.5,
    "ridgeHeightM": 33.0,
    "ridgeDistanceM": 2000.0,
    "ridgeRadiusM": 0.0,
    "diameterM": 0.0861,
    "eta": 0.55,
    "pointingErrorDeg": 0.0,
    "txPowerDbw": reg.value("rf.tx_power_dbw"),
    "tsysK": reg.value("rf.tsys_k"),
    "stationGainDbi": reg.value("rf.station_gain_dbi"),
    "ebn0Db": reg.value("rf.ebn0_db"),
    "miscLossDb": reg.value("rf.misc_loss_db"),
    "rateBps": 1e5,
    "station": "dsn34",
    "earthDistanceKm": 384_400.0,
    "mastM": 2.0,
    "applyCorrection": True,
    "multipath": {"enabled": False, "epsReal": 3.7, "epsImag": 0.01, "roughnessM": 0.25},
}


def case(**over: Any) -> dict[str, Any]:
    c: dict[str, Any] = json.loads(json.dumps(BASE))
    for k, v in over.items():
        if k == "multipath":
            c["multipath"].update(v)
        else:
            c[k] = v
    if "gainDbi" in over:
        c.pop("diameterM", None)
    if "ridgeAngleDeg" in over:
        c.pop("ridgeHeightM", None)
    return c


def compute(c: dict[str, Any]) -> dict[str, Any]:
    f_hz = c["frequencyGhz"] * 1e9
    lam = ant.C_MS / f_hz
    mast = c["mastM"]
    e = c["ridgeDistanceM"]
    if "ridgeAngleDeg" in c:
        u = e * math.tan(math.radians(c["ridgeAngleDeg"]))
    else:
        u = c["ridgeHeightM"] - mast
    el = math.radians(c["earthElDeg"])
    h = u * math.cos(el) - e * math.sin(el)
    d1 = e * math.cos(el) + u * math.sin(el)
    rng_m = c["earthDistanceKm"] * 1000.0
    d2 = rng_m - d1
    nu = float(nu_from_geometry(h, d1, d2, lam))
    j = float(knife_edge_loss_db(nu))
    corr = unc = split = 0.0
    clamped = False
    if c["applyCorrection"]:
        cc, uu, _a, kk, ss = ridge_correction(nu, c["ridgeRadiusM"], max(d1, 1e-3), lam, d2)
        corr, unc, clamped, split = float(cc), float(uu), bool(kk), float(ss)
    if "gainDbi" in c:
        g = c["gainDbi"]
        dia = ant.diameter_for_gain_m(g, f_hz, c["eta"])
    else:
        dia = c["diameterM"]
        g = float(ant.gain_dbi(dia, f_hz, c["eta"]))
    hp70 = float(ant.hpbw_deg(dia, f_hz, "script_70"))
    hpu = float(ant.hpbw_deg(dia, f_hz, "uniform"))
    err = c["pointingErrorDeg"]
    pt = float(ant.pointing_loss_db(err, hp70, "gaussian"))
    pt_script = float(ant.pointing_loss_db(err, hp70, "script"))
    pt_airy = float(ant.pointing_loss_airy_db(err, dia, f_hz))
    fs = float(fspl_db(c["earthDistanceKm"], c["frequencyGhz"]))
    mp = c["multipath"]
    g2 = 0.0
    mp_ok = False
    spec = None
    if mp["enabled"]:
        tr = two_ray(
            c["earthElDeg"],
            mast,
            lam,
            polarization="circular_co",
            eps_r=complex(mp["epsReal"], -mp["epsImag"]),
            sigma_m=mp["roughnessM"],
            ridge_distance_m=e,
        )
        mp_ok = bool(tr.applicable[0])
        g2 = float(tr.gain_db[0])
        sd = float(tr.specular_distance_m[0])
        spec = None if math.isnan(sd) else sd
    st = ant.STATIONS[c["station"]]
    n0 = ant.BOLTZMANN_DBW + 10.0 * math.log10(c["tsysK"])
    st_gain = st.gain_dbi if c.get("stationGainDbi") is None else c["stationGainDbi"]
    cn0 = c["txPowerDbw"] + g + st_gain - c["miscLossDb"] - pt - fs - (j + corr) + g2 - n0
    margins = [cn0 - c["ebn0Db"] - 10.0 * math.log10(r) for r in DEFAULT_RATES_BPS]
    margin = cn0 - c["ebn0Db"] - 10.0 * math.log10(c["rateBps"])
    ok = [r for r, m in zip(DEFAULT_RATES_BPS, margins, strict=True) if m >= 0.0]
    return {
        "hAboveLosM": h,
        "d1LosM": d1,
        "nu": nu,
        "knifeEdgeDb": j,
        "ituDb": float(itu_knife_edge_db(nu)),
        "correctionDb": corr,
        "correctionSplitStepDb": split,
        "correctionUncertaintyDb": unc,
        "correctionClamped": clamped,
        "fsplDb": fs,
        "gainDbi": g,
        "diameterM": dia,
        "hpbwScriptDeg": hp70,
        "hpbwUniformDeg": hpu,
        "pointingLossDb": pt,
        "pointingScriptDb": pt_script,
        "pointingAiryDb": pt_airy,
        "multipathGainDb": g2,
        "multipathApplicable": mp_ok,
        "specularDistanceM": spec,
        "cn0DbHz": cn0,
        "marginDb": margin,
        "marginByRateDb": margins,
        "maxRateBps": max(ok) if ok else 0.0,
        "state": link_state(margin, not (h > 0.0)),
    }


CASES = [
    ("default scenario", case()),
    ("earth high", case(earthElDeg=8.0)),
    ("grazing at the tip", case(earthElDeg=0.85)),
    ("ridge blocks", case(earthElDeg=1.0, ridgeHeightM=80.0)),
    ("small antenna 3 Mbps", case(diameterM=0.03, earthElDeg=0.9, rateBps=3e6)),
    ("rounded ridge 100 m", case(earthElDeg=0.7, ridgeRadiusM=100.0)),
    (
        "rounded ridge 400 m deep shadow",
        case(earthElDeg=0.3, ridgeRadiusM=400.0, ridgeHeightM=60.0),
    ),
    ("radius between grid rows", case(earthElDeg=0.6, ridgeRadiusM=33.0)),
    ("nu above table", case(earthElDeg=0.2, ridgeHeightM=120.0, ridgeRadiusM=200.0)),
    ("nu below table", case(earthElDeg=5.0, ridgeRadiusM=50.0)),
    (
        "short ridge distance",
        case(ridgeDistanceM=300.0, ridgeHeightM=8.0, earthElDeg=1.0, ridgeRadiusM=20.0),
    ),
    (
        "far ridge",
        case(ridgeDistanceM=9000.0, ridgeHeightM=150.0, earthElDeg=0.8, ridgeRadiusM=100.0),
    ),
    ("ridge angle input", case(ridgeAngleDeg=1.2, earthElDeg=1.0)),
    ("gain input 30 dBi", case(gainDbi=30.0, earthElDeg=2.0, rateBps=3e6)),
    ("pointing error 5 deg", case(pointingErrorDeg=5.0)),
    ("pointing error at HPBW", case(pointingErrorDeg=29.0)),
    ("18 m station", case(station="dsn18", stationGainDbi=None, earthElDeg=0.8)),
    ("perigee", case(earthDistanceKm=363_300.0)),
    ("apogee", case(earthDistanceKm=405_500.0, earthElDeg=0.85)),
    ("S band", case(frequencyGhz=2.2, earthElDeg=0.85)),
    ("Ka band", case(frequencyGhz=32.0, earthElDeg=1.2, diameterM=0.2)),
    (
        "multipath applied 1 deg",
        case(earthElDeg=1.0, ridgeHeightM=10.0, multipath={"enabled": True}),
    ),
    (
        "multipath 0.5 deg",
        case(earthElDeg=0.5, ridgeHeightM=5.0, ridgeDistanceM=4000.0, multipath={"enabled": True}),
    ),
    (
        "multipath beyond ridge",
        case(earthElDeg=0.05, ridgeHeightM=3.0, multipath={"enabled": True}),
    ),
    (
        "multipath sub-floor beyond ridge",
        case(earthElDeg=0.01, ridgeDistanceM=5000.0, multipath={"enabled": True}),
    ),
    (
        "multipath sub-floor within ridge",
        case(earthElDeg=0.02, ridgeDistanceM=9000.0, multipath={"enabled": True}),
    ),
    (
        "multipath smooth regolith",
        case(
            earthElDeg=2.0,
            ridgeHeightM=10.0,
            multipath={"enabled": True, "roughnessM": 0.0, "epsReal": 6.0, "epsImag": 0.5},
            mastM=5.0,
        ),
    ),
    ("multipath earth below horizon", case(earthElDeg=-0.5, multipath={"enabled": True})),
    ("correction off", case(earthElDeg=0.7, ridgeRadiusM=100.0, applyCorrection=False)),
    ("earth below horizon", case(earthElDeg=-1.0)),
    ("tall mast", case(mastM=10.0, earthElDeg=0.7)),
    ("high power hot receiver", case(txPowerDbw=20.0, tsysK=120.0, ebn0Db=6.0, miscLossDb=1.0)),
]


def main() -> None:
    tb = load_table()
    out = {
        "generator": "scripts/dump_link_parity.py",
        "table_version": tb.version,
        "table_sha256": tb.file_sha256,
        "hpbw_factor_uniform": ant.hpbw_factor_uniform(),
        "gaussian_db_per_x2": ant.GAUSSIAN_DB_PER_X2,
        "boltzmann_dbw": ant.BOLTZMANN_DBW,
        "rates_bps": list(DEFAULT_RATES_BPS),
        "knife_edge": [
            {"nu": v, "db": float(knife_edge_loss_db(v))}
            for v in np.round(np.arange(-3.0, 12.01, 0.25), 2).tolist()
        ],
        "cases": [{"name": n, "input": c, "output": compute(c)} for n, c in CASES],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, allow_nan=False) + "\n", encoding="utf-8")
    print(f"{len(CASES)} cases -> {OUT}")


if __name__ == "__main__":
    main()
