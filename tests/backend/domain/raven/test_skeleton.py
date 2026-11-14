# SPDX-License-Identifier: Apache-2.0
"""RAVEN skeleton (M3): stage contracts, pipeline interface and the import-linter contracts."""

import dataclasses
import importlib
import subprocess
from pathlib import Path

import pytest

from backend.domain.raven import pipeline

ROOT = Path(__file__).resolve().parents[4]
STAGE_MODULES = {
    "s0": "s0_context",
    "s1": "s1_geometry",
    "s2": "s2_terrain",
    "s3": "s3_illumination",
    "s4": "s4_power",
    "s5": "s5_rf",
    "s6": "s6_dsn",
    "s7": "s7_mission",
}


def test_every_stage_has_a_module_with_a_documented_contract() -> None:
    for stage, mod in STAGE_MODULES.items():
        m = importlib.import_module(f"backend.domain.raven.{mod}")
        assert m.__doc__ and m.__doc__.strip(), stage
        assert m.__all__, stage


def test_stage_order_only_reads_earlier_stages() -> None:
    seen: set[str] = set()
    for stage, reads in pipeline.STAGE_ORDER:
        assert set(reads) <= seen, (stage, reads)
        seen.add(stage)
    assert seen == set(STAGE_MODULES)


def test_stage_order_matches_the_import_layers() -> None:
    """Whatever a stage reads must sit below it in the .importlinter layers."""
    text = (ROOT / ".importlinter").read_text(encoding="utf-8")
    layers = text.split("[importlinter:contract:raven-layers]")[1].split("[importlinter")[0]
    rows = [r.strip() for r in layers.splitlines() if "backend.domain.raven." in r]
    height: dict[str, int] = {}
    for level, row in enumerate(reversed(rows)):
        for part in row.split("|"):
            height[part.strip(" ()").rsplit(".", 1)[1]] = level
    for stage, reads in pipeline.STAGE_ORDER:
        for r in reads:
            assert height[STAGE_MODULES[r]] < height[STAGE_MODULES[stage]], (stage, r)


def test_evaluation_declares_what_ran() -> None:
    fields = {f.name for f in dataclasses.fields(pipeline.Evaluation)}
    assert {"model_version", "registry_sha256", "implemented_stages", "grid", "site"} <= fields
    assert {"geometry", "terrain", "illumination", "power", "rf", "dsn", "mission"} <= fields


def test_registry_sha256_is_stable() -> None:
    a = pipeline.registry_sha256()
    assert a == pipeline.registry_sha256() and len(a) == 64


def test_import_contracts_hold() -> None:
    """The layer contracts pass on the current tree (the same check as `make lint`)."""
    exe = ROOT / ".venv" / "bin" / "lint-imports"
    if not exe.exists():
        pytest.skip("lint-imports not installed")
    r = subprocess.run([str(exe)], cwd=ROOT, capture_output=True, text=True, check=False)
    assert r.returncode == 0, r.stdout[-800:]
    assert "raven" in r.stdout
