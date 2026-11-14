# SPDX-License-Identifier: Apache-2.0
import importlib
import logging
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI

from backend.adapters.cache_memory import MemoryCache
from backend.adapters.subprocess_sim import ExecSimulation, resolve_inside
from backend.api.app import ConfigError, create_app
from backend.core.errors import PluginError
from backend.core.manifest import Manifest
from backend.core.registry import Factory, Registry

PLUGIN_PACKAGE = "backend.plugins."
PLUGINS_DIR = Path(__file__).parent / "plugins"
log = logging.getLogger(__name__)


def make_loader() -> Callable[[Manifest], Factory]:
    """Interpreta `python:modulo:Classe` ed `exec:percorso` (relativo alla cartella del plugin)."""

    def loader(manifest: Manifest) -> Factory:
        scheme, _, rest = manifest.entry.partition(":")
        if scheme == "python":
            module_name, sep, cls_name = rest.partition(":")
            if not sep or not module_name or not cls_name:
                raise PluginError(f"entry python non valido: {manifest.entry!r}")
            if not module_name.startswith(PLUGIN_PACKAGE):
                raise PluginError(f"modulo fuori da {PLUGIN_PACKAGE}*: {module_name}")
            try:
                cls = getattr(importlib.import_module(module_name), cls_name)
            except (ImportError, AttributeError) as e:
                raise PluginError(f"{manifest.entry}: {e}") from e
            return lambda m: cls(m)
        if scheme == "exec":
            if manifest.kind != "simulation":
                raise PluginError(f"entry exec non supportato per kind {manifest.kind!r}")
            if not rest:
                raise PluginError(f"entry exec vuoto: {manifest.entry!r}")
            path = resolve_inside(manifest.root, rest)
            if not path.is_file():
                raise PluginError(f"eseguibile mancante: {rest} (compilare con make build-c?)")
            return lambda m: ExecSimulation([str(path)], m.root)
        raise PluginError(f"schema entry sconosciuto: {manifest.entry!r}")

    return loader


def build_app() -> FastAPI:
    registry = Registry()
    errors = registry.discover(PLUGINS_DIR, make_loader())
    for path, err in errors:
        log.error("plugin %s non caricato: %s: %s", path.name, type(err).__name__, err)
    try:
        return create_app(registry, MemoryCache(), errors)
    except ConfigError as e:
        raise SystemExit(f"configurazione non valida: {e}") from None
