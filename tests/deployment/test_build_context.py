# SPDX-License-Identifier: Apache-2.0
"""Opt-in Docker test with fake credentials only; never reads real secret files."""

import io
import os
import subprocess
import tarfile
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(
    os.environ.get("RAVEN_TEST_DOCKER_CONTEXT") != "1",
    reason="set RAVEN_TEST_DOCKER_CONTEXT=1 for the isolated Docker canary",
)


def test_nested_credentials_do_not_enter_the_docker_context(tmp_path: Path) -> None:
    excluded = {
        ".env",
        ".env.prod",
        ".secrets/tunnel-token",
        "frontend/.env",
        "frontend/.env.prod",
        "frontend/.npmrc",
        "backend/.env",
        "backend/.secrets/token",
        "backend/.pypirc",
        "backend/tls.pem",
        "backend/tls.key",
        "backend/.netrc",
        "backend/.ssh/id_ed25519",
        "frontend/id_rsa",
    }
    examples = {".env.example", ".env.oracle.example", "frontend/.env.example"}
    for name in excluded | examples:
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("SECURITY_CANARY_NOT_A_CREDENTIAL\n", encoding="utf-8")
    (tmp_path / ".dockerignore").write_bytes((ROOT / ".dockerignore").read_bytes())
    (tmp_path / "Dockerfile").write_text("FROM scratch\nCOPY . /context\n", encoding="utf-8")
    tag = f"raven-security-canary:{uuid.uuid4().hex}"
    container: str | None = None
    built = False

    def docker(*args: str) -> bytes:
        return subprocess.run(["docker", *args], check=True, capture_output=True).stdout

    try:
        docker("build", "-t", tag, str(tmp_path))
        built = True
        container = docker("create", tag, "/unused").decode().strip()
        with tarfile.open(fileobj=io.BytesIO(docker("export", container))) as archive:
            names = set(archive.getnames())
        assert not {f"context/{name}" for name in excluded} & names
        assert {f"context/{name}" for name in examples} <= names
    finally:
        try:
            if container is not None:
                docker("rm", container)
        finally:
            if built:
                docker("image", "rm", tag)
