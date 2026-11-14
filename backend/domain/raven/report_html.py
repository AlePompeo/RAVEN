# SPDX-License-Identifier: Apache-2.0
"""Allow-list sanitiser for the report HTML that the browser sends to the PDF renderer.

The renderer never fetches anything (its URL fetcher accepts only data: URIs); this module is the
first of two layers: it drops every tag and attribute that is not needed to lay out a printed report
(scripts, frames, objects, links, forms, event handlers) and every URL that is not a data: image or
an in-page #anchor. Standard library only, so it is testable without the PDF extra.
"""

import re
from html import escape
from html.parser import HTMLParser

MAX_ELEMENTS = 60_000
MAX_DEPTH = 120

_VOID = frozenset({"br", "hr", "img", "col", "wbr"})
_DROP_VOID = frozenset(  # void elements that are removed: they have no end tag to wait for
    {"link", "meta", "base", "input", "embed", "frame", "source", "track", "param", "area"}
)
_HTML_TAGS = frozenset(
    {
        "main", "section", "article", "aside", "header", "footer", "nav", "div",
        "span", "p", "br", "hr", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "dl", "dt",
        "dd", "table", "caption", "colgroup", "col", "thead", "tbody", "tfoot", "tr", "th", "td",
        "a", "strong", "em", "b", "i", "u", "small", "sub", "sup", "code", "pre", "kbd", "abbr",
        "mark", "q", "blockquote", "figure", "figcaption", "img", "details", "summary", "time",
        "cite", "dfn", "s", "wbr", "bdi", "bdo", "var", "samp",
    }
)  # fmt: skip
_SVG_TAGS = frozenset(
    {
        "svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "text",
        "tspan", "defs", "lineargradient", "radialgradient", "stop", "clippath", "mask", "title",
        "desc", "use", "marker", "pattern", "symbol",
    }
)  # fmt: skip
# Tags removed together with everything inside them.
_DROP_CONTENT = frozenset(
    {
        "script", "iframe", "frame", "frameset", "object", "embed", "applet", "noscript",
        "template", "foreignobject", "audio", "video", "canvas", "select", "textarea", "button",
        "input", "form", "link", "meta", "base", "math", "dialog", "map",
    }
)  # fmt: skip
_GLOBAL_ATTRS = frozenset(
    {"id", "class", "lang", "dir", "title", "style", "role", "aria-label", "aria-hidden",
     "aria-labelledby", "aria-describedby", "aria-level", "tabindex", "data-rp", "data-phase",
     "data-kind", "data-report-root", "data-testid"}
)  # fmt: skip
_TAG_ATTRS: dict[str, frozenset[str]] = {
    "td": frozenset({"colspan", "rowspan", "headers", "scope"}),
    "th": frozenset({"colspan", "rowspan", "headers", "scope", "abbr"}),
    "col": frozenset({"span"}),
    "colgroup": frozenset({"span"}),
    "ol": frozenset({"start", "reversed", "type"}),
    "li": frozenset({"value"}),
    "time": frozenset({"datetime"}),
    "img": frozenset({"src", "alt", "width", "height"}),
    "a": frozenset({"href"}),
    "details": frozenset({"open"}),
}
_SVG_ATTRS = frozenset(
    {
        "viewbox", "width", "height", "x", "y", "x1", "y1", "x2", "y2", "cx", "cy", "r", "rx", "ry",
        "d", "points", "transform", "fill", "fill-opacity", "fill-rule", "stroke", "stroke-width",
        "stroke-opacity", "stroke-dasharray", "stroke-dashoffset", "stroke-linecap",
        "stroke-linejoin", "opacity", "text-anchor", "dominant-baseline", "font-size",
        "font-family", "font-weight", "font-style", "letter-spacing", "dx", "dy", "offset",
        "stop-color", "stop-opacity", "gradientunits", "gradienttransform", "preserveaspectratio",
        "xmlns", "version", "clip-path", "mask", "marker-start", "marker-mid", "marker-end",
        "markerwidth", "markerheight", "refx", "refy", "orient", "patternunits", "clippathunits",
        "maskunits", "href", "xlink:href", "visibility", "display", "vector-effect",
    }
)  # fmt: skip
_DATA_IMG = re.compile(r"^data:image/(png|jpeg|gif|webp|svg\+xml)(;[a-z0-9=.+-]+)*,", re.IGNORECASE)
_ESCAPED = re.compile(r"\\([0-9a-fA-F]{1,6}\s?|.)", re.DOTALL)
_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_IMPORT = re.compile(r"@import\b[^;{}]*;?", re.IGNORECASE)
_URL = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.IGNORECASE | re.DOTALL)
_DANGEROUS = re.compile(
    r"expression\s*\(|behaviou?r\s*:|-moz-binding|javascript:|@namespace", re.IGNORECASE
)
# CSS functions that take a bare string as an image source (a way around url()): removed whole
_ELEMENT_FN = re.compile(
    r"(?<![\w])(?:image|image-set|cross-fade|element)\s*\([^)]*\)", re.IGNORECASE
)


class UnsafeHtml(ValueError):
    """The document exceeds the structural limits (too many elements or too deep)."""


def _unescape_css(text: str) -> str:
    """Resolve CSS escapes (\\75 rl) so that obfuscated url() or @import cannot slip through."""

    def repl(m: re.Match[str]) -> str:
        g = m.group(1)
        if re.fullmatch(r"[0-9a-fA-F]{1,6}\s?", g):
            try:
                return chr(int(g.strip(), 16))
            except (ValueError, OverflowError):
                return ""
        return g

    return _ESCAPED.sub(repl, text)


def sanitize_css(css: str) -> str:
    """Remove @import, every url() that is not a data: image and a few legacy script hooks."""
    css = _CSS_COMMENT.sub("", _unescape_css(css)).replace("<", "").replace(">", "")
    css = _IMPORT.sub("", css)
    css = _DANGEROUS.sub("", css)
    css = _ELEMENT_FN.sub("none", css)

    def url(m: re.Match[str]) -> str:
        target = m.group(2).strip()
        return m.group(0) if _DATA_IMG.match(target) else "none"

    return _URL.sub(url, css)


def _safe_attr(tag: str, name: str, value: str, in_svg: bool) -> str | None:
    if name.startswith(("on", "xml:")) or name == "xmlns:xlink":
        return None
    if name in ("href", "xlink:href"):
        v = value.strip()
        return v if v.startswith("#") and len(v) > 1 and (in_svg or tag == "a") else None
    if name == "src":
        return value.strip() if tag == "img" and _DATA_IMG.match(value.strip()) else None
    if name == "style":
        return sanitize_css(value)
    if name in _GLOBAL_ATTRS or name in _TAG_ATTRS.get(tag, ()):
        return value
    if in_svg and name in _SVG_ATTRS:
        return sanitize_css(value) if "url(" in value.lower() else value
    return None


class _Cleaner(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.styles: list[str] = []
        self._stack: list[str] = []
        self._skip: list[str] = []  # nested drop-with-content tags
        self._in_style = False
        self._svg_depth = 0
        self._count = 0

    def _allowed(self, tag: str) -> bool:
        return tag in _SVG_TAGS if self._svg_depth else tag in _HTML_TAGS or tag == "svg"

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._skip:
            if tag not in _VOID and tag not in _DROP_VOID:
                self._skip.append(tag)
            return
        if tag == "style":
            self._in_style = True
            return
        if tag in _DROP_CONTENT or (tag == "title" and not self._svg_depth):
            if tag not in _VOID and tag not in _DROP_VOID:
                self._skip.append(tag)
            return
        if not self._allowed(tag):
            return  # unknown tag: unwrap (keep its text)
        self._count += 1
        if self._count > MAX_ELEMENTS or len(self._stack) > MAX_DEPTH:
            raise UnsafeHtml("document too large or too deeply nested")
        if tag == "svg":
            self._svg_depth += 1
        in_svg = self._svg_depth > 0
        parts = [tag]
        for name, value in attrs:
            safe = _safe_attr(tag, name.lower(), value or "", in_svg)
            if safe is not None:
                parts.append(f' {name.lower()}="{escape(safe, quote=True)}"')
        self.out.append("<" + parts[0] + "".join(parts[1:]) + ">")
        if tag not in _VOID:
            self._stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        before = len(self._stack)
        self.handle_starttag(tag, attrs)
        if len(self._stack) > before and self._stack[-1] == tag:
            self.handle_endtag(tag)
        elif self._skip and self._skip[-1] == tag and tag not in _VOID:
            self._skip.pop()

    def handle_endtag(self, tag: str) -> None:
        if self._skip:
            if tag in self._skip:
                while self._skip and self._skip.pop() != tag:
                    pass
            return
        if tag == "style":
            self._in_style = False
            return
        if tag in self._stack:
            while self._stack:
                top = self._stack.pop()
                self.out.append(f"</{top}>")
                if top == "svg":
                    self._svg_depth -= 1
                if top == tag:
                    break

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        if self._in_style:
            self.styles.append(data)
        else:
            self.out.append(escape(data, quote=False))

    def finish(self) -> None:
        while self._stack:
            self.out.append(f"</{self._stack.pop()}>")


def sanitize_report_html(html: str) -> tuple[str, str]:
    """Return (body_html, css): the cleaned body content and the cleaned concatenated <style> text."""
    parser = _Cleaner()
    parser.feed(html)
    parser.close()
    parser.finish()
    css = "\n".join(sanitize_css(s) for s in parser.styles)
    return "".join(parser.out), css
