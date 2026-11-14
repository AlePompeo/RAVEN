# SPDX-License-Identifier: Apache-2.0
from pathlib import Path

from backend.assistant.index import Index, chunk_doc, slug
from backend.assistant.kb import KnowledgeBase
from backend.assistant.loader import parse_doc
from backend.assistant.text import detect_lang, fold, tokens

FORMULA = """---
id: fspl-test
title: Perdita nello spazio libero
kind: formula
summary: Attenuazione del segnale in spazio libero.
tags: [FSPL, link budget]
applies_to: [fspl-c]
expression: "FSPL = 92.45 + 20 log10(d) + 20 log10(f)"
variables:
  - {symbol: d, name: distanza, unit: km}
  - {symbol: f, name: frequenza, unit: GHz}
assumptions: [spazio libero]
limits: [non vale in atmosfera]
worked_example: {inputs: {d: 1, f: 1}, outputs: {fspl: 92.45}}
sources: [{ref: docs/hal.md, supports: x}]
last_verified: 2026-10-15
---
## Contesto

Testo lungo sulla propagazione.

## Altro

Il servo usa un controllore PI.
"""

OTHER = """---
id: servo
title: Controllore PI del servo
kind: method
summary: Controllore proporzionale integrale con anti-windup.
tags: [PI, servo]
applies_to: [servo-ctrl-c]
sources: [{ref: docs/hal.md, supports: x}]
last_verified: 2026-10-15
---
Il controllore limita l'uscita.
"""


def _index() -> Index:
    return Index([parse_doc(FORMULA), parse_doc(OTHER)])


def test_fold_and_tokens_accents_stems_synonyms() -> None:
    assert fold("Perché è già") == "perche e gia"
    assert tokens("distanza") == tokens("distance")
    assert tokens("azimut") == tokens("azimuth")
    assert tokens("il La the of") == []
    assert tokens("G/T e Eb/N0") == ["gt", "ebn0"]


def test_detect_lang() -> None:
    assert detect_lang("What is the link margin?") == "en"
    assert detect_lang("Che cos'è il margine di collegamento?") == "it"


def test_chunking_by_heading_with_unique_anchors() -> None:
    chunks = chunk_doc(parse_doc(FORMULA))
    assert chunks[0].role == "card" and "92.45" in chunks[0].text and "[km]" in chunks[0].text
    assert [c.anchor for c in chunks[1:]] == ["contesto", "altro"]
    assert slug("Perché così?") == "perche-cosi"


def test_retrieval_it_and_en_and_refusal() -> None:
    idx = _index()
    r = idx.search("Come si calcola la perdita nello spazio libero?")
    assert r.doc_ids[0] == "fspl-test"
    r = idx.search("what is the free space loss")
    assert r.doc_ids[0] == "fspl-test"
    assert idx.search("Qual è la capitale della Francia?").hits == []
    assert idx.search("").hits == []


def test_page_context_boost_and_fallback() -> None:
    idx = _index()
    plain = idx.search("controllore")
    assert plain.doc_ids[0] == "servo"
    boosted = idx.search("controllore", page_ids=["servo-ctrl-c"])
    assert boosted.doc_ids[0] == "servo"
    fb = idx.search("cosa fa questa simulazione?", page_ids=["fspl-c"])
    assert fb.via_page_fallback and fb.doc_ids == ["fspl-test"]
    assert idx.search("cosa fa questa simulazione?").hits == []


def test_budget_and_per_doc_cap() -> None:
    idx = _index()
    r = idx.search("perdita spazio libero controllore", top_k=10, budget_tokens=1)
    assert 1 <= len(r.hits) <= 2 and any(h.chunk.role == "card" for h in r.hits)
    r = idx.search("perdita spazio libero controllore", top_k=10, budget_tokens=5000)
    assert max(r.doc_ids.count(d) for d in set(r.doc_ids)) == 1
    from collections import Counter

    assert max(Counter(h.chunk.doc_id for h in r.hits).values()) <= 3  # 2 passaggi + la scheda


def test_deterministic() -> None:
    a = _index().search("perdita spazio libero")
    b = _index().search("perdita spazio libero")
    assert [(h.chunk.doc_id, h.chunk.anchor, h.score) for h in a.hits] == [
        (h.chunk.doc_id, h.chunk.anchor, h.score) for h in b.hits
    ]


def test_generic_page_question_prefers_the_named_page() -> None:
    named = parse_doc(
        OTHER.replace("id: servo", "id: page-sims").replace(
            "applies_to: [servo-ctrl-c]", "applies_to: [sims]"
        )
    )
    unrelated = parse_doc(FORMULA.replace("applies_to: [fspl-c]", "applies_to: [sims]"))
    result = Index([unrelated, named]).search("Come si usa questa pagina?", page_ids=["sims"])
    assert result.doc_ids[0] == "page-sims"


def test_external_named_vendor_does_not_retrieve_project_pricing() -> None:
    pricing = parse_doc(
        OTHER.replace(
            "summary: Controllore proporzionale integrale con anti-windup.",
            "summary: Il piano gratuito del progetto non costa nulla.",
        )
    )
    assert Index([pricing]).search("Quanto costa il piano gratuito di Gemini?").hits == []
    assert Index([pricing]).search("What is the price of the free Gemini plan?").hits == []


def test_reload_picks_up_new_file(tmp_path: Path) -> None:
    (tmp_path / "docs/knowledge").mkdir(parents=True)
    (tmp_path / "docs/knowledge/a.md").write_text(FORMULA.replace("docs/hal.md", "x"))
    kb = KnowledgeBase(tmp_path, reload=True)
    assert len(kb.docs) == 1
    (tmp_path / "docs/knowledge/b.md").write_text(OTHER.replace("docs/hal.md", "x"))
    kb._checked = 0.0
    assert kb.refresh_if_changed() and len(kb.docs) == 2
    off = KnowledgeBase(tmp_path, reload=False)
    assert off.refresh_if_changed() is False
