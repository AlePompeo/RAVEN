# Hackathon Base Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Costruire su `master` il template modulare per hackathon spaziali (backend FastAPI a plugin, frontend Svelte 5, contratti, compliance, CI) e poi derivare `hackathon/nasa-lunar`.

**Architecture:** Monolite modulare esagonale: `core/` (porte, registry, manifest) non dipende da nessun altro livello; `adapters/` e `plugins/` implementano le porte; `api/` espone REST+SSE. Frontend con shell Svelte e moduli pesanti (3D/grafici) in TypeScript puro dietro `ViewportPort`, caricati con `import()`.

**Tech Stack:** Python (FastAPI, Pydantic v2, pytest, httpx, ruff, mypy, import-linter), Node/Vite/TypeScript/Svelte 5, Three.js, uPlot, Docker Compose, GitHub Actions. Versioni esatte: da fissare e verificare nel Task 1 e 10 (non assunte).

**Spec:** `docs/superpowers/specs/2026-10-12-hackathon-base-design.md`

## Global Constraints

- Licenza progetto Apache-2.0; ogni file sorgente ha intestazione `SPDX-License-Identifier: Apache-2.0`.
- `core/` non importa mai da `plugins/`, `domain/`, `adapters/`, `api/` (import-linter in CI).
- Unità nel nome dei campi (`_deg`, `_w`, `_db`, `_km`); tempi UTC ISO-8601; ogni messaggio ha `schema_version`.
- Nessun cookie non essenziale e nessun tracker per default.
- Segreti solo da variabili d'ambiente, mai nel client.
- Nessuna shell nei subprocess: `create_subprocess_exec` con lista argomenti; eseguibili solo dentro la cartella del plugin.
- Ambiente verificato: Python 3.14.7, Node 20.18.1, Docker 29.6.2, make 4.4.1, gcc 15.3.1. Mancano `uv`, `pnpm`, Octave: si usa `venv`+`pip` e `npm`; i test Octave vengono saltati se manca.
- Test sempre prima del codice (TDD), commit frequenti con messaggi convenzionali e riga `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## Review Focus

1. Simulazione che non termina o ignora il timeout → deve essere uccisa e dare `SimulationTimeout` (Task 5).
2. Manifest malformato o plugin con `entry` rotto → errore chiaro, gli altri plugin e l'app partono comunque (Task 3).
3. `entry` di tipo `exec:` che punta fuori dalla cartella del plugin (path traversal, `../`) → rifiutato (Task 5).
4. API esterna giù o lenta → si serve la cache scaduta (stale) o 503 pulito, mai crash (Task 6, 8).
5. Output di simulazione con `NaN`/`inf` o non numerico → rifiutato prima di arrivare al client (Task 5).

---

## Mappa file

```
Makefile  pyproject.toml  importlinter  LICENSE  REUSE.toml  .gitignore  .editorconfig
.github/workflows/ci.yml  Dockerfile  compose.yaml  .env.example
contracts/telemetry.schema.json   contracts/gen.py
backend/core/{errors,ports,manifest,registry}.py
backend/adapters/{subprocess_sim,cache_memory,cache_valkey}.py
backend/plugins/example_sim/{manifest.toml,plugin.py}
backend/plugins/fspl_c/{manifest.toml,fspl.c}
backend/plugins/example_llm/{manifest.toml,plugin.py}
backend/plugins/example_data/{manifest.toml,plugin.py}
backend/api/{app.py,security.py,routes.py}
backend/bootstrap.py
tests/backend/...
frontend/{package.json,vite.config.ts,index.html}
frontend/src/{main.ts,App.svelte}
frontend/src/shell/{router.ts,a11y.ts,consent.ts}
frontend/src/pages/{home,telemetry,viewer,chat,sims,legal}/
frontend/src/{viewports,charts}/
docs/{architecture.md,traceability.md}
```

---

### Task 1: Scaffold, licenza, tooling

**Files:**
- Create: `LICENSE`, `REUSE.toml`, `.gitignore`, `.editorconfig`, `pyproject.toml`, `Makefile`, `.importlinter`, `tests/backend/test_smoke.py`, `backend/__init__.py`, `backend/core/__init__.py`

- [ ] **Step 1: Test di fumo (fallisce)**

```python
# tests/backend/test_smoke.py
# SPDX-License-Identifier: Apache-2.0
def test_core_importable():
    import backend.core

    assert backend.core is not None
```

- [ ] **Step 2: Run** `python3 -m pytest tests/backend/test_smoke.py -v` → FAIL (`No module named pytest` o `backend`).

- [ ] **Step 3: Scaffold.** Scarica il testo ufficiale Apache-2.0 in `LICENSE` (`curl -fsSL https://www.apache.org/licenses/LICENSE-2.0.txt -o LICENSE`). Crea `pyproject.toml`:

```toml
[project]
name = "hackathon-base"
version = "0.1.0"
requires-python = ">=3.12"
license = "Apache-2.0"
dependencies = ["fastapi", "pydantic>=2", "uvicorn[standard]", "httpx"]
[project.optional-dependencies]
dev = ["pytest", "pytest-asyncio", "ruff", "mypy", "import-linter", "datamodel-code-generator", "cyclonedx-bom", "pip-licenses"]
[tool.pytest.ini_options]
asyncio_mode = "auto"
pythonpath = ["."]
testpaths = ["tests/backend"]
[tool.ruff]
line-length = 100
[tool.mypy]
strict = true
files = ["backend"]
```

`.importlinter`:

```ini
[importlinter]
root_packages = backend

[importlinter:contract:core-independent]
name = core non dipende dagli altri livelli
type = forbidden
source_modules = backend.core
forbidden_modules = backend.adapters, backend.api, backend.plugins, backend.domain
```

`Makefile` (target: `venv`, `test`, `lint`, `dev`, `build-c`):

```make
PY=.venv/bin/python
venv: ; python3 -m venv .venv && $(PY) -m pip install -e ".[dev]"
test: ; $(PY) -m pytest
lint: ; $(PY) -m ruff check . && $(PY) -m mypy && .venv/bin/lint-imports
build-c: ; mkdir -p build && gcc -O2 -o build/fspl backend/plugins/fspl_c/fspl.c -lm
dev: ; $(PY) -m uvicorn --factory backend.bootstrap:build_app --reload
```

- [ ] **Step 4:** `make venv && make test` → PASS. Registra le versioni installate in `docs/versions.md` (`pip freeze | head`), così le versioni sono verificate e non assunte.
- [ ] **Step 5: Commit** `git add -A && git commit -m "chore: scaffold, license and tooling"`

---

### Task 2: Core — errori e porte

**Files:** Create `backend/core/errors.py`, `backend/core/ports.py`; Test `tests/backend/core/test_ports.py`

**Interfaces — Produces:** `Simulation.run(inputs, *, timeout_s) -> Mapping[str,float]`, `CachePort.get/set`, `DataSource.fetch(query)`, `LLMProvider.stream(messages)`, errori `PluginError`, `ManifestError`, `PluginNotFound`, `SimulationTimeout`, `InvalidOutput`.

- [ ] **Step 1: Test**

```python
# tests/backend/core/test_ports.py
from backend.core.errors import PluginError, SimulationTimeout, InvalidOutput
from backend.core.ports import Simulation


class Fake:
    async def run(self, inputs, *, timeout_s):
        return {"y": 1.0}


def test_errors_share_base():
    assert issubclass(SimulationTimeout, PluginError)
    assert issubclass(InvalidOutput, PluginError)


def test_simulation_protocol_is_structural():
    assert isinstance(Fake(), Simulation)
```

- [ ] **Step 2:** `.venv/bin/python -m pytest tests/backend/core/test_ports.py -v` → FAIL (moduli mancanti).
- [ ] **Step 3: Implementazione**

```python
# backend/core/errors.py
# SPDX-License-Identifier: Apache-2.0
class PluginError(Exception): ...


class ManifestError(PluginError): ...


class PluginNotFound(PluginError): ...


class SimulationTimeout(PluginError): ...


class InvalidOutput(PluginError): ...
```

```python
# backend/core/ports.py
# SPDX-License-Identifier: Apache-2.0
from collections.abc import AsyncIterator, Mapping
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Simulation(Protocol):
    async def run(
        self, inputs: Mapping[str, float], *, timeout_s: float
    ) -> Mapping[str, float]: ...


@runtime_checkable
class CachePort(Protocol):
    async def get(self, key: str, *, allow_stale: bool = False) -> bytes | None: ...
    async def set(self, key: str, value: bytes, ttl_s: float) -> None: ...


@runtime_checkable
class DataSource(Protocol):
    async def fetch(self, query: Mapping[str, Any]) -> Mapping[str, Any]: ...


@runtime_checkable
class LLMProvider(Protocol):
    def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]: ...
```

- [ ] **Step 4:** test → PASS. **Step 5: Commit** `feat(core): ports and errors`.

---

### Task 3: Manifest e registry (Review Focus 2)

**Files:** Create `backend/core/manifest.py`, `backend/core/registry.py`; Test `tests/backend/core/test_manifest_registry.py`

**Interfaces — Consumes:** errori Task 2. **Produces:** `Manifest(id, kind, version, entry, license, terms_url, timeout_s, root: Path)`, `load_manifest(path) -> Manifest`, `Registry.register(manifest, factory)`, `Registry.create(kind, id)`, `Registry.discover(plugins_dir, loader) -> list[tuple[Path, Exception]]` (errori raccolti, non sollevati).

- [ ] **Step 1: Test**

```python
# tests/backend/core/test_manifest_registry.py
import pytest
from backend.core.errors import ManifestError, PluginNotFound
from backend.core.manifest import load_manifest
from backend.core.registry import Registry

GOOD = 'id="a"\nkind="simulation"\nversion="0.1.0"\nentry="python:x:Y"\nlicense="Apache-2.0"\n'


def test_load_manifest_ok(tmp_path):
    (tmp_path / "manifest.toml").write_text(GOOD)
    m = load_manifest(tmp_path / "manifest.toml")
    assert (m.id, m.kind, m.timeout_s) == ("a", "simulation", 30.0)


@pytest.mark.parametrize("bad", ["", 'id="a"', GOOD.replace("simulation", "bogus"), "not = [toml"])
def test_load_manifest_rejects_bad(tmp_path, bad):
    (tmp_path / "manifest.toml").write_text(bad)
    with pytest.raises(ManifestError):
        load_manifest(tmp_path / "manifest.toml")


def test_data_source_requires_terms_url(tmp_path):
    (tmp_path / "manifest.toml").write_text(GOOD.replace("simulation", "data_source"))
    with pytest.raises(ManifestError, match="terms_url"):
        load_manifest(tmp_path / "manifest.toml")


def test_registry_create_and_missing(tmp_path):
    (tmp_path / "manifest.toml").write_text(GOOD)
    m = load_manifest(tmp_path / "manifest.toml")
    r = Registry()
    r.register(m, lambda manifest: "instance")
    assert r.create("simulation", "a") == "instance"
    with pytest.raises(PluginNotFound):
        r.create("simulation", "nope")


def test_discover_isolates_broken_plugins(tmp_path):
    ok = tmp_path / "ok"
    ok.mkdir()
    (ok / "manifest.toml").write_text(GOOD)
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "manifest.toml").write_text("garbage = [")
    r = Registry()
    errors = r.discover(tmp_path, loader=lambda m: lambda manifest: "inst")
    assert r.create("simulation", "a") == "inst"
    assert len(errors) == 1 and errors[0][0].name == "bad"
```

- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: Implementazione**

```python
# backend/core/manifest.py
# SPDX-License-Identifier: Apache-2.0
import tomllib
from dataclasses import dataclass
from pathlib import Path
from backend.core.errors import ManifestError

KINDS = {"data_source", "simulation", "llm", "telemetry"}
REQUIRED = ("id", "kind", "version", "entry", "license")


@dataclass(frozen=True)
class Manifest:
    id: str
    kind: str
    version: str
    entry: str
    license: str
    terms_url: str
    timeout_s: float
    root: Path


def load_manifest(path: Path) -> Manifest:
    try:
        data = tomllib.loads(path.read_text())
    except (tomllib.TOMLDecodeError, OSError) as e:
        raise ManifestError(f"{path}: {e}") from e
    missing = [k for k in REQUIRED if k not in data]
    if missing:
        raise ManifestError(f"{path}: campi mancanti {missing}")
    if data["kind"] not in KINDS:
        raise ManifestError(f"{path}: kind non valido {data['kind']!r}")
    if data["kind"] in ("data_source", "llm") and not data.get("terms_url"):
        raise ManifestError(f"{path}: terms_url obbligatorio per {data['kind']}")
    return Manifest(
        data["id"],
        data["kind"],
        data["version"],
        data["entry"],
        data["license"],
        data.get("terms_url", ""),
        float(data.get("timeout_s", 30.0)),
        path.parent,
    )
```

```python
# backend/core/registry.py
# SPDX-License-Identifier: Apache-2.0
from collections.abc import Callable
from pathlib import Path
from typing import Any
from backend.core.errors import PluginNotFound
from backend.core.manifest import Manifest, load_manifest

Factory = Callable[[Manifest], Any]


class Registry:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], tuple[Manifest, Factory]] = {}

    def register(self, manifest: Manifest, factory: Factory) -> None:
        self._items[(manifest.kind, manifest.id)] = (manifest, factory)

    def create(self, kind: str, id: str) -> Any:
        try:
            manifest, factory = self._items[(kind, id)]
        except KeyError:
            raise PluginNotFound(f"{kind}/{id}") from None
        return factory(manifest)

    def manifests(self) -> list[Manifest]:
        return [m for m, _ in self._items.values()]

    def discover(
        self, plugins_dir: Path, loader: Callable[[Manifest], Factory]
    ) -> list[tuple[Path, Exception]]:
        errors: list[tuple[Path, Exception]] = []
        for mf in sorted(plugins_dir.glob("*/manifest.toml")):
            try:
                manifest = load_manifest(mf)
                self.register(manifest, loader(manifest))
            except Exception as e:  # un plugin rotto non ferma gli altri
                errors.append((mf.parent, e))
        return errors
```

- [ ] **Step 4:** PASS. **Step 5: Commit** `feat(core): manifest and registry with fault isolation`.

---

### Task 4: Adapter subprocess (C/MATLAB/Octave) — Review Focus 1, 3, 5

**Files:** Create `backend/adapters/subprocess_sim.py`, `backend/plugins/fspl_c/{fspl.c,manifest.toml}`; Test `tests/backend/adapters/test_subprocess_sim.py`

**Protocollo piatto numerico:** stdin righe `chiave=valore`; stdout righe `chiave=valore`. Semplice da produrre in C, MATLAB e Octave.

**Interfaces — Produces:** `ExecSimulation(command: list[str], root: Path)` che implementa `Simulation`; `resolve_inside(root, rel) -> Path` (solleva `PluginError` se esce da `root`).

- [ ] **Step 1: Test**

```python
# tests/backend/adapters/test_subprocess_sim.py
import shutil, subprocess, sys
from pathlib import Path
import pytest
from backend.adapters.subprocess_sim import ExecSimulation, resolve_inside
from backend.core.errors import InvalidOutput, PluginError, SimulationTimeout

ROOT = Path(__file__).resolve().parents[3]


def test_resolve_inside_rejects_traversal(tmp_path):
    with pytest.raises(PluginError):
        resolve_inside(tmp_path, "../evil")
    with pytest.raises(PluginError):
        resolve_inside(tmp_path, "/bin/sh")


@pytest.fixture(scope="session")
def fspl_bin():
    if not shutil.which("gcc"):
        pytest.skip("gcc assente")
    out = ROOT / "build" / "fspl"
    out.parent.mkdir(exist_ok=True)
    subprocess.run(
        ["gcc", "-O2", "-o", str(out), str(ROOT / "backend/plugins/fspl_c/fspl.c"), "-lm"],
        check=True,
    )
    return out


async def test_fspl_c_matches_formula(fspl_bin):
    sim = ExecSimulation([str(fspl_bin)], root=fspl_bin.parent)
    out = await sim.run({"distance_km": 384400.0, "freq_ghz": 2.2}, timeout_s=5)
    assert out["fspl_db"] == pytest.approx(210.99, abs=0.02)


def script(tmp_path, body):
    p = tmp_path / "s.py"
    p.write_text(body)
    return ExecSimulation([sys.executable, str(p)], root=tmp_path)


async def test_timeout_kills_process(tmp_path):
    sim = script(tmp_path, "import time; time.sleep(60)")
    with pytest.raises(SimulationTimeout):
        await sim.run({}, timeout_s=0.5)


@pytest.mark.parametrize("line", ["y=nan", "y=inf", "y=abc", "senza_uguale"])
async def test_invalid_output_rejected(tmp_path, line):
    sim = script(tmp_path, f"print({line!r})")
    with pytest.raises(InvalidOutput):
        await sim.run({}, timeout_s=5)


async def test_nonzero_exit_is_error(tmp_path):
    sim = script(tmp_path, "import sys; sys.exit(3)")
    with pytest.raises(PluginError):
        await sim.run({}, timeout_s=5)
```

- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: Implementazione**

```c
/* backend/plugins/fspl_c/fspl.c — SPDX-License-Identifier: Apache-2.0 */
#include <stdio.h>
#include <string.h>
#include <math.h>
int main(void) {
    char line[256]; double d = 0, f = 0;
    while (fgets(line, sizeof line, stdin)) {
        if (sscanf(line, "distance_km=%lf", &d) == 1) continue;
        sscanf(line, "freq_ghz=%lf", &f);
    }
    if (d <= 0 || f <= 0) return 2;
    printf("fspl_db=%.6f\n", 92.45 + 20.0 * log10(d) + 20.0 * log10(f));
    return 0;
}
```

```python
# backend/adapters/subprocess_sim.py
# SPDX-License-Identifier: Apache-2.0
import asyncio, math
from collections.abc import Mapping
from pathlib import Path
from backend.core.errors import InvalidOutput, PluginError, SimulationTimeout


def resolve_inside(root: Path, rel: str) -> Path:
    root = root.resolve()
    p = (root / rel).resolve()
    if not p.is_relative_to(root):
        raise PluginError(f"percorso fuori dal plugin: {rel}")
    return p


class ExecSimulation:
    def __init__(self, command: list[str], root: Path) -> None:
        self._command, self._root = command, root

    async def run(self, inputs: Mapping[str, float], *, timeout_s: float) -> Mapping[str, float]:
        payload = "".join(f"{k}={float(v)!r}\n" for k, v in inputs.items()).encode()
        proc = await asyncio.create_subprocess_exec(
            *self._command,
            cwd=self._root,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(payload), timeout_s)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            raise SimulationTimeout(f"oltre {timeout_s}s") from None
        if proc.returncode != 0:
            raise PluginError(f"exit {proc.returncode}: {err.decode(errors='replace')[:200]}")
        return self._parse(out.decode(errors="replace"))

    @staticmethod
    def _parse(text: str) -> dict[str, float]:
        result: dict[str, float] = {}
        for line in text.splitlines():
            if not line.strip():
                continue
            key, sep, val = line.partition("=")
            try:
                num = float(val)
            except ValueError:
                raise InvalidOutput(f"riga non valida: {line!r}") from None
            if not sep or not math.isfinite(num):
                raise InvalidOutput(f"riga non valida: {line!r}")
            result[key.strip()] = num
        if not result:
            raise InvalidOutput("nessun output")
        return result
```

`manifest.toml` di `fspl_c`: `id="fspl-c"`, `kind="simulation"`, `version="0.1.0"`, `entry="exec:../../build/fspl"`, `license="Apache-2.0"`, `timeout_s=5`. Nota: l'`entry` esce dalla cartella per usare `build/`; per evitare l'eccezione di `resolve_inside` il Makefile `build-c` compila **dentro** `backend/plugins/fspl_c/bin/fspl` e l'entry diventa `exec:bin/fspl` (aggiorna Makefile e `.gitignore`: `bin/`).

- [ ] **Step 4:** `make build-c` poi test → PASS. **Step 5: Commit** `feat(adapters): sandboxed subprocess simulation (C/MATLAB/Octave)`.

---

### Task 5: Loader di plugin e plugin Python di esempio

**Files:** Create `backend/bootstrap.py` (parte loader), `backend/plugins/example_sim/{manifest.toml,plugin.py}`; Test `tests/backend/test_loader.py`

**Interfaces — Consumes:** `Registry.discover`, `ExecSimulation`, `resolve_inside`. **Produces:** `make_loader() -> Callable[[Manifest], Factory]` che interpreta `python:modulo:Classe` ed `exec:percorso`.

- [ ] **Step 1: Test** — `python:` istanzia la classe con `manifest`; `exec:` costruisce `ExecSimulation([resolve_inside(root, rel)])`; `exec:../x` solleva `PluginError` nel `discover` (errore raccolto); entry con modulo inesistente è raccolto, non propagato.

```python
# tests/backend/test_loader.py
from backend.bootstrap import make_loader
from backend.core.registry import Registry


def write(d, entry, kind="simulation"):
    d.mkdir(parents=True)
    (d / "manifest.toml").write_text(
        f'id="{d.name}"\nkind="{kind}"\nversion="0.1.0"\nentry="{entry}"\nlicense="Apache-2.0"\n'
    )


def test_exec_traversal_collected(tmp_path):
    write(tmp_path / "evil", "exec:../../bin/sh")
    errors = Registry().discover(tmp_path, make_loader())
    assert len(errors) == 1


def test_missing_module_collected(tmp_path):
    write(tmp_path / "ghost", "python:no.such.module:X")
    errors = Registry().discover(tmp_path, make_loader())
    assert len(errors) == 1


async def test_python_plugin_runs():
    from pathlib import Path

    r = Registry()
    errors = r.discover(Path("backend/plugins"), make_loader())
    assert [
        p.name for p, _ in errors
    ] == []  # fspl_c senza binario compilato va escluso dal test o compilato prima
    sim = r.create("simulation", "example-sim")
    assert (await sim.run({"x": 2.0}, timeout_s=1))["y"] == 4.0
```

- [ ] **Step 2:** FAIL. **Step 3:** implementa `make_loader` con `importlib.import_module` (il modulo `python:` è sotto `backend.plugins.*`; rifiuta moduli che non iniziano con `backend.plugins.`) e `example_sim.plugin.ExampleSim` (`y = x*x`). Il loader `exec:` restituisce `lambda m: ExecSimulation([str(resolve_inside(m.root, rel))], m.root)`; la risoluzione avviene al `load`, così il traversal fallisce in `discover`.
- [ ] **Step 4:** PASS. **Step 5: Commit** `feat: plugin loader with python and exec entries`.

---

### Task 6: Cache e resilienza upstream (Review Focus 4)

**Files:** Create `backend/adapters/cache_memory.py`, `backend/adapters/cache_valkey.py`; Test `tests/backend/adapters/test_cache.py`

**Interfaces — Produces:** `MemoryCache(clock=time.monotonic)` implementa `CachePort`; `cached_fetch(cache, key, ttl_s, fetch) -> bytes` che, se `fetch` fallisce e c'è un valore scaduto, lo restituisce (stale), altrimenti rilancia.

- [ ] **Step 1: Test**

```python
# tests/backend/adapters/test_cache.py
import pytest
from backend.adapters.cache_memory import MemoryCache, cached_fetch


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


async def test_ttl_and_stale():
    clock = Clock()
    c = MemoryCache(clock=clock)
    await c.set("k", b"v", ttl_s=10)
    assert await c.get("k") == b"v"
    clock.t = 11
    assert await c.get("k") is None
    assert await c.get("k", allow_stale=True) == b"v"


async def test_cached_fetch_serves_stale_when_upstream_down():
    clock = Clock()
    c = MemoryCache(clock=clock)

    async def ok():
        return b"fresh"

    async def down():
        raise ConnectionError("giù")

    assert await cached_fetch(c, "k", 10, ok) == b"fresh"
    clock.t = 99
    assert await cached_fetch(c, "k", 10, down) == b"fresh"


async def test_cached_fetch_raises_without_stale():
    async def down():
        raise ConnectionError("giù")

    with pytest.raises(ConnectionError):
        await cached_fetch(MemoryCache(), "x", 10, down)
```

- [ ] **Step 2:** FAIL. **Step 3:**

```python
# backend/adapters/cache_memory.py
# SPDX-License-Identifier: Apache-2.0
import time
from collections.abc import Awaitable, Callable


class MemoryCache:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._data: dict[str, tuple[bytes, float]] = {}

    async def get(self, key: str, *, allow_stale: bool = False) -> bytes | None:
        item = self._data.get(key)
        if item is None:
            return None
        value, expires = item
        return value if allow_stale or self._clock() < expires else None

    async def set(self, key: str, value: bytes, ttl_s: float) -> None:
        self._data[key] = (value, self._clock() + ttl_s)


async def cached_fetch(
    cache: "MemoryCache", key: str, ttl_s: float, fetch: Callable[[], Awaitable[bytes]]
) -> bytes:
    hit = await cache.get(key)
    if hit is not None:
        return hit
    try:
        value = await fetch()
    except Exception:
        stale = await cache.get(key, allow_stale=True)
        if stale is not None:
            return stale
        raise
    await cache.set(key, value, ttl_s)
    return value
```

`cache_valkey.py`: adapter opzionale con `redis.asyncio` (client compatibile con Valkey); import pigro, test marcato `@pytest.mark.skipif` se il server non risponde su `VALKEY_URL`. Il tipo di `cached_fetch` si generalizza a `CachePort` appena esiste un secondo adapter.
- [ ] **Step 4:** PASS. **Step 5: Commit** `feat(adapters): in-memory cache with stale-on-error`.

---

### Task 7: API, hardening HTTP, telemetria SSE (Review Focus 4, 5)

**Files:** Create `backend/api/{app.py,security.py,routes.py}`; completa `backend/bootstrap.py` (`app = create_app(...)`); Test `tests/backend/api/test_api.py`

**Interfaces — Consumes:** `Registry`, `ExecSimulation`. **Produces:** `create_app(registry, cache) -> FastAPI` con `GET /health`, `GET /api/plugins`, `POST /api/simulations/{id}/run` (body `{"inputs": {str: float}}`), `GET /api/telemetry/stream` (SSE).

- [ ] **Step 1: Test**

```python
# tests/backend/api/test_api.py
from fastapi.testclient import TestClient
from backend.bootstrap import build_app


def client():
    return TestClient(build_app())


def test_health_and_security_headers():
    r = client().get("/health")
    assert r.status_code == 200
    for h in ("content-security-policy", "x-content-type-options", "referrer-policy"):
        assert h in r.headers
    assert "set-cookie" not in r.headers


def test_run_example_sim():
    r = client().post("/api/simulations/example-sim/run", json={"inputs": {"x": 3.0}})
    assert r.json()["outputs"]["y"] == 9.0


def test_unknown_sim_is_404():
    assert client().post("/api/simulations/nope/run", json={"inputs": {}}).status_code == 404


def test_non_numeric_inputs_rejected_422():
    assert (
        client().post("/api/simulations/example-sim/run", json={"inputs": {"x": "a"}}).status_code
        == 422
    )


def test_timeout_maps_to_504(monkeypatch):
    from backend.core.errors import SimulationTimeout

    app = build_app()

    class Slow:
        async def run(self, inputs, *, timeout_s):
            raise SimulationTimeout("t")

    app.state.registry.create = lambda kind, id: Slow()
    assert TestClient(app).post("/api/simulations/x/run", json={"inputs": {}}).status_code == 504
```

- [ ] **Step 2:** FAIL. **Step 3:** implementa: middleware `security.py` che imposta `Content-Security-Policy: default-src 'self'`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `Strict-Transport-Security` (solo se `ENV=prod`); CORS con origini da `CORS_ORIGINS` (default vuoto); body `RunRequest(inputs: dict[str, float])` (Pydantic dà il 422); mappa `PluginNotFound→404`, `SimulationTimeout→504`, `InvalidOutput/PluginError→502`; `build_app()` in `bootstrap.py` istanzia `Registry`, chiama `discover(Path("backend/plugins"), make_loader())`, registra gli errori nel log e li espone in `/api/plugins` (campo `errors`).
- [ ] **Step 4:** PASS.
- [ ] **Step 5: Test SSE e rilascio sottoscrizione.** `TelemetryHub` (Observer) con `subscribe() -> asyncio.Queue` e `unsubscribe(q)`; endpoint SSE che si iscrive e si disiscrive in `finally`.

```python
# tests/backend/api/test_telemetry_hub.py
from backend.api.routes import TelemetryHub


async def test_unsubscribe_releases_queue():
    hub = TelemetryHub()
    q = hub.subscribe()
    assert hub.subscriber_count == 1
    hub.unsubscribe(q)
    assert hub.subscriber_count == 0


async def test_publish_reaches_subscribers():
    hub = TelemetryHub()
    q = hub.subscribe()
    hub.publish({"schema_version": "1.0.0", "power_w": 12.5})
    assert (await q.get())["power_w"] == 12.5
```

Implementa `TelemetryHub` (set di code limitate `maxsize=100`, `publish` scarta i campioni se una coda è piena per non bloccare). Endpoint SSE con `StreamingResponse` e `finally: hub.unsubscribe(q)`; un generatore di replay da file CSV alimenta l'hub (demo offline).
- [ ] **Step 6: Commit** `feat(api): REST, SSE telemetry, security headers`.

---

### Task 8: LLM e DataSource di esempio (Review Focus 4)

**Files:** Create `backend/plugins/example_llm/{manifest.toml,plugin.py}`, `backend/plugins/example_data/{manifest.toml,plugin.py}`; rotta `POST /api/chat` (SSE di token); rotta `GET /api/data/{id}`; Test `tests/backend/api/test_chat_data.py`

**Interfaces:** `EchoLLM.stream(messages)` (provider stub per test e demo offline); `FixtureData.fetch(query)` legge `fixtures/*.json`. Un provider reale (tier gratuito) è un plugin a parte: manifest con `terms_url`, chiave in `LLM_API_KEY` dall'ambiente, nessuna chiave nel client. Che provider usare e le sue condizioni attuali si **verificano** al momento di scriverlo; il piano non ne assume uno.

- [ ] **Step 1: Test** — chat con `EchoLLM` restituisce eventi SSE `data:`; `/api/data/example-data` con upstream che solleva `ConnectionError` e cache scaduta risponde 200 con dato stale e header `X-Cache: stale`; senza cache risponde 503 con JSON `{"detail": ...}`.
- [ ] **Step 2:** FAIL. **Step 3:** implementa usando `cached_fetch`; errori upstream mappati a 503. **Step 4:** PASS. **Step 5: Commit** `feat: LLM and data-source example plugins with stale fallback`.

---

### Task 9: Contratti e generazione tipi

**Files:** Create `contracts/telemetry.schema.json`, `contracts/gen.py`, `backend/contracts_models.py` (generato), `frontend/src/contracts/telemetry.ts` (generato); Test `tests/backend/test_contracts.py`

- [ ] **Step 1: Test**

```python
# tests/backend/test_contracts.py
import json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_schema_requires_version_and_utc():
    s = json.loads((ROOT / "contracts/telemetry.schema.json").read_text())
    assert "schema_version" in s["required"] and "t_utc" in s["required"]


def test_generated_files_are_in_sync():
    r = subprocess.run([sys.executable, "contracts/gen.py", "--check"], cwd=ROOT)
    assert r.returncode == 0
```

- [ ] **Step 2:** FAIL. **Step 3:** schema JSON con `schema_version` (pattern semver), `t_utc` (format `date-time`), `site_id`, `power_w`, `link_margin_db` opzionale; `gen.py` genera il modello Pydantic con `datamodel-codegen` e i tipi TS con `npx json-schema-to-typescript` (versione fissata in `frontend/package.json`); `--check` rigenera in temp e confronta, ritorna 1 se diverso. **Step 4:** PASS. **Step 5: Commit** `feat(contracts): single-source schema with generated types`.

---

### Task 10: Frontend — shell, router, a11y

**Files:** Create `frontend/{package.json,vite.config.ts,index.html,tsconfig.json}`, `frontend/src/{main.ts,App.svelte}`, `frontend/src/shell/{router.ts,a11y.ts}`, `frontend/src/pages/{home,404}/index.ts`; Test `frontend/src/shell/router.test.ts` (Vitest)

- [ ] **Step 1:** Verifica compatibilità prima di installare: `npm view vite engines` e `npm view @sveltejs/vite-plugin-svelte engines`. Node locale è 20.18.1: se la versione corrente di Vite richiede ≥20.19, fissa l'ultima major compatibile oppure aggiorna Node; registra la scelta in `docs/versions.md`. Poi `npm create vite@latest frontend -- --template svelte-ts` e `npm i -D vitest @testing-library/svelte jsdom`.
- [ ] **Step 2: Test del router (fallisce)**

```ts
// frontend/src/shell/router.test.ts
import { describe, it, expect } from 'vitest';
import { createRouter, type PageModule } from './router';

const page = (path: string): PageModule => ({ path, title: path, load: async () => ({ default: {} as never }) });

describe('router', () => {
  it('risolve un percorso registrato', () => {
    const r = createRouter([page('/'), page('/telemetry')]);
    expect(r.resolve('/telemetry')?.path).toBe('/telemetry');
  });
  it('usa la pagina 404 per percorsi sconosciuti', () => {
    const r = createRouter([page('/')], page('/404'));
    expect(r.resolve('/boh')?.path).toBe('/404');
  });
  it('normalizza slash finale e query', () => {
    const r = createRouter([page('/telemetry')]);
    expect(r.resolve('/telemetry/?x=1')?.path).toBe('/telemetry');
  });
});
```

- [ ] **Step 3:** Implementa `createRouter(pages, notFound?)` (mappa percorso→`PageModule`, `resolve(url)` normalizza) e l'auto-registrazione con `import.meta.glob('./pages/*/index.ts')`. `a11y.ts`: al cambio rotta aggiorna `document.title`, sposta il focus sull'`<h1>` della pagina e annuncia in una `aria-live="polite"`; link "Salta al contenuto"; rispetta `prefers-reduced-motion`.
- [ ] **Step 4:** `npx vitest run` → PASS; `npm run build`. **Step 5: Commit** `feat(frontend): shell, router, a11y primitives`.

---

### Task 11: Grafici 2D e ViewportPort 3D

**Files:** Create `frontend/src/charts/lineChart.ts`, `frontend/src/viewports/{port.ts,threeViewport.ts}`, `frontend/src/pages/{telemetry,viewer}/index.ts` (+ `.svelte`); Test `frontend/src/viewports/port.test.ts`

**Interfaces — Produces:** 

```ts
export interface ViewportPort {
  mount(el: HTMLElement): void;
  update(state: unknown): void;
  dispose(): void;
}
export type ViewportFactory = () => Promise<ViewportPort>;
```

- [ ] **Step 1: Test** — un `FakeViewport` che implementa la porta; la pagina lo carica via `ViewportFactory`; dopo `dispose()` non restano listener (contatore) e `update` dopo `dispose` non lancia.
- [ ] **Step 2–3:** implementa `threeViewport.ts` con `import()` dinamico di `three` dentro la factory (chunk separato), `ResizeObserver`, `dispose()` che rilascia geometrie/materiali/renderer e `cancelAnimationFrame`. `lineChart.ts` avvolge uPlot, accetta `Float64Array` (tempo) e serie. Ogni pagina espone anche una **tabella accessibile** equivalente (`<table>` con `<caption>`) e una descrizione testuale della scena 3D.
- [ ] **Step 4:** Aggiungi un controllo di budget: script `scripts/check-bundle.mjs` che fallisce se il chunk iniziale supera una soglia (da fissare dopo la prima build misurata e annotata in `docs/versions.md`). **Step 5: Commit** `feat(frontend): charts and lazy viewport port`.

---

### Task 12: Pagine chat/simulazioni, legali, consenso

**Files:** Create `frontend/src/pages/{chat,sims,legal}/…`, `frontend/src/shell/consent.ts`; Test `frontend/src/shell/consent.test.ts`

- [ ] **Step 1: Test** — `consent`: di default nessuna categoria non essenziale attiva; `grant('analytics')` salva nel `localStorage` con timestamp; `loadScript` per categoria non concessa **non** inietta lo script; `revoke` lo rimuove. Se `localStorage` lancia eccezione, si comporta come "nessun consenso".
- [ ] **Step 2–3:** implementa `consent.ts`; pagine `/privacy`, `/cookies` (template con elenco reale: per default "nessun cookie non essenziale"), `/licenses` (legge `/licenses.json` generato in CI), pagina chat con avviso "il testo viene inviato a un servizio esterno", pagina simulazioni (form generato dallo schema del manifest).
- [ ] **Step 4:** PASS. **Step 5: Commit** `feat(frontend): chat, sims, legal pages and consent module`.

---

### Task 13: Compliance, CI, Docker, documentazione

**Files:** Create `.github/workflows/ci.yml`, `Dockerfile`, `compose.yaml`, `.env.example`, `scripts/license_check.py`, `docs/{architecture.md,traceability.md}`; Test `tests/backend/test_license_check.py`

- [ ] **Step 1: Test** — `license_check.check(licenses: dict[str,str]) -> list[str]` restituisce le violazioni: `{"a": "MIT"}` → `[]`; `{"b": "GPL-3.0"}` e `{"c": "AGPL-3.0"}` → violazione; licenza sconosciuta → violazione "da rivedere".
- [ ] **Step 2–3:** implementa `license_check.py` con allowlist (MIT, BSD, Apache-2.0, ISC, MPL-2.0 come caso da rivedere esplicitamente) leggendo `pip-licenses --format=json` e `npx license-checker --json`. CI (`ci.yml`): job `backend` (ruff, mypy, lint-imports, pytest, `contracts/gen.py --check`, licenze, SBOM CycloneDX come artefatto), job `frontend` (svelte-check, vitest, build, budget bundle, a11y con axe via Playwright sulle pagine principali). `Dockerfile` multi-stage: build frontend → immagine Python che serve API e statici, utente non root. `compose.yaml` con servizio `app` e servizio `valkey` opzionale (profilo `cache`). Tracciabilità: tabella S1–S6/§5–§7 → file di test.
- [ ] **Step 4:** `make lint test` e `docker compose build` → OK. Esegui `docker compose up -d` e `curl -i localhost:8000/health` per verificare gli header. **Step 5: Commit** `chore: compliance gates, CI, Docker, docs`.

---

### Task 14: Verifica requisiti e rilascio su master

- [ ] **Step 1:** Esegui la checklist S1–S6 della spec; per ognuna annota il comando e l'esito in `docs/traceability.md` (S1: aggiungi un plugin fittizio senza toccare `core/`; S2: aggiungi `fspl-c` — già fatto; S3: `make dev` e `docker compose up`; S4: pagine presenti; S5: gate CI verdi; S6: sostituzione di un adapter con uno finto remoto in un test).
- [ ] **Step 2:** Revisione indipendente: agenti `architect-reviewer`, `accessibility-tester` e `security-auditor` sul diff; correggi i rilievi con test.
- [ ] **Step 3:** Merge del lavoro su `master` **dopo conferma dell'utente**; tag `v0.1.0`.

### Task 15: Branch `hackathon/nasa-lunar`

- [ ] **Step 1:** `git switch -c hackathon/nasa-lunar master`. Crea solo `backend/domain/` e plugin specifici; `docs/hackathon/nasa-lunar.md` con il contratto dati del dominio da scrivere nelle prime 2 ore (azimut/elevazione Sole e Terra, potenza, margine link) e il riparto compiti.
- [ ] **Step 2:** Plugin iniziali, ciascuno TDD con propri test e `terms_url` verificato: effemeridi/orizzonte (libreria da scegliere e licenza da verificare al momento), link budget (riusa `fspl-c` più guadagni e margini dichiarati), bilancio energetico, mission-hours, confronto siti.
- [ ] **Step 3:** Regola di flusso: modifiche generiche solo su `master`, poi `git merge master` nel branch; un test in CI verifica che `git diff master -- backend/core` sia vuoto.
- [ ] **Step 4: Commit** `feat(nasa-lunar): domain skeleton`. I dettagli dei dataset ufficiali (dopo il 28 ottobre) si aggiungono qui.

---

## Self-Review (eseguita)

- **Copertura spec:** §3 (T2–T5), §4 (T9), §5 (T10–T12), §6 (T13), §7 (T6–T8, T12–T13), §8 (T14–T15), §9 (CI T13, tracciabilità T14), §10 (T14). Nessun requisito scoperto.
- **Segnaposto:** i Task 5, 7, 8, 11, 12 descrivono la struttura e i test da scrivere ma non riportano tutto il codice; l'esecutore li espande seguendo i test indicati. Le soglie (budget bundle) e le versioni sono volutamente da misurare, non inventate.
- **Coerenza tipi:** `Simulation.run(inputs, *, timeout_s)`, `CachePort.get(key, *, allow_stale)`, `Registry.discover(dir, loader)`, `Manifest.root` coerenti tra i task.
- **Review Focus:** ogni voce ha un test nel task indicato.

---

### Task 16: Embedded/firmware in simulazione e sensor fusion (spec §12; dopo il Task 9)

**Agenti:** `embedded-critical-agents:firmware-hardware-engineer` (HAL, L0, QEMU), `embedded-critical-agents:control-systems-gnc-engineer` (filtri, validazione formule), `voltagent-lang:python-pro` (adapter), `voltagent-qa-sec:test-automator` (test).

- [ ] **Step 1: Porte e contratti.** Test per `FirmwareSim` e `Estimator` come Protocol; schema `state_estimate` (con unità nei nomi e `schema_version`); manifest accetta `kind = "firmware"` e `"estimator"` (test su `load_manifest`).
- [ ] **Step 2: HAL host (L0).** `contracts/hal/hal.h` (`hal_servo_write_deg`, `hal_adc_read`, `hal_uart_write`, `hal_millis`) e `hal_host.c`; esempio `plugins/servo_ctrl_c` con controllore proporzionale compilato su host; test che verifica la convergenza dell'angolo al setpoint tramite `ExecSimulation` e che le uscite non sono mai non finite.
- [ ] **Step 3: Estimatore.** Plugin `estimator_imu` che avvolge `imufusion` (`pip install imufusion`, verifica licenza e versione installata); test con dati sintetici a rotazione nota, errore di assetto sotto soglia dichiarata nel test.
- [ ] **Step 4: Verifica L2.** Spike di sola lettura: consultare `esp-toolchain-docs/qemu/README.md`, registrare in `docs/versions.md` chip supportati, comando di avvio e licenza. Implementare l'adapter QEMU solo se un esempio ESP32 gira davvero in locale; altrimenti annotare "non supportato" e restare su L0/L1.
- [ ] **Step 5: L1 opzionale.** Worker frontend con `avr8js` (MIT) dietro `ViewportPort`-like `FirmwarePort`, caricato in modo pigro; test con sketch che accende un pin.
- [ ] **Step 6: Commit** `feat: firmware simulation levels and sensor fusion plugins`.

---

### Task 17: ML/RL/DL e data science (spec §13; dopo il Task 7 e il Task 16)

**Agenti:** `voltagent-data-ai:ml-engineer` (pipeline e Trainer), `voltagent-data-ai:reinforcement-learning-engineer` (Environment e agente), `voltagent-data-ai:mlops-engineer` (ModelRegistry, versionamento, promozione), `voltagent-data-ai:data-scientist` (valutazione e baseline), `voltagent-lang:python-pro`; revisione con `voltagent-qa-sec:architect-reviewer`.

- [ ] **Step 1: Porte e isolamento.** Test per `Predictor`, `Trainer`, `Environment`, `ModelRegistry` come Protocol; manifest accetta `kind = "model" | "trainer" | "environment"`; `.importlinter` vieta a `backend.core` di importare `torch`, `sklearn`, `gymnasium`, `stable_baselines3`, `pandas`; test che l'app parte e i test passano **senza** extra ML installati.
- [ ] **Step 2: ModelRegistry su file system.** Salva modello + `model_card.json` (versione, seed, hash dataset, versioni librerie, metriche, soglia); test su salvataggio/caricamento, rollback alla versione precedente, rifiuto di una promozione se la metrica non supera la soglia o manca l'approvazione.
- [ ] **Step 3: Esempio data science.** Plugin `predictor_baseline` con scikit-learn su dati sintetici della telemetria: baseline + modello, valutazione su test set fisso, test che il modello promosso batte il baseline oltre la soglia dichiarata e che una regressione viene bloccata.
- [ ] **Step 4: Job di addestramento.** `TrainerRunner` che esegue il trainer in un subprocess con timeout, limite di memoria, annullamento e stato (`queued/running/done/failed/cancelled`); endpoint `POST /api/train`, `GET /api/jobs/{id}`; test con un trainer finto che non termina (viene ucciso) e con output non finito (rifiutato).
- [ ] **Step 5: Ambiente RL.** `SimulationEnv` che avvolge una `Simulation` (es. `servo_ctrl_c` del Task 16) in interfaccia Gymnasium; test sul contratto `reset/step`, determinismo con seed e limiti su azioni e osservazioni; esempio con Stable-Baselines3 solo come extra `.[rl]`, test saltato se non installato.
- [ ] **Step 6: Deep learning opzionale.** Esempio PyTorch minimo (extra `.[dl]`) con export ONNX e inferenza via ONNX Runtime; test saltato se gli extra mancano; verifica che l'output ONNX coincida con quello PyTorch entro tolleranza dichiarata.
- [ ] **Step 7: Pagina frontend** "Modelli ed esperimenti" (elenco, metriche, stato job, promozione con conferma, alternativa tabellare ai grafici).
- [ ] **Step 8: Compliance.** `pip-licenses` sugli extra ML, SBOM, aggiornamento di `docs/versions.md`; ogni dataset usato dichiara licenza e origine.
- [ ] **Step 9: Commit** `feat: ML/RL/DL plugin kinds, model registry and training jobs`.

---

### Task 18: Data engineering e pipeline di ingestione (spec §14; dopo il Task 9)

**Agenti:** `voltagent-data-ai:data-engineer` (pipeline), `voltagent-data-ai:database-optimizer` (partizionamento e query), `voltagent-lang:python-pro`, `voltagent-qa-sec:test-automator`, `voltagent-infra:sre-engineer` (metriche, allarmi), revisione con `voltagent-qa-sec:architect-reviewer`.

- [ ] **Step 1: Porte e isolamento.** Test per `IngestSource`, `Queue`, `Processor`, `Store`, `QueryEngine`, `Scheduler` come Protocol; `core/` non importa `pyarrow`, `duckdb`, `polars`, `pandas`, `astropy` (import-linter); l'app parte senza gli extra `.[data]`.
- [ ] **Step 2: Coda.** `MemoryQueue` con limite e `DurableQueue` su SQLite; test: ack/nack, redelivery dopo crash simulato (at-least-once), dead-letter dopo N tentativi, backpressure con politica configurabile (blocca o scarta con contatore), nessuna perdita con produttori concorrenti.
- [ ] **Step 3: Processor idempotente.** Validazione contro lo schema di `contracts/`, normalizzazione unità, chiave di deduplicazione; test: stesso record due volte → un solo record in `clean`; record invalido → dead-letter con motivo; valori NaN/inf scartati; tempi fuori ordine gestiti per partizione.
- [ ] **Step 4: Store a livelli.** Scrittura `raw/clean/curated` in Parquet partizionato per sorgente e data, scritture atomiche (file temporaneo + rename), compattazione dei file piccoli, retention configurabile; test: lettura dopo scrittura, nessun file parziale visibile dopo un crash, lineage curated → raw.
- [ ] **Step 5: Query.** `QueryEngine` SQL su Parquet con parametri legati (nessuna concatenazione di stringhe, test di injection) e limite di righe; endpoint `GET /api/data/query` per interrogazioni predefinite, non SQL libero dal client.
- [ ] **Step 6: Sorgenti e parser.** `IngestSource` per API HTTP (rispetta cache, limiti di richiesta, `terms_url`), per file/CSV e per replay; parser plugin per pacchetti binari a campi fissi con test su pacchetti troncati, lunghezze errate e valori limite.
- [ ] **Step 7: Scheduler e qualità.** Job periodici di ingestione/compattazione/retention con timeout e non sovrapposizione; controlli di qualità per livello con metriche; test che una sorgente silenziosa oltre soglia genera lo stato `stale`.
- [ ] **Step 8: Metriche e pagina.** `/api/pipeline/metrics` (JSON, opzionale testo Prometheus), pagina frontend "Pipeline dati" con alternative tabellari.
- [ ] **Step 9: Benchmark.** Script riproducibile che misura record/s e latenza su questa macchina con dati sintetici; i risultati e le soglie scelte vanno in `docs/versions.md`, non assunti a priori.
- [ ] **Step 10: Compliance e commit.** `pip-licenses` sugli extra `.[data]`, SBOM aggiornato; commit `feat: data ingestion pipeline with layered storage`.

---

### Task 19: Reti TCP/UDP e protocolli spaziali (spec §15; dopo i Task 7 e 18)

**Agenti:** `embedded-critical-agents:network-protocols-engineer` (transport, framer, codec; usa la skill `network-protocols-reference`), `voltagent-core-dev:websocket-engineer` (gateway verso il frontend), `embedded-critical-agents:embedded-security-engineer` (threat model e fuzzing), `embedded-critical-agents:verification-test-engineer` (fuzzing e test dinamici), skill `ground-systems` e `satellite-comms` per i vincoli CCSDS e di collegamento; revisione con `voltagent-qa-sec:security-auditor`.

- [ ] **Step 1: Porte e isolamento.** Test per `Transport`, `Framer`, `ProtocolCodec`, `Channel` come Protocol; `core/` non importa `socket`/`asyncio` per la rete (import-linter); loopback in memoria per testare tutto senza rete.
- [ ] **Step 2: Transport TCP/UDP.** Server e client asincroni con limiti (connessioni, dimensione messaggio, timeout di inattività, velocità), bind di default `127.0.0.1`; test su loopback reale: connessione, disconnessione brusca, client lento, messaggio sopra il limite (chiusura pulita), flood oltre il limite di velocità, multicast con gruppo e interfaccia espliciti.
- [ ] **Step 3: Framer.** Prefisso di lunghezza, SLIP/KISS e lunghezza da intestazione; test: frammentazione arbitraria dei byte (un byte alla volta), più messaggi in un solo segmento, lunghezza dichiarata enorme (rifiutata senza allocare), flusso troncato.
- [ ] **Step 4: Space Packet (CCSDS).** Codec per intestazione primaria (versione, tipo, flag di intestazione secondaria, APID, flag di sequenza, conteggio sequenza, lunghezza dati) con encode/decode e validazione; test su vettori costruiti a mano dall'esperto (campi ai limiti: APID massimo, lunghezza 0 e massima, conteggio che si riavvolge) e proprietà `decode(encode(x)) == x`; la specifica esatta dei campi si legge dal Libro Blu e si cita nel file di test, non si ricorda a memoria.
- [ ] **Step 5: CSP e AX.25/KISS.** Codec minimali con CRC verificato, scarto dei frame con CRC errato e contatore; test su frame corrotti bit per bit e su sequenze KISS con escape non valide.
- [ ] **Step 6: Canale simulato.** `Channel` con ritardo, jitter, perdita, errori sui bit, banda e finestre di contatto, con generatore casuale a seme fisso; test deterministici: perdita al 100%, ritardo costante misurato, errore sui bit che fa fallire il CRC, nessuna consegna fuori finestra di contatto.
- [ ] **Step 7: Integrazione.** I record decodificati passano da `Processor` e `Queue` del Task 18 e arrivano a `/api/telemetry/stream`; test end-to-end: sorgente UDP simulata → canale con perdite → codec → pipeline → SSE, con conteggi coerenti (ricevuti + persi = inviati).
- [ ] **Step 8: Fuzzing e threat model.** Documento STRIDE breve per i listener; fuzz dei codec (Hypothesis o libFuzzer/AFL++ se installati, altrimenti Hypothesis) con invarianti: nessuna eccezione non gestita, nessuna allocazione illimitata, tempo di elaborazione limitato; i casi che hanno trovato un bug diventano test di regressione.
- [ ] **Step 9: Pagina e metriche.** Metriche di rete nella pagina "Pipeline dati" (pacchetti, errori CRC, perdite, ritardo, ultimo contatto) con alternative tabellari.
- [ ] **Step 10: Commit** `feat: network transports and space protocol codecs with simulated channel`.
