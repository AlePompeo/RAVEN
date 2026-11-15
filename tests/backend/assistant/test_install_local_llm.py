# SPDX-License-Identifier: Apache-2.0
"""Exercise model selection and installation without downloading model weights."""

import io
import json
import subprocess
import tarfile
from pathlib import Path

import pytest

from scripts import install_local_llm as installer

ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    ("args", "selected"),
    [
        (["--model", "350m"], "350m"),
        (["--model", "1b"], "1b"),
        (["--model", "3b"], "3b"),
        (["--small"], "1b"),
        ([], "default"),
    ],
)
def test_install_selected_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, args: list[str], selected: str
) -> None:
    monkeypatch.setattr(installer, "DEST", tmp_path)
    monkeypatch.setattr(installer.sys, "platform", "linux")
    monkeypatch.setattr(installer.platform, "machine", lambda: "x86_64")
    models = {
        key: (url, 1, sha, name, free)
        for key, (url, _, sha, name, free) in installer.MODELS.items()
    }
    monkeypatch.setattr(installer, "MODELS", models)
    fetched: list[str] = []

    def fake_fetch(url: str, size: int, sha: str, to: Path) -> None:
        fetched.append(url)
        if to.name == "llama.tar.gz":
            with tarfile.open(to, "w:gz") as archive:
                info = tarfile.TarInfo("llama/llama-server")
                info.size = 1
                archive.addfile(info, io.BytesIO(b"x"))
        else:
            assert (url, size, sha) == models[selected][:3]
            to.write_bytes(b"x")

    monkeypatch.setattr(installer, "fetch", fake_fetch)
    assert installer.main(args) == 0
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["name"] == models[selected][3]
    assert manifest["min_free_mb"] == models[selected][4]
    assert len(fetched) == 2
    assert installer.main(args) == 0
    assert len(fetched) == 2


def test_install_script_rejects_bad_model_before_installing() -> None:
    result = subprocess.run(
        ["bash", "install.sh", "--llm-model", "bad"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "--llm-model must be" in result.stderr
