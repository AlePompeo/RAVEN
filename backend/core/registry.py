# SPDX-License-Identifier: Apache-2.0
from collections.abc import Callable
from pathlib import Path
from typing import Any

from backend.core.errors import PluginError, PluginNotFound
from backend.core.manifest import Manifest, load_manifest

Factory = Callable[[Manifest], Any]


class Registry:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], tuple[Manifest, Factory]] = {}

    def register(self, manifest: Manifest, factory: Factory) -> None:
        key = (manifest.kind, manifest.id)
        if key in self._items:
            raise PluginError(f"plugin duplicato: {manifest.kind}/{manifest.id}")
        self._items[key] = (manifest, factory)

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
            except Exception as e:  # noqa: BLE001  un plugin rotto non ferma gli altri
                errors.append((mf.parent, e))
        return errors
