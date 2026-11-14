# SPDX-License-Identifier: Apache-2.0
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.types import Scope

_NO_FALLBACK_PREFIXES = ("api", "health", "assets")
_IMMUTABLE = "public, max-age=31536000, immutable"


class SPAStaticFiles(StaticFiles):
    """StaticFiles con fallback a index.html per le rotte lato client (pushState).

    Il fallback vale solo per GET/HEAD, fuori da /api, /health, /assets e per percorsi
    senza estensione; non serve mai nulla fuori dalla cartella (lo garantisce StaticFiles,
    il fallback legge solo `index.html` nella cartella stessa).
    """

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404 or not self._is_spa_route(path, scope):
                raise
            response = await super().get_response("index.html", scope)
        self._set_cache_headers(path, response)
        return response

    @staticmethod
    def _is_spa_route(path: str, scope: Scope) -> bool:
        if scope["method"] not in ("GET", "HEAD"):
            return False
        parts = [p for p in path.split("/") if p]
        if parts and parts[0] in _NO_FALLBACK_PREFIXES:
            return False
        return not (parts and "." in parts[-1])

    @staticmethod
    def _set_cache_headers(path: str, response: Response) -> None:
        if response.status_code >= 400:
            return
        first = path.lstrip("/").split("/", 1)[0]
        if first == "assets":
            response.headers["Cache-Control"] = _IMMUTABLE
        else:
            response.headers["Cache-Control"] = "no-cache"


def mount_static(app: FastAPI, directory: str | os.PathLike[str] | None = None) -> bool:
    """Serve il frontend compilato su `/` (da montare DOPO le rotte API).

    `directory` default: variabile STATIC_DIR. Senza cartella valida non fa nulla.
    """
    path = directory if directory is not None else os.environ.get("STATIC_DIR")
    if not path or not Path(path).is_dir():
        return False
    kwargs: dict[str, Any] = {"directory": str(path), "html": True}
    app.mount("/", SPAStaticFiles(**kwargs), name="static")
    return True
