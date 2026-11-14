# SPDX-License-Identifier: Apache-2.0
import re

import pytest

from backend.core.errors import ManifestError, PluginError
from backend.core.manifest import load_manifest
from backend.core.registry import Registry

GOOD = 'id="a"\nkind="simulation"\nversion="0.1.0"\nentry="python:x:Y"\nlicense="Apache-2.0"\n'


@pytest.mark.parametrize("val", ["nan", "inf", "-1", "0", '"x"'])
def test_manifest_rejects_bad_timeout(tmp_path, val):
    (tmp_path / "manifest.toml").write_text(GOOD + f"timeout_s = {val}\n")
    with pytest.raises(ManifestError):
        load_manifest(tmp_path / "manifest.toml")


@pytest.mark.parametrize("field", ["id", "entry", "version", "license"])
@pytest.mark.parametrize("bad", ['""', "5"])
def test_manifest_rejects_empty_or_non_str(tmp_path, field, bad):
    text = re.sub(rf"^{field}=.*$", f"{field}={bad}", GOOD, flags=re.MULTILINE)
    (tmp_path / "manifest.toml").write_text(text)
    with pytest.raises(ManifestError):
        load_manifest(tmp_path / "manifest.toml")


def test_manifest_kind_non_str(tmp_path):
    (tmp_path / "manifest.toml").write_text(GOOD.replace('"simulation"', "[1]"))
    with pytest.raises(ManifestError):
        load_manifest(tmp_path / "manifest.toml")


def test_manifest_reads_utf8(tmp_path):
    (tmp_path / "manifest.toml").write_bytes(GOOD.replace("Apache-2.0", "Apache-é").encode())
    assert load_manifest(tmp_path / "manifest.toml").license == "Apache-é"


def test_registry_rejects_duplicate(tmp_path):
    (tmp_path / "manifest.toml").write_text(GOOD)
    m = load_manifest(tmp_path / "manifest.toml")
    r = Registry()
    r.register(m, lambda manifest: 1)
    with pytest.raises(PluginError):
        r.register(m, lambda manifest: 2)
