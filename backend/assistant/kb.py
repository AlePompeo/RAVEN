# SPDX-License-Identifier: Apache-2.0
"""Base di conoscenza viva: caricamento, indice, ricostruzione su modifica dei file (solo dev)."""

import threading
import time
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from backend.assistant.index import Index
from backend.assistant.loader import knowledge_files, load_all
from backend.assistant.model import KnowledgeDoc

RELOAD_CHECK_S = 1.0


class KnowledgeBase:
    def __init__(
        self, repo_root: Path, extra_roots: Iterable[Path] = (), *, reload: bool = False
    ) -> None:
        self.repo_root = repo_root
        self.extra_roots = tuple(extra_roots)
        self.reload = reload
        self._lock = threading.Lock()
        self._checked = 0.0
        self.docs: list[KnowledgeDoc] = []
        self.errors: list[str] = []
        self.index = Index([])
        self.last_build = ""
        self.build()

    def _signature(self) -> tuple[tuple[str, int, int], ...]:
        paths = list(knowledge_files(self.repo_root, self.extra_roots))
        paths += sorted((self.repo_root / "backend/plugins").glob("*/manifest.toml"))
        paths += sorted((self.repo_root / "contracts").glob("*.schema.json"))
        sig = []
        for p in paths:
            try:
                st = p.stat()
            except OSError:
                continue
            sig.append((str(p), st.st_mtime_ns, st.st_size))
        return tuple(sig)

    def build(self) -> None:
        docs, errors = load_all(self.repo_root, self.extra_roots)
        # un id duplicato non entra due volte nell'indice: vince il primo
        unique = list({d.id: d for d in reversed(docs)}.values())[::-1]
        self.docs, self.errors = unique, errors
        self.index = Index(unique)
        self._sig = self._signature()
        self.last_build = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    def refresh_if_changed(self) -> bool:
        if not self.reload:
            return False
        now = time.monotonic()
        with self._lock:
            if now - self._checked < RELOAD_CHECK_S:
                return False
            self._checked = now
            if self._signature() == self._sig:
                return False
            self.build()
            return True

    def get(self, doc_id: str) -> KnowledgeDoc | None:
        return self.index.docs.get(doc_id)
