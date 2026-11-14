# SPDX-License-Identifier: Apache-2.0
"""Validation status of the RAVEN stages and parameter groups (migration follow-up to M9).

Everything here is taken from the validation matrix of `docs/domain/raven-model.md` (section 3) and
from `docs/domain/validation.md`; nothing is new evidence. Status values:

* `verified`: checked against a published formula, an independent re-implementation or like-for-like
  independent data, with the residual stated;
* `plausibility_only`: compared with independent data whose criterion is not identical, or with a
  literature range;
* `not_validated`: no independent check of the numbers (arithmetic may be checked, the values are
  illustrative or a design choice);
* `unknown`: a claim made in a document that has not been re-run on this model.

No row is a radio or power measurement on the Moon. A `verified` row MUST carry evidence (a source
and at least one test or document path); `tests/backend/domain/raven/test_validation.py` enforces it.
"""

from dataclasses import dataclass
from typing import Any

from backend.domain.raven import params as reg

__all__ = ["STATUSES", "ValidationEntry", "parameter_groups", "validation_report"]

STATUSES = ("verified", "plausibility_only", "not_validated", "unknown")
VAL = "docs/domain/validation.md"
MODEL = "docs/domain/raven-model.md"


@dataclass(frozen=True)
class ValidationEntry:
    id: str
    stage: str  # s0..s7 or "time"
    status: str
    what: str  # what is checked
    against: str  # against what, and the type of comparison
    residual: str  # the measured difference, as documented
    not_validated: str  # what the check does NOT cover
    evidence: tuple[str, ...]  # test and document paths
    phrase: str  # the sentence UI and README may use

    def to_dict(self) -> dict[str, Any]:
        return {f: getattr(self, f) for f in self.__dataclass_fields__} | {
            "evidence": list(self.evidence)
        }


E = ValidationEntry
_T = "tests/backend/"
ENTRIES: tuple[ValidationEntry, ...] = (
    E(
        "s0.coordinates",
        "s0",
        "verified",
        "copy of the site coordinates",
        "IAU Gazetteer, NSSDCA, LROC (reading of the published text)",
        "none",
        "not the centres of the Artemis regions; height not taken from the source",
        (_T + "domain/raven/test_s0_context.py", "backend/domain/data/sites.json", VAL),
        "coordinates copied from the cited source (IAU feature centres), not Artemis region centres",
    ),
    E(
        "s1.sun_earth",
        "s1",
        "verified",
        "Sun and Earth azimuth, elevation, distance from a site",
        "JPL Horizons, offline fixture (like-for-like)",
        "8.2e-7 deg and 7 m (Sun); 1.2e-6 deg and 0.16 m (Earth)",
        "UT1 after 2027-01 is predicted, its uncertainty is not quantified",
        (_T + "ephemeris/test_validation.py", _T + "domain/raven/test_s1_geometry.py", VAL),
        "verified against JPL Horizons",
    ),
    E(
        "s1.dsn_geometry",
        "s1",
        "verified",
        "elevation of the Moon from the three DSN complexes",
        "independent skyfield computation on 1753 instants (re-implementation); DSN 810-005/301 Table 5 coordinates",
        "6.6e-5 deg; 1e-6 deg",
        "no scheduling",
        (_T + "domain/test_lunar_visibility.py", _T + "domain/raven/test_s4_s6_s7.py", VAL),
        "geometry verified; no DSN scheduling",
    ),
    E(
        "s1.earth_at_pole",
        "s1",
        "verified",
        "Earth elevation at the poles",
        "independent geometric formula (re-implementation)",
        "0.001 deg (poles), 0.006 deg (Apollo 11)",
        "",
        (_T + "domain/grazing/test_geometry.py", VAL),
        "verified against an independent formula",
    ),
    E(
        "s2.mask",
        "s2",
        "verified",
        "horizon mask, Sun and (new) Earth azimuth",
        "independent implementation scripts/solar_horizon_arbiter.py (same geometry)",
        "2.2e-9 deg and 0 different states of 21900 (historical profile); mask: at most 1 step of 4380; "
        "horizon at the Sun azimuth 0.007-0.053 deg; Earth azimuth: within 0.06 deg (test tolerance)",
        "DEM vertical error, relief below 20 m, terrain beyond 200 km, 5 m DEMs",
        (
            _T + "domain/grazing/test_solar_horizon_arbiter.py",
            _T + "domain/grazing/test_horizon.py",
            _T + "domain/raven/test_s2_s3_real.py",
            VAL,
        ),
        "horizon verified against an independent implementation",
    ),
    E(
        "s2.s3.lroc",
        "s3",
        "plausibility_only",
        "illumination fraction near the pole",
        "LROC WAC WAC_POLE_ILL_TWI_SOUTH_100M (independent data, criterion not identical)",
        "r 0.954, RMS 4.2 points; pole 46.0 % vs 26.7 % not explained",
        "different radiometric criterion; Malapert, Haworth, Nobile outside the 88-90 S coverage",
        (VAL, "scripts/solar_horizon_arbiter.py"),
        "agrees with LROC WAC observations within 4-6 points RMS near the pole (criteria not identical)",
    ),
    E(
        "s2.dem_orientation",
        "s2",
        "plausibility_only",
        "DEM orientation convention",
        "LROC rotated by 180 deg (independent data, criterion not identical)",
        "r drops to 0.237",
        "",
        (VAL, "backend/domain/grazing/dem.lock.json"),
        "DEM orientation confirmed by independent data",
    ),
    E(
        "s2.literature",
        "s2",
        "plausibility_only",
        "illumination at the Shackleton-de Gerlache ridge",
        "Barker et al., Table 2, 1st percentile (plausibility)",
        "arbiter above the 1st percentile in every RoI",
        "nominal values not published; Mazarico 2011 and Glaser 2014 not read",
        (VAL,),
        "plausibility only",
    ),
    E(
        "s2.rf_obstacle",
        "s2",
        "not_validated",
        "dominant obstacle and its radius along the Earth azimuth",
        "one analytic case (re-implementation)",
        "0.007 dB",
        "single obstacle, radius from a fit on 20 m data, no multiple diffraction; far terrain beyond the "
        "profile is a single-obstacle estimate with an illustrative 30 dB threshold (D4)",
        (_T + "domain/grazing/test_terrain.py", _T + "domain/raven/test_s2_s3.py", MODEL),
        "single-obstacle model, not validated",
    ),
    E(
        "s2.rf_geometry",
        "s2",
        "verified",
        "sampled obstacle projection, signed height, distances and maximum Fresnel parameter",
        "independent Cartesian dot-product construction on a spherical Moon, three Earth elevations",
        "absolute tolerance 1e-8 m for distances and height; relative tolerance 1e-9 for nu",
        "not a validation of measured DEM heights, the fitted radius or the single-obstacle propagation assumption",
        (_T + "domain/grazing/test_terrain.py", VAL),
        "sampled RF geometry verified independently; real terrain and obstacle modelling remain unvalidated",
    ),
    E(
        "s2.polar_rays",
        "s2",
        "verified",
        "great-circle bearings for terrain profiles, horizon masks and download footprints at the poles",
        "independent Cartesian horizon oracle at both poles and near-polar sites; analytic south-pole meridians",
        "horizon tolerance 1e-8 deg; profile longitude tolerance 1e-8 deg",
        "spherical coordinate arithmetic only, not measured relief or sub-pixel terrain",
        (_T + "domain/grazing/test_horizon.py", _T + "domain/grazing/test_terrain.py", VAL),
        "polar bearings verified; distinct rays no longer collapse onto the same longitude",
    ),
    E(
        "s2.ridge_fit_arithmetic",
        "s2",
        "verified",
        "parabolic radius fit under vertical datum translation and rejection of unsupported crests",
        "analytic parabola with radius 400 m at three vertical offsets; four constant and three linear profiles",
        "relative tolerance 1e-9 on fitted radius; constant and monotone linear relief return unresolved",
        "not empirical DEM curvature, a projected-ray vertex qualification or relief below the DEM resolution",
        (_T + "domain/grazing/test_terrain.py", VAL),
        "radius-fit arithmetic verified; extrapolated crests are rejected; real curvature remains unvalidated",
    ),
    E(
        "s3.disc",
        "s3",
        "verified",
        "visible fraction of the solar disc",
        "analytic circular segment; independent adaptive strip quadrature and refined arbiter integration on identical masks (not independent terrain)",
        "flat-horizon area <= 2e-15; tilted horizons <= 2e-13; continuous variable-horizon quadrature <= 1e-9; five real 2027 masks vs 2048-column arbiter <= 1.46e-6 fraction",
        "exact area above the piecewise-linear mask, splitting 48 base strips at interpolation knots; "
        "tangent-plane azimuth projection only; no limb darkening, DEM uncertainty or like-for-like observation",
        (
            _T + "domain/raven/test_s2_s3.py",
            _T + "domain/raven/test_s2_s3_real.py",
            _T + "domain/grazing/test_horizon.py",
            VAL,
        ),
        "piecewise-linear horizon area verified; fully hidden tilted discs remain dark; physical illumination remains plausibility only",
    ),
    E(
        "s4.energy_arithmetic",
        "s4",
        "verified",
        "solar generation, charge/discharge efficiencies, SOC and unserved energy of current S4",
        "closed independent energy balances with fixed synthetic inputs, including a thin solar crescent",
        "relative tolerance 1e-9",
        "not hardware qualification: usable capacity, efficiencies, loads, dust and temperature remain unmeasured",
        (_T + "domain/raven/test_s4_s6_s7.py", VAL),
        "S4 arithmetic verified against closed solutions; hardware and illustrative values not validated",
    ),
    E(
        "s4.energy",
        "s4",
        "not_validated",
        "physical generation and usable battery energy under illustrative hardware parameters",
        "arithmetic checked separately in s4.energy_arithmetic; no equivalent independent hardware trace",
        "physical residual unknown",
        "no real case; panel, battery and loads are illustrative (tag I)",
        (
            _T + "domain/test_lunar_energy.py",
            _T + "domain/test_lunar_coupled.py",
            _T + "domain/raven/test_s4_s6_s7.py",
            VAL,
        ),
        "arithmetic verified; not validated (illustrative parameters)",
    ),
    E(
        "s5.browser_mirror",
        "s5",
        "verified",
        "TypeScript mirror of the manual RF controls: FSPL, Fresnel diffraction, rounded ridge, multipath, pointing and margins by rate. "
        "Verified within 0.01 dB against the Python engine on 32 fixture cases (and 61 exact knife-edge points within 1e-6 dB)",
        "Python shared S5 formulas, offline vectors generated by scripts/dump_link_parity.py (implementation parity, not independent validation)",
        "tolerance 0.01 dB on 32 cases; exact knife edge tolerance 1e-6 dB on 61 points; relative geometric tolerance 1e-9",
        "not a lunar measurement or a validation of terrain, material assumptions, absolute link margin or battery; manual illustrative geometry only",
        (
            "frontend/src/pages/simula/linkModel.test.ts",
            "frontend/src/pages/simula/fixtures/link_parity.json",
            "scripts/dump_link_parity.py",
            MODEL,
        ),
        "the browser implementation agrees with the Python engine within 0.01 dB on 32 fixture cases (linkModel.test.ts); physical assumptions remain unvalidated",
    ),
    E(
        "s5.fspl",
        "s5",
        "verified",
        "free-space loss, EIRP, C/N0, Eb/N0",
        "exact formula and linear-unit computation (re-implementation); plugin fspl_c (formula)",
        "1e-4 dB; constant +0.0022 dB offset of the plugin",
        "",
        (_T + "domain/test_lunar_link.py", _T + "domain/raven/test_s5.py", VAL),
        "verified",
    ),
    E(
        "s5.nasa_differential",
        "s5",
        "plausibility_only",
        "rate ratios with G/T and diameter",
        "NASA/TM-2019-220203 Tables 4 and 10 (differential plausibility)",
        "-0.04 dB (tolerance 0.1); 0.11 dB",
        "the absolute margin cannot be rebuilt from the sources",
        (_T + "domain/test_lunar_link.py", VAL),
        "differential check against a NASA study; absolute margin not validated",
    ),
    E(
        "s5.power_arithmetic",
        "s5",
        "verified",
        "arithmetic of a published power budget",
        "NASA/TM-2020-220472 Table V, CADeT (arithmetic of a published budget)",
        "0.02 dB",
        "not a lunar link; noise, Eb/N0 and margin are not covered",
        (_T + "domain/test_lunar_link.py", VAL),
        "arithmetic check against a published budget",
    ),
    E(
        "s5.surveyor_absolute_arithmetic",
        "s5",
        "verified",
        "absolute received power, noise density and margin of a published lunar design budget; current S5 sum",
        "NASA CR-69102 Table 10-3 (PDF p.215), telemetry and television design budgets, not measurements",
        "0.0471 dB maximum margin residual; tolerance 0.1 dB for the rounded published inputs",
        "reported 211.4 dB space loss is supplied, not independently validated; range unit is only 'miles'; S5 rate is rebased to source rate; no measured terrain, multipath, weather or flight performance",
        (_T + "domain/test_lunar_link.py", _T + "domain/raven/test_s5.py", VAL),
        "absolute arithmetic checked against a published lunar design budget; not flight validation",
    ),
    E(
        "s5.knife_edge",
        "s5",
        "verified",
        "exact knife-edge J(nu), ITU equation (27), nu, Fresnel radius",
        "ITU-R P.526-9 equations (2), (22)-(23), (26), (27); P.526-16 section 4.1 equations (30)-(31) retain the J(nu) expressions",
        "< 1e-7 dB; ITU <= 0.123 dB for -0.78 < nu <= 5",
        "not a measurement of the local lunar obstacle or its geometry",
        (_T + "domain/grazing/test_diffraction.py", VAL),
        "knife-edge formulas verified; J(nu) also checked against ITU-R P.526-16",
    ),
    E(
        "s5.rounded_ridge_formula",
        "s5",
        "verified",
        "T(m,n) algebra at supplied projected-ray vertex geometry",
        "ITU-R P.526-16 section 4.2 equations (34a)-(36), unchanged from P.526-9 equations (30a)-(32)",
        "absolute tolerance 1e-9 dB on six independent-formula cases; zero-radius limit checked",
        "not measured lunar propagation; radius and projected-ray vertex are not validated; the nonnegative policy clamp and split-step uncertainty band are not an ITU qualification",
        (_T + "domain/grazing/test_compensation.py", VAL),
        "rounded-obstacle formula verified against the current ITU edition; physical ridge model not validated",
    ),
    E(
        "s5.rounded_ridge",
        "s5",
        "not_validated",
        "rounded-ridge term T(m,n)",
        "ITU-R P.526-9 section 4.2, also checked against P.526-16 equations (32)-(36); refined split-step (plausibility)",
        "ITU minus split-step up to 1.3 dB (nu = 3) and 2.4 dB (nu = 8), R = 400 m",
        "no measurement; exact cylinder (Mie/Fock) not computed",
        (_T + "domain/grazing/test_compensation.py", VAL),
        "ITU-R P.526-9 formula; uncertainty band from an unvalidated simulation; not validated",
    ),
    E(
        "s5.circular_basis",
        "s5",
        "verified",
        "lossless pure-circular reflected component power",
        "NASA CR-119032 printed pp.13-14 (PDF pp.20-21), real-coefficient circular power ratio and independent Snell-angle construction",
        "relative tolerance 1e-12 and absolute tolerance 1e-15 of incident-normalized power; two real permittivities, six grazing angles",
        "not a source for lossy complex permittivity, coherent phase or actual TX/RX antenna coupling; no lunar multipath measurement",
        (_T + "domain/grazing/test_multipath.py", VAL),
        "lossless circular power algebra checked against a primary source; hardware multipath not validated",
    ),
    E(
        "s5.reflection_formulas",
        "s5",
        "verified",
        "TE/TM complex Fresnel coefficients and Gaussian coherent-field roughness factor",
        "JPL IPN PR 42-226 equations (48)-(49), independent Snell-angle construction; independent integral of Gaussian height-induced phase",
        "complex coefficients absolute tolerance 1e-12; Gaussian coherent field absolute tolerance 1e-10",
        "not lossy circular antenna coupling or coherent lunar multipath; Gaussian height statistics and regolith values are assumptions",
        (_T + "domain/grazing/test_multipath.py", VAL),
        "reflection algebra and Gaussian field attenuation verified; lunar multipath remains unvalidated",
    ),
    E(
        "s5.multipath",
        "s5",
        "not_validated",
        "Fresnel coefficients and roughness",
        "JPL 42-226 eq. (48)-(49) (formula); NASA CR-119032 circular power ratio for real coefficients; qualitative context: JPL IPN PR 42-243 (Sanchez Net 2025) reports S-band fading on Chandrayaan-3 and IM-1 lander downlinks",
        "script roughness error corrected; specular geometry regression checked below the numerical angle floor; plausibility: JPL 42-243 states that fades can exceed 20 dB at low elevation, the model reaches -21.5 dB (circular co-polar, smooth ground) but only about -10 dB with rms roughness 0.25 m, so the depth depends on the unknown roughness; the report publishes no plotted values",
        "no fade depth, elevation or lander geometry from 42-243 is available to compare with the model; lossy circular phase and hardware coupling not established by the primary power-ratio source; flat ground, coherent part; regolith tag I; the 0.05 degree field-angle floor is illustrative and does not move the geometric specular point",
        (_T + "domain/grazing/test_multipath.py", VAL),
        "order of magnitude agrees with JPL 42-243 only for smooth ground; no numbers to compare; not validated",
    ),
    E(
        "s5.antenna",
        "s5",
        "verified",
        "gain formula G = eta (pi D / lambda)^2 and the 12.04 constant",
        "Crane & Blood 1979 section 2.7 (formula); derivation",
        "none",
        "beamwidth factor 70 lambda/D not verified on the source; station gains tag I",
        (_T + "domain/grazing/test_antenna.py", VAL),
        "gain formula verified; beamwidth factor illustrative",
    ),
    E(
        "s5.compensator",
        "s5",
        "not_validated",
        "bit-rate choice rule max R: M - k sigma >= 0",
        "Gaussian formula (formula)",
        "none",
        "sigma assumed known and Gaussian",
        (_T + "domain/grazing/test_bitrate.py", VAL),
        "statistical rule; sigma is an assumption",
    ),
    E(
        "s6.dsn_visibility",
        "s6",
        "verified",
        "geometric visibility above the registry threshold (6 deg)",
        "DSN 810-005/301 Rev. P sections 2.2.2-2.2.3 (published value)",
        "none",
        "no real tracking; the 18 m class is unknown",
        (_T + "domain/raven/test_s4_s6_s7.py", _T + "domain/test_lunar_visibility.py", VAL),
        "geometric visibility only",
    ),
    E(
        "s7.rule_arithmetic",
        "s7",
        "verified",
        "three-valued link usability, useful-state flags and attribution of definite limiting causes",
        "independent exhaustive nine-case three-valued RF/DSN truth table on current S4-S7",
        "exact states, flags and limiting fractions; unknown never counted as a definite failure",
        "not mission qualification or approval of the illustrative useful-hour and hardware definitions",
        (_T + "domain/raven/test_s4_s6_s7.py", VAL),
        "mission-rule implementation verified; unknown inputs are not labelled as failures; mission policy remains a design choice",
    ),
    E(
        "s7.mission",
        "s7",
        "not_validated",
        "link-usable, state and useful-hour flags",
        "scalar re-implementation (arithmetic); Malapert golden",
        "1e-9",
        "the definition of a useful hour is a design choice (tag I)",
        (
            _T + "domain/raven/test_s4_s6_s7.py",
            _T + "domain/test_lunar_coupled.py",
            "tests/backend/domain/golden/real.json",
        ),
        "definitions are design choices, stated",
    ),
    E(
        "time.windows",
        "time",
        "verified",
        "window edges refined by bisection",
        "analytic sinusoidal Sun (re-implementation)",
        "<= 1 s",
        "one change per step assumed; edges next to unknown steps are not refined; `useful` stays at the step",
        (_T + "domain/raven/test_windows.py", MODEL),
        "window edges refined to 1 s for lit and link-usable; useful windows at the sampling step",
    ),
    E(
        "claims.not_rerun",
        "s7",
        "unknown",
        "claims of earlier documents (Malapert Earth up to 10.7 deg, sunset of about 8 days, relay 77 % / 100 %)",
        "not re-run with `evaluate`",
        "unknown",
        "must not be cited before being re-run",
        (MODEL,),
        "not re-run: do not quote",
    ),
)

_PARAM_STAGE_NAME = {
    "s0": "time and site", "s1": "ephemeris", "s2": "terrain", "s3": "illumination",
    "s4": "power and battery", "s5": "RF link", "s6": "DSN", "s7": "mission rules",
}  # fmt: skip


def parameter_groups() -> list[dict[str, Any]]:
    """Parameter groups by owner stage and tag, from the registry (V and D read from a source or
    derived by a repeatable formula; I illustrative = not validated)."""
    out: list[dict[str, Any]] = []
    for stage in reg.STAGES:
        for tag, status in (("V", "verified"), ("D", "verified"), ("I", "not_validated")):
            specs = [s for s in reg.REGISTRY.values() if s.stage == stage and s.tag == tag]
            if not specs:
                continue
            out.append(
                {
                    "id": f"params.{stage}.{tag}",
                    "stage": stage,
                    "group": _PARAM_STAGE_NAME[stage],
                    "tag": tag,
                    "status": status,
                    "meaning": {
                        "V": "value read from a primary source (a copy, not a measurement)",
                        "D": "derived by a repeatable formula from V values",
                        "I": "illustrative design choice, to be replaced by customer data",
                    }[tag],
                    "n_parameters": len(specs),
                    "keys": [s.key for s in specs],
                    "evidence": [s.source for s in specs][:3],
                    "phrase": (
                        "illustrative parameters: results are potential under stated assumptions"
                        if tag == "I"
                        else "source read; every API answer reports the tag and the source"
                    ),
                }
            )
    return out


def validation_report() -> dict[str, Any]:
    return {
        "statuses": list(STATUSES),
        "note": (
            "Taken from docs/domain/raven-model.md (3) and docs/domain/validation.md. No row is a radio "
            "or power measurement on the Moon."
        ),
        "stages": [e.to_dict() for e in ENTRIES],
        "parameter_groups": parameter_groups(),
    }
