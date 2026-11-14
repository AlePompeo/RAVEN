# SPDX-License-Identifier: Apache-2.0
"""Gestore dei kernel NAIF (dominio pubblico) con hash fissati in `kernels.lock.json`.

Sicurezza: solo HTTPS verso l'host del lock, nessun redirect verso altri host o http, timeout,
tetto di byte uguale alla dimensione attesa, file temporaneo + `os.replace` atomico, hash SHA-256
verificato PRIMA di rendere visibile il file. Il contenuto scaricato non viene mai eseguito,
ne' interpretato oltre al calcolo dell'hash.

Riconoscimento: i kernel sono prodotti da NAIF/JPL; vedi docs/ephemeris.md.
"""

import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from http.client import HTTPMessage
from pathlib import Path
from typing import Any, Protocol

LOCK_PATH = Path(__file__).with_name("kernels.lock.json")
DEFAULT_DIR = Path(__file__).resolve().parents[2] / "build" / "ephemeris"
ALLOWED_HOST = "naif.jpl.nasa.gov"
TIMEOUT_S = 60.0
CHUNK = 1 << 20


class EphemerisUnavailable(RuntimeError):
    """Kernel assenti o non verificati: le funzioni di efemeride non sono disponibili."""


class KernelIntegrityError(RuntimeError):
    """Download rifiutato (schema/host, dimensione o hash non corrispondenti)."""


@dataclass(frozen=True)
class KernelSpec:
    name: str
    url: str
    size: int
    sha256: str
    retrieved: str
    role: str


def load_lock(path: Path = LOCK_PATH) -> list[KernelSpec]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [
        KernelSpec(**{f: e[f] for f in KernelSpec.__dataclass_fields__}) for e in raw["kernels"]
    ]


def ephemeris_dir(env: Mapping[str, str] | None = None) -> Path:
    value = (os.environ if env is None else env).get("EPHEMERIS_DIR")
    return Path(value) if value else DEFAULT_DIR


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def problems(directory: Path, specs: Sequence[KernelSpec] | None = None) -> list[str]:
    """Elenco dei problemi (vuoto = tutti i kernel presenti, della dimensione e con l'hash del lock)."""
    out: list[str] = []
    for s in specs if specs is not None else load_lock():
        p = directory / s.name
        if not p.is_file():
            out.append(f"{s.name}: assente")
        elif p.stat().st_size != s.size:
            out.append(f"{s.name}: dimensione diversa dal lock")
        elif sha256_file(p) != s.sha256:
            out.append(f"{s.name}: hash diverso dal lock")
    return out


def require_kernels(
    directory: Path | None = None, specs: Sequence[KernelSpec] | None = None
) -> dict[str, Path]:
    """Percorsi verificati dei kernel, o `EphemerisUnavailable` (mai un crash dell'app)."""
    d = directory if directory is not None else ephemeris_dir()
    use = list(specs) if specs is not None else load_lock()
    try:
        bad = problems(d, use)
    except OSError as e:
        raise EphemerisUnavailable("kernel di efemeride non leggibili") from e
    if bad:
        raise EphemerisUnavailable(
            "kernel di efemeride assenti o non verificati: " + "; ".join(bad)
        )
    return {s.name: d / s.name for s in use}


class _SameHostRedirect(urllib.request.HTTPRedirectHandler):
    """Segue i redirect solo verso https sullo stesso host della richiesta originale."""

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: HTTPMessage | Mapping[str, str],
        newurl: str,
    ) -> urllib.request.Request | None:
        new = urllib.parse.urlsplit(newurl)
        old = urllib.parse.urlsplit(req.full_url)
        if new.scheme != "https" or new.hostname != old.hostname:
            raise urllib.error.HTTPError(req.full_url, code, "redirect rifiutato", headers, fp)  # type: ignore[arg-type]
        return super().redirect_request(req, fp, code, msg, headers, newurl)  # type: ignore[arg-type]


class _Opener(Protocol):
    def open(self, url: str, timeout: float) -> Any: ...


def _default_opener() -> _Opener:
    d = urllib.request.OpenerDirector()
    for h in (
        urllib.request.HTTPSHandler(),
        _SameHostRedirect(),
        urllib.request.HTTPErrorProcessor(),
        urllib.request.UnknownHandler(),
    ):
        d.add_handler(h)
    return d  # type: ignore[return-value]


def _check_spec(spec: KernelSpec) -> None:
    u = urllib.parse.urlsplit(spec.url)
    if u.scheme != "https" or u.hostname != ALLOWED_HOST:
        raise KernelIntegrityError(f"{spec.name}: URL non consentito (solo https://{ALLOWED_HOST})")
    if Path(spec.name).name != spec.name or spec.name in ("", ".", ".."):
        raise KernelIntegrityError("nome file non valido")


def download(spec: KernelSpec, directory: Path, opener: _Opener | None = None) -> Path:
    """Scarica un kernel; lo rende visibile solo se dimensione e SHA-256 coincidono col lock."""
    _check_spec(spec)
    directory.mkdir(parents=True, exist_ok=True)
    dest = directory / spec.name
    tmp = directory / f".{spec.name}.{os.getpid()}.part"
    h = hashlib.sha256()
    total = 0
    try:
        with (opener or _default_opener()).open(spec.url, timeout=TIMEOUT_S) as resp:
            declared = resp.headers.get("Content-Length")
            if declared is not None and int(declared) != spec.size:
                raise KernelIntegrityError(f"{spec.name}: Content-Length diversa dal lock")
            with tmp.open("wb") as out:
                while chunk := resp.read(CHUNK):
                    total += len(chunk)
                    if total > spec.size:
                        raise KernelIntegrityError(f"{spec.name}: oltre la dimensione del lock")
                    h.update(chunk)
                    out.write(chunk)
        if total != spec.size:
            raise KernelIntegrityError(f"{spec.name}: dimensione diversa dal lock")
        if h.hexdigest() != spec.sha256:
            raise KernelIntegrityError(f"{spec.name}: hash diverso dal lock, file rifiutato")
        os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)
    return dest


def fetch_all(
    directory: Path, specs: Sequence[KernelSpec] | None = None, opener: _Opener | None = None
) -> list[Path]:
    """Scarica i kernel mancanti o non validi; quelli gia' validi non vengono riscaricati."""
    out: list[Path] = []
    for s in specs if specs is not None else load_lock():
        if problems(directory, [s]):
            download(s, directory, opener)
        out.append(directory / s.name)
    return out
