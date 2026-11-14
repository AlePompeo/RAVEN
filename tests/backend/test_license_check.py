# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path

import pytest

from scripts.license_check import check, collect_node, load_reviewed, main


def test_allowed():
    lic = {"a": "MIT", "b": "BSD-3-Clause", "c": "Apache-2.0", "d": "ISC", "e": "0BSD"}
    assert check(lic) == []
    assert check({"x": "Python-2.0", "y": "PSF-2.0", "z": "BSD License"}) == []


@pytest.mark.parametrize(
    "lic", ["GPL-3.0", "AGPL-3.0", "LGPL-2.1", "GNU General Public License v3 (GPLv3)"]
)
def test_forbidden(lic):
    out = check({"b": lic})
    assert len(out) == 1 and "vietata" in out[0] and "b" in out[0]


def test_unknown_and_mpl_need_review():
    out = check({"u": "Weird-1.0", "m": "MPL-2.0", "e": "", "n": "UNKNOWN"})
    assert len(out) == 4
    assert all("da rivedere" in v for v in out)


def test_or_expression_takes_best_choice():
    assert check({"a": "(MIT OR GPL-3.0)"}) == []
    assert check({"a": "MIT OR Apache-2.0"}) == []
    assert len(check({"a": "GPL-3.0 OR AGPL-3.0"})) == 1


def test_and_expression_requires_all():
    assert check({"a": "MIT AND BSD-2-Clause"}) == []
    assert len(check({"a": "MIT AND GPL-3.0"})) == 1


def test_whitespace_normalised():
    assert check({"a": "MIT\tOR  GPL-3.0"}) == []
    assert check({"a": "(MIT\n OR   Apache-2.0)"}) == []
    assert len(check({"a": "MIT \t AND\tGPL-3.0"})) == 1


def test_reviewed_matches_name_and_version_only():
    lic = {"pip:certifi@1.0": "MPL-2.0"}
    assert check(lic, reviewed={"pip:certifi@1.0"}) == []
    assert check(lic, reviewed={"certifi@1.0"}) == []  # senza ecosistema
    assert len(check(lic, reviewed={"pip:certifi@2.0"})) == 1  # altra versione
    assert len(check(lic, reviewed={"npm:certifi@1.0"})) == 1  # altro ecosistema
    assert len(check(lic, reviewed={"pip:certifi"})) == 1  # solo nome: non basta


def test_reviewed_never_overrides_forbidden():
    out = check({"pip:evil@1.0": "GPL-3.0"}, reviewed={"pip:evil@1.0"})
    assert len(out) == 1 and "vietata" in out[0]


def test_reviewed_file_parsing(tmp_path: Path):
    f = tmp_path / "r.txt"
    f.write_text("# commento\n\npip:certifi@1.0  # motivo: MPL file-level\nnpm:x@2\n")
    assert load_reviewed(f) == {"pip:certifi@1.0", "npm:x@2"}


def test_main_reviewed_file_is_version_scoped(tmp_path: Path):
    py = tmp_path / "py.json"
    py.write_text('[{"Name":"certifi","Version":"1.0","License":"MPL-2.0"}]')
    rev = tmp_path / "rev.txt"
    rev.write_text("pip:certifi@1.0\n")
    assert main(["--python-json", str(py), "--reviewed-file", str(rev)]) == 0
    py.write_text('[{"Name":"certifi","Version":"1.1","License":"MPL-2.0"}]')
    assert main(["--python-json", str(py), "--reviewed-file", str(rev)]) == 1


def test_zlib_cc0_and_composite_and():
    assert check({"a": "Zlib", "b": "CC0-1.0"}) == []
    assert check({"n": "BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0"}) == []
    assert len(check({"n": "MIT AND GPL-3.0"})) == 1
    out = check({"n": "MIT AND Unknown-1.0"})
    assert len(out) == 1 and "da rivedere" in out[0]


@pytest.mark.parametrize(
    "lic",
    [
        "3-Clause BSD License",
        "2-Clause BSD License",
        "BSD 3-Clause",
        "BSD 3-Clause License",
        "BSD License",
        "Apache Software License",
        "Apache License 2.0",
        "MIT License",
    ],
)
def test_common_non_spdx_spellings_allowed(lic):
    assert check({"p": lic}) == []


@pytest.mark.parametrize(
    "lic",
    [
        "GNU General Public License v3 (GPLv3)",
        "GNU Lesser General Public License v3 (LGPLv3)",
        "BSD License; GNU General Public License v2 (GPLv2)",
        "3-Clause BSD License AND GPL-3.0",
    ],
)
def test_aliases_cannot_hide_copyleft(lic):
    out = check({"p": lic})
    assert len(out) == 1 and "vietata" in out[0]


def test_unlicense_needs_review():
    out = check({"p": "The Unlicense"})
    assert len(out) == 1 and "da rivedere" in out[0]


def test_empty():
    assert check({}) == []


def test_collect_node(tmp_path: Path):
    for name, lic in [("a", "MIT"), ("@s/b", {"type": "ISC"}), ("c", None)]:
        d = tmp_path / "node_modules" / name
        d.mkdir(parents=True)
        pkg = {"name": name, "version": "1.0.0"}
        if lic is not None:
            pkg["license"] = lic
        (d / "package.json").write_text(json.dumps(pkg))
    got = {e["name"]: e["license"] for e in collect_node(tmp_path / "node_modules")}
    assert got == {"a": "MIT", "@s/b": "ISC", "c": "UNKNOWN"}


def test_main_writes_licenses_json_and_fails_on_violation(tmp_path: Path):
    nm = tmp_path / "node_modules" / "a"
    nm.mkdir(parents=True)
    (nm / "package.json").write_text('{"name":"a","version":"1.2.3","license":"MIT"}')
    out = tmp_path / "licenses.json"
    py = tmp_path / "py.json"
    py.write_text('[{"Name":"p","Version":"1","License":"MIT"}]')
    args = ["--python-json", str(py), "--node-modules", str(nm.parent), "--out", str(out)]
    assert main(args) == 0
    data = json.loads(out.read_text())
    assert {"name": "a", "version": "1.2.3", "license": "MIT"} in data
    assert all(set(e) == {"name", "version", "license"} for e in data)
    py.write_text('[{"Name":"bad","Version":"1","License":"GPL-3.0"}]')
    assert main(args) == 1
