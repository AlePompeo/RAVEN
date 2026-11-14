# SPDX-License-Identifier: Apache-2.0
"""S5 RF link (docs/domain/raven-model.md, 2.8; migration step M5).

One link sum in dB per step with the TRUE Earth distance of S1: free-space loss, exact knife-edge
loss of the dominant obstacle of S2, ITU-R P.526-9 rounded-ridge correction (split-step only as a
band), two-ray multipath where applicable, antenna pointing, margin per bit rate, and the bit rate
chosen by the statistical compensator. The sum is `grazing.analysis.link_series`, moved verbatim out
of `analyze` (the legacy endpoint calls the same function, so both give identical numbers).

States per step (`rf_state`): `open` (margin >= 0 and the Earth centre clears the ridge),
`transition` (margin >= 0 but the ridge blocks the geometric line of sight), `blocked` (margin < 0).
Terrain knowledge decides what is a number and what is not (decision D4, ruling 2026-11-05):

* `terrain_reason` ok: all values are numbers;
* `blocked_far_terrain`: KNOWN no: `closes = False`, `rf_state = blocked`, margin None (the number
  is outside the single-obstacle model, the answer is not);
* `outside_model` or any missing input: everything None and `closes = None` (unknown, never "open").

The radio parameters are the legacy GrazingLink `LinkInputs` until the intentional unification (M8).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from backend.domain.grazing import bitrate as br
from backend.domain.grazing.analysis import RATES_BPS, LinkInputs, link_series
from backend.domain.grazing.snapshot import link_state
from backend.domain.raven import params as reg
from backend.domain.raven.known import Known, Reason
from backend.domain.raven.s1_geometry import Geometry
from backend.domain.raven.s2_terrain import Terrain, TerrainParams

__all__ = ["RfLink", "RfStage", "rf_link", "terrain_params", "unified_link_inputs"]


@dataclass(frozen=True)
class RfLink:
    fspl_db: list[Known[float]]
    knife_edge_db: list[Known[float]]
    ridge_correction_db: list[Known[float]]
    ridge_uncertainty_db: list[Known[float]]
    multipath_gain_db: list[Known[float]]
    pointing_loss_db: list[Known[float]]
    margin_db_by_rate: dict[int, list[Known[float]]]
    margin_db: list[Known[float]]  # at `inputs.rate_bps`
    chosen_rate_bps: list[Known[int]]
    geometric_visible: list[Known[bool]]
    closes: list[Known[bool]]  # margin >= 0; False for a known far-terrain block; None = unknown
    rf_state: list[Known[str]]  # open | transition | blocked
    reason: list[Reason]
    rate_bps: int


class RfStage(Protocol):
    def __call__(
        self, geo: Geometry, terrain: Terrain, inputs: LinkInputs, step_min: float
    ) -> RfLink: ...


def _col(a: np.ndarray, idx: np.ndarray, n: int) -> list[Known[float]]:
    out: list[Known[float]] = [None] * n
    for j, i in enumerate(idx):
        v = float(a[j])
        out[int(i)] = v if np.isfinite(v) else None
    return out


def unified_link_inputs(overrides: Mapping[str, float | str | bool] | None = None) -> LinkInputs:
    """The single radio set of RAVEN (D2) from the registry, with optional overrides.

    Frequency, station gain, system noise temperature and Eb/N0 are V/D values (DSN 810-005/104);
    transmit power, gain and miscellaneous losses are illustrative (tag I). The antenna height is the
    D8 parameter `rf.antenna_height_m`; overrides are validated like the legacy inputs.
    """
    base: dict[str, float | str | bool] = {
        "frequency_ghz": reg.value("rf.frequency_ghz"),
        "station_gain_dbi": reg.value("rf.station_gain_dbi"),
        "tsys_k": reg.value("rf.tsys_k"),
        "ebn0_db": reg.value("rf.ebn0_db"),
        "tx_power_dbw": reg.value("rf.tx_power_dbw"),
        "tx_gain_dbi": reg.value("rf.tx_gain_dbi"),
        "misc_loss_db": reg.value("rf.misc_loss_db"),
        "antenna_height_m": reg.value("rf.antenna_height_m"),
    }
    merged = {**base, **(overrides or {})}
    if merged.get("station") == "dsn18" and not (overrides and "station_gain_dbi" in overrides):
        # rf.station_gain_dbi is the 34 m antenna (DSN 810-005/104); the 18 m class keeps its own table value (tag I)
        del merged["station_gain_dbi"]
    return LinkInputs.from_overrides(merged)


def terrain_params(inputs: LinkInputs) -> TerrainParams:
    """S2 parameters consistent with the link inputs (antenna height, profile length, wavelength)."""
    return TerrainParams.from_registry(
        antenna_height_m=inputs.antenna_height_m,
        profile_length_m=inputs.profile_length_m,
        wavelength_m=inputs.wavelength_m,
    )


def rf_link(geo: Geometry, terr: Terrain, inputs: LinkInputs, step_min: float) -> RfLink:
    """S5 over the grid of `geo` and the obstacles of `terr`."""
    n = geo.earth_el_deg.size
    if terr.params.antenna_height_m != inputs.antenna_height_m:
        raise ValueError("terrain was built for another antenna height")
    if abs(terr.params.wavelength_m - inputs.wavelength_m) > 1e-9 * inputs.wavelength_m:
        raise ValueError("terrain was built for another wavelength")
    if terr.params.profile_length_m != inputs.profile_length_m:
        raise ValueError("terrain was built for another profile length")
    has = [o is not None for o in terr.rf_obstacle]
    idx = np.array([i for i in range(n) if has[i]], dtype=int)
    reasons = list(terr.terrain_reason)
    for i, obstacle in enumerate(terr.rf_obstacle):
        if (
            reasons[i] is Reason.OK
            and inputs.apply_correction
            and obstacle is not None
            and obstacle.nu > 0.0
            and not np.isfinite(obstacle.radius_of_curvature_m)
        ):
            reasons[i] = Reason.OUTSIDE_MODEL
    rates = [int(r) for r in RATES_BPS]
    none_f: list[Known[float]] = [None] * n
    out_cols: dict[str, list[Known[float]]] = {
        k: list(none_f) for k in ("fspl", "j", "corr", "unc", "g2", "pt", "margin", "geo_vis_f")
    }
    by_rate: dict[int, list[Known[float]]] = {r: list(none_f) for r in rates}
    chosen: list[Known[int]] = [None] * n
    geo_vis: list[Known[bool]] = [None] * n
    # the gimbal tracker needs the whole time series: any hole makes everything unknown
    holes_matter = inputs.mount == "gimbal" and len(idx) != n
    if len(idx) > 0 and not holes_matter:
        az, el, rng = geo.earth_az_deg[idx], geo.earth_el_deg[idx], geo.earth_range_km[idx]
        ridges = [terr.rf_obstacle[int(i)] for i in idx]
        step_s = step_min * 60.0
        ls = link_series(inputs, az, el, rng, [r for r in ridges if r is not None], step_s)
        ks = tuple(dict.fromkeys((*br.DEFAULT_K_VALUES, inputs.compensator_k)))
        rows = br.tradeoff(
            ls.pred, ls.truth, RATES_BPS, ks, inputs.compensator_sigma_db, step_s, inputs.seed
        )
        sel = next(r for r in rows if r.k == inputs.compensator_k)
        crate = np.where(
            sel.chosen_rate_index >= 0,
            np.asarray(RATES_BPS)[np.maximum(sel.chosen_rate_index, 0)],
            0.0,
        )
        out_cols["fspl"] = _col(ls.fspl, idx, n)
        out_cols["j"] = _col(ls.j_db, idx, n)
        out_cols["corr"] = _col(ls.corr, idx, n)
        out_cols["unc"] = _col(ls.unc, idx, n)
        out_cols["g2"] = _col(ls.g2_pred, idx, n)
        out_cols["pt"] = _col(ls.pt_gauss, idx, n)
        out_cols["margin"] = _col(ls.margin, idx, n)
        for j, rt in enumerate(rates):
            by_rate[rt] = _col(ls.pred[:, j], idx, n)
        for j, i in enumerate(idx):
            chosen[int(i)] = int(crate[j])
            geo_vis[int(i)] = bool(~ls.blocks[j])
    else:
        idx = np.array([], dtype=int)

    margin = out_cols["margin"]
    closes: list[Known[bool]] = [None] * n
    state: list[Known[str]] = [None] * n
    final: list[Reason] = []
    known_idx = {int(i) for i in idx}
    for i in range(n):
        r = reasons[i]
        if r is Reason.BLOCKED_FAR_TERRAIN:
            closes[i], state[i] = False, "blocked"
            final_r: Reason = r
            _blank(i, out_cols, by_rate, chosen, geo_vis)
        elif r is Reason.OK and i in known_idx and margin[i] is not None:
            m = margin[i]
            assert m is not None
            closes[i] = m >= 0.0
            gv = geo_vis[i]
            state[i] = link_state(m, bool(gv))
            final_r = Reason.OK
        else:
            final_r = r if r is not Reason.OK else Reason.UPSTREAM_UNKNOWN
            _blank(i, out_cols, by_rate, chosen, geo_vis)
        final.append(final_r)
    return RfLink(
        fspl_db=out_cols["fspl"],
        knife_edge_db=out_cols["j"],
        ridge_correction_db=out_cols["corr"],
        ridge_uncertainty_db=out_cols["unc"],
        multipath_gain_db=out_cols["g2"],
        pointing_loss_db=out_cols["pt"],
        margin_db_by_rate=by_rate,
        margin_db=margin,
        chosen_rate_bps=chosen,
        geometric_visible=geo_vis,
        closes=closes,
        rf_state=state,
        reason=final,
        rate_bps=int(inputs.rate_bps),
    )


def _blank(
    i: int,
    cols: dict[str, list[Known[float]]],
    by_rate: dict[int, list[Known[float]]],
    chosen: list[Known[int]],
    geo_vis: list[Known[bool]],
) -> None:
    for c in cols.values():
        c[i] = None
    for c in by_rate.values():
        c[i] = None
    chosen[i] = None
    geo_vis[i] = None
