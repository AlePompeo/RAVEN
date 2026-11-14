# SPDX-License-Identifier: Apache-2.0
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("port", ["0", "-1", "65536", "999999999999999999999999", "abc"])
def test_installer_rejects_invalid_ports_before_installing(tmp_path: Path, port: str) -> None:
    script = tmp_path / "install.sh"
    shutil.copy2(ROOT / "install.sh", script)
    result = subprocess.run(
        ["bash", str(script), "--yes", "--port", port],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 2
    assert "--port must be a number between 1 and 65535" in result.stderr
    assert not (tmp_path / ".tools").exists()


def test_stop_refuses_another_process_even_with_a_matching_module_name(tmp_path: Path) -> None:
    script = tmp_path / "stop.sh"
    shutil.copy2(ROOT / "stop.sh", script)
    other = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)", "backend.bootstrap:build_app"]
    )
    try:
        (tmp_path / ".server.pid").write_text(f"{other.pid}\n8765\n")
        result = subprocess.run(
            ["bash", str(script)], check=False, capture_output=True, text=True, timeout=15
        )
        assert result.returncode == 1
        assert "not this project's server" in result.stderr
        assert other.poll() is None
        assert (tmp_path / ".server.pid").exists()
    finally:
        if other.poll() is None:
            other.terminate()
        other.wait(timeout=10)
