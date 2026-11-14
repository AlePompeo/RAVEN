# SPDX-License-Identifier: Apache-2.0
"""Golden outputs (RAVEN migration M0): the engines must keep producing the frozen numbers.

The fixtures under `golden/` are written by `scripts/raven_golden.py` and carry their provenance
(commit, date, scenarios, kernel and DEM hashes). The real set skips when the NAIF kernels or the
cached LOLA tiles are absent, like the other real-engine tests. They pin the CURRENT numbers; they
are not a validation of the model.
"""

import json
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("numpy")
pytest.importorskip("scipy")

from scripts import raven_golden as rg
from scripts.raven_reference import terrain as archived_terrain

GOLDEN = Path(__file__).parent / "golden"
needs_real = pytest.mark.skipif(
    not (rg.have_kernels() and rg.have_tiles()), reason="kernels or LOLA tiles missing"
)


def _load(which: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((GOLDEN / f"{which}.json").read_text(encoding="utf-8"))
    return data


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Any:
    from backend.domain.grazing import horizon, terrain

    # Archived endpoints need archived terrain dependencies, not the corrected current S2.
    monkeypatch.setattr(horizon, "ALGORITHM", "raven-horizon-v1")
    monkeypatch.setattr(horizon, "great_circle_destination", archived_terrain.destination)
    monkeypatch.setattr(terrain, "great_circle_destination", archived_terrain.destination)
    monkeypatch.setattr(terrain, "_ridge_radius", archived_terrain.ridge_radius)
    return rg.make_client()


def _check(which: str, client: Any) -> None:
    golden = _load(which)
    cases = {c[0]: c for c in rg.cases_of(which)}
    assert set(golden["outputs"]) == set(cases), "golden cases and scenarios differ"
    for name, (_n, _s, method, path, payload) in cases.items():
        fresh = rg.run_case(client, method, path, payload)
        diffs = rg.close(golden["outputs"][name], fresh)
        assert not diffs, f"{name}: {len(diffs)} differences, first: {diffs[:3]}"


def test_provenance_is_declared() -> None:
    for which in ("synthetic", "real"):
        prov = _load(which)["provenance"]
        for key in ("git_commit", "generated_utc", "generator", "cases", "note"):
            assert prov[key], (which, key)
        assert set(prov["cases"]) == set(_load(which)["outputs"])
    real = _load("real")["provenance"]
    assert real["kernels"] and real["dem_products"] and real["dem_lock_sha256"]


def test_golden_synthetic(client: Any) -> None:
    _check("synthetic", client)


@needs_real
def test_golden_real(client: Any) -> None:
    _check("real", client)


def test_close_helper_detects_differences() -> None:
    assert rg.close({"a": [1.0, 2.0]}, {"a": [1.0, 2.0 + 1e-12]}) == []
    assert rg.close({"a": [1.0]}, {"a": [1.1]})
    assert rg.close({"a": 1}, {"b": 1})
    assert rg.close({"a": None}, {"a": 0.0})
