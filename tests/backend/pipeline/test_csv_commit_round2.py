# SPDX-License-Identifier: Apache-2.0
"""Fix round 2, N4: lo stato del CSV si registra per blocchi, non per riga."""

import hashlib
from pathlib import Path
from typing import Any

import pytest

from backend.core.manifest import load_manifest
from backend.plugins.ingest_csv import plugin as plugin_mod
from backend.plugins.ingest_csv.plugin import CsvIngestSource

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "backend/plugins/ingest_csv/manifest.toml"


def make(tmp_path: Path, n: int) -> Path:
    p = tmp_path / "big.csv"
    with p.open("w", encoding="utf-8") as f:
        f.write("t_utc,site_id,power_w\n")
        for i in range(n):
            f.write(f"2026-10-13T10:00:00Z,s{i % 7},{i}\n")
    return p


async def test_hashing_is_proportional_to_batches_not_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows = 100_000
    src = CsvIngestSource(load_manifest(MANIFEST), path=make(tmp_path, rows), max_rows=200_000)
    calls = {"n": 0}
    real = hashlib.sha256

    def counting(*a: Any, **k: Any) -> Any:
        calls["n"] += 1
        return real(*a, **k)

    monkeypatch.setattr(plugin_mod.hashlib, "sha256", counting)
    n = 0
    async for _ in src.read():
        n += 1
    assert n == rows
    batches = rows // plugin_mod.COMMIT_EVERY
    assert calls["n"] <= 2 * (batches + 3)  # 2 hash per fingerprint, O(batch) e non O(righe)
    # e il secondo poll (file invariato) non rilegge ne' rifa' hash dell'intero prefisso
    calls["n"] = 0
    assert [r async for r in src.read()] == []
    assert calls["n"] <= 2


async def test_abandoned_consumer_reemits_at_most_one_batch(tmp_path: Path) -> None:
    total, stop_at = 5000, 2500
    src = CsvIngestSource(load_manifest(MANIFEST), path=make(tmp_path, total))
    first: list[int] = []
    async for r in src.read():
        first.append(int(r["power_w"]))
        if len(first) == stop_at:
            break  # il consumatore si ferma a meta': righe consegnate ma non confermate
    rest = [int(r["power_w"]) async for r in src.read()]
    assert set(first) | set(rest) == set(range(total))  # nessuna riga saltata
    overlap = set(first) & set(rest)
    # righe rielaborate: dall'ultimo commit (multiplo di COMMIT_EVERY) fino al punto di arresto
    assert len(overlap) == stop_at % plugin_mod.COMMIT_EVERY
    assert len(overlap) <= plugin_mod.COMMIT_EVERY
    assert rest == sorted(rest) and rest[-1] == total - 1
    assert [r async for r in src.read()] == []  # e poi il file risulta interamente consumato
