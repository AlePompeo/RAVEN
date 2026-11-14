# SPDX-License-Identifier: Apache-2.0
import pytest

from backend.core.errors import ManifestError, PluginNotFound
from backend.core.manifest import load_manifest
from backend.core.registry import Registry

GOOD = 'id="a"\nkind="simulation"\nversion="0.1.0"\nentry="python:x:Y"\nlicense="Apache-2.0"\n'


def test_load_manifest_ok(tmp_path):
    (tmp_path / "manifest.toml").write_text(GOOD)
    m = load_manifest(tmp_path / "manifest.toml")
    assert (m.id, m.kind, m.timeout_s) == ("a", "simulation", 30.0)


@pytest.mark.parametrize("bad", ["", 'id="a"', GOOD.replace("simulation", "bogus"), "not = [toml"])
def test_load_manifest_rejects_bad(tmp_path, bad):
    (tmp_path / "manifest.toml").write_text(bad)
    with pytest.raises(ManifestError):
        load_manifest(tmp_path / "manifest.toml")


def test_data_source_requires_terms_url(tmp_path):
    (tmp_path / "manifest.toml").write_text(GOOD.replace("simulation", "data_source"))
    with pytest.raises(ManifestError, match="terms_url"):
        load_manifest(tmp_path / "manifest.toml")


def test_registry_create_and_missing(tmp_path):
    (tmp_path / "manifest.toml").write_text(GOOD)
    m = load_manifest(tmp_path / "manifest.toml")
    r = Registry()
    r.register(m, lambda manifest: "instance")
    assert r.create("simulation", "a") == "instance"
    with pytest.raises(PluginNotFound):
        r.create("simulation", "nope")


def test_discover_isolates_broken_plugins(tmp_path):
    ok = tmp_path / "ok"
    ok.mkdir()
    (ok / "manifest.toml").write_text(GOOD)
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "manifest.toml").write_text("garbage = [")
    r = Registry()
    errors = r.discover(tmp_path, loader=lambda m: lambda manifest: "inst")
    assert r.create("simulation", "a") == "inst"
    assert len(errors) == 1 and errors[0][0].name == "bad"
