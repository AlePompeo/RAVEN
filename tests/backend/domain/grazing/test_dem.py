# SPDX-License-Identifier: Apache-2.0
"""LOLA reader: protocol and integrity tests with a local stub server (no network), plus real-data
checks that run only when the tiles are already cached in build/lola (never downloaded by tests)."""

import dataclasses
import io
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Self

import numpy as np
import pytest

from backend.domain.grazing import dem as dem_mod
from backend.domain.grazing.dem import (
    FAR_DEM_ID,
    DemOutOfCoverage,
    DemUnavailable,
    LolaDem,
    dem_dir,
    load_lock,
    parse_ranges,
)
from backend.domain.grazing.terrain import dominant_ridge, profile_from_dem

N = 256
ETAG = '"test-etag"'
# TEST-ONLY array (not LOLA data): a smooth ramp used to exercise the parser and the cache
FAKE = (np.add.outer(np.arange(N), np.arange(N) * 0.5) / 1000.0).astype("<f4")
BODY = FAKE.tobytes()


class _Resp(io.BytesIO):
    def __init__(self, data: bytes, headers: dict[str, str], status: int = 206) -> None:
        super().__init__(data)
        self.headers = headers
        self.status = status

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *a: object) -> None:
        self.close()


class _StubServer:
    def __init__(self, etag: str = ETAG, total: int | None = None, fail: bool = False) -> None:
        self.calls = 0
        self.etag, self.fail = etag, fail
        self.total = len(BODY) if total is None else total

    def open(self, req: urllib.request.Request, timeout: float) -> _Resp:
        self.calls += 1
        if self.fail:
            raise urllib.error.URLError("offline")
        rng = req.get_header("Range")
        assert rng is not None
        spans = [tuple(map(int, p.split("-"))) for p in rng.removeprefix("bytes=").split(",")]
        parts = b""
        for a, b in spans:
            parts += (
                b"--B\r\nContent-Type: application/octet-stream\r\n"
                + f"Content-Range: bytes {a}-{b}/{self.total}\r\n\r\n".encode()
                + BODY[a : b + 1]
                + b"\r\n"
            )
        parts += b"--B--\r\n"
        return _Resp(parts, {"Content-Type": "multipart/byteranges; boundary=B", "ETag": self.etag})


def _spec() -> Any:
    return dataclasses.replace(
        load_lock(),
        lines=N,
        samples=N,
        size=len(BODY),
        etag=ETAG,
        min_km=-1.0,
        max_km=1.0,
        orientation={"swap": 0, "sx": 1, "sy": -1},
    )


def test_lock_is_complete_and_https_pds_only() -> None:
    s = load_lock()
    assert s.size == 15168 * 15168 * 4 == 920_272_896
    assert re.fullmatch(r"[0-9a-f]{64}", s.sha256) and re.fullmatch(r"[0-9a-f]{64}", s.label_sha256)
    assert s.url.startswith("https://pds-geosciences.wustl.edu/")
    bad = dataclasses.replace(s, url="http://pds-geosciences.wustl.edu/x.img")
    with pytest.raises(DemUnavailable):
        LolaDem(Path("/nonexistent"), bad)
    bad2 = dataclasses.replace(s, url="https://evil.example.com/x.img")
    with pytest.raises(DemUnavailable):
        LolaDem(Path("/nonexistent"), bad2)


def test_far_horizon_product_is_locked_with_full_hash() -> None:
    s = load_lock(dataset_id=FAR_DEM_ID)
    assert s.size == 3812 * 3812 * 4 == 58_125_376
    assert s.scale_m == 240.0 and s.center_px == 1905.5 and s.max_lat_deg == 75.0
    assert re.fullmatch(r"[0-9a-f]{64}", s.sha256) and re.fullmatch(r"[0-9a-f]{64}", s.label_sha256)
    assert s.url.startswith("https://pds-geosciences.wustl.edu/") and s.etag
    assert {k: v for k, v in s.orientation.items() if k != "note"} == {
        k: v for k, v in load_lock().orientation.items() if k != "note"
    }
    d = LolaDem(Path("/nonexistent"), s, allow_download=False)
    assert d.pixel(-90.0, 0.0) == (1905.5, 1905.5)
    with pytest.raises(KeyError):
        load_lock(dataset_id="nope")


def test_projection_pole_and_coverage_edge() -> None:
    d = LolaDem(Path("/nonexistent"), load_lock(), allow_download=False)
    r, c = d.pixel(-90.0, 0.0)
    assert (r, c) == (7583.5, 7583.5)
    # 85.1 deg S, lon 0: rho = 2 R tan(2.45 deg) = 148.675 km = 7433.75 px from the centre
    r, c = d.pixel(-85.1, 0.0)
    assert c == pytest.approx(7583.5, abs=1e-6) and r == pytest.approx(7583.5 - 7433.75, abs=0.5)
    with pytest.raises(DemOutOfCoverage):
        d.pixel(-85.0, 0.0)  # edge of the square product is just outside on the axis
    with pytest.raises(DemOutOfCoverage):
        d.pixel(-84.0, 0.0)
    with pytest.raises(DemOutOfCoverage):
        d.pixel(float("nan"), 0.0)


def test_parse_ranges_single_and_multipart() -> None:
    assert parse_ranges(b"abcd", "application/octet-stream", [(8, 11)]) == {8: b"abcd"}
    body = (
        b"--B\r\nContent-Type: x\r\nContent-Range: bytes 0-3/100\r\n\r\nabcd\r\n"
        b"--B\r\nContent-Type: x\r\nContent-Range: bytes 10-13/100\r\n\r\n\r\n\r\n\r\n\r\n--B--"
    )
    got = parse_ranges(body, "multipart/byteranges; boundary=B", [(0, 3), (10, 13)])
    assert got == {0: b"abcd", 10: b"\r\n\r\n"}  # payload bytes may contain CRLF CRLF


def test_fetch_tile_cache_and_values(tmp_path: Path) -> None:
    srv = _StubServer()
    d = LolaDem(tmp_path, _spec(), opener=srv)
    h = d.heights_m_at_pixels(np.array([10.0, 130.5]), np.array([20.0, 200.25]))
    assert h[0] == pytest.approx(FAKE[10, 20] * 1000.0, abs=1e-3)
    assert h[1] == pytest.approx(130.5 + 0.5 * 200.25, abs=0.01)  # a linear ramp: bilinear is exact
    assert srv.calls >= 2
    # second reader: tiles come from disk, zero network calls, even with download disabled
    srv2 = _StubServer(fail=True)
    d2 = LolaDem(tmp_path, _spec(), allow_download=False, opener=srv2)
    h2 = d2.heights_m_at_pixels(np.array([10.0]), np.array([20.0]))
    assert h2[0] == h[0] and srv2.calls == 0


def test_no_cache_no_network_is_unavailable(tmp_path: Path) -> None:
    with pytest.raises(DemUnavailable):
        LolaDem(tmp_path, _spec(), allow_download=False).heights_m_at_pixels(
            np.array([1.0]), np.array([1.0])
        )
    with pytest.raises(DemUnavailable):
        LolaDem(tmp_path, _spec(), opener=_StubServer(fail=True)).heights_m_at_pixels(
            np.array([1.0]), np.array([1.0])
        )


@pytest.mark.parametrize("srv", [_StubServer(etag='"other"'), _StubServer(total=123)])
def test_integrity_mismatch_refused(tmp_path: Path, srv: _StubServer) -> None:
    with pytest.raises(DemUnavailable):
        LolaDem(tmp_path, _spec(), opener=srv).heights_m_at_pixels(np.array([1.0]), np.array([1.0]))
    assert not list(tmp_path.glob("*.f32"))  # nothing cached from a refused response


def test_corrupted_cache_is_dropped_and_refetched(tmp_path: Path) -> None:
    d = LolaDem(tmp_path, _spec(), opener=_StubServer())
    d.heights_m_at_pixels(np.array([1.0]), np.array([1.0]))
    f = next(tmp_path.glob("*.f32"))
    f.write_bytes(b"\x00" * f.stat().st_size)  # same size, wrong hash
    srv = _StubServer()
    d2 = LolaDem(tmp_path, _spec(), opener=srv)
    h = d2.heights_m_at_pixels(np.array([1.0]), np.array([1.0]))
    assert srv.calls >= 1 and h[0] == pytest.approx(FAKE[1, 1] * 1000.0, abs=1e-3)


def test_values_outside_label_range_refused(tmp_path: Path) -> None:
    spec = dataclasses.replace(_spec(), max_km=-1.0, min_km=-2.0)  # FAKE (0..0.38) exceeds it
    with pytest.raises(DemUnavailable):
        LolaDem(tmp_path, spec, opener=_StubServer()).heights_m_at_pixels(
            np.array([200.0]), np.array([200.0])
        )


def test_dem_dir_env() -> None:
    assert dem_dir({"GRAZING_DEM_DIR": "/tmp/x"}) == Path("/tmp/x")
    assert dem_dir({}) == dem_mod.DEFAULT_DIR


# ---- real LOLA data, only when already cached (run `scripts`/the report procedure to fill build/lola)
_REAL = dem_dir()
needs_lola = pytest.mark.skipif(
    not list(_REAL.glob("ldem_85s_20m_float.t128.*.f32")),
    reason="LOLA tiles not cached in build/lola",
)


@needs_lola
def test_real_lola_features_when_cached() -> None:
    d = LolaDem(_REAL, allow_download=False)
    for lat, lon, lo, hi in [
        (-85.98, -1.67, 4000.0, 6000.0),  # Malapert Massif summit area (+4.9 km)
        (-87.45, -5.17, -5000.0, -2500.0),  # Haworth floor
        (-89.67, 129.78, -3500.0, -2000.0),  # Shackleton floor
    ]:
        try:
            r, c = d.pixel(lat, lon)
            h = float(d.heights_m_at_pixels(np.array([r]), np.array([c]))[0])
        except DemUnavailable:
            pytest.skip("tile of this feature not cached")
        assert lo < h < hi


@needs_lola
def test_real_profile_and_ridge_when_cached() -> None:
    d = LolaDem(_REAL, allow_download=False)
    try:
        p = profile_from_dem(d, -85.98, -1.67, 0.0, length_m=2000.0)
    except DemUnavailable:
        pytest.skip("profile tiles not cached")
    assert p.source == "lola" and not p.synthetic and p.spacing_m == 20.0
    assert np.all(np.isfinite(p.height_m))
    r = dominant_ridge(p, 1.0, 0.03569)
    assert r.d1_m > 0 and np.isfinite(r.nu)
