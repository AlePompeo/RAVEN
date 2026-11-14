# SPDX-License-Identifier: Apache-2.0
import asyncio
import contextlib
import math
from collections.abc import Mapping
from pathlib import Path

from backend.core.errors import InvalidOutput, PluginError, SimulationTimeout

MAX_STDOUT_BYTES = 64 * 1024
_ERR_KEEP = 4096
_CHUNK = 8192


def resolve_inside(root: Path, rel: str) -> Path:
    root = root.resolve()
    p = (root / rel).resolve()
    if not p.is_relative_to(root):
        raise PluginError(f"percorso fuori dal plugin: {rel}")
    return p


def _encode_inputs(inputs: Mapping[str, float]) -> bytes:
    lines = []
    for k, v in inputs.items():
        if not k or any(c in k for c in "=\n\r"):
            raise PluginError(f"chiave di input non valida: {k!r}")
        num = float(v)
        if not math.isfinite(num):
            raise PluginError(f"valore di input non finito: {k}")
        lines.append(f"{k}={num!r}\n")
    return "".join(lines).encode()


async def _feed(proc: asyncio.subprocess.Process, payload: bytes) -> None:
    stdin = proc.stdin
    assert stdin is not None
    with contextlib.suppress(BrokenPipeError, ConnectionResetError):
        stdin.write(payload)
        await stdin.drain()
    with contextlib.suppress(BrokenPipeError, ConnectionResetError):
        stdin.close()


async def _read_stdout(proc: asyncio.subprocess.Process) -> bytes:
    stream = proc.stdout
    assert stream is not None
    buf = bytearray()
    while chunk := await stream.read(_CHUNK):
        buf += chunk
        if len(buf) > MAX_STDOUT_BYTES:
            raise InvalidOutput(f"output oltre {MAX_STDOUT_BYTES} byte")
    return bytes(buf)


async def _read_stderr(proc: asyncio.subprocess.Process) -> bytes:
    stream = proc.stderr
    assert stream is not None
    kept = bytearray()
    while chunk := await stream.read(_CHUNK):  # si scarta l'eccedenza
        if len(kept) < _ERR_KEEP:
            kept += chunk[: _ERR_KEEP - len(kept)]
    return bytes(kept)


class ExecSimulation:
    def __init__(self, command: list[str], root: Path) -> None:
        self._command, self._root = command, root

    async def run(self, inputs: Mapping[str, float], *, timeout_s: float) -> Mapping[str, float]:
        payload = _encode_inputs(inputs)
        proc = await asyncio.create_subprocess_exec(
            *self._command,
            cwd=self._root,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        tasks: list[asyncio.Task[bytes] | asyncio.Task[None]] = []
        try:
            feed = asyncio.create_task(_feed(proc, payload))
            out_t = asyncio.create_task(_read_stdout(proc))
            err_t = asyncio.create_task(_read_stderr(proc))
            tasks = [feed, out_t, err_t]
            try:
                async with asyncio.timeout(timeout_s):
                    out = await out_t
                    err = await err_t
                    await feed
                    await proc.wait()
            except TimeoutError:
                raise SimulationTimeout(f"oltre {timeout_s}s") from None
            if proc.returncode != 0:
                raise PluginError(f"exit {proc.returncode}: {err.decode(errors='replace')[:200]}")
            return self._parse(out.decode(errors="replace"))
        finally:
            if proc.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    proc.kill()
            for t in tasks:
                t.cancel()
            await asyncio.shield(proc.wait())
            for t in tasks:
                with contextlib.suppress(BaseException):
                    await t

    @staticmethod
    def _parse(text: str) -> dict[str, float]:
        result: dict[str, float] = {}
        for line in text.splitlines():
            if not line.strip():
                continue
            key, sep, val = line.partition("=")
            key = key.strip()
            try:
                num = float(val)
            except ValueError:
                raise InvalidOutput(f"riga non valida: {line!r}") from None
            if not sep or not key or not math.isfinite(num):
                raise InvalidOutput(f"riga non valida: {line!r}")
            if key in result:
                raise InvalidOutput(f"chiave duplicata: {key!r}")
            result[key] = num
        if not result:
            raise InvalidOutput("nessun output")
        return result
