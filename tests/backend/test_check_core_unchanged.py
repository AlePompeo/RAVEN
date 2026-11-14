# SPDX-License-Identifier: Apache-2.0
import subprocess
from pathlib import Path

import pytest

from scripts.check_core_unchanged import check


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        check=True,
        capture_output=True,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q", "-b", "base")
    core = tmp_path / "backend" / "core"
    core.mkdir(parents=True)
    (core / "ports.py").write_text("X = 1\n")
    (tmp_path / "backend" / "domain").mkdir()
    (tmp_path / "backend" / "domain" / "a.py").write_text("A = 1\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "base")
    _git(tmp_path, "switch", "-q", "-c", "hack")
    return tmp_path


def test_unchanged_when_only_domain_changes(repo: Path) -> None:
    (repo / "backend" / "domain" / "a.py").write_text("A = 2\n")
    _git(repo, "commit", "-q", "-am", "domain only")
    assert check("base", repo) == (0, [])


def test_modified_core_is_reported(repo: Path) -> None:
    (repo / "backend" / "core" / "ports.py").write_text("X = 2\n")
    _git(repo, "commit", "-q", "-am", "touch core")
    code, files = check("base", repo)
    assert code == 1
    assert files == ["backend/core/ports.py"]


def test_uncommitted_core_change_is_reported(repo: Path) -> None:
    (repo / "backend" / "core" / "ports.py").write_text("X = 3\n")
    assert check("base", repo)[0] == 1


@pytest.mark.parametrize("ref", ["--output=/x", "no such ref", "", "a" * 300])
def test_invalid_reference_is_rejected_without_running_git(repo: Path, ref: str) -> None:
    assert check(ref, repo)[0] == 2


def test_unknown_reference_is_an_error(repo: Path) -> None:
    assert check("does-not-exist", repo)[0] == 2
