# SPDX-License-Identifier: Apache-2.0
"""Server-side PDF of the report: sanitiser (always run) and rendering (needs the `pdf` extra)."""

import base64
import io
import re
import shutil
import subprocess
import threading
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.adapters.report_weasyprint import WeasyPrintRenderer
from backend.api.report_routes import MAX_PDF_BODY_BYTES, PDF_PATH, include_report_routes
from backend.api.security import BodySizeLimitMiddleware
from backend.core.ports import RendererUnavailable, ReportRenderRequest
from backend.domain.raven.report_html import UnsafeHtml, sanitize_css, sanitize_report_html

pdf_engine = pytest.mark.skipif(
    not WeasyPrintRenderer.available(), reason="extra `pdf` (weasyprint + Pango) not installed"
)
SVG = base64.b64encode(
    b'<svg xmlns="http://www.w3.org/2000/svg" width="80" height="30"><rect width="80" height="30"/></svg>'
).decode()
SECTIONS = ["Alpha mission", "Bravo energy", "Charlie reliability", "Delta legal", "Echo appendix"]


def sample_html(sections: list[str] = SECTIONS, filler: int = 60) -> str:
    toc = "".join(
        f'<li class="toc-level-1"><a href="#sec-{i}">{s}</a></li>' for i, s in enumerate(sections)
    )
    body = "".join(
        f'<section><h1 id="sec-{i}">{s}</h1><h2 id="sub-{i}">Details of {s}</h2>'
        f'<img alt="chart {i}" src="data:image/svg+xml;base64,{SVG}">'
        "<table><thead><tr><th>Item</th><th>Value</th></tr></thead>"
        f"<tbody><tr><td>x</td><td>{i}</td></tr></tbody></table>"
        + "".join(
            f"<p>Paragraph {j} about {s.lower()} with unremarkable text.</p>" for j in range(filler)
        )
        + "</section>"
        for i, s in enumerate(sections)
    )
    return f'<nav class="report-toc"><ol>{toc}</ol></nav>{body}'


class FakeRenderer:
    def __init__(self, delay: float = 0.0, error: Exception | None = None) -> None:
        self.delay = delay
        self.error = error
        self.seen: list[ReportRenderRequest] = []

    def render(self, request: ReportRenderRequest) -> bytes:
        self.seen.append(request)
        time.sleep(self.delay)
        if self.error:
            raise self.error
        return b"%PDF-fake"


def make_client(renderer: object | None = None, **env: str) -> TestClient:
    app = FastAPI()
    app.state.trusted_proxy = False
    app.add_middleware(
        BodySizeLimitMiddleware, max_bytes=64 * 1024, path_limits={PDF_PATH: MAX_PDF_BODY_BYTES}
    )
    include_report_routes(app, renderer)  # type: ignore[arg-type]
    return TestClient(app)


def payload(html: str, **extra: object) -> dict[str, object]:
    return {"html": html, "title": "RAVEN test report", "lang": "en", **extra}


# ---- sanitiser: no engine needed -------------------------------------------------------------


def test_sanitiser_drops_scripts_handlers_frames_and_external_references() -> None:
    dirty = (
        '<script>alert(1)</script><p onclick="x()">ok</p><iframe src="http://evil/"></iframe>'
        '<img src="http://evil/a.png" alt="e"><img src="file:///etc/passwd" alt="f">'
        f'<img src="data:image/svg+xml;base64,{SVG}" alt="good" onerror="x()">'
        '<a href="javascript:alert(1)">j</a><a href="https://evil/">h</a><a href="#sec">in</a>'
        '<object data="x"></object><embed src="x"><link rel="stylesheet" href="http://evil/c.css">'
        '<form action="http://evil"><input name="a"><button>b</button></form>'
        '<svg viewBox="0 0 1 1"><script>1</script><foreignObject><p>x</p></foreignObject>'
        '<use xlink:href="http://evil/x.svg#a"/><path d="M0 0" onload="x()"/></svg>'
    )
    html, _ = sanitize_report_html(dirty)
    low = html.lower()
    for bad in ("script", "onclick", "onerror", "onload", "iframe", "evil", "file:", "javascript", "object",
                "embed", "<link", "<form", "<input", "<button", "foreignobject"):  # fmt: skip
        assert bad not in low, bad
    assert "ok" in html and 'alt="good"' in html and 'href="#sec"' in html
    assert f"data:image/svg+xml;base64,{SVG}" in html and "<path" in html and "viewbox" in low


def test_sanitiser_css_removes_imports_and_non_data_urls() -> None:
    css = (
        "@import url(http://evil/x.css); @IMPORT 'y.css'; a{background:url(http://evil/a.png)}"
        " b{background:url('file:///etc/passwd')} c{background:u\\72l(//evil/z)}"
        f" d{{background:url(data:image/svg+xml;base64,{SVG})}} e{{width:expression(alert(1))}}"
        " f{background:image-set('//evil/a.png' 1x)}"
    )
    out = sanitize_css(css)
    assert "evil" not in out and "passwd" not in out and "@import" not in out.lower()
    assert "expression" not in out.lower() and "image-set" not in out.lower()
    assert f"data:image/svg+xml;base64,{SVG}" in out
    _, body_css = sanitize_report_html("<style>@import 'x.css'; p{color:red}</style><p>t</p>")
    assert "@import" not in body_css and "color:red" in body_css


def test_sanitiser_limits_nesting_depth() -> None:
    with pytest.raises(UnsafeHtml):
        sanitize_report_html("<div>" * 500)


def test_sanitiser_keeps_title_out_of_the_body() -> None:
    html, _ = sanitize_report_html(
        "<html><head><title>T</title></head><body><p>b</p></body></html>"
    )
    assert "T" not in re.sub(r"<[^>]+>", "", html).replace("b", "")


# ---- route behaviour with a fake renderer ---------------------------------------------------------


def test_route_sanitises_before_rendering_and_returns_pdf() -> None:
    fake = FakeRenderer()
    r = make_client(fake).post(
        PDF_PATH, json=payload("<script>x</script><p>hi</p>", filename="../a b?.pdf")
    )
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert 'filename="a-b.pdf"' in r.headers["content-disposition"]
    assert "script" not in fake.seen[0].body_html and fake.seen[0].lang == "en"


def test_route_validation_is_generic_and_does_not_echo() -> None:
    r = make_client(FakeRenderer()).post(
        PDF_PATH, json={"html": "SECRET-MARKER", "title": "t", "lang": "fr"}
    )
    assert r.status_code == 422 and "SECRET-MARKER" not in r.text


def test_route_body_cap_is_route_specific() -> None:
    client = make_client(FakeRenderer())
    big = payload("<p>" + "a" * (MAX_PDF_BODY_BYTES + 10) + "</p>")
    assert client.post(PDF_PATH, json=big).status_code == 413
    medium = payload("<p>" + "a" * (300 * 1024) + "</p>")  # above the global 64 KB cap, below 6 MB
    assert client.post(PDF_PATH, json=medium).status_code == 200
    assert client.post("/other", content=b"x" * (70 * 1024)).status_code in (404, 405, 413)


def test_route_503_when_engine_missing_and_generic_500_otherwise() -> None:
    r = make_client(FakeRenderer(error=RendererUnavailable("OSError"))).post(
        PDF_PATH, json=payload("<p>x</p>")
    )
    assert r.status_code == 503 and "OSError" not in r.text
    r = make_client(FakeRenderer(error=RuntimeError("boom secret"))).post(
        PDF_PATH, json=payload("<p>x</p>")
    )
    assert r.status_code == 500 and "secret" not in r.text


def test_route_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PDF_RATE_PER_MIN", "2")
    client = make_client(FakeRenderer())
    codes = [client.post(PDF_PATH, json=payload("<p>x</p>")).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_route_concurrency_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PDF_MAX_CONCURRENT", "1")
    client = make_client(FakeRenderer(delay=0.6))
    codes: list[int] = []

    def call() -> None:
        codes.append(client.post(PDF_PATH, json=payload("<p>x</p>")).status_code)

    threads = [threading.Thread(target=call) for _ in range(3)]
    for t in threads:
        t.start()
        time.sleep(0.1)
    for t in threads:
        t.join()
    assert sorted(codes) == [200, 503, 503]


# ---- real rendering (needs the extra `pdf`) -----------------------------------------------------------


def pages_text(pdf: bytes) -> list[str]:
    pypdf = pytest.importorskip("pypdf")
    return [p.extract_text() or "" for p in pypdf.PdfReader(io.BytesIO(pdf)).pages]


def render(html: str, **extra: object) -> bytes:
    r = make_client().post(
        PDF_PATH,
        json=payload(html, created="2026-11-09T10:00:00Z", subtitle="Site Shackleton", **extra),
    )
    assert r.status_code == 200, r.text
    return r.content


@pdf_engine
def test_pdf_metadata_pages_counters_and_bookmarks() -> None:
    pypdf = pytest.importorskip("pypdf")
    pdf = render(sample_html())
    assert pdf.startswith(b"%PDF")
    reader = pypdf.PdfReader(io.BytesIO(pdf))
    assert len(reader.pages) > 3
    assert reader.metadata.title == "RAVEN test report" and reader.metadata.author == "RAVEN"
    assert reader.trailer["/Root"]["/Lang"] == "en"
    assert reader.trailer["/Root"]["/MarkInfo"]["/Marked"]
    titles = [o.title for o in reader.outline if not isinstance(o, list)]
    assert titles[: len(SECTIONS)] == SECTIONS
    text = pages_text(pdf)
    assert f"Page 2 of {len(text)}" in text[1] and f"Page 1 of {len(text)}" in text[0]
    assert "test report" in text[0] and "Site Shackleton" in text[1]


@pdf_engine
def test_toc_page_numbers_match_the_pages_of_the_headings() -> None:
    text = pages_text(render(sample_html()))
    toc = text[0]  # the short table of contents opens page 1
    for name in SECTIONS:
        m = re.search(re.escape(name) + r"[\s.]*?(\d+)\s", toc.replace("\n", " ") + " ")
        assert m, f"{name} missing from the table of contents: {toc!r}"
        page = int(m.group(1))
        assert page >= 1
        assert f"Details of {name}" in text[page - 1] and name in text[page - 1]
        earlier = [i + 1 for i, t in enumerate(text) if f"Details of {name}" in t and i + 1 < page]
        assert not earlier


@pdf_engine
def test_italian_footer_and_language() -> None:
    pypdf = pytest.importorskip("pypdf")
    r = make_client().post(PDF_PATH, json={**payload(sample_html()), "lang": "it"})
    assert r.status_code == 200
    text = pages_text(r.content)
    assert re.search(r"Pagina 2 di \d+", text[1])
    assert pypdf.PdfReader(io.BytesIO(r.content)).trailer["/Root"]["/Lang"] == "it"


@pdf_engine
def test_same_input_gives_the_same_bytes() -> None:
    assert render(sample_html()) == render(sample_html())


@pdf_engine
def test_nothing_is_fetched_and_external_references_are_refused(
    tmp_path: pytest.TempPathFactory,
) -> None:
    renderer = WeasyPrintRenderer()
    secret = tmp_path / "secret.png"  # type: ignore[operator]
    secret.write_bytes(b"not an image")
    # bypass the sanitiser on purpose: the fetcher is the second, independent layer
    css = f"p {{ background: url(file://{secret}) }} @font-face {{ font-family: X; src: url(http://127.0.0.1:9/x.woff2) }}"
    body = (
        f'<p>x</p><img src="file://{secret}" alt="f"><img src="http://127.0.0.1:9/a.png" alt="h">'
    )
    pdf = renderer.render(ReportRenderRequest(body, css, "T", "", "en", "2026-11-09T10:00:00Z"))
    assert pdf.startswith(b"%PDF")
    assert {"file", "http"} <= set(renderer.last_refused)


@pdf_engine
def test_css_grids_of_the_page_do_not_hang_or_break_the_engine() -> None:
    # WeasyPrint 70 asserts on a splitting two-column grid and crawls on a grid wrapping the report
    grid = "<style>.results{display:grid;gap:1rem}.graphs{display:grid;grid-template-columns:1fr 1fr}</style>"
    charts = "".join(
        "<figure class='chart'><svg viewBox='0 0 9 9' width='300' height='400'><title>c</title></svg></figure>"
        for _ in range(30)
    )
    html = (
        grid
        + f"<div class='results'>{sample_html(filler=40)}<div class='graphs'>{charts}</div></div>"
    )
    started = time.monotonic()
    text = pages_text(render(html))
    assert time.monotonic() - started < 30 and len(text) > 3


@pdf_engine
def test_malicious_input_still_renders_without_the_hostile_parts() -> None:
    html = sample_html(filler=2) + '<script>1</script><img src="http://127.0.0.1:9/a.png" alt="x">'
    text = pages_text(render(html))
    assert any("Alpha mission" in t for t in text)


def test_design_hooks_survive_the_sanitiser_and_the_pdf_stylesheet_has_no_grid() -> None:
    from backend.adapters.report_weasyprint import server_css

    html = '<section class="phase" data-phase="A" data-x="1"><h3 data-rp="section" onclick="x()">T</h3><div data-kind="engine_result">k</div></section>'
    body, _css = sanitize_report_html(html)
    assert (
        'data-phase="A"' in body
        and 'data-rp="section"' in body
        and 'data-kind="engine_result"' in body
    )
    assert "data-x" not in body and "onclick" not in body
    css = server_css()
    assert not re.search(r"display\s*:\s*(inline-)?grid", css, re.IGNORECASE)
    assert "bookmark-level" in css and "target-counter" in css


@pdf_engine
@pytest.mark.skipif(shutil.which("pdfinfo") is None, reason="poppler-utils not installed")
def test_pdf_is_tagged_and_has_title_author_and_language(tmp_path) -> None:
    html = (
        '<h1 data-rp="cover">Doc</h1><h2 id="a">Section</h2><h3>Sub</h3>'
        "<table><thead><tr><th scope='col'>H</th></tr></thead><tbody><tr><td>v</td></tr></tbody></table>"
    )
    out = tmp_path / "t.pdf"
    out.write_bytes(render(html))
    info = subprocess.run(["pdfinfo", str(out)], capture_output=True, text=True, check=True).stdout
    assert "Tagged:" in info and "yes" in info.split("Tagged:")[1].splitlines()[0]
    assert re.search(r"Title:\s+\S", info) and "Author:" in info
