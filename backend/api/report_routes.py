# SPDX-License-Identifier: Apache-2.0
"""POST /api/raven/report/pdf: the printable report rendered to PDF by the server.

Same bytes everywhere (the browser's print engine is not involved). Safeguards, all generic and
without echoing the input: body cap of 6 MB for this route only (the global cap stays 64 KB),
per-client rate limit, at most PDF_MAX_CONCURRENT renders at once, a time limit, an allow-list HTML
sanitiser and a renderer that fetches nothing. 503 when the optional engine (extra `pdf`) or its
Pango libraries are missing: the page then falls back to the browser's print dialog.
"""

import asyncio
import logging
import os
import re
import time
from collections import OrderedDict
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from backend.adapters.report_weasyprint import WeasyPrintRenderer
from backend.api.security import client_key
from backend.core.ports import RendererUnavailable, ReportRenderer, ReportRenderRequest
from backend.domain.raven.report_html import UnsafeHtml, sanitize_report_html
from backend.envconf import env_positive_int

log = logging.getLogger(__name__)
PDF_PATH = "/api/raven/report/pdf"
MAX_PDF_BODY_BYTES = (
    6 * 1024 * 1024
)  # route-specific cap (documented in docs/knowledge/report-pdf.md)
DEFAULT_MAX_CONCURRENT = 2
DEFAULT_RATE_PER_MIN = 10
DEFAULT_TIMEOUT_S = 60
_NAME = re.compile(r"[^A-Za-z0-9._-]+")


class PdfRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    html: str = Field(min_length=1, max_length=MAX_PDF_BODY_BYTES)
    title: str = Field(min_length=1, max_length=200)
    subtitle: str = Field(default="", max_length=200)  # scenario shown in the running header
    lang: Literal["it", "en"]
    filename: str | None = Field(default=None, max_length=120)
    created: datetime | None = None  # report timestamp: same input -> same bytes


def _error(status: int, detail: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"detail": detail}, status_code=status, headers=headers)


class _ReportPdfService:
    def __init__(self, renderer: ReportRenderer, *, max_concurrent: int, rate: int, timeout_s: int):
        self.renderer = renderer
        self.sem = asyncio.Semaphore(max_concurrent)
        self.rate = rate
        self.timeout_s = timeout_s
        self._hits: OrderedDict[str, list[float]] = OrderedDict()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        hits = [t for t in self._hits.get(key, []) if now - t < 60.0]
        if len(hits) >= self.rate:
            self._hits[key] = hits
            return False
        hits.append(now)
        self._hits[key] = hits
        self._hits.move_to_end(key)
        while len(self._hits) > 1024:
            self._hits.popitem(last=False)
        return True


def _file_name(raw: str | None, lang: str) -> str:
    base = _NAME.sub("-", (raw or "").removesuffix(".pdf")).strip("-.")[:80]
    return (base or ("raven-report-" + lang)) + ".pdf"


def build_report_router() -> APIRouter:
    router = APIRouter()

    @router.post(PDF_PATH)
    async def report_pdf(body: PdfRequest, request: Request) -> Response:
        svc: _ReportPdfService = request.app.state.report_pdf
        if not svc.allow(client_key(request.scope, trusted_proxy=request.app.state.trusted_proxy)):
            return _error(429, "troppe richieste", {"Retry-After": "30"})
        try:
            body_html, css = sanitize_report_html(body.html)
        except UnsafeHtml:
            return _error(422, "documento non valido")
        created = (body.created or datetime.fromtimestamp(_epoch(), UTC)).astimezone(UTC)
        job = ReportRenderRequest(
            body_html=body_html,
            css=css,
            title=body.title,
            subtitle=body.subtitle,
            lang=body.lang,
            created=created.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        if svc.sem.locked():
            return _error(503, "generatore PDF occupato", {"Retry-After": "5"})
        await svc.sem.acquire()
        task = asyncio.create_task(asyncio.to_thread(svc.renderer.render, job))
        task.add_done_callback(
            lambda _t: svc.sem.release()
        )  # il thread non si interrompe: il posto
        try:  # resta occupato finche' non termina davvero
            pdf = await asyncio.wait_for(asyncio.shield(task), svc.timeout_s)
        except RendererUnavailable:
            return _error(503, "generatore PDF non disponibile")
        except TimeoutError:
            return _error(504, "generazione PDF troppo lenta")
        except Exception:
            log.exception("PDF del report non generato")
            return _error(500, "generazione PDF non riuscita")
        name = _file_name(body.filename, body.lang)
        return Response(
            pdf,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{name}"',
                "Cache-Control": "no-store",
            },
        )

    return router


def _epoch() -> float:
    """SOURCE_DATE_EPOCH when set (reproducible builds), otherwise the current time."""
    raw = os.environ.get("SOURCE_DATE_EPOCH", "")
    return float(raw) if raw.isdigit() else time.time()


def include_report_routes(app: FastAPI, renderer: ReportRenderer | None = None) -> None:
    """The WeasyPrint import is lazy (inside the adapter): the app starts without the extra."""
    app.state.report_pdf = _ReportPdfService(
        renderer or WeasyPrintRenderer(),
        max_concurrent=env_positive_int("PDF_MAX_CONCURRENT", DEFAULT_MAX_CONCURRENT),
        rate=env_positive_int("PDF_RATE_PER_MIN", DEFAULT_RATE_PER_MIN),
        timeout_s=env_positive_int("PDF_TIMEOUT_S", DEFAULT_TIMEOUT_S),
    )
    app.include_router(build_report_router())
