# SPDX-License-Identifier: Apache-2.0
"""Motore di efemeridi per Sole, Terra, Luna e Marte (JPL DE440 + orientamento dei corpi).

Convenzioni (vedi docs/ephemeris.md):

* Tempo: ingresso solo UTC (ISO-8601 con `Z`, oppure `datetime` con offset 0). UTC -> TT/TDB con i
  secondi intercalari e il Delta-T integrati in Skyfield; UT1 e' quello PREDETTO da Skyfield (nessun
  file EOP): l'errore di UT1 si riflette solo sulla rotazione terrestre.
* Posizioni: DE440s (Sole, Terra, Luna, baricentro di Marte, che coincide col centro di Marte entro
  decimetri). Direzione del Sole APPARENTE (tempo di luce + aberrazione dalla velocita' del corpo +
  deflessione relativistica), come "apparent" di JPL Horizons.
* Orientamento: Luna = frame MOON_ME_DE440_ME421 (Mean Earth/Polar Axis, kernel NAIF PA+FK);
  Terra = ITRS di Skyfield; Marte = modello IAU (pck00011.tpc, Archinal et al.) implementato qui,
  perche' Skyfield non supporta i PCK testuali.
* Longitudine EST positiva; latitudine PLANETOCENTRICA (angolo del vettore dal piano equatoriale):
  e' quello che serve a una sfera texturizzata. Per le funzioni topocentriche la latitudine del sito
  e' GEODETICA sull'ellissoide di riferimento (Luna: sfera 1737.4 km, dove coincide col planetocentrico).
* Assi del viewer (`frame="viewer"`): x = Est a lon 90 (Y del corpo), y = Nord (Z), z = lon 0 (X),
  cioe' (cos(lat) sin(lon), sin(lat), cos(lat) cos(lon)); terna destrorsa.
* Non modellati: rifrazione, terreno/orizzonte locale, velocita' di rotazione della superficie
  nell'aberrazione (<= 0.0001 gradi sulla Terra), dimensione finita dei dischi.
"""

import importlib
import math
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import numpy as np
from numpy.typing import NDArray

from backend.ephemeris import kernels
from backend.ephemeris.timeutil import MAX_SAMPLES, TimeError, parse_utc, utc_grid

__all__ = [
    "AzElRange",
    "Engine",
    "LatLon",
    "OutOfRange",
    "TimeError",
    "get_engine",
    "iau_rotation",
    "parse_utc",
    "utc_grid",
]

Body = Literal["sun", "earth", "moon", "mars"]
Float = NDArray[np.float64]
Instants = str | datetime | Sequence[str | datetime]

AU_KM = 149597870.7
J2000_JD = 2451545.0
BODIES: tuple[str, ...] = ("sun", "earth", "moon", "mars")
SURFACE_BODIES: tuple[str, ...] = ("earth", "moon", "mars")
# L'era dei secondi intercalari interi inizia nel 1972: prima di allora UTC e' un'approssimazione.
UTC_ERA_START = datetime(1972, 1, 1, tzinfo=UTC)
MARGIN = timedelta(days=1)  # margine per tempo di luce e istanti ritardati ai bordi dell'SPK

_WGS84 = (6378.137, 6356.752314245)  # km, semiasse maggiore e minore
_MOON_R = 1737.4  # km, sfera di riferimento (come JPL Horizons e il registro dei siti)


class OutOfRange(ValueError):
    """Istante fuori dall'intervallo coperto dai kernel."""


@dataclass(frozen=True)
class LatLon:
    """Punto sulla superficie: latitudine planetocentrica, longitudine Est in [-180, 180)."""

    lat_deg: Float
    lon_deg_east: Float


@dataclass(frozen=True)
class AzElRange:
    """Azimut (0 = Nord locale, orario), elevazione sull'orizzonte locale, distanza (km)."""

    az_deg: Float
    el_deg: Float
    range_km: Float


def _wrap180(lon: Float) -> Float:
    return np.asarray((lon + 180.0) % 360.0 - 180.0, dtype=np.float64)


def _unit(v: Float) -> Float:
    return np.asarray(v / np.linalg.norm(v, axis=-1, keepdims=True), dtype=np.float64)


def _latlon_from_unit(u: Float) -> LatLon:
    return LatLon(
        np.degrees(np.arcsin(np.clip(u[:, 2], -1.0, 1.0))),
        _wrap180(np.degrees(np.arctan2(u[:, 1], u[:, 0]))),
    )


def _rz(a: Float) -> Float:
    c, s, z, o = np.cos(a), np.sin(a), np.zeros_like(a), np.ones_like(a)
    return np.stack(
        [np.stack([c, s, z], -1), np.stack([-s, c, z], -1), np.stack([z, z, o], -1)], -2
    )


def _rx(a: Float) -> Float:
    c, s, z, o = np.cos(a), np.sin(a), np.zeros_like(a), np.ones_like(a)
    return np.stack(
        [np.stack([o, z, z], -1), np.stack([z, c, s], -1), np.stack([z, -s, c], -1)], -2
    )


def iau_rotation(variables: dict[str, Any], body_id: int, system_id: int, tdb_jd: Float) -> Float:
    """Matrici ICRF -> corpo (N,3,3) dal modello IAU in un PCK testuale NAIF.

    alpha = a0 + a1 T + a2 T^2 + sum_i A_i sin(theta_i);  delta = ... + sum_i D_i cos(theta_i);
    W = w0 + w1 d + w2 d^2 + sum_i W_i sin(theta_i);  theta_i = t0 + t1 T + t2 T^2
    (T secoli giuliani, d giorni da J2000 TDB; Archinal et al. 2018, formule NAIF "rotation
    constants"). Matrice = R3(W) R1(90 deg - delta) R3(90 deg + alpha).
    """
    d = np.asarray(tdb_jd, dtype=np.float64) - J2000_JD
    T = d / 36525.0
    pre = f"BODY{body_id}_"
    ra, dec, pm = (
        np.asarray(variables[pre + k], dtype=np.float64) for k in ("POLE_RA", "POLE_DEC", "PM")
    )
    alpha = ra[0] + ra[1] * T + ra[2] * T**2
    delta = dec[0] + dec[1] * T + dec[2] * T**2
    w = pm[0] + pm[1] * d + pm[2] * d**2
    deg = int(variables.get(f"BODY{system_id}_MAX_PHASE_DEGREE", 1))
    ang = np.asarray(variables[f"BODY{system_id}_NUT_PREC_ANGLES"], dtype=np.float64).reshape(
        -1, deg + 1
    )
    theta = np.radians(
        np.stack([sum(a[k] * T**k for k in range(deg + 1)) for a in ang], axis=-1)  # (N, n_ang)
    )
    for key, trig in (("NUT_PREC_RA", np.sin), ("NUT_PREC_DEC", np.cos), ("NUT_PREC_PM", np.sin)):
        coef = variables.get(pre + key)
        if coef is None:
            continue
        c = np.asarray(coef, dtype=np.float64)
        term = (trig(theta[:, : len(c)]) * c).sum(axis=-1)
        if key == "NUT_PREC_RA":
            alpha = alpha + term
        elif key == "NUT_PREC_DEC":
            delta = delta + term
        else:
            w = w + term
    r = _rz(np.radians(w)) @ _rx(np.radians(90.0 - delta)) @ _rz(np.radians(90.0 + alpha))
    return np.asarray(r, dtype=np.float64)


class Engine:
    """Efemeridi caricate da kernel verificati. Solo lettura dopo l'inizializzazione."""

    def __init__(self, directory: Path | None = None) -> None:
        paths = kernels.require_kernels(directory)
        try:
            self._api = importlib.import_module("skyfield.api")
            framelib = importlib.import_module("skyfield.framelib")
            positionlib = importlib.import_module("skyfield.positionlib")
            jplephem = importlib.import_module("jplephem")
        except ImportError as e:
            raise kernels.EphemerisUnavailable("extra opzionale `sky` non installato") from e
        self._barycentric = positionlib.Barycentric
        self._itrs = framelib.itrs
        self.versions = {
            "skyfield": str(importlib.import_module("skyfield").__version__),
            "jplephem": str(jplephem.__version__),
        }
        self.ts = self._api.load.timescale()
        spk = importlib.import_module("skyfield.iokit").load_file(str(paths["de440s.bsp"]))
        self._spk = spk
        self._vf = {
            "sun": spk["sun"],
            "earth": spk["earth"],
            "moon": spk["moon"],
            "mars": spk["mars barycenter"],
        }
        pc = self._api.PlanetaryConstants()
        with paths["moon_de440_250416.tf"].open("rb") as tf:
            pc.read_text(tf)
        with paths["pck00011.tpc"].open("rb") as tpc:
            pc.read_text(tpc)
        # il file del PCK binario resta aperto: i dati si caricano alla prima chiamata (_warm)
        self._bpc = paths["moon_pa_de440_200625.bpc"].open("rb")
        pc.read_binary(self._bpc)
        segs = [s for s in pc._segment_list if s.body == 31008]
        # il primo segmento copre 1550-2426: contiene tutto l'intervallo di DE440s
        seg = min(segs, key=lambda s: s.initial_jd)
        self._moon_frame = pc.build_frame(31009, _segment=seg)
        self._mars_vars = dict(pc.variables)
        radii = self._mars_vars["BODY499_RADII"]
        self._radii = {
            "moon": (_MOON_R, _MOON_R),
            "earth": _WGS84,
            "mars": (float(radii[0]), float(radii[2])),
        }
        lo = max(s.time_range(self.ts)[0].tdb for s in spk.segments)
        hi = min(s.time_range(self.ts)[1].tdb for s in spk.segments)
        lo = max(lo, float(seg.initial_jd))
        hi = min(hi, float(seg.final_jd))
        self._range = (
            max(UTC_ERA_START, self.ts.tdb_jd(lo).utc_datetime() + MARGIN),
            self.ts.tdb_jd(hi).utc_datetime() - MARGIN,
        )
        self._kernels = {s.name: s.sha256 for s in kernels.load_lock()}
        self._warm()

    # ------------------------------------------------------------------ infrastruttura

    def _warm(self) -> None:
        """Una chiamata di prova: carica i segmenti e fallisce subito se qualcosa non va."""
        t = parse_utc("2027-01-01T00:00:00Z")
        for b in SURFACE_BODIES:
            self.subsolar_point(b, t)

    def supported_range(self) -> tuple[datetime, datetime]:
        """Primo e ultimo istante UTC accettati (derivati dai kernel, con margine)."""
        return self._range

    def info(self) -> dict[str, Any]:
        return {"versions": self.versions, "kernels": self._kernels}

    def _times(self, t: Instants) -> tuple[Any, bool]:
        scalar = isinstance(t, str | datetime)
        items: Sequence[str | datetime] = [t] if isinstance(t, str | datetime) else t
        if len(items) == 0 or len(items) > MAX_SAMPLES:
            raise TimeError("numero di istanti non valido")
        dts = [parse_utc(x) for x in items]
        lo, hi = self._range
        if min(dts) < lo or max(dts) > hi:
            raise OutOfRange(
                f"istante fuori intervallo: {lo:%Y-%m-%dT%H:%M:%SZ} .. {hi:%Y-%m-%dT%H:%M:%SZ}"
            )
        return self.ts.from_datetimes(dts), scalar

    @staticmethod
    def _out(a: Float, scalar: bool) -> Float:
        return np.asarray(a[0] if scalar else a, dtype=np.float64)

    def _check(self, body: str, allowed: tuple[str, ...] = SURFACE_BODIES) -> None:
        if body not in allowed:
            raise ValueError(f"corpo non supportato: scegliere tra {', '.join(allowed)}")

    def _epoch(self, body: str, t: Any, seen_from: str | None) -> Any:
        """Istante (TDB) in cui il corpo e' osservato; con `seen_from` sottrae il tempo di luce."""
        if seen_from is None:
            return t
        self._check(seen_from, SURFACE_BODIES)
        if seen_from == body:
            raise ValueError("osservatore e corpo coincidono")
        lt = self._vf[seen_from].at(t).observe(self._vf[body]).light_time
        return self.ts.tdb_jd(t.tdb - lt)

    def _rotation(self, body: str, tb: Any) -> Float:
        """Matrici ICRF -> frame solidale al corpo, shape (N,3,3)."""
        if body == "moon":
            r = self._moon_frame.rotation_at(tb)
            return np.asarray(np.moveaxis(r, -1, 0), dtype=np.float64)
        if body == "earth":
            r = self._itrs.rotation_at(tb)
            return np.asarray(np.moveaxis(r, -1, 0), dtype=np.float64)
        return iau_rotation(self._mars_vars, 499, 4, np.atleast_1d(tb.tdb))

    @staticmethod
    def _bf(R: Float, v_km: Float) -> Float:
        """Vettore (3,N) ICRF -> (N,3) nel frame del corpo."""
        return np.asarray(np.einsum("nij,jn->ni", R, v_km), dtype=np.float64)

    @staticmethod
    def _viewer(u: Float) -> Float:
        return np.stack([u[:, 1], u[:, 2], u[:, 0]], axis=-1)

    # ------------------------------------------------------------------ API pubblica

    def _sun_dir(self, body: str, t: Instants, seen_from: str | None) -> tuple[Float, bool]:
        self._check(body)
        tt, scalar = self._times(t)
        tb = self._epoch(body, tt, seen_from)
        app = self._vf[body].at(tb).observe(self._vf["sun"]).apparent()
        u = _unit(self._bf(self._rotation(body, tb), app.position.km))
        return u, scalar

    def subsolar_point(self, body: str, t: Instants, seen_from: str | None = None) -> LatLon:
        """Punto subsolare di `body` a un istante UTC.

        Per default e' lo stato del corpo all'istante t (ora del corpo). Con `seen_from` (altro
        corpo) il corpo e' quello visto da li' a t: stesso significato di JPL Horizons SunSub.
        """
        u, scalar = self._sun_dir(body, t, seen_from)
        p = _latlon_from_unit(u)
        return LatLon(self._out(p.lat_deg, scalar), self._out(p.lon_deg_east, scalar))

    def solar_direction_body_fixed(
        self, body: str, t: Instants, frame: Literal["viewer", "iau"] = "viewer"
    ) -> Float:
        """Versore corpo -> Sole (apparente) nel frame solidale al corpo.

        `viewer`: (cos lat sin lon, sin lat, cos lat cos lon) come `latLonToBody` del frontend;
        `iau`: X verso lon 0 / lat 0, Y verso 90 E, Z polo Nord.
        """
        u, scalar = self._sun_dir(body, t, None)
        if frame == "viewer":
            u = self._viewer(u)
        elif frame != "iau":
            raise ValueError("frame non valido")
        return np.asarray(u[0] if scalar else u, dtype=np.float64)

    def sub_earth_point(self, body: str, t: Instants) -> LatLon:
        """Punto del corpo sotto il centro della Terra, visto dal geocentro (librazione per la Luna)."""
        self._check(body, ("moon", "mars"))
        tt, scalar = self._times(t)
        ast = self._vf["earth"].at(tt).observe(self._vf[body])
        tb = self.ts.tdb_jd(tt.tdb - ast.light_time)
        u = _unit(self._bf(self._rotation(body, tb), -ast.position.km))
        p = _latlon_from_unit(u)
        return LatLon(self._out(p.lat_deg, scalar), self._out(p.lon_deg_east, scalar))

    def _site(
        self, body: str, lat_deg: float, lon_deg_east: float, h_m: float
    ) -> tuple[Float, Float]:
        """Vettore del sito (km, frame del corpo) e base locale (E, N, U) come righe."""
        if not (math.isfinite(lat_deg) and -90.0 <= lat_deg <= 90.0):
            raise ValueError("latitudine non valida")
        if not (math.isfinite(lon_deg_east) and math.isfinite(h_m)):
            raise ValueError("longitudine o quota non valida")
        a, c = self._radii[body]
        e2 = 1.0 - (c / a) ** 2
        la, lo = math.radians(lat_deg), math.radians(lon_deg_east)
        sl, cl, so, co = math.sin(la), math.cos(la), math.sin(lo), math.cos(lo)
        n = a / math.sqrt(1.0 - e2 * sl * sl)
        h = h_m / 1000.0
        pos = np.array([(n + h) * cl * co, (n + h) * cl * so, (n * (1.0 - e2) + h) * sl])
        enu = np.array([[-so, co, 0.0], [-sl * co, -sl * so, cl], [cl * co, cl * so, sl]])
        return pos, enu

    def icrf_to_enu(
        self, body: str, lat_deg: float, lon_deg_east: float, t: str | datetime
    ) -> Float:
        """Rotation from ICRF to the site's east, north, up frame at the observation instant."""
        self._check(body)
        tt, _ = self._times(t)
        _, enu = self._site(body, lat_deg, lon_deg_east, 0.0)
        return np.asarray(enu @ self._rotation(body, tt)[0], dtype=np.float64)

    def topocentric_azel(
        self,
        site_body: str,
        lat_deg: float,
        lon_deg_east: float,
        target: str,
        t: Instants,
        h_m: float = 0.0,
    ) -> AzElRange:
        """Azimut/elevazione apparenti (senza rifrazione) di `target` da un sito di `site_body`.

        Il sito e' geodetico sull'ellissoide di riferimento; l'orizzonte e' il piano locale
        dell'ellissoide (nessun terreno). `range_km` = distanza astrometrica (tempo di luce).
        """
        self._check(site_body)
        self._check(target, BODIES)
        if target == site_body:
            raise ValueError("bersaglio e corpo del sito coincidono")
        tt, scalar = self._times(t)
        pos_bf, enu = self._site(site_body, lat_deg, lon_deg_east, h_m)
        R = self._rotation(site_body, tt)  # ICRF -> corpo (N,3,3)
        centre = self._vf[site_body].at(tt)
        off_icrf = np.einsum("nji,j->in", R, pos_bf)  # R^T pos, (3,N) km
        obs = self._barycentric(
            centre.position.au + off_icrf / AU_KM, centre.velocity.au_per_d, tt, 0
        )
        obs._ephemeris = self._spk  # richiesto da apparent() per la deflessione (skyfield 1.55)
        ast = obs.observe(self._vf[target])
        app = ast.apparent()
        local = np.einsum("ij,nj->ni", enu, self._bf(R, app.position.km))  # (N,3) = E,N,U
        u = _unit(local)
        az = np.degrees(np.arctan2(u[:, 0], u[:, 1])) % 360.0
        el = np.degrees(np.arcsin(np.clip(u[:, 2], -1.0, 1.0)))
        rng = np.linalg.norm(ast.position.km, axis=0)
        return AzElRange(self._out(az, scalar), self._out(el, scalar), self._out(rng, scalar))

    def distance_km(self, a: str, b: str, t: Instants, light_path: bool = False) -> Float:
        """Distanza tra i centri.

        Default: a TDB comune (stesso istante). Con `light_path=True`: lunghezza del percorso della
        luce da `b` ad `a` (astrometrica, = `delta` di JPL Horizons); differisce da quella
        simultanea di v_orbitale * tempo di luce (fino a ~40 km per Terra-Luna).
        """
        self._check(a, BODIES)
        self._check(b, BODIES)
        tt, scalar = self._times(t)
        if light_path:
            d = self._vf[a].at(tt).observe(self._vf[b]).position.km
        else:
            d = self._vf[a].at(tt).position.km - self._vf[b].at(tt).position.km
        return self._out(np.linalg.norm(d, axis=0), scalar)

    def sun_distance_au(self, body: str, t: Instants) -> Float:
        """Distanza Sole-corpo (centri, stesso istante) in unita' astronomiche."""
        self._check(body)
        return self.distance_km(body, "sun", t) / AU_KM

    def geodetic_lat_deg(self, body: str, planetocentric_lat_deg: Float) -> Float:
        """Latitudine geodetica sull'ellissoide di riferimento: tan(phi_g) = tan(phi_c) (a/c)^2."""
        self._check(body)
        a, c = self._radii[body]
        phi = np.radians(np.asarray(planetocentric_lat_deg, dtype=np.float64))
        return np.asarray(np.degrees(np.arctan(np.tan(phi) * (a / c) ** 2)), dtype=np.float64)


_engine: Engine | None = None
_lock = threading.Lock()


def get_engine() -> Engine:
    """Motore predefinito (EPHEMERIS_DIR); `EphemerisUnavailable` se i kernel mancano."""
    global _engine
    with _lock:
        if _engine is None:
            _engine = Engine()
        return _engine


def reset_engine() -> None:
    global _engine
    with _lock:
        _engine = None


def subsolar_point(body: str, t: Instants) -> LatLon:
    return get_engine().subsolar_point(body, t)


def sub_earth_point(body: str, t: Instants) -> LatLon:
    return get_engine().sub_earth_point(body, t)


def topocentric_azel(
    site_body: str, lat_deg: float, lon_deg_east: float, target: str, t: Instants
) -> AzElRange:
    return get_engine().topocentric_azel(site_body, lat_deg, lon_deg_east, target, t)


def distance_km(a: str, b: str, t: Instants) -> Float:
    return get_engine().distance_km(a, b, t)


def sun_distance_au(body: str, t: Instants) -> Float:
    return get_engine().sun_distance_au(body, t)


def solar_direction_body_fixed(
    body: str, t: Instants, frame: Literal["viewer", "iau"] = "viewer"
) -> Float:
    return get_engine().solar_direction_body_fixed(body, t, frame)
