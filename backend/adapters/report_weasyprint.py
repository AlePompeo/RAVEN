# SPDX-License-Identifier: Apache-2.0
"""WeasyPrint adapter of the ReportRenderer port (optional extra `pdf`; needs Pango on the system).

Nothing is fetched from the network or the disk: the URL fetcher refuses everything but data: URIs
and the only font (HB Sans, SIL OFL 1.1) is embedded in the stylesheet as a data: URI. The output is
deterministic: creation date and file identifier derive from the request, never from the clock.
"""

import base64
import hashlib
import logging
import os
import re
import threading
from datetime import UTC, datetime
from functools import lru_cache
from html import escape
from pathlib import Path
from typing import Any

from backend.core.ports import RendererUnavailable, ReportRenderRequest

log = logging.getLogger(__name__)
FONT_PATH = Path(__file__).resolve().parent.parent / "assets" / "fonts" / "hb-sans-latin.woff2"
AUTHOR = "RAVEN"
_FOOTER = {"it": ("Pagina ", " di "), "en": ("Page ", " of ")}
_TOC_NOTE = {"it": "Pagina", "en": "Page"}

# Server stylesheet (page boxes, running header, bookmarks, contents leaders, chart layout): a file of its
# own so that it can be read, linted and contrast-checked as CSS. It is appended AFTER the client's print
# CSS so that @page and the page-number rules win. Palette and component styles travel with the markup.
STYLE_PATH = Path(__file__).resolve().parent.parent / "assets" / "report-print.css"


@lru_cache(maxsize=1)
def server_css() -> str:
    return STYLE_PATH.read_text(encoding="utf-8")


class _DataOnlyFetcherFactory:
    """Builds a WeasyPrint URL fetcher that refuses everything but data: URIs."""

    @staticmethod
    def make() -> Any:
        from weasyprint import URLFetcher  # lazy: the extra may be absent

        class DataOnlyFetcher(URLFetcher):  # type: ignore[misc]
            def __init__(self) -> None:
                super().__init__(allowed_protocols=["data"], fail_on_errors=False)
                self.refused: list[str] = []

            def fetch(self, url: str, headers: Any = None) -> Any:
                if url[:5].lower() != "data:":
                    self.refused.append(url.split(":", 1)[0].lower() if ":" in url else "relative")
                    raise ValueError("resource refused: only data: URIs are allowed")
                return super().fetch(url, headers)

        return DataOnlyFetcher()


@lru_cache(maxsize=1)
def _font_css() -> str:
    data = base64.b64encode(FONT_PATH.read_bytes()).decode("ascii")
    src = f"src: url('data:font/woff2;base64,{data}') format('woff2');"
    # WeasyPrint does not accept a weight range in @font-face: one face per weight, both from the
    # same variable font (the wght axis is set per face).
    return "".join(
        f"@font-face {{ font-family: 'HB Sans'; font-weight: {w}; font-style: normal; {src} }}\n"
        for w in (400, 700)
    )


_GRID = re.compile(r"display\s*:\s*(?:inline-)?grid", re.IGNORECASE)


def _engine_compat(css: str) -> str:
    """WeasyPrint 70 cannot split CSS grids across pages: it asserts in page layout on a two-column
    chart grid and needs minutes for a grid wrapping the whole report. Grids become blocks (same
    reading order, single column); the page layout is the server stylesheet's job."""
    return _GRID.sub("display: block", css)


def _created(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return datetime.fromtimestamp(0, UTC)


class WeasyPrintRenderer:
    """ReportRenderer implemented with WeasyPrint. Thread-safe (renders are serialised)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()  # WeasyPrint's font cache is not documented as thread-safe
        self.last_refused: list[str] = []

    @staticmethod
    def available() -> bool:
        try:
            import weasyprint  # noqa: F401
        except Exception:  # noqa: BLE001  ImportError, or OSError when pango/gobject libraries are missing
            return False
        return True

    def render(self, request: ReportRenderRequest) -> bytes:
        try:
            from weasyprint import CSS, HTML
            from weasyprint.text.fonts import FontConfiguration
        except Exception as exc:  # ImportError / OSError (missing shared libraries)
            raise RendererUnavailable(type(exc).__name__) from exc
        created = _created(request.created)
        lang = request.lang if request.lang in _FOOTER else "en"
        page, of = _FOOTER[lang]
        header = escape(request.title) + (
            " &middot; " + escape(request.subtitle) if request.subtitle else ""
        )
        document = (
            f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8">'
            f"<title>{escape(request.title)}</title>"
            f'<meta name="author" content="{AUTHOR}">'
            f'<meta name="dcterms.created" content="{created.strftime("%Y-%m-%dT%H:%M:%SZ")}">'
            f'<meta name="dcterms.modified" content="{created.strftime("%Y-%m-%dT%H:%M:%SZ")}">'
            f'</head><body><div class="rv-running-header">{header}</div>{request.body_html}'
            "</body></html>"
        )
        ident = hashlib.sha256(document.encode() + request.css.encode()).digest()[:16]
        fetcher = _DataOnlyFetcherFactory.make()
        with self._lock:
            # fontTools stamps the subsetted font with the current time unless SOURCE_DATE_EPOCH is
            # set: pin it to the report date for the duration of the (serialised) render.
            previous = os.environ.get("SOURCE_DATE_EPOCH")
            os.environ["SOURCE_DATE_EPOCH"] = str(max(0, int(created.timestamp())))
            try:
                fonts = FontConfiguration()
                sheets = [
                    CSS(string=_font_css(), url_fetcher=fetcher, font_config=fonts),
                    CSS(string=_engine_compat(request.css), url_fetcher=fetcher, font_config=fonts),
                    CSS(
                        string=server_css().replace("@PAGE@", page).replace("@OF@", of),
                        url_fetcher=fetcher,
                        font_config=fonts,
                    ),
                ]
                pdf = HTML(string=document, url_fetcher=fetcher).write_pdf(
                    stylesheets=sheets,
                    font_config=fonts,
                    pdf_variant="pdf/ua-1",
                    pdf_tags=True,
                    identifier=ident,
                    pdf_version="1.7",
                )
            finally:
                if previous is None:
                    os.environ.pop("SOURCE_DATE_EPOCH", None)
                else:
                    os.environ["SOURCE_DATE_EPOCH"] = previous
                self.last_refused = list(getattr(fetcher, "refused", []))
        return bytes(pdf)
