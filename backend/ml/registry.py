# SPDX-License-Identifier: Apache-2.0
"""Registro modelli su file system (spec 13.2): versioni, model card, promozione con cancello.

Scelte di sicurezza
-------------------
* Nessun pickle: il registro memorizza byte opachi (`model.bin`) e non li interpreta. I modelli
  scikit-learn vengono esportati in ONNX (formato dati, non codice eseguibile) dal chiamante e
  letti da onnxruntime. Se un chiamante usasse joblib/pickle, il `sha256` nella card verificato
  prima della restituzione dei byte e' l'UNICA difesa: protegge da corruzione e da sostituzione
  del solo `model.bin`, NON da chi puo' scrivere anche la card (stessa directory, stessa fiducia).
  Per questo la directory del registro deve essere scrivibile solo dal servizio.
* Gli id di versione sono `v` + 4..8 cifre (regex, nessun separatore di percorso); i percorsi sono
  costruiti solo da id validati; link simbolici rifiutati.
* Scritture atomiche (file temporaneo nella stessa directory + fsync + rename).
* Lettura con `open(O_NOFOLLOW)` + `fstat` sul descrittore, traversal relativo a dir_fd (una
  cartella di versione che e' un symlink e' rifiutata). Il modello promosso e' incrociato con la
  card (status, soglia, sha256) a ogni uso: `promoted_version()` fallisce chiusa. La directory del
  registro DEVE essere scrivibile solo dal servizio (chi scrive card e modello insieme vince).
* Concorrenza tra processi: `flock` su `.lock` per allocazione versioni e promozioni (su sistemi
  senza fcntl resta solo il lock di thread: un solo processo scrittore). Non e' multi-nodo.
* Tetto sui candidati (ML_MAX_CANDIDATES, default 50): si potano i piu' vecchi NON promossi;
  directory temporanee `.tmp-<pid>-*` orfane vengono rimosse all'apertura e dopo trainer uccisi.
"""

import contextlib
import hmac
import json
import math
import os
import re
import secrets
import shutil
import stat
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:  # pragma: no cover  (Windows)
    fcntl = None  # type: ignore[assignment]

from backend.core.errors import (
    InvalidVersion,
    ModelIntegrityError,
    ModelNotFound,
    ModelRegistryError,
    PromotionRefused,
)
from backend.envconf import ConfigError, env_positive_int

VERSION_RE = re.compile(r"v[0-9]{4,8}")
KEY_RE = re.compile(r"[a-z][a-z0-9_]{0,63}")
SHA_RE = re.compile(r"[0-9a-f]{64}")
STATUSES = ("candidate", "promoted", "rolled_back")
FORMATS = ("onnx",)
MAX_MODEL_BYTES = 64 * 1024 * 1024
MAX_CARD_BYTES = 64 * 1024
MAX_ENTRIES = 64
DEFAULT_MAX_CANDIDATES = 50
MAX_VERSION_NUMBER = 99_999_999
STALE_TMP_S = 3600.0
MODEL_FILE = "model.bin"
CARD_FILE = "model_card.json"
STATE_FILE = "promotions.json"
_APPROVER_RE = re.compile(r"[\w.@+\- ]{1,64}")


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _check_version(version: object) -> str:
    if not isinstance(version, str) or VERSION_RE.fullmatch(version) is None:
        raise InvalidVersion("id di versione non valido")
    return version


def _finite_map(name: str, value: object) -> dict[str, float]:
    if not isinstance(value, dict) or not value or len(value) > MAX_ENTRIES:
        raise ModelRegistryError(f"{name}: mappa non vuota richiesta")
    out: dict[str, float] = {}
    for k, v in value.items():
        if not isinstance(k, str) or KEY_RE.fullmatch(k) is None:
            raise ModelRegistryError(f"{name}: nome non valido")
        if isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v):
            raise ModelRegistryError(f"{name}.{k}: valore non finito o non numerico")
        out[k] = float(v)
    return out


def _validate_new_card(card: dict[str, Any]) -> dict[str, Any]:
    seed = card.get("seed")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ModelRegistryError("seed: intero richiesto")
    ds = card.get("dataset_sha256")
    if not isinstance(ds, str) or SHA_RE.fullmatch(ds) is None:
        raise ModelRegistryError("dataset_sha256: hex sha256 richiesto")
    libs = card.get("library_versions")
    if (
        not isinstance(libs, dict)
        or len(libs) > MAX_ENTRIES
        or not all(
            isinstance(k, str) and isinstance(v, str) and len(k) < 64 and len(v) < 64
            for k, v in libs.items()
        )
    ):
        raise ModelRegistryError("library_versions: mappa nome -> versione richiesta")
    fmt = card.get("format", "onnx")
    if fmt not in FORMATS:
        raise ModelRegistryError("format non supportato")
    return {
        "seed": seed,
        "dataset_sha256": ds,
        "library_versions": dict(libs),
        "metrics": _finite_map("metrics", card.get("metrics")),
        "threshold": _finite_map("threshold", card.get("threshold")),
        "format": fmt,
    }


def _validate_approver(approver: object) -> str:
    if (
        not isinstance(approver, str)
        or approver != approver.strip()
        or _APPROVER_RE.fullmatch(approver) is None
    ):
        raise PromotionRefused("approvatore non valido")
    return approver


def _sha256_hex(data: bytes) -> str:
    return sha256(data).hexdigest()


_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
PromotedKey = tuple[str, str, int, int, int, int]
Fingerprint = tuple[int, int, int, int]  # (inode, size, mtime_ns, ctime_ns)
# memo condiviso tra istanze: (radice, versione) -> (fingerprint del file, sha256 verificato)
_VERIFIED: dict[tuple[str, str], tuple[Fingerprint, str]] = {}


def _fsync_fd(fd: int) -> None:
    try:
        os.fsync(fd)
    except OSError:
        pass


def _dump(obj: object) -> bytes:
    return json.dumps(obj, indent=2, sort_keys=True, allow_nan=False).encode("utf-8") + b"\n"


def _open_dir_at(dirfd: int, name: str) -> int:
    """Apre una sotto-directory senza seguire link simbolici (traversal relativo a dirfd)."""
    try:
        return os.open(name, _DIR_FLAGS, dir_fd=dirfd)
    except FileNotFoundError:
        raise ModelNotFound("modello non trovato") from None
    except OSError:
        raise ModelIntegrityError("directory del modello non valida") from None


def _open_regular_at(dirfd: int, name: str, cap: int) -> tuple[int, os.stat_result]:
    """open con O_NOFOLLOW + fstat sul descrittore: file regolare e sotto il tetto."""
    try:
        fd = os.open(name, _FILE_FLAGS, dir_fd=dirfd)
    except FileNotFoundError:
        raise ModelNotFound("modello non trovato") from None
    except OSError:
        raise ModelIntegrityError("file del modello non valido") from None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise ModelIntegrityError("file del modello non regolare")
        if st.st_size > cap:
            raise ModelIntegrityError("file del modello troppo grande")
    except BaseException:
        os.close(fd)
        raise
    return fd, st


def _read_fd(fd: int, cap: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    try:
        while True:
            chunk = os.read(fd, min(1 << 20, cap + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > cap:
                raise ModelIntegrityError("file del modello troppo grande")
    except OSError:
        raise ModelIntegrityError("file del modello non leggibile") from None
    finally:
        os.close(fd)
    return b"".join(chunks)


def _read_at(dirfd: int, name: str, cap: int) -> bytes:
    fd, _ = _open_regular_at(dirfd, name, cap)
    return _read_fd(fd, cap)


def _write_at(dirfd: int, name: str, data: bytes) -> None:
    """Scrittura atomica relativa a dirfd: temporaneo O_EXCL + fsync + rename."""
    tmp = f".{name}.{secrets.token_hex(6)}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open(tmp, flags, 0o640, dir_fd=dirfd)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, name, src_dir_fd=dirfd, dst_dir_fd=dirfd)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp, dir_fd=dirfd)
        raise
    _fsync_fd(dirfd)


def _fingerprint(st: os.stat_result) -> Fingerprint:
    return (st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def _gate_failure(card: dict[str, Any]) -> str | None:
    try:
        thr = _finite_map("threshold", card["threshold"])
        met = _finite_map("metrics", card["metrics"])
    except ModelRegistryError:
        return "metriche o soglia non valide"
    for name, minimum in thr.items():
        if name not in met or not met[name] >= minimum:
            return f"metrica {name} sotto la soglia o assente"
    return None


def _env_cap() -> int:
    try:
        return env_positive_int("ML_MAX_CANDIDATES", DEFAULT_MAX_CANDIDATES)
    except ConfigError as e:
        raise ModelRegistryError(str(e)) from None


class FileModelRegistry:
    def __init__(
        self,
        root: Path | str,
        *,
        max_model_bytes: int = MAX_MODEL_BYTES,
        max_candidates: int | None = None,
        stale_tmp_s: float = STALE_TMP_S,
    ) -> None:
        self._root = Path(root)
        self._max_model = max_model_bytes
        self.max_candidates = max_candidates if max_candidates is not None else _env_cap()
        if self.max_candidates < 1:
            raise ModelRegistryError("max_candidates deve essere >= 1")
        self._thread_lock = threading.RLock()
        self._depth = 0
        self._root.mkdir(parents=True, exist_ok=True)
        self._key_root = str(self._root.resolve())
        self.cleanup_tmp(min_age_s=stale_tmp_s)

    # -- infrastruttura ---------------------------------------------------------------------
    @contextlib.contextmanager
    def _root_fd(self) -> Iterator[int]:
        try:
            fd = os.open(self._root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        except OSError:
            raise ModelRegistryError("registro non accessibile") from None
        try:
            yield fd
        finally:
            os.close(fd)

    @contextlib.contextmanager
    def _locked(self) -> Iterator[int]:
        """Lock di thread + flock su `.lock` (cross-processo). Rientrante.

        Senza `fcntl` (Windows) resta solo il lock di thread: registro a singolo processo.
        """
        with self._thread_lock, self._root_fd() as rfd:
            if self._depth == 0 and fcntl is not None:
                lflags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC
                lfd = os.open(".lock", lflags, 0o640, dir_fd=rfd)
                try:
                    fcntl.flock(lfd, fcntl.LOCK_EX)
                    self._depth += 1
                    try:
                        yield rfd
                    finally:
                        self._depth -= 1
                        fcntl.flock(lfd, fcntl.LOCK_UN)
                finally:
                    os.close(lfd)
            else:
                self._depth += 1
                try:
                    yield rfd
                finally:
                    self._depth -= 1

    def _existing_versions(self, rfd: int) -> list[str]:
        out = []
        os.lseek(rfd, 0, os.SEEK_SET)  # listdir(fd) parte dalla posizione corrente
        for name in os.listdir(rfd):
            if VERSION_RE.fullmatch(name) is None:
                continue
            try:
                st = os.stat(name, dir_fd=rfd, follow_symlinks=False)
            except OSError:
                continue
            if stat.S_ISDIR(st.st_mode):
                out.append(name)
        return sorted(out, key=lambda v: int(v[1:]))

    # -- stato promozioni ---------------------------------------------------------------------
    def _stack(self, rfd: int) -> list[str]:
        try:
            raw = _read_at(rfd, STATE_FILE, MAX_CARD_BYTES)
        except ModelNotFound:
            return []
        try:
            stack = json.loads(raw)["stack"]
            if not isinstance(stack, list):
                raise TypeError
            return [_check_version(v) for v in stack]
        except (ValueError, KeyError, TypeError, ModelRegistryError):
            raise ModelIntegrityError("stato delle promozioni non valido") from None

    def _write_stack(self, rfd: int, stack: list[str]) -> None:
        _write_at(rfd, STATE_FILE, _dump({"stack": stack}))

    # -- card ---------------------------------------------------------------------------------
    @staticmethod
    def _parse_card(raw: bytes, version: str) -> dict[str, Any]:
        try:
            card = json.loads(raw, parse_constant=_reject_constant)
        except ValueError:
            raise ModelIntegrityError("model card non valida") from None
        if (
            not isinstance(card, dict)
            or card.get("version") != version
            or card.get("status") not in STATUSES
            or not isinstance(card.get("model_sha256"), str)
            or SHA_RE.fullmatch(card["model_sha256"]) is None
            or not isinstance(card.get("metrics"), dict)
            or not isinstance(card.get("threshold"), dict)
        ):
            raise ModelIntegrityError("model card non valida")
        return card

    def _card_at(self, vfd: int, version: str) -> dict[str, Any]:
        return self._parse_card(_read_at(vfd, CARD_FILE, MAX_CARD_BYTES), version)

    def _write_card(self, rfd: int, version: str, card: dict[str, Any]) -> None:
        vfd = _open_dir_at(rfd, _check_version(version))
        try:
            _write_at(vfd, CARD_FILE, _dump(card))
        finally:
            os.close(vfd)

    def _verified(
        self, rfd: int, version: str, *, need_blob: bool
    ) -> tuple[bytes | None, dict[str, Any], Fingerprint]:
        """Card + modello verificati (sha256). Senza `need_blob` riusa l'esito se il file e'
        invariato (inode, size, mtime, ctime) e la card ha lo stesso sha256."""
        vfd = _open_dir_at(rfd, _check_version(version))
        try:
            card = self._card_at(vfd, version)
            fd, st = _open_regular_at(vfd, MODEL_FILE, self._max_model)
        finally:
            os.close(vfd)
        fp = _fingerprint(st)
        key = (self._key_root, version)
        memo = _VERIFIED.get(key)
        if not need_blob and memo == (fp, card["model_sha256"]):
            os.close(fd)
            return None, card, fp
        blob = _read_fd(fd, self._max_model)
        if not hmac.compare_digest(_sha256_hex(blob), card["model_sha256"]):
            _VERIFIED.pop(key, None)
            raise ModelIntegrityError("sha256 del modello non corrisponde alla card")
        _VERIFIED[key] = (fp, card["model_sha256"])
        return blob, card, fp

    # -- pulizia ------------------------------------------------------------------------------
    def cleanup_tmp(self, *, pid: int | None = None, min_age_s: float | None = None) -> int:
        """Rimuove directory `.tmp-<pid>-*` orfane. Con `pid` solo quelle di quel processo
        (qualsiasi eta'); altrimenti quelle piu' vecchie di `min_age_s`. Non segue symlink."""
        removed = 0
        now = time.time()
        try:
            names = os.listdir(self._root)
        except OSError:
            return 0
        for name in names:
            if not name.startswith(".tmp-"):
                continue
            path = self._root / name
            try:
                st = path.lstat()
            except OSError:
                continue
            if not stat.S_ISDIR(st.st_mode):
                continue  # niente symlink: non vengono seguiti ne' rimossi
            if pid is not None:
                if not name.startswith(f".tmp-{pid}-"):
                    continue
            elif min_age_s is None or now - st.st_mtime < min_age_s:
                continue
            shutil.rmtree(path, ignore_errors=True)
            removed += 1
        return removed

    def _prune_candidates(self, rfd: int) -> None:
        stack = set(self._stack(rfd))
        candidates = []
        for v in self._existing_versions(rfd):
            if v in stack:
                continue
            try:
                vfd = _open_dir_at(rfd, v)
                try:
                    card = self._card_at(vfd, v)
                finally:
                    os.close(vfd)
            except ModelRegistryError:
                continue
            if card["status"] == "candidate":
                candidates.append(v)
        for v in candidates[: max(0, len(candidates) - self.max_candidates)]:
            shutil.rmtree(self._root / v, ignore_errors=True)
            _VERIFIED.pop((self._key_root, v), None)

    # -- API ----------------------------------------------------------------------------------
    def save(self, model: bytes, card: Any) -> str:
        if not isinstance(model, bytes | bytearray) or not model:
            raise ModelRegistryError("modello vuoto")
        if len(model) > self._max_model:
            raise ModelRegistryError("modello troppo grande")
        if not isinstance(card, dict):
            raise ModelRegistryError("card non valida")
        body = _validate_new_card(card)
        blob = bytes(model)
        with self._locked() as rfd:
            existing = self._existing_versions(rfd)
            n = int(existing[-1][1:]) + 1 if existing else 1
            if n > MAX_VERSION_NUMBER:
                raise ModelRegistryError("spazio delle versioni esaurito")
            version = f"v{n:04d}"
            tmp = f".tmp-{os.getpid()}-{secrets.token_hex(8)}"
            os.mkdir(tmp, 0o750, dir_fd=rfd)
            try:
                tfd = _open_dir_at(rfd, tmp)
                try:
                    full = {
                        **body,
                        "version": version,
                        "status": "candidate",
                        "model_sha256": _sha256_hex(blob),
                        "model_bytes": len(blob),
                        "created_utc": _utc_now(),
                    }
                    _write_at(tfd, MODEL_FILE, blob)
                    _write_at(tfd, CARD_FILE, _dump(full))
                finally:
                    os.close(tfd)
                os.rename(tmp, version, src_dir_fd=rfd, dst_dir_fd=rfd)
                _fsync_fd(rfd)
            except BaseException:
                shutil.rmtree(self._root / tmp, ignore_errors=True)
                raise
            self._prune_candidates(rfd)
            return version

    def load(self, version: str) -> tuple[bytes, dict[str, Any]]:
        _check_version(version)
        with self._root_fd() as rfd:
            blob, card, _ = self._verified(rfd, version, need_blob=True)
        assert blob is not None
        return blob, card

    def list_versions(self) -> list[dict[str, Any]]:
        out = []
        with self._root_fd() as rfd:
            for v in self._existing_versions(rfd):
                try:
                    vfd = _open_dir_at(rfd, v)
                    try:
                        out.append(self._card_at(vfd, v))
                    finally:
                        os.close(vfd)
                except ModelRegistryError:
                    continue
        return out

    def _promoted(
        self, *, need_blob: bool
    ) -> tuple[bytes | None, dict[str, Any], PromotedKey] | None:
        """Un'unica istantanea coerente: card, controllo incrociato e (opz.) byte verificati.

        Il scrittore aggiorna card e poi stack (promozione) o stack e poi card (rollback): un
        lettore concorrente puo' vedere al piu' lo stato vecchio o nuovo. Se la card in cima non e'
        coerente ma lo stack e' cambiato nel frattempo si riprova (al massimo 3 volte).
        """
        last: ModelIntegrityError | None = None
        for _ in range(3):
            with self._root_fd() as rfd:
                stack = self._stack(rfd)
                if not stack:
                    return None
                top = stack[-1]
                try:
                    blob, card, fp = self._verified(rfd, top, need_blob=need_blob)
                    if card["status"] != "promoted":
                        raise ModelIntegrityError(
                            "il modello in cima alle promozioni non e' promosso"
                        )
                    if _gate_failure(card) is not None:
                        raise ModelIntegrityError("il modello promosso non rispetta la soglia")
                except ModelIntegrityError as e:
                    if self._stack(rfd) == stack:
                        raise  # nessuna scrittura concorrente: inconsistenza reale, fail-closed
                    last = e
                    continue
            return blob, card, (top, card["model_sha256"], fp[0], fp[1], fp[2], fp[3])
        raise last or ModelIntegrityError("stato del registro instabile")

    def promoted_card(self) -> tuple[dict[str, Any], PromotedKey] | None:
        """Card del modello promosso dopo il controllo incrociato (fail-closed).

        Richiede: versione in cima a promotions.json, `status == promoted`, metriche >= soglia,
        sha256 verificato (ricalcolato solo se cambiano inode/size/mtime/ctime del file o lo sha256
        nella card). La chiave (versione, sha256, inode, size, mtime_ns, ctime_ns) serve alle cache.
        """
        snap = self._promoted(need_blob=False)
        return None if snap is None else (snap[1], snap[2])

    def promoted_snapshot(self) -> tuple[bytes, dict[str, Any], PromotedKey] | None:
        """Come `promoted_card` ma restituisce i byte verificati dalla STESSA lettura: chi li usa
        costruisce il modello esattamente da cio' che e' stato controllato."""
        snap = self._promoted(need_blob=True)
        if snap is None:
            return None
        assert snap[0] is not None
        return snap[0], snap[1], snap[2]

    def promoted_version(self) -> str | None:
        pc = self.promoted_card()
        return None if pc is None else str(pc[0]["version"])

    def promote(self, version: str, *, approver: str, approved: bool = False) -> dict[str, Any]:
        _check_version(version)
        if approved is not True:
            raise PromotionRefused("approvazione esplicita mancante")
        who = _validate_approver(approver)
        with self._locked() as rfd:
            _, card, _ = self._verified(rfd, version, need_blob=True)
            stack = self._stack(rfd)
            if card["status"] not in ("candidate", "promoted") or version in stack:
                raise PromotionRefused("solo un candidato puo' essere promosso")
            why = _gate_failure(card)
            if why is not None:
                raise PromotionRefused(why)
            card = {**card, "status": "promoted", "approved_by": who, "promoted_utc": _utc_now()}
            # card prima, stack dopo: chi legge non vede mai in cima un candidato
            self._write_card(rfd, version, card)
            self._write_stack(rfd, [*stack, version])
            return card

    def rollback(self, *, approver: str) -> str:
        who = _validate_approver(approver)
        with self._locked() as rfd:
            stack = self._stack(rfd)
            if len(stack) < 2:
                raise PromotionRefused("nessuna versione promossa precedente")
            current, previous = stack[-1], stack[-2]
            _, prev_card, _ = self._verified(rfd, previous, need_blob=True)
            if prev_card["status"] != "promoted" or _gate_failure(prev_card) is not None:
                raise ModelIntegrityError("la versione precedente non e' piu' valida")
            vfd = _open_dir_at(rfd, current)
            try:
                cur_card = self._card_at(vfd, current)
            finally:
                os.close(vfd)
            self._write_stack(rfd, stack[:-1])
            self._write_card(
                rfd,
                current,
                {
                    **cur_card,
                    "status": "rolled_back",
                    "rolled_back_by": who,
                    "rolled_back_utc": _utc_now(),
                },
            )
            return previous


def _reject_constant(name: str) -> float:
    raise ValueError(f"costante JSON non ammessa: {name}")


def default_registry_dir() -> Path:
    """`MODEL_REGISTRY_DIR` se impostata, altrimenti `build/models` (cartella ignorata da git)."""
    env = os.environ.get("MODEL_REGISTRY_DIR")
    return Path(env) if env else Path(__file__).resolve().parents[2] / "build" / "models"
