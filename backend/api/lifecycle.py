# SPDX-License-Identifier: Apache-2.0
"""Ciclo di vita esplicito dell'app: i moduli di rotte registrano hook, app.py li ordina."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import FastAPI

Hook = Callable[[FastAPI], Awaitable[None]]


@dataclass
class _Entry:
    start: Hook | None
    stop: Hook | None


class Lifecycle:
    def __init__(self) -> None:
        self._entries: dict[str, _Entry] = {}

    def register(self, name: str, *, start: Hook | None = None, stop: Hook | None = None) -> None:
        if name in self._entries:
            raise ValueError(f"hook gia' registrato: {name}")
        self._entries[name] = _Entry(start, stop)

    def get(self, name: str) -> _Entry | None:
        return self._entries.get(name)
