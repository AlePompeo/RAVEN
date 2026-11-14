# SPDX-License-Identifier: Apache-2.0
"""Lint della base di conoscenza del repository + esempi svolti confrontati col codice reale."""

import asyncio
import shutil
import subprocess
from pathlib import Path

import pytest

from backend.adapters.subprocess_sim import ExecSimulation
from backend.assistant.kb import KnowledgeBase
from backend.assistant.loader import LINK_RE, knowledge_files, load_all
from backend.assistant.model import KnowledgeDoc
from backend.core.manifest import load_manifest

ROOT = Path(__file__).resolve().parents[3]
# Plugin senza documento scritto a mano: solo voce generata dal manifest (motivo in ogni riga).
EXEMPT_PLUGINS = {
    "echo-llm": "stub di test che ripete l'input",
    "example-data": "sorgente dati di esempio per i test",
    "example-sim": "simulazione di esempio per i test",
}


@pytest.fixture(scope="module")
def kb() -> KnowledgeBase:
    return KnowledgeBase(ROOT)


def test_all_documents_are_valid(kb: KnowledgeBase) -> None:
    assert kb.errors == []
    assert len([d for d in kb.docs if d.origin == "manual"]) >= 20


def test_every_formula_has_units_and_worked_example(kb: KnowledgeBase) -> None:
    formulas = [d for d in kb.docs if d.kind == "formula"]
    assert {d.id for d in formulas} >= {"fspl", "servo-pi-law"}
    for d in formulas:
        assert d.expression and d.assumptions and d.limits, d.id
        assert d.worked_example.get("inputs") and d.worked_example.get("outputs"), d.id
        assert all(v.unit for v in d.variables), d.id


def test_every_plugin_has_a_knowledge_doc_or_is_exempt(kb: KnowledgeBase) -> None:
    manual = [d for d in kb.docs if d.origin == "manual"]
    for mf in sorted((ROOT / "backend/plugins").glob("*/manifest.toml")):
        pid = load_manifest(mf).id
        own = (mf.parent / "knowledge").is_dir() and any((mf.parent / "knowledge").glob("*.md"))
        if own or any(pid in d.applies_to for d in manual):
            continue
        assert pid in EXEMPT_PLUGINS, f"plugin {pid} senza documento di conoscenza"
    assert not [p for p in EXEMPT_PLUGINS if any(p in d.applies_to for d in manual)], (
        "esenzione superflua: il plugin ha gia' un documento"
    )


def test_no_dead_links_and_reserved_ids(kb: KnowledgeBase) -> None:
    ids = {d.id for d in kb.docs}
    for d in kb.docs:
        for target in list(d.related) + LINK_RE.findall(d.body):
            assert target in ids, f"{d.id} -> {target}"
        if d.origin == "manual":
            assert not d.id.startswith(("plugin-", "contract-")), d.id


def test_templates_and_readme_are_not_indexed() -> None:
    names = {p.name for p in knowledge_files(ROOT)}
    assert "README.md" not in names and "_template.md" not in names
    assert "_problem_template.md" not in names
    assert (ROOT / "docs/knowledge/hackathon/_problem_template.md").is_file()


def test_every_manifest_and_contract_gets_a_generated_entry(kb: KnowledgeBase) -> None:
    ids = {d.id for d in kb.docs}
    for mf in (ROOT / "backend/plugins").glob("*/manifest.toml"):
        assert f"plugin-{load_manifest(mf).id}" in ids
    for sc in (ROOT / "contracts").glob("*.schema.json"):
        assert "contract-" + sc.name.removesuffix(".schema.json").replace("_", "-") in ids


def _doc(kb: KnowledgeBase, id_: str) -> KnowledgeDoc:
    d = kb.get(id_)
    assert d is not None
    return d


async def test_fspl_worked_example_equals_real_plugin_output(
    kb: KnowledgeBase, tmp_path: Path
) -> None:
    if not shutil.which("gcc"):
        pytest.skip("gcc assente")
    exe = tmp_path / "fspl"
    await asyncio.to_thread(
        subprocess.run,
        ["gcc", "-O2", "-o", str(exe), str(ROOT / "backend/plugins/fspl_c/fspl.c"), "-lm"],
        check=True,
    )
    ex = _doc(kb, "fspl").worked_example
    out = await ExecSimulation([str(exe)], root=tmp_path).run(
        {k: float(v) for k, v in ex["inputs"].items()}, timeout_s=5
    )
    assert out["fspl_db"] == pytest.approx(float(ex["outputs"]["fspl_db"]), abs=6e-4)
    assert ex["inputs"] == {"distance_km": 384400, "freq_ghz": 2.2}


_DRIVER = r"""
#include <stdio.h>
#include "control.h"
int main(void) {
    pi_ctrl_t c; float u = 0;
    if (pi_init(&c, 2.0f, 20.0f, 0.01f, 0.0f, 180.0f, 1) != CTRL_OK) return 1;
    if (pi_step(&c, 10.0f, 0.0f, &u) != CTRL_OK) return 2;
    printf("%.4f\n", u);
    return 0;
}
"""


def test_servo_pi_worked_example_equals_real_control_code(
    kb: KnowledgeBase, tmp_path: Path
) -> None:
    if not shutil.which("gcc"):
        pytest.skip("gcc assente")
    plugin = ROOT / "backend/plugins/servo_ctrl_c"
    (tmp_path / "drv.c").write_text(_DRIVER)
    exe = tmp_path / "drv"
    subprocess.run(
        [
            "gcc",
            "-std=c99",
            f"-I{plugin}",
            "-o",
            str(exe),
            str(tmp_path / "drv.c"),
            str(plugin / "control.c"),
            "-lm",
        ],
        check=True,
    )
    u = float(subprocess.run([str(exe)], check=True, capture_output=True, text=True).stdout)
    ex = _doc(kb, "servo-pi-law").worked_example
    assert ex["inputs"]["kp"] == 2 and ex["inputs"]["ki"] == 20 and ex["inputs"]["dt_s"] == 0.01
    assert u == pytest.approx(float(ex["outputs"]["u_deg"]), abs=1e-3)


def test_every_suggestion_retrieves_its_own_document(kb: KnowledgeBase) -> None:
    from backend.assistant.service import AssistantService

    svc = AssistantService(
        kb,
        lambda _p: None,
        provider_id="assistant-extractive",
        timeout_for=lambda _p: 1.0,
        llm_allowed=lambda _k: True,
    )
    pages = ["", "sims", "telemetry", "viewer", "fspl-c", "servo-ctrl-c", "chat", "home"]
    seen = 0
    for page in pages:
        for s in svc.suggestions(page, limit=20):
            top = kb.index.search(s["question"], top_k=5).doc_ids
            assert s["doc_id"] in top, (page, s)
            seen += 1
    assert seen >= 20


def test_load_all_matches_kb_and_is_deterministic() -> None:
    a, _ = load_all(ROOT)
    b, _ = load_all(ROOT)
    assert [d.id for d in a] == [d.id for d in b]
