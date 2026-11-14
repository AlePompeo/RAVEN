# SPDX-License-Identifier: Apache-2.0
import json
from collections.abc import Mapping
from typing import Any

from backend.core.manifest import Manifest


class FixtureData:
    """DataSource offline: unisce i file `fixtures/*.json` del plugin, chiave = nome file."""

    def __init__(self, manifest: Manifest) -> None:
        self.manifest = manifest

    async def fetch(self, query: Mapping[str, Any]) -> Mapping[str, Any]:
        out: dict[str, Any] = {}
        for f in sorted((self.manifest.root / "fixtures").glob("*.json")):
            out[f.stem] = json.loads(f.read_text(encoding="utf-8"))
        return out
