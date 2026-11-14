# SPDX-License-Identifier: Apache-2.0
from backend.domain.raven import fresnel_estimates as f


def test_permittivity_interval_contains_the_jpl_value_and_is_tagged_estimate() -> None:
    r = f.estimate()
    eps = r["eps_real"]
    assert r["tag"] == "I" and r["finite"] is True
    assert eps["min"] < 3.7 < eps["max"]  # JPL 42-226 uses 3.7
    assert eps["min"] < eps["typical"] < eps["max"]
    assert eps["source"]


def test_loss_is_bounded_above_only_and_roughness_stays_unknown() -> None:
    r = f.estimate()
    assert (
        r["eps_imag"]["min"] == 0.0
        and r["eps_imag"]["typical"] is None
        and r["eps_imag"]["max"] > 0
    )
    rough = r["roughness_rms_m"]
    assert (
        rough["min"] is None
        and rough["typical"] is None
        and rough["max"] is None
        and rough["source"] is None
    )
