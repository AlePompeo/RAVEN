# SPDX-License-Identifier: Apache-2.0
"""Install the local language model of RAVEN SI into build/llm (opt-in: ./install.sh --with-llm, or run this script).

Downloads two pinned files over HTTPS, checks size and SHA-256 before using them, and writes build/llm/manifest.json:
  * llama.cpp b12110 (MIT), the server binary for Linux x86_64 or aarch64;
  * Ministral 3 3B Instruct 2512, Q4_K_M quantisation (Apache-2.0, Mistral AI), 2.1 GB; with --small, Granite 4.0-h 1B Q4_K_M
    (Apache-2.0, IBM), 0.9 GB, for machines with little memory.
Linux only. Nothing outside build/llm is touched. Attribution notices of both are in THIRD_PARTY_NOTICES.md, not in the README.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = Path(os.environ.get("RAVEN_LLM_DIR") or ROOT / "build" / "llm")
LLAMA = {
    "x86_64": (
        "https://github.com/ggml-org/llama.cpp/releases/download/b12110/llama-b12110-bin-ubuntu-x64.tar.gz",
        23_051_958,
        "368227edcc229be5f9bed16a2223d79b5e41d0ac2e19bcf5825e82291c060e55",
    ),
    "aarch64": (
        "https://github.com/ggml-org/llama.cpp/releases/download/b12110/llama-b12110-bin-ubuntu-arm64.tar.gz",
        18_723_578,
        "4758b51335e37b4346251f2687d64841ff1c07ecb27fc46323945bb2ec9c44d2",
    ),
}
# (url, size, sha256, name, minimum free memory in MB the manager requires before it starts the server)
MODELS = {
    "default": (
        "https://huggingface.co/unsloth/Ministral-3-3B-Instruct-2512-GGUF/resolve/main/Ministral-3-3B-Instruct-2512-Q4_K_M.gguf",
        2_146_497_824,
        "fd46fc371ff0509bfa8657ac956b7de8534d7d9baaa4947975c0648c3aa397f4",
        "ministral-3-3b-instruct-2512-q4_k_m",
        4096,
    ),
    "small": (  # for machines with little memory: measured 79 % of the fields instead of 91 %, about 1.7 GB instead of 2.8 GB
        "https://huggingface.co/ibm-granite/granite-4.0-h-1b-GGUF/resolve/main/granite-4.0-h-1b-Q4_K_M.gguf",
        901_162_208,
        "da3d737121a96f3c9a316685212376257a7f167b74380855666dd488d6af3bcb",
        "granite-4.0-h-1b-q4_k_m",
        2560,
    ),
}


def fetch(url: str, size: int, sha: str, to: Path) -> None:
    """Download to a partial file, check size and SHA-256, then move into place; a mismatch deletes the file and stops."""
    part = to.with_suffix(to.suffix + ".part")
    h = hashlib.sha256()
    n = 0
    req = urllib.request.Request(url, headers={"User-Agent": "raven-installer"})
    with urllib.request.urlopen(req, timeout=60) as r, part.open("wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
            h.update(chunk)
            n += len(chunk)
            if n > size:
                break
    if n != size or h.hexdigest() != sha:
        part.unlink(missing_ok=True)
        raise SystemExit(
            f"download of {to.name} does not match the pinned size/checksum; nothing was installed"
        )
    part.replace(to)


def main(argv: list[str]) -> int:
    kind = "small" if "--small" in argv else "default"
    murl, msize, msha, mname, mfree = MODELS[kind]
    if sys.platform != "linux":
        print("the local model is supported on Linux only", file=sys.stderr)
        return 2
    arch = platform.machine()
    if arch not in LLAMA:
        print(f"no pinned llama.cpp build for {arch}", file=sys.stderr)
        return 2
    manifest = DEST / "manifest.json"
    model = DEST / "model.gguf"
    server = DEST / "llama" / "llama-server"
    try:
        have = json.loads(manifest.read_text())
    except (OSError, ValueError):
        have = {}
    if (
        have.get("sha256") == msha
        and model.is_file()
        and model.stat().st_size == msize
        and server.is_file()
    ):
        print("local model already installed")
        return 0
    DEST.mkdir(parents=True, exist_ok=True)
    url, size, sha = LLAMA[arch]
    tgz = DEST / "llama.tar.gz"
    print("downloading llama.cpp b12110 ...", flush=True)
    fetch(url, size, sha, tgz)
    tmp = DEST / "llama.new"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    with tarfile.open(tgz) as t:
        t.extractall(tmp, filter="data")
    tgz.unlink()
    inner = next(p for p in tmp.iterdir() if p.is_dir())
    shutil.rmtree(DEST / "llama", ignore_errors=True)
    inner.replace(DEST / "llama")
    shutil.rmtree(tmp, ignore_errors=True)
    server.chmod(0o755)
    print(f"downloading the model ({msize / 1e9:.1f} GB) ...", flush=True)
    fetch(murl, msize, msha, model)
    manifest.write_text(
        json.dumps(
            {"name": mname, "sha256": msha, "size": msize, "min_free_mb": mfree, "llama": "b12110"}
        )
    )
    print("local model installed in", DEST)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
