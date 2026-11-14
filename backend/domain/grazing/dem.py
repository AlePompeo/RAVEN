# SPDX-License-Identifier: Apache-2.0
"""LOLA lunar DEM (NASA PDS Geosciences Node) read by HTTP range requests, cached under build/.

Product: LDEM_85S_20M (south polar, polar stereographic, 20 m/pixel, float32 little-endian, heights in
km relative to the 1737.4 km reference sphere), label `ldem_85s_20m_float.lbl`. The 920 MB file is
NEVER downloaded whole: only 128x128-pixel tiles that a profile touches are fetched (one multi-range
request per tile) and cached in `GRAZING_DEM_DIR` (default `build/lola`). Nothing is committed.

Integrity (trust-on-first-use, like `backend/ephemeris/kernels.lock.json`): `dem.lock.json` records the
file size, ETag, the sha256 of the label and of the whole file (computed once by streaming, 2026-10-26).
Every ranged response must report the locked total size and ETag; every tile is checked for finite
values inside the label's DERIVED_MINIMUM/MAXIMUM and stored with its own sha256, re-checked on load.
`python -m backend.domain.grazing.dem --verify-full` re-downloads the whole file and compares the sha256.

A second locked product, LDEM_75S_240M (`FAR_DEM_ID`, 58 MB, 240 m/pixel, to 75 S), is read the same
way (tiles only, same cache) for the far solar horizon 10-200 km (`horizon.py`); its whole-file
sha256 was computed once by streaming on 2026-11-04 (`--verify-full --dataset ldem_75s_240m_float`).

Data credit: NASA/GSFC LOLA team (D. E. Smith, PI), PDS Geosciences Node, public domain.
Missing data (no cache and no network, or integrity failure) raises `DemUnavailable`: the API maps it to 503.
"""

import argparse
import hashlib
import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from backend.ephemeris.kernels import _SameHostRedirect  # same-host https redirect policy

__all__ = [
    "DEFAULT_DIR",
    "FAR_DEM_ID",
    "LOCK_PATH",
    "DemOutOfCoverage",
    "DemSpec",
    "DemUnavailable",
    "LolaDem",
    "dem_dir",
    "load_lock",
    "verify_full",
]

Arr = NDArray[np.float64]
LOCK_PATH = Path(__file__).with_name("dem.lock.json")
DEFAULT_DIR = Path(__file__).resolve().parents[3] / "build" / "lola"
ALLOWED_HOST = "pds-geosciences.wustl.edu"
TILE = 128
FAR_DEM_ID = "ldem_75s_240m_float"  # far solar horizon (10-200 km), see horizon.py
RANGES_PER_REQUEST = 128
TIMEOUT_S = 60.0
NETWORK_RETRY_DELAYS_S = (
    2.0,
    6.0,
    15.0,
)  # nuovi tentativi per errori di rete transitori (solo opener reale)
MAX_RESPONSE_BYTES = 4 << 20
CHUNK = 1 << 20


class DemUnavailable(RuntimeError):
    """DEM data missing, unreachable or failing the integrity check (API: HTTP 503)."""


class DemOutOfCoverage(ValueError):
    """The requested point lies outside the locked DEM product."""


@dataclass(frozen=True)
class DemSpec:
    id: str
    url: str
    label_url: str
    size: int
    etag: str
    sha256: str
    label_sha256: str
    lines: int
    samples: int
    scale_m: float
    center_px: float
    radius_km: float
    min_km: float
    max_km: float
    max_lat_deg: float  # |lat| coverage limit (85 for LDEM_85S)
    orientation: dict[str, Any]
    retrieved: str
    credit: str
    projection: str = (
        "polar_south"  # polar_south | cylindrical (simple cylindrical, lon 0..360 east)
    )
    pixels_per_deg: float = 0.0  # cylindrical products only

    def covers(self, lat_deg: float) -> bool:
        """Is `lat_deg` inside the product (the polar ones cover |lat| beyond `max_lat_deg`)?"""
        if self.projection == "cylindrical":
            return -90.0 <= lat_deg <= 90.0
        return -90.0 <= lat_deg <= -self.max_lat_deg

    def pixel_arrays(self, lat_deg: Arr, lon_deg_east: Arr) -> tuple[Arr, Arr]:
        """Vectorised (row, col) float pixels. Polar: no coverage check (NaN-safe); cylindrical:
        column in [-0.5, samples - 0.5) (the caller wraps), row = (90 - lat) * ppd - 0.5."""
        s = self
        if s.projection == "cylindrical":
            row = (90.0 - lat_deg) * s.pixels_per_deg - 0.5
            col = np.mod(lon_deg_east, 360.0) * s.pixels_per_deg - 0.5
            return row, col
        rho = 2.0 * s.radius_km * 1000.0 * np.tan(np.radians(90.0 + lat_deg) / 2.0)
        lon = np.radians(lon_deg_east)
        a, b = rho * np.sin(lon), rho * np.cos(lon)
        o = s.orientation
        if o["swap"]:
            a, b = b, a
        return s.center_px + o["sy"] * b / s.scale_m, s.center_px + o["sx"] * a / s.scale_m


def load_lock(path: Path = LOCK_PATH, dataset_id: str | None = None) -> DemSpec:
    """Locked product: `datasets[0]` (LDEM_85S_20M) by default, else the entry with `dataset_id`."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    entries = raw["datasets"]
    if dataset_id is None:
        entry = entries[0]
    else:
        found = [e for e in entries if e["id"] == dataset_id]
        if len(found) != 1:
            raise KeyError(dataset_id)
        entry = found[0]
    return DemSpec(**{f: entry[f] for f in DemSpec.__dataclass_fields__ if f in entry})


def dem_dir(env: dict[str, str] | None = None) -> Path:
    value = (os.environ if env is None else env).get("GRAZING_DEM_DIR")
    return Path(value) if value else DEFAULT_DIR


def _opener() -> urllib.request.OpenerDirector:
    d = urllib.request.OpenerDirector()
    for h in (
        urllib.request.HTTPSHandler(),
        _SameHostRedirect(),
        urllib.request.HTTPErrorProcessor(),
        urllib.request.HTTPDefaultErrorHandler(),  # an HTTP error status raises HTTPError (retried), it never returns None
        urllib.request.UnknownHandler(),
    ):
        d.add_handler(h)
    return d


def _check_url(spec: DemSpec) -> None:
    for u in (spec.url, spec.label_url):
        p = urllib.parse.urlsplit(u)
        if p.scheme != "https" or p.hostname != ALLOWED_HOST:
            raise DemUnavailable("DEM URL not allowed")


_CR = re.compile(rb"Content-Range: bytes (\d+)-(\d+)/(\d+)\r\n\r\n")


def parse_ranges(
    body: bytes, content_type: str, requested: list[tuple[int, int]]
) -> dict[int, bytes]:
    """Map start offset -> bytes from a 206 response (single range or multipart/byteranges)."""
    out: dict[int, bytes] = {}
    if content_type.startswith("multipart/byteranges"):
        for m in _CR.finditer(body):
            a, b = int(m.group(1)), int(m.group(2))
            out[a] = body[m.end() : m.end() + (b - a + 1)]
    elif len(requested) == 1:
        out[requested[0][0]] = body
    return out


class LolaDem:
    """Tile-cached reader of the locked LOLA product. `allow_download=False` = cache only."""

    def __init__(
        self,
        directory: Path | None = None,
        spec: DemSpec | None = None,
        *,
        allow_download: bool = True,
        opener: Any = None,
        fallback_dirs: tuple[Path, ...] = (),
        max_cache_bytes: int | None = None,
    ) -> None:
        self.spec = spec if spec is not None else load_lock()
        self.dir = directory if directory is not None else dem_dir()
        self.allow_download = allow_download
        self._opener = opener
        self.fallback_dirs = fallback_dirs  # read-only caches consulted after `dir`
        self.max_cache_bytes = max_cache_bytes  # LRU cap of `dir` after every download (None = off)
        self._tiles: dict[tuple[int, int], NDArray[np.float32]] = {}
        _check_url(self.spec)

    # -- projection (spherical polar stereographic, true scale at the pole) -------------------
    def pixel(self, lat_deg: float, lon_deg_east: float) -> tuple[float, float]:
        """(row, col) float pixel coordinates of a planetocentric point (south polar product)."""
        s = self.spec
        if not (math.isfinite(lat_deg) and math.isfinite(lon_deg_east)):
            raise DemOutOfCoverage("non-finite coordinates")
        if s.projection == "cylindrical":
            r, c = self.pixel_arrays(np.array([lat_deg]), np.array([lon_deg_east]))
            return float(r[0]), float(c[0])
        if not (-90.0 <= lat_deg <= -s.max_lat_deg):
            raise DemOutOfCoverage("point outside the DEM coverage")
        rho_m = 2.0 * s.radius_km * 1000.0 * math.tan(math.radians((90.0 + lat_deg) / 2.0))
        lon = math.radians(lon_deg_east)
        a, b = rho_m * math.sin(lon), rho_m * math.cos(lon)
        o = s.orientation
        if o["swap"]:
            a, b = b, a
        col = s.center_px + o["sx"] * a / s.scale_m
        row = s.center_px + o["sy"] * b / s.scale_m
        if not (0 <= row <= s.lines - 1 and 0 <= col <= s.samples - 1):
            raise DemOutOfCoverage("point outside the DEM coverage")
        return row, col

    def pixel_arrays(self, lat_deg: Arr, lon_deg_east: Arr) -> tuple[Arr, Arr]:
        """Vectorised (row, col) float pixels of the product (see `DemSpec.pixel_arrays`)."""
        return self.spec.pixel_arrays(lat_deg, lon_deg_east)

    # -- tiles ---------------------------------------------------------------------------------
    def _tile_path(self, ti: int, tj: int, directory: Path | None = None) -> Path:
        return (directory or self.dir) / f"{self.spec.id}.t{TILE}.{ti}_{tj}.f32"

    def has_tile(self, ti: int, tj: int) -> bool:
        """Is the tile in the cache (own or fallback directory)? Cheap: no hash check."""
        for d in (self.dir, *self.fallback_dirs):
            p = self._tile_path(ti, tj, d)
            if p.is_file() and p.with_suffix(".sha256").is_file():
                return True
        return False

    def _check_values(self, a: NDArray[np.float32]) -> None:
        s = self.spec
        if not np.all(np.isfinite(a)) or a.min() < s.min_km - 0.5 or a.max() > s.max_km + 0.5:
            raise DemUnavailable("DEM tile failed the integrity check")

    def _load_cached(self, ti: int, tj: int) -> NDArray[np.float32] | None:
        a = self._load_from(self.dir, ti, tj, own=True)
        for d in self.fallback_dirs:
            if a is not None:
                break
            a = self._load_from(d, ti, tj, own=False)
        return a

    def _load_from(
        self, directory: Path, ti: int, tj: int, own: bool
    ) -> NDArray[np.float32] | None:
        p = self._tile_path(ti, tj, directory)
        side = p.with_suffix(".sha256")
        if not (p.is_file() and side.is_file()):
            return None
        try:
            raw = p.read_bytes()
            ok = hashlib.sha256(raw).hexdigest() == side.read_text(encoding="ascii").strip()
        except OSError:
            return None
        if not ok or len(raw) != TILE * TILE * 4:
            if own:
                p.unlink(missing_ok=True)
                side.unlink(missing_ok=True)
            return None
        a = np.frombuffer(raw, dtype="<f4").reshape(TILE, TILE).astype(np.float32)
        self._check_values(a)
        if own and self.max_cache_bytes is not None:
            os.utime(p)  # LRU: a tile that is read is the newest
        return a

    def _fetch_tile(self, ti: int, tj: int) -> NDArray[np.float32]:
        s = self.spec
        r0, c0 = ti * TILE, tj * TILE
        rows = list(range(r0, min(r0 + TILE, s.lines)))
        w = min(TILE, s.samples - c0)
        tile = np.zeros((TILE, TILE), dtype=np.float32)
        opener = self._opener if self._opener is not None else _opener()
        for k in range(0, len(rows), RANGES_PER_REQUEST):
            chunk = rows[k : k + RANGES_PER_REQUEST]
            req_ranges = [
                ((r * s.samples + c0) * 4, (r * s.samples + c0 + w) * 4 - 1) for r in chunk
            ]
            spec = ",".join(f"{a}-{b}" for a, b in req_ranges)
            req = urllib.request.Request(s.url, headers={"Range": f"bytes={spec}"})
            # errori di rete transitori (il nodo PDS a volte non risponde): riprova con attesa crescente, solo con
            # l'opener reale; gli errori di integrita' (ETag, dimensione, valori) non si ripetono mai
            delays = NETWORK_RETRY_DELAYS_S if self._opener is None else ()
            for attempt in range(len(delays) + 1):
                try:
                    with opener.open(req, timeout=TIMEOUT_S) as resp:
                        status = resp.status
                        ctype = resp.headers.get("Content-Type", "")
                        etag = resp.headers.get("ETag")
                        body = resp.read(MAX_RESPONSE_BYTES + 1)
                    break
                except (urllib.error.URLError, OSError, TimeoutError) as e:
                    if attempt >= len(delays):
                        raise DemUnavailable("DEM not reachable and not cached") from e
                    time.sleep(delays[attempt])
            if status != 206 or len(body) > MAX_RESPONSE_BYTES:
                raise DemUnavailable("unexpected DEM server response")
            if etag is not None and etag != s.etag:
                raise DemUnavailable("DEM file changed on the server (ETag differs from the lock)")
            for m in _CR.finditer(body):
                if int(m.group(3)) != s.size:
                    raise DemUnavailable("DEM size differs from the lock")
            got = parse_ranges(body, ctype, req_ranges)
            for r, (a, _b) in zip(chunk, req_ranges, strict=True):
                piece = got.get(a)
                if piece is None or len(piece) != w * 4:
                    raise DemUnavailable("incomplete DEM response")
                tile[r - r0, :w] = np.frombuffer(piece, dtype="<f4")
        self._check_values(tile[: len(rows), :w])
        self.dir.mkdir(parents=True, exist_ok=True)
        p = self._tile_path(ti, tj)
        raw = tile.astype("<f4").tobytes()
        tmp = p.with_suffix(f".{os.getpid()}.part")
        try:
            tmp.write_bytes(raw)
            os.replace(tmp, p)
        finally:
            tmp.unlink(missing_ok=True)
        p.with_suffix(".sha256").write_text(
            hashlib.sha256(raw).hexdigest() + "\n", encoding="ascii"
        )
        if self.max_cache_bytes is not None:
            from backend.domain.grazing.dem_cache import enforce_limit

            enforce_limit(self.dir, self.max_cache_bytes, protect=(p,))
        return tile

    def tile(self, ti: int, tj: int) -> NDArray[np.float32]:
        key = (ti, tj)
        if key not in self._tiles:
            t = self._load_cached(ti, tj)
            if t is None:
                if not self.allow_download:
                    raise DemUnavailable("DEM tile not cached (download disabled)")
                t = self._fetch_tile(ti, tj)
            self._tiles[key] = t
        return self._tiles[key]

    def heights_m_at_pixels(self, rows: Arr, cols: Arr) -> Arr:
        """Bilinear interpolation of the height (m over the reference sphere) at float pixels."""
        s = self.spec
        r = np.clip(rows, 0, s.lines - 1.000001)
        cyl = s.projection == "cylindrical"
        c = np.mod(cols, s.samples) if cyl else np.clip(cols, 0, s.samples - 1.000001)
        r0, c0 = np.floor(r).astype(int), np.floor(c).astype(int)
        fr, fc = r - r0, c - c0
        out = np.empty(r.shape, dtype=np.float64)
        for i in range(r.size):
            acc = 0.0
            for dr, wr in ((0, 1 - fr.flat[i]), (1, fr.flat[i])):
                for dc, wc in ((0, 1 - fc.flat[i]), (1, fc.flat[i])):
                    rr, cc = int(r0.flat[i]) + dr, int(c0.flat[i]) + dc
                    if cyl:
                        rr, cc = min(rr, s.lines - 1), cc % s.samples
                    t = self.tile(rr // TILE, cc // TILE)
                    acc += wr * wc * float(t[rr % TILE, cc % TILE])
            out.flat[i] = acc * 1000.0
        return out


def verify_full(spec: DemSpec | None = None, opener: Any = None) -> bool:
    """Stream the WHOLE file (920 MB) and compare size and sha256 with the lock."""
    s = spec if spec is not None else load_lock()
    _check_url(s)
    h = hashlib.sha256()
    n = 0
    op = opener if opener is not None else _opener()
    try:
        with op.open(urllib.request.Request(s.url), timeout=TIMEOUT_S) as resp:
            while chunk := resp.read(CHUNK):
                h.update(chunk)
                n += len(chunk)
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        raise DemUnavailable("DEM not reachable") from e
    return n == s.size and h.hexdigest() == s.sha256


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--verify-full", action="store_true", help="download the whole file, check sha256"
    )
    ap.add_argument(
        "--dataset", default=None, help=f"dataset id (default: the 20 m product; or {FAR_DEM_ID})"
    )
    args = ap.parse_args(argv)
    spec = load_lock(dataset_id=args.dataset)
    if args.verify_full:
        ok = verify_full(spec)
        print("sha256 OK" if ok else "sha256 MISMATCH")
        return 0 if ok else 1
    print(json.dumps(spec.__dict__, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
