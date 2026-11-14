# SPDX-License-Identifier: Apache-2.0
from collections.abc import AsyncIterator

from backend.core.manifest import Manifest


class EchoLLM:
    """Provider stub (test e demo offline): ripete l'ultimo messaggio utente, parola per parola."""

    def __init__(self, manifest: Manifest) -> None:
        self.manifest = manifest

    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        last = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        for word in last.split():
            yield word + " "
