# SPDX-License-Identifier: Apache-2.0
"""Validazione del motore di efemeridi contro JPL Horizons (e un algoritmo NOAA indipendente).

Le tolleranze sono quelle MISURATE il 2026-10-20 (colonna "misurato") con un margine di 3-10x:
non sono desideri. Se un test fallisce dopo un aggiornamento di kernel o librerie, aggiornare
prima docs/ephemeris.md con la nuova misura, poi la tolleranza.

I test si saltano se l'extra `sky` o i kernel (`make ephemeris`) mancano.
"""

import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from backend.ephemeris import kernels

pytest.importorskip("skyfield")
if kernels.problems(kernels.ephemeris_dir()):
    pytest.skip("kernel NAIF assenti: eseguire `make ephemeris`", allow_module_level=True)

from backend.ephemeris.engine import (
    Engine,
    OutOfRange,
    TimeError,
    iau_rotation,
    utc_grid,
)

ROOT = Path(__file__).resolve().parents[3]
FIX = Path(__file__).parent / "fixtures" / "horizons_subpoints.json"
PHASE_A = ROOT / "tests/backend/domain/fixtures/horizons_reference.json"
SITES = ROOT / "backend/domain/data/sites.json"
MONTHS = {
    m: i + 1
    for i, m in enumerate(
        ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    )
}

# (tolleranza, misurato 2026-10-20). Angoli in gradi, distanze in km.
TOL = {
    "azel_sun_angle": (1e-5, 8.3e-7),
    "azel_earth_angle": (1e-5, 1.2e-6),
    "azel_sun_range_km": (0.05, 0.007),
    "azel_earth_range_km": (0.005, 0.00016),
    "moon_subsolar": (1e-5, 1.0e-6),
    "moon_subearth": (1e-5, 7.6e-7),
    "mars_subsolar_lon": (2e-4, 4.6e-5),
    "mars_subsolar_lat": (2e-5, 1e-6),
    "mars_bodytime_lon": (3e-4, 8.3e-5),
    "earth_subsolar_lon": (2e-3, 9.3e-4),
    "earth_subsolar_lat": (2e-5, 3e-6),
    "light_path_km": (1e-3, 1.5e-4),
    "sun_distance_km": (20.0, 7.2),
    "noaa_lat": (0.01, 0.0031),
    "noaa_lon": (0.03, 0.0122),
}


@pytest.fixture(scope="module")
def eng() -> Engine:
    return Engine()


@pytest.fixture(scope="module")
def hz() -> dict[str, Any]:
    cfg: dict[str, Any] = json.loads(FIX.read_text(encoding="utf-8"))["configs"]
    return cfg


def dlon(a: Any, b: Any) -> Any:
    return np.abs((np.asarray(a) - np.asarray(b) + 180.0) % 360.0 - 180.0)


def col(cfg: dict[str, Any], key: str) -> Any:
    return np.array([r[key] for r in cfg["rows"]])


def utcs(cfg: dict[str, Any]) -> list[str]:
    return [r["utc"] for r in cfg["rows"]]


def test_icrf_to_local_sky_axes_and_time(eng: Engine) -> None:
    t = "2027-04-07T00:00:00Z"
    lat, lon = -86.0, 35.0
    matrix = eng.icrf_to_enu("moon", lat, lon, t)
    np.testing.assert_allclose(matrix @ matrix.T, np.eye(3), atol=1e-12)
    assert np.linalg.det(matrix) == pytest.approx(1.0, abs=1e-12)

    # Compare independent spherical formulae in the lunar body frame, including a known ICRF star.
    tt, _ = eng._times(t)
    rotation = eng._moon_frame.rotation_at(tt)[:, :, 0]
    for ra, dec in ((0.0, 0.0), (90.0, 0.0), (0.0, 90.0), (37.9546, 89.2641)):
        ra, dec = math.radians(ra), math.radians(dec)
        direction = np.array(
            [math.cos(dec) * math.cos(ra), math.cos(dec) * math.sin(ra), math.sin(dec)]
        )
        x, y, z = rotation @ direction
        longitude = math.atan2(y, x) - math.radians(lon)
        latitude = math.asin(z)
        site_lat = math.radians(lat)
        east = math.cos(latitude) * math.sin(longitude)
        north = math.sin(latitude) * math.cos(site_lat) - math.cos(latitude) * math.cos(
            longitude
        ) * math.sin(site_lat)
        up = math.sin(latitude) * math.sin(site_lat) + math.cos(latitude) * math.cos(
            longitude
        ) * math.cos(site_lat)
        np.testing.assert_allclose(matrix @ direction, [east, north, up], atol=1e-12)
    assert not np.allclose(matrix, eng.icrf_to_enu("moon", lat, lon, "2027-04-08T00:00:00Z"))
    assert not np.allclose(matrix, eng.icrf_to_enu("moon", lat, lon + 30, t))


# --------------------------------------------------------------------------- fixture di fase A


def test_phase_a_azel_sun_earth(eng: Engine) -> None:
    ref = json.loads(PHASE_A.read_text(encoding="utf-8"))["values"]
    sites = {s["id"]: s for s in json.loads(SITES.read_text(encoding="utf-8"))["sites"]}
    assert len(ref) == 24
    worst = {"sun": [0.0, 0.0], "earth": [0.0, 0.0]}  # [angolo, range]
    for v in ref:
        y, mo, d = v["time_ut"].split()[0].split("-")
        s = sites[v["site"]]
        r = eng.topocentric_azel(
            "moon",
            s["lat_deg"],
            s["lon_deg_east"],
            v["target"],
            f"{y}-{MONTHS[mo]:02d}-{d}T00:00:00Z",
        )
        daz = dlon(r.az_deg, v["az_deg"]) * math.cos(math.radians(v["el_deg"]))
        w = worst[v["target"]]
        w[0] = max(w[0], float(daz), abs(float(r.el_deg) - v["el_deg"]))
        w[1] = max(w[1], abs(float(r.range_km) - v["range_km"]))
    assert worst["sun"][0] < TOL["azel_sun_angle"][0]
    assert worst["earth"][0] < TOL["azel_earth_angle"][0]
    assert worst["sun"][1] < TOL["azel_sun_range_km"][0]
    assert worst["earth"][1] < TOL["azel_earth_range_km"][0]


# --------------------------------------------------------------------------- sub-punti


def test_moon_subsolar_and_subearth_vs_horizons(eng: Engine, hz: dict[str, Any]) -> None:
    c = hz["moon_from_geocentre"]
    p = eng.subsolar_point("moon", utcs(c), seen_from="earth")
    assert dlon(p.lon_deg_east, col(c, "sun_sub_lon")).max() < TOL["moon_subsolar"][0]
    assert np.abs(p.lat_deg - col(c, "sun_sub_lat")).max() < TOL["moon_subsolar"][0]
    q = eng.sub_earth_point("moon", utcs(c))
    assert dlon(q.lon_deg_east, col(c, "obs_sub_lon")).max() < TOL["moon_subearth"][0]
    assert np.abs(q.lat_deg - col(c, "obs_sub_lat")).max() < TOL["moon_subearth"][0]
    # stato della Luna "all'ora della Luna" (default): differisce solo per 1.3 s di rotazione
    b = eng.subsolar_point("moon", utcs(c))
    assert dlon(b.lon_deg_east, p.lon_deg_east).max() < 3e-4


def test_mars_subsolar_vs_horizons(eng: Engine, hz: dict[str, Any]) -> None:
    # Horizons: IAU_MARS, longitudine OVEST e latitudine planetografica -> Est / planetocentrica
    for name, seen in (("mars_from_geocentre", "earth"), ("mars_from_phobos", None)):
        c = hz[name]
        p = eng.subsolar_point("mars", utcs(c), seen_from=seen)
        lon_h = -col(c, "sun_sub_lon")
        lat_g = eng.geodetic_lat_deg("mars", p.lat_deg)
        tol_lon = TOL["mars_subsolar_lon" if seen else "mars_bodytime_lon"][0]
        assert dlon(p.lon_deg_east, lon_h).max() < tol_lon, name
        assert np.abs(lat_g - col(c, "sun_sub_lat")).max() < TOL["mars_subsolar_lat"][0], name
    c = hz["mars_from_geocentre"]
    q = eng.sub_earth_point("mars", utcs(c))
    assert dlon(q.lon_deg_east, -col(c, "obs_sub_lon")).max() < TOL["mars_subsolar_lon"][0]
    assert (
        np.abs(eng.geodetic_lat_deg("mars", q.lat_deg) - col(c, "obs_sub_lat")).max()
        < TOL["mars_subsolar_lat"][0]
    )


def test_earth_subsolar_vs_horizons(eng: Engine, hz: dict[str, Any]) -> None:
    c = hz["earth_from_moon"]
    p = eng.subsolar_point("earth", utcs(c), seen_from="moon")
    assert dlon(p.lon_deg_east, col(c, "sun_sub_lon")).max() < TOL["earth_subsolar_lon"][0]
    lat_g = eng.geodetic_lat_deg("earth", p.lat_deg)
    assert np.abs(lat_g - col(c, "sun_sub_lat")).max() < TOL["earth_subsolar_lat"][0]


def noaa_subsolar(dt: datetime) -> tuple[float, float]:
    """NOAA GML "Solar Calculator" (Meeus, Astronomical Algorithms): declinazione ed equazione del tempo.

    https://gml.noaa.gov/grad/solcalc/calcdetails.html  Indipendente da Skyfield/JPL, ~0.01 gradi.
    """
    jd = (dt - datetime(2000, 1, 1, 12, tzinfo=UTC)).total_seconds() / 86400 + 2451545.0
    jc = (jd - 2451545.0) / 36525
    rad = math.radians
    l0 = (280.46646 + jc * (36000.76983 + jc * 0.0003032)) % 360
    m = 357.52911 + jc * (35999.05029 - 0.0001537 * jc)
    e = 0.016708634 - jc * (0.000042037 + 0.0000001267 * jc)
    c = (
        math.sin(rad(m)) * (1.914602 - jc * (0.004817 + 0.000014 * jc))
        + math.sin(rad(2 * m)) * (0.019993 - 0.000101 * jc)
        + math.sin(rad(3 * m)) * 0.000289
    )
    om = 125.04 - 1934.136 * jc
    lam = l0 + c - 0.00569 - 0.00478 * math.sin(rad(om))
    ob0 = 23 + (26 + (21.448 - jc * (46.815 + jc * (0.00059 - jc * 0.001813))) / 60) / 60
    ob = ob0 + 0.00256 * math.cos(rad(om))
    decl = math.degrees(math.asin(math.sin(rad(ob)) * math.sin(rad(lam))))
    y = math.tan(rad(ob / 2)) ** 2
    eot_min = 4 * math.degrees(
        y * math.sin(2 * rad(l0))
        - 2 * e * math.sin(rad(m))
        + 4 * e * y * math.sin(rad(m)) * math.cos(2 * rad(l0))
        - 0.5 * y * y * math.sin(4 * rad(l0))
        - 1.25 * e * e * math.sin(2 * rad(m))
    )
    hours = dt.hour + dt.minute / 60 + dt.second / 3600
    return decl, ((-(15 * (hours - 12) + eot_min / 4)) + 180) % 360 - 180


def test_earth_subsolar_vs_noaa_independent(eng: Engine) -> None:
    rng = np.random.default_rng(7)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    span = (datetime(2031, 1, 1, tzinfo=UTC) - start).total_seconds()
    dts = [start + timedelta(seconds=int(span * float(rng.random()))) for _ in range(100)]
    p = eng.subsolar_point("earth", dts)
    ref = [noaa_subsolar(d) for d in dts]
    assert np.abs(p.lat_deg - np.array([r[0] for r in ref])).max() < TOL["noaa_lat"][0]
    assert dlon(p.lon_deg_east, np.array([r[1] for r in ref])).max() < TOL["noaa_lon"][0]


# --------------------------------------------------------------------------- distanze


def test_distances_vs_horizons(eng: Engine, hz: dict[str, Any]) -> None:
    c = hz["moon_from_geocentre"]
    d = eng.distance_km("earth", "moon", utcs(c), light_path=True)  # osservatore: geocentro
    assert np.abs(d - col(c, "delta_km")).max() < TOL["light_path_km"][0]
    # la distanza simultanea differisce da quella del percorso della luce di v_orbitale * tempo di luce
    sim = eng.distance_km("earth", "moon", utcs(c))
    assert 1.0 < np.abs(sim - d).max() < 60.0
    for name, body in (
        ("moon_from_geocentre", "moon"),
        ("mars_from_phobos", "mars"),
        ("earth_from_moon", "earth"),
    ):
        cc = hz[name]
        r = eng.sun_distance_au(body, utcs(cc)) * 149597870.7
        assert np.abs(r - col(cc, "r_km")).max() < TOL["sun_distance_km"][0], name


# --------------------------------------------------------------------------- invarianti


def test_subsolar_latitude_bounded_by_obliquity(eng: Engine) -> None:
    ts = utc_grid("2026-01-01T00:00:00Z", "2028-01-01T00:00:00Z", 86400.0 * 3)
    assert (
        np.abs(eng.subsolar_point("moon", ts).lat_deg).max() < 1.7
    )  # 1.54 deg + piccole variazioni
    assert np.abs(eng.subsolar_point("earth", ts).lat_deg).max() < 23.5
    assert np.abs(eng.subsolar_point("mars", ts).lat_deg).max() < 25.4  # obliquita' 25.19 deg


def test_rotation_rates(eng: Engine) -> None:
    def rate(body: str, t0: str, days: float) -> float:
        ts = utc_grid(t0, "2027-12-31T00:00:00Z", 3600.0)[: int(days * 24) + 1]
        lon = np.unwrap(np.radians(eng.subsolar_point(body, ts).lon_deg_east))
        return float(np.degrees(lon[-1] - lon[0]) / days)

    # media su un mese sinodico: 360/29.530589 = 12.19 gradi/giorno (misurato -12.168 nel marzo 2027)
    assert rate("moon", "2027-03-01T00:00:00Z", 29.530589) == pytest.approx(-12.19, abs=0.1)
    assert rate("moon", "2027-03-01T00:00:00Z", 1.0) == pytest.approx(-12.19, abs=0.7)
    assert rate("earth", "2027-03-01T00:00:00Z", 1.0) == pytest.approx(-360.0, abs=0.05)
    assert rate("mars", "2027-03-01T00:00:00Z", 1.0) == pytest.approx(-350.36, abs=0.2)


def test_earth_moon_distance_range(eng: Engine) -> None:
    ts = utc_grid("2026-11-01T00:00:00Z", "2027-11-01T00:00:00Z", 6 * 3600.0)
    d = eng.distance_km("earth", "moon", ts)
    assert 356_000 < d.min() < 360_000 and 405_000 < d.max() < 407_500


def test_sun_distance_ranges(eng: Engine) -> None:
    ts = utc_grid("2027-01-01T00:00:00Z", "2028-12-31T00:00:00Z", 86400.0 * 5)
    e = eng.sun_distance_au("earth", ts)
    assert 0.9832 < e.min() < 0.9835 and 1.0165 < e.max() < 1.0168
    m = eng.sun_distance_au(
        "mars", utc_grid("2026-01-01T00:00:00Z", "2030-01-01T00:00:00Z", 86400.0 * 10)
    )
    assert 1.37 < m.min() < 1.40 and 1.64 < m.max() < 1.67


def test_vectorised_equals_scalar(eng: Engine) -> None:
    ts = utc_grid("2027-06-01T00:00:00Z", "2027-06-02T00:00:00Z", 5400.0)
    for body in ("earth", "moon", "mars"):
        p = eng.subsolar_point(body, ts)
        for i in (0, 3, len(ts) - 1):
            s = eng.subsolar_point(body, ts[i])
            assert p.lat_deg[i] == pytest.approx(float(s.lat_deg), abs=1e-10)
            assert p.lon_deg_east[i] == pytest.approx(float(s.lon_deg_east), abs=1e-10)
    r = eng.topocentric_azel("moon", -85.98, -1.67, "earth", ts)
    s2 = eng.topocentric_azel("moon", -85.98, -1.67, "earth", ts[4])
    assert r.az_deg[4] == pytest.approx(float(s2.az_deg), abs=1e-10)
    assert r.range_km[4] == pytest.approx(float(s2.range_km), abs=1e-6)
    assert np.shape(s2.az_deg) == ()


def test_sun_overhead_at_subsolar_point(eng: Engine) -> None:
    """Due percorsi di calcolo indipendenti nel codice: sub-solare (direzione) e az-el (sito)."""
    t = "2027-05-17T08:09:10Z"
    for body in ("moon", "earth", "mars"):
        p = eng.subsolar_point(body, t)
        # la declinazione del Sole nel frame del corpo e' la latitudine GEODETICA del punto allo zenit
        r = eng.topocentric_azel(body, float(p.lat_deg), float(p.lon_deg_east), "sun", t)
        assert float(r.el_deg) > 89.99, body


def test_viewer_axes_and_iau_axes(eng: Engine) -> None:
    ts = utc_grid("2027-02-01T00:00:00Z", "2027-02-03T00:00:00Z", 7200.0)
    for body in ("moon", "earth", "mars"):
        p = eng.subsolar_point(body, ts)
        la, lo = np.radians(p.lat_deg), np.radians(p.lon_deg_east)
        v = eng.solar_direction_body_fixed(body, ts)
        expected = np.stack([np.cos(la) * np.sin(lo), np.sin(la), np.cos(la) * np.cos(lo)], -1)
        assert np.allclose(v, expected, atol=1e-12)
        assert np.allclose(np.linalg.norm(v, axis=-1), 1.0, atol=1e-12)
        i = eng.solar_direction_body_fixed(body, ts, frame="iau")
        assert (
            np.allclose(i[:, 0], v[:, 2])
            and np.allclose(i[:, 1], v[:, 0])
            and np.allclose(i[:, 2], v[:, 1])
        )
    assert eng.solar_direction_body_fixed("moon", ts[0]).shape == (3,)


def test_libration_bounds(eng: Engine) -> None:
    q = eng.sub_earth_point(
        "moon", utc_grid("2026-12-01T00:00:00Z", "2028-12-01T00:00:00Z", 86400.0)
    )
    assert (
        np.abs(q.lat_deg).max() < 7.0 and np.abs(q.lon_deg_east).max() < 8.1
    )  # fase A: +6.83 / +7.63


def test_mars_iau_rotation_is_proper(eng: Engine) -> None:
    r = iau_rotation(eng._mars_vars, 499, 4, np.array([2461000.5, 2462000.5]))
    for m in r:
        assert np.allclose(m @ m.T, np.eye(3), atol=1e-12) and np.linalg.det(m) == pytest.approx(
            1.0
        )


# --------------------------------------------------------------------------- tempo e intervallo


def test_input_validation(eng: Engine) -> None:
    for bad in (
        "2027-01-01T00:00:00",
        "2027-01-01 00:00:00Z",
        "2027-02-30T00:00:00Z",
        "x",
        "2027-01-01T00:00:00+01:00",
    ):
        with pytest.raises(TimeError):
            eng.subsolar_point("moon", bad)
    with pytest.raises(TimeError):
        eng.subsolar_point("moon", datetime(2027, 1, 1))  # naive
    with pytest.raises(ValueError):
        eng.subsolar_point("sun", "2027-01-01T00:00:00Z")
    with pytest.raises(ValueError):
        eng.topocentric_azel("moon", 95.0, 0.0, "sun", "2027-01-01T00:00:00Z")
    with pytest.raises(TimeError):
        eng.subsolar_point("moon", [])


def test_supported_range_enforced(eng: Engine) -> None:
    lo, hi = eng.supported_range()
    assert lo == datetime(1972, 1, 1, tzinfo=UTC) and datetime(
        2150, 1, 1, tzinfo=UTC
    ) < hi < datetime(2150, 1, 22, tzinfo=UTC)
    eng.subsolar_point("moon", lo)
    eng.subsolar_point("mars", hi)
    for bad in ("1971-12-31T23:59:59Z", "2150-01-22T00:00:00Z", "1900-01-01T00:00:00Z"):
        with pytest.raises(OutOfRange):
            eng.subsolar_point("moon", bad)
    assert eng.info()["versions"]["skyfield"] == "1.55"


def test_microseconds_and_datetime_equivalent(eng: Engine) -> None:
    a = eng.subsolar_point("moon", "2027-03-03T03:03:03.250000Z")
    b = eng.subsolar_point("moon", datetime(2027, 3, 3, 3, 3, 3, 250000, tzinfo=UTC))
    assert float(a.lon_deg_east) == float(b.lon_deg_east)
