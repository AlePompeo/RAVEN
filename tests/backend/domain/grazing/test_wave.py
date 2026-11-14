# SPDX-License-Identifier: Apache-2.0
"""Onda 3D: motore split-step (energia, lama esatta, cresta arrotondata, determinismo, limiti), generatore, rotta."""

import math
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("scipy")
from fastapi.testclient import TestClient

from backend.bootstrap import build_app
from backend.domain.grazing.diffraction import knife_edge_loss_db
from backend.domain.grazing.wave import WaveParams, simulate_wave
from backend.domain.raven.meta import MODEL_VERSION

ROOT = Path(__file__).resolve().parents[4]


def _sec(out: dict[str, Any]) -> tuple[Any, Any]:
    s = out["section"]
    return np.array(s["nu"]), np.array(s["intensity"])


def test_energy_far_above_tends_to_one_and_deep_shadow_is_dark() -> None:
    out = simulate_wave(WaveParams(y_min_m=-100.0, y_max_m=100.0))
    y = np.array(out["section"]["y_m"])
    i = np.array(out["section"]["intensity"])
    assert abs(i[y > 80].mean() - 1.0) < 0.05
    assert i[y < -90].max() < 0.02  # deep shadow, nu ~ 15
    gy = np.array(out["y_m"])
    first = np.array(out["intensity"][0])  # x = 0: step function
    assert first[gy > 1].min() > 0.99
    assert first[gy < -1].max() < 0.01


def test_knife_edge_section_equals_exact_curve() -> None:
    out = simulate_wave(WaveParams(y_min_m=-60.0, y_max_m=60.0, n_section=800))
    nu, inten = _sec(out)
    exact = 10 ** (-knife_edge_loss_db(nu) / 10)
    assert (
        np.max(np.abs(inten - exact)) < 0.005
    )  # measured 7e-4: fringes of ~1 m are resolved at dy = 0.1 m
    assert out["section"]["max_abs_diff_vs_knife"] < 0.005
    assert not out["meta"]["warnings"]


def test_model_doc_numbers_on_the_shadow_boundary() -> None:
    out = simulate_wave(WaveParams(y_min_m=-60.0, y_max_m=60.0, n_section=800))
    nu, inten = _sec(out)
    db = {v: -10 * math.log10(float(np.interp(v, nu[::-1], inten[::-1]))) for v in (-1, 0, 1)}
    assert db[-1] == pytest.approx(-1.001, abs=0.02)
    assert db[0] == pytest.approx(6.021, abs=0.03)
    assert db[1] == pytest.approx(13.864, abs=0.05)
    assert 10 ** (-db[0] / 10) == pytest.approx(0.25, abs=0.003)


def test_rounded_ridge_differs_from_knife_edge() -> None:
    knife = simulate_wave(WaveParams(radius_m=0.0))
    rnd = simulate_wave(WaveParams(radius_m=400.0))
    assert knife["section"]["max_abs_diff_vs_knife"] < 0.005
    assert rnd["section"]["max_abs_diff_vs_knife"] > 0.02  # table: R(nu, 400 m) of the order of dB
    assert rnd["meta"]["ridge_steps"] > 100 and rnd["meta"]["x_start_m"] > 100
    assert rnd["x_m"][0] == pytest.approx(rnd["meta"]["x_start_m"], abs=1e-3)
    nu, a = _sec(knife)
    _, b = _sec(rnd)
    k = np.abs(nu) < 1.5
    assert np.max(np.abs(a[k] - b[k])) > 0.02


def test_determinism_and_shapes() -> None:
    p = WaveParams(radius_m=50.0, nx=40, ny=60, n_section=100)
    a, b = simulate_wave(p), simulate_wave(p)
    assert a == b
    assert (
        len(a["intensity"]) == len(a["x_m"]) == 40 and len(a["intensity"][0]) == len(a["y_m"]) == 60
    )
    assert a["x_m"][-1] == p.distance_m and a["meta"]["fft_size"] == 2**14
    assert all(len(str(v).split(".")[-1]) <= 4 for v in a["intensity"][5])


def test_sampling_warnings_and_budget() -> None:
    bad = simulate_wave(WaveParams(wavelength_m=1.0, dy_m=0.4, distance_m=5000.0, step_m=1000.0))
    codes = {w.split(":")[0] for w in bad["meta"]["warnings"]}
    assert {"kernel_aliasing", "paraxial"} <= codes
    fine = simulate_wave(WaveParams(wavelength_m=0.0075, dy_m=0.4, step_m=2.0, distance_m=300.0))
    assert "dy_coarse" in " ".join(fine["meta"]["warnings"])
    t = time.perf_counter()
    big = simulate_wave(WaveParams(dy_m=0.05, radius_m=400.0, distance_m=5000.0, step_m=1.0))
    assert time.perf_counter() - t < 4.0  # about 1 s here, margin for slow CI
    assert big["meta"]["fft_size"] == 2**15 and big["meta"]["steps"] <= 399
    assert "step_raised" in " ".join(big["meta"]["warnings"])


@pytest.mark.parametrize(
    "kw",
    [
        {"wavelength_m": 0.0},
        {"wavelength_m": float("nan")},
        {"radius_m": 401.0},
        {"radius_m": -1.0},
        {"distance_m": 99.0},
        {"distance_m": 100.0, "radius_m": 400.0},  # shorter than the ridge itself
        {"dy_m": 0.01},
        {"nx": 121},
        {"y_max_m": 500.0},
    ],
)
def test_engine_rejects_bad_input(kw: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        simulate_wave(WaveParams(**kw))


def _original_hi_fidelity(radius_m: float, lam: float, dist: float, n: int, dy: float) -> Any:
    """Verbatim copy of the pre-refactor generator code (compensation_demo.py approach)."""
    y = (np.arange(n) - n // 2) * dy
    fy = np.fft.fftfreq(n, dy)
    e = np.ones(n, complex)
    if radius_m == 0:
        e[y <= 0] = 0
        x_end = 0.0
    else:
        w = math.sqrt(2 * radius_m * 20.0)
        for x in np.arange(-w, w + 2.0, 2.0):
            e[y < -x * x / (2 * radius_m)] = 0
            e = np.fft.ifft(np.fft.fft(e) * np.exp(-1j * math.pi * lam * 2.0 * fy**2))
        x_end = w + 2.0
    e = np.fft.ifft(np.fft.fft(e) * np.exp(-1j * math.pi * lam * (dist - x_end) * fy**2))
    inten = np.abs(e) ** 2
    i0 = inten[(y > 300) & (y < 600)].mean()
    return -10.0 * np.log10(inten / i0)


def test_generator_output_is_bit_identical_to_pre_refactor_code() -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import gen_compensation_table as g
    finally:
        sys.path.pop(0)
    for r in (0.0, 5.0, 100.0):
        ref = _original_hi_fidelity(r, g.LAM, g.DIST, g.N, g.DY)
        assert np.array_equal(g.hi_fidelity_loss(r), ref)


def test_ridge_sensitivity_baseline_matches_generator() -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import gen_compensation_table as g
        import ridge_sensitivity as sensitivity
    finally:
        sys.path.pop(0)
    targets = -np.array([0.0, 3.0]) * math.sqrt(g.LAM * g.DIST / 2)
    y = (np.arange(g.N) - g.N // 2) * g.DY
    expected = np.interp(targets, y, g.hi_fidelity_loss(400.0))
    np.testing.assert_allclose(sensitivity.loss_at_nus(*sensitivity.CASES[0]), expected, atol=1e-10)


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    mp = pytest.MonkeyPatch()
    mp.setenv("GRAZING_DEM_ALLOW_DOWNLOAD", "0")
    mp.setenv("RATE_LIMIT_PER_MIN", "100000")
    try:
        yield TestClient(build_app())
    finally:
        mp.undo()


def test_route_get_post_and_cache(client: TestClient) -> None:
    g = client.get("/api/raven/wave", params={"radius_m": 10, "nx": 20, "ny": 30})
    assert g.status_code == 200
    body = g.json()
    assert body["model_version"] == MODEL_VERSION
    assert body["scope"] == "educational_wave" and body["mission_evaluation"] is False
    assert (
        len(body["intensity"]) == 20 and body["meta"]["radius_m"] == 10.0 and "disclaimer" in body
    )
    p = client.post(
        "/api/raven/wave", json={"radius_m": 10.04, "nx": 20, "ny": 30}
    )  # quantised to 10.0
    assert p.status_code == 200 and p.json() == body
    f = client.post("/api/raven/wave", json={"frequency_ghz": 8.4, "nx": 10, "ny": 10})
    assert f.json()["meta"]["wavelength_m"] == pytest.approx(0.03569, abs=1e-4)


@pytest.mark.parametrize(
    "bad",
    [
        {"radius_m": 1000},
        {"radius_m": "secret-xyz"},
        {"nx": 500},
        {"nope": 1},
        {"wavelength_m": 0.03, "frequency_ghz": 8.4},
        {"distance_m": 100, "radius_m": 400},
    ],
)
def test_route_422_generic_without_echo(client: TestClient, bad: dict[str, Any]) -> None:
    r = client.post("/api/raven/wave", json=bad)
    assert r.status_code == 422
    assert "secret-xyz" not in r.text and "1000" not in r.text
    q = client.get("/api/raven/wave", params={"radius_m": 999, "zzz": 1})
    assert q.status_code == 422 and "999" not in q.text
