# SPDX-License-Identifier: Apache-2.0
from pathlib import Path

import pytest

from backend.assistant.loader import (
    KnowledgeError,
    contract_docs,
    load_all,
    manifest_docs,
    parse_doc,
    unit_from_name,
    validate,
)

ROOT = Path(__file__).resolve().parents[3]

BASIC = """---
id: demo
title: Demo
kind: concept
summary: Un concetto.
tags: [a, b]
sources:
  - {ref: docs/architecture.md, supports: tutto}
last_verified: 2026-10-15
---
## Testo

Vedi [altro](kb:other).
"""


def test_parse_basic_and_date_normalised() -> None:
    d = parse_doc(BASIC, "x.md")
    assert d.id == "demo" and d.tags == ("a", "b") and d.last_verified == "2026-10-15"
    assert "kb:other" in d.body


@pytest.mark.parametrize(
    "text", ["niente", "---\nid: [\n---\nx", "---\n- a\n---\nx", "---\nid: a\n"]
)
def test_parse_rejects_bad_front_matter(text: str) -> None:
    with pytest.raises(KnowledgeError):
        parse_doc(text)


def test_validate_detects_problems() -> None:
    a = parse_doc(BASIC)
    dup = parse_doc(BASIC)
    errs = validate([a, dup], ROOT)
    assert any("duplicato" in e for e in errs)
    assert any("inesistente" in e and "other" in e for e in errs)


def test_validate_formula_requires_units_and_example() -> None:
    text = BASIC.replace("kind: concept", "kind: formula").replace(
        "last_verified",
        "expression: x = y\nvariables:\n  - {symbol: x, name: ics, unit: ''}\nlast_verified",
    )
    errs = validate([parse_doc(text)], ROOT)
    assert any("senza unit" in e for e in errs)
    assert any("worked_example" in e for e in errs)
    assert any("assumptions" in e for e in errs)


def test_validate_missing_source_file() -> None:
    text = BASIC.replace("docs/architecture.md", "docs/non-esiste.md")
    assert any("fonte non trovata" in e for e in validate([parse_doc(text)], ROOT))


def test_unit_suffixes() -> None:
    assert "dB" in unit_from_name("link_margin_db")
    assert "deg" in unit_from_name("az_deg")
    assert "W" in unit_from_name("power_w")
    assert unit_from_name("t_utc") == ""
    assert unit_from_name("site_id") == ""


def test_contract_docs_list_fields_with_units() -> None:
    docs = {d.id: d for d in contract_docs(ROOT / "contracts")}
    tel = docs["contract-telemetry"]
    assert "`sun.az_deg`" in tel.body and "gradi (deg)" in tel.body
    assert "`link_margin_db`: tipo number, opzionale, unita' decibel (dB)" in tel.body
    assert "`power_w`: tipo number, obbligatorio" in tel.body


def test_manifest_docs_cover_every_plugin() -> None:
    docs = manifest_docs(ROOT / "backend/plugins", ROOT)
    ids = {d.id for d in docs}
    assert {"plugin-fspl-c", "plugin-echo-llm", "plugin-servo-ctrl-c"} <= ids
    fspl = next(d for d in docs if d.id == "plugin-fspl-c")
    assert fspl.kind == "simulation" and "licenza: Apache-2.0" in fspl.body


def test_extra_root_picked_up_without_code_change(tmp_path: Path) -> None:
    (tmp_path / "docs/knowledge").mkdir(parents=True)
    (tmp_path / "docs/knowledge/x.md").write_text(BASIC.replace("docs/architecture.md", "x"))
    (tmp_path / "docs/knowledge/_skip.md").write_text("niente front matter")
    (tmp_path / "docs/knowledge/broken.md").write_text("niente")
    docs, errors = load_all(tmp_path)
    assert [d.id for d in docs] == ["demo"]
    assert any("broken.md" in e for e in errors)
