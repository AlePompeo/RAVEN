# SPDX-License-Identifier: Apache-2.0
"""Chunking per intestazione e recupero BM25F (puro Python, deterministico).

Campi ponderati: testo (1), intestazione (2), id (2), applies_to (2), titolo del documento (3),
tag (3). Gancio per embeddings futuri: `Index.search` accetta un `reranker` opzionale che
riceve gli hit e restituisce un nuovo ordine; nessuna dipendenza pesante e' richiesta.
"""

import math
import re
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from backend.assistant.model import KnowledgeDoc
from backend.assistant.text import fold, tokens

K1 = 1.4
B = 0.75
MIN_COVERAGE = 0.34
PAGE_BOOST = 1.3
MANUAL_BOOST = 1.15  # i documenti scritti a mano battono le voci generate a parita' di testo
MAX_CHUNK_CHARS = 900
MAX_PER_DOC = 2
CHARS_PER_TOKEN = 3.5
_FIELD_W = {"text": 1.0, "heading": 2.0, "id": 2.0, "applies": 2.0, "title": 3.0, "tags": 3.0}
_HEADING = re.compile(r"^(#{1,4})\s+(.+?)\s*#*\s*$")
_DEICTIC = re.compile(
    r"\b(quest[aoei]|qui|qua|here|this|current|corrente|pagina|page|schermata|simulazione)\b"
)
_PAGE_QUERY_TOKENS = frozenset(
    tokens("pagina page schermata screen simulazione simulation usa use uso")
)
_KIND_ORDER = {"simulation": 0, "page": 1, "formula": 2, "method": 3, "concept": 4}
KIND_PRIORITY_DEFAULT = 9


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", fold(s)).strip("-") or "sezione"


@dataclass(frozen=True)
class Chunk:
    doc_id: str
    anchor: str
    heading: str
    text: str
    role: str = "body"  # card | body | derivation


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float
    coverage: float
    doc: KnowledgeDoc


@dataclass
class Retrieval:
    hits: list[Hit] = field(default_factory=list)
    via_page_fallback: bool = False

    @property
    def doc_ids(self) -> list[str]:
        seen: list[str] = []
        for h in self.hits:
            if h.chunk.doc_id not in seen:
                seen.append(h.chunk.doc_id)
        return seen


def formula_card(d: KnowledgeDoc) -> str:
    lines = [f"Formula: {d.expression}", "Variabili:"]
    for v in d.variables:
        rng = f", intervallo {v.range}" if v.range else ""
        lines.append(f"- {v.symbol} = {v.name} [{v.unit}]{rng}")
    if d.assumptions:
        lines.append("Ipotesi:")
        lines += [f"- {a}" for a in d.assumptions]
    if d.limits:
        lines.append("Limiti:")
        lines += [f"- {a}" for a in d.limits]
    we = d.worked_example
    if we:
        lines.append("Esempio svolto:")
        for k, label in (("inputs", "ingressi"), ("outputs", "risultato")):
            vals = we.get(k) or {}
            if isinstance(vals, dict):
                lines.append(f"- {label}: " + ", ".join(f"{a} = {b}" for a, b in vals.items()))
        if we.get("note"):
            lines.append(f"- nota: {we['note']}")
    return "\n".join(lines)


def _split_long(text: str) -> list[str]:
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]
    out: list[str] = []
    cur = ""
    for para in re.split(r"\n\s*\n", text):
        if cur and len(cur) + len(para) + 2 > MAX_CHUNK_CHARS:
            out.append(cur)
            cur = ""
        while len(para) > MAX_CHUNK_CHARS:  # paragrafo enorme: taglio duro
            out.append(para[:MAX_CHUNK_CHARS])
            para = para[MAX_CHUNK_CHARS:]
        cur = f"{cur}\n\n{para}" if cur else para
    if cur:
        out.append(cur)
    return out


def chunk_doc(d: KnowledgeDoc) -> list[Chunk]:
    chunks: list[Chunk] = []
    head = d.summary
    if d.kind == "formula":
        head = f"{d.summary}\n{formula_card(d)}"
    chunks.append(Chunk(d.id, "", d.title, head, "card"))
    if d.kind == "formula" and d.derivation:
        steps = "\n".join(f"{i}. {s}" for i, s in enumerate(d.derivation, 1))
        chunks.append(Chunk(d.id, "derivazione", "Derivazione", steps, "derivation"))
    used: set[str] = {""}
    heading, in_code = d.title, False
    buf: list[str] = []

    def flush() -> None:
        text = "\n".join(buf).strip()
        buf.clear()
        if not text:
            return
        a = base = slug(heading)
        n = 2
        while a in used:
            a = f"{base}-{n}"
            n += 1
        used.add(a)
        for piece in _split_long(text):
            chunks.append(Chunk(d.id, a, heading, piece, "body"))

    for line in d.body.splitlines():
        if line.lstrip().startswith("```"):
            in_code = not in_code
        m = None if in_code else _HEADING.match(line)
        if m:
            flush()
            heading = m.group(2)
        else:
            buf.append(line)
    flush()
    return chunks


Reranker = Callable[[str, list[Hit]], list[Hit]]


class Index:
    def __init__(self, docs: Sequence[KnowledgeDoc]) -> None:
        self.docs = {d.id: d for d in docs}
        self.chunks: list[Chunk] = []
        for d in docs:
            self.chunks += chunk_doc(d)
        self._card = {c.doc_id: c for c in self.chunks if c.role == "card"}
        self._tf: list[dict[str, float]] = []
        self._len: list[int] = []
        df: Counter[str] = Counter()
        for c in self.chunks:
            d = self.docs[c.doc_id]
            fields = {
                "text": tokens(c.text),
                "heading": tokens(c.heading),
                "id": tokens(c.doc_id.replace("-", " ").replace(".", " ")),
                "applies": tokens(" ".join(d.applies_to)),
                "title": tokens(d.title),
                "tags": tokens(" ".join(d.tags)),
            }
            tf: dict[str, float] = {}
            for name, toks in fields.items():
                for t in toks:
                    tf[t] = tf.get(t, 0.0) + _FIELD_W[name]
            self._tf.append(tf)
            self._len.append(len(fields["text"]) + len(fields["heading"]) + 1)
            df.update(tf.keys())
        n = len(self.chunks)
        self._n = n
        self._avg = (sum(self._len) / n) if n else 1.0
        self._idf = {t: math.log(1 + (n - k + 0.5) / (k + 0.5)) for t, k in df.items()}
        self._idf_oov = math.log(1 + (n + 0.5) / 0.5)

    def __len__(self) -> int:
        return len(self.chunks)

    def search(
        self,
        query: str,
        *,
        page_ids: Sequence[str] = (),
        top_k: int = 5,
        budget_tokens: int = 1800,
        level: str = "",
        reranker: Reranker | None = None,
    ) -> Retrieval:
        q = list(dict.fromkeys(tokens(query)))
        # Named subjects must be present: a question about another vendor must not
        # retrieve our plans just because it also mentions a price and a free tier.
        names = {
            t
            for word in re.findall(r"[A-Za-z0-9]+", query)[1:]
            if len(word) >= 3 and word[0].isupper()
            for t in tokens(word)
        }
        pages = {p for p in page_ids if p}
        generic_page = bool(pages and _DEICTIC.search(fold(query)) and set(q) <= _PAGE_QUERY_TOKENS)
        scored: list[Hit] = []
        if q and self._n:
            total = sum(self._idf.get(t, self._idf_oov) for t in q)
            for i, c in enumerate(self.chunks):
                tf = self._tf[i]
                if not names <= tf.keys():
                    continue
                s = 0.0
                matched = 0.0
                norm = K1 * (1 - B + B * self._len[i] / self._avg)
                for t in q:
                    f = tf.get(t, 0.0)
                    if f:
                        idf = self._idf[t]
                        s += idf * f * (K1 + 1) / (f + norm)
                        matched += idf
                if s <= 0:
                    continue
                cov = matched / total if total else 0.0
                if cov < MIN_COVERAGE:
                    continue
                if pages & set(self.docs[c.doc_id].applies_to):
                    s *= PAGE_BOOST
                if self.docs[c.doc_id].origin == "manual":
                    s *= MANUAL_BOOST
                if c.role == "derivation" and level != "tecnico":
                    s *= 0.6
                scored.append(Hit(c, s, cov, self.docs[c.doc_id]))
        scored.sort(key=lambda h: (-h.score, h.chunk.doc_id, h.chunk.anchor))
        if generic_page:
            named = {f"page-{p}" for p in pages} | {f"sim-{p}" for p in pages}
            preferred = [h for h in scored if h.chunk.doc_id in named]
            if preferred:
                scored = preferred + [h for h in scored if h.chunk.doc_id not in named]
            elif named & self.docs.keys():
                scored = self._page_fallback(pages)
        fallback = False
        if not scored and pages and _DEICTIC.search(fold(query)):
            fallback = True
            scored = self._page_fallback(pages)
        if reranker is not None:
            scored = reranker(query, scored)
        return Retrieval(self._with_cards(self._select(scored, top_k, budget_tokens)), fallback)

    def _page_fallback(self, pages: set[str]) -> list[Hit]:
        ids = [
            d for d in self.docs.values() if pages & set(d.applies_to) and d.origin != "contract"
        ]
        ids.sort(
            key=lambda d: (
                d.id not in {f"page-{p}" for p in pages},
                _KIND_ORDER.get(d.kind, KIND_PRIORITY_DEFAULT),
                d.origin != "manual",
                d.id,
            )
        )
        return [Hit(self.chunks[self._first_chunk(d.id)], 1.0, 1.0, d) for d in ids]

    def _first_chunk(self, doc_id: str) -> int:
        return next(i for i, c in enumerate(self.chunks) if c.doc_id == doc_id)

    def _with_cards(self, hits: list[Hit]) -> list[Hit]:
        """Garantisce la scheda (sintesi/formula) dei primi due documenti: e' il passaggio piu' denso."""
        out = list(hits)
        for doc_id in list(dict.fromkeys(h.chunk.doc_id for h in hits))[:2]:
            card = self._card[doc_id]
            if not any(h.chunk is card for h in out):
                best = max(h.score for h in hits if h.chunk.doc_id == doc_id)
                first = next(i for i, h in enumerate(out) if h.chunk.doc_id == doc_id)
                out.insert(first, Hit(card, best, 1.0, self.docs[doc_id]))
        return out

    @staticmethod
    def _select(hits: list[Hit], top_k: int, budget_tokens: int) -> list[Hit]:
        out: list[Hit] = []
        per_doc: Counter[str] = Counter()
        used = 0.0
        for h in hits:
            if len(out) >= top_k:
                break
            if per_doc[h.chunk.doc_id] >= MAX_PER_DOC:
                continue
            cost = len(h.chunk.text) / CHARS_PER_TOKEN
            if out and used + cost > budget_tokens:
                continue
            out.append(h)
            per_doc[h.chunk.doc_id] += 1
            used += cost
        return out
