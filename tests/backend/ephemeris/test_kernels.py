# SPDX-License-Identifier: Apache-2.0
"""Gestore dei kernel NAIF: solo rete finta, nessun accesso a internet."""

import hashlib
import io
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from backend.ephemeris import kernels as k


class FakeResp(io.BytesIO):
    def __init__(self, data: bytes, length: int | None = None) -> None:
        super().__init__(data)
        self.headers = {} if length is None else {"Content-Length": str(length)}


class FakeOpener:
    def __init__(self, data: bytes, length: int | None = None) -> None:
        self.data, self.length, self.calls = data, length, []

    def open(self, url: str, timeout: float) -> FakeResp:
        self.calls.append((url, timeout))
        return FakeResp(self.data, self.length)


def spec_for(data: bytes, name: str = "x.bpc", url: str | None = None) -> k.KernelSpec:
    return k.KernelSpec(
        name=name,
        url=url or f"https://naif.jpl.nasa.gov/pub/{name}",
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        retrieved="2026-10-20",
        role="test",
    )


def test_lock_file_is_well_formed() -> None:
    specs = k.load_lock()
    assert {s.name for s in specs} == {
        "de440s.bsp",
        "moon_pa_de440_200625.bpc",
        "moon_de440_250416.tf",
        "pck00011.tpc",
    }
    for s in specs:
        assert s.url.startswith("https://naif.jpl.nasa.gov/")
        assert len(s.sha256) == 64 and s.size > 0


def test_default_dir_and_env(tmp_path: Path) -> None:
    assert k.ephemeris_dir({}).name == "ephemeris"
    assert k.ephemeris_dir({"EPHEMERIS_DIR": str(tmp_path)}) == tmp_path


def test_download_ok_atomic(tmp_path: Path) -> None:
    data = b"abc" * 1000
    spec = spec_for(data)
    op = FakeOpener(data, len(data))
    p = k.download(spec, tmp_path, opener=op)
    assert p.read_bytes() == data
    assert [f.name for f in tmp_path.iterdir()] == ["x.bpc"]  # nessun .part residuo
    assert op.calls[0][1] > 0  # timeout impostato


def test_download_hash_mismatch_refused(tmp_path: Path) -> None:
    data = b"abc" * 1000
    spec = spec_for(data)
    bad = bytes([data[0] ^ 1]) + data[1:]
    with pytest.raises(k.KernelIntegrityError):
        k.download(spec, tmp_path, opener=FakeOpener(bad))
    assert list(tmp_path.iterdir()) == []


def test_download_size_cap(tmp_path: Path) -> None:
    data = b"a" * 100
    spec = spec_for(data)
    with pytest.raises(k.KernelIntegrityError):
        k.download(spec, tmp_path, opener=FakeOpener(data + b"b" * 5000))
    assert list(tmp_path.iterdir()) == []
    with pytest.raises(k.KernelIntegrityError):  # Content-Length dichiarata troppo grande
        k.download(spec, tmp_path, opener=FakeOpener(data, length=10**9))


def test_https_only_and_host_pinned(tmp_path: Path) -> None:
    data = b"z"
    with pytest.raises(k.KernelIntegrityError):
        k.download(
            spec_for(data, url="http://naif.jpl.nasa.gov/x"), tmp_path, opener=FakeOpener(data)
        )
    with pytest.raises(k.KernelIntegrityError):
        k.download(
            spec_for(data, url="https://evil.example.com/x"), tmp_path, opener=FakeOpener(data)
        )
    with pytest.raises(k.KernelIntegrityError):
        k.download(spec_for(data, name="../x"), tmp_path, opener=FakeOpener(data))


def test_redirect_to_other_host_refused() -> None:
    h = k._SameHostRedirect()
    req = urllib.request.Request("https://naif.jpl.nasa.gov/a")
    with pytest.raises(urllib.error.HTTPError):
        h.redirect_request(req, io.BytesIO(), 302, "Found", {}, "https://evil.example.com/b")
    with pytest.raises(urllib.error.HTTPError):
        h.redirect_request(req, io.BytesIO(), 302, "Found", {}, "http://naif.jpl.nasa.gov/b")
    ok = h.redirect_request(req, io.BytesIO(), 302, "Found", {}, "https://naif.jpl.nasa.gov/b")
    assert ok is not None and ok.full_url == "https://naif.jpl.nasa.gov/b"


def test_verify_and_paths(tmp_path: Path) -> None:
    data = b"hello"
    spec = spec_for(data)
    assert k.problems(tmp_path, [spec]) == ["x.bpc: assente"]
    (tmp_path / "x.bpc").write_bytes(data)
    assert k.problems(tmp_path, [spec]) == []
    (tmp_path / "x.bpc").write_bytes(b"HELLO")
    assert "hash" in k.problems(tmp_path, [spec])[0]
    with pytest.raises(k.EphemerisUnavailable):
        k.require_kernels(tmp_path, [spec])


def test_unavailable_when_dir_missing(tmp_path: Path) -> None:
    with pytest.raises(k.EphemerisUnavailable):
        k.require_kernels(tmp_path / "nope")


def test_fetch_all_skips_valid(tmp_path: Path) -> None:
    data = b"q" * 10
    spec = spec_for(data)
    (tmp_path / "x.bpc").write_bytes(data)
    op = FakeOpener(b"")
    assert k.fetch_all(tmp_path, [spec], opener=op) == [tmp_path / "x.bpc"]
    assert op.calls == []
