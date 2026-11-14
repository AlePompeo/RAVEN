# SPDX-License-Identifier: Apache-2.0
"""In un'immagine di runtime (senza `tests/`) le fonti mancanti non sono errori; nel checkout completo si'."""

from pathlib import Path

from backend.assistant.loader import load_all

DOC = """---
id: demo-doc
title: Demo
kind: concept
summary: Documento di prova.
sources:
  - ref: docs/non-esiste.md
    supports: nulla
last_verified: 2026-10-19
---
Testo.
"""


def _tree(tmp_path: Path, with_tests: bool) -> Path:
    (tmp_path / "docs" / "knowledge").mkdir(parents=True)
    (tmp_path / "docs" / "knowledge" / "demo.md").write_text(DOC, encoding="utf-8")
    (tmp_path / "backend" / "plugins").mkdir(parents=True)
    (tmp_path / "contracts").mkdir()
    if with_tests:
        (tmp_path / "tests").mkdir()
    return tmp_path


def test_missing_source_is_an_error_in_a_full_checkout(tmp_path: Path) -> None:
    _, errors = load_all(_tree(tmp_path, with_tests=True))
    assert any("fonte non trovata" in e for e in errors)


def test_missing_source_is_not_an_error_in_a_runtime_image(tmp_path: Path) -> None:
    docs, errors = load_all(_tree(tmp_path, with_tests=False))
    assert [d.id for d in docs] == ["demo-doc"]
    assert not any("fonte non trovata" in e for e in errors)
