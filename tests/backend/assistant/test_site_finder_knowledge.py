# SPDX-License-Identifier: Apache-2.0
from pathlib import Path

import pytest

from backend.assistant.kb import KnowledgeBase

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def kb() -> KnowledgeBase:
    return KnowledgeBase(ROOT)


def test_the_site_finder_page_loads_without_lint_errors(kb: KnowledgeBase) -> None:
    assert any(d.id == "site-finder" for d in kb.docs)
    assert not [e for e in kb.errors if "site-finder" in e]


@pytest.mark.parametrize(
    "question",
    [
        "come faccio a trovare automaticamente i siti migliori?",
        "cosa significa la probabilita' di raggiungere gli obiettivi nella ricerca dei siti",
        "perche' un sito risulta non confrontabile nella ricerca automatica",
    ],
)
def test_the_assistant_finds_the_page_for_questions_about_the_search(
    kb: KnowledgeBase, question: str
) -> None:
    hits = kb.index.search(question, page_ids=("siti",), top_k=5).hits
    assert "site-finder" in [h.doc.id for h in hits[:3]], [h.doc.id for h in hits]
