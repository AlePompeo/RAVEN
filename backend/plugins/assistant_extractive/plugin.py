# SPDX-License-Identifier: Apache-2.0
from collections.abc import AsyncIterator

from backend.assistant.extractive import compose, stream_text
from backend.core.manifest import Manifest


class ExtractiveProvider:
    """LLMProvider senza modello: risposta estrattiva e citata, zero rete, zero chiavi."""

    def __init__(self, manifest: Manifest) -> None:
        self.manifest = manifest

    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[str]:
        async for piece in stream_text(compose(messages)):
            yield piece
