# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path
from typing import Any

import pytest

from backend.core.errors import (
    InvalidVersion,
    ModelIntegrityError,
    ModelNotFound,
    ModelRegistryError,
    PromotionRefused,
)
from backend.core.ports import ModelRegistry
from backend.ml.registry import FileModelRegistry


def card(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "seed": 7,
        "dataset_sha256": "a" * 64,
        "library_versions": {"scikit-learn": "1.9.1"},
        "metrics": {"skill": 0.8},
        "threshold": {"skill": 0.5},
    }
    base.update(over)
    return base


@pytest.fixture
def reg(tmp_path: Path) -> FileModelRegistry:
    return FileModelRegistry(tmp_path / "models")


def test_is_model_registry(reg: FileModelRegistry) -> None:
    assert isinstance(reg, ModelRegistry)


def test_round_trip(reg: FileModelRegistry) -> None:
    v = reg.save(b"onnx-bytes", card())
    assert v == "v0001"
    blob, c = reg.load(v)
    assert blob == b"onnx-bytes"
    assert c["version"] == v
    assert c["status"] == "candidate"
    assert c["seed"] == 7
    assert c["dataset_sha256"] == "a" * 64
    assert c["metrics"] == {"skill": 0.8}
    assert c["threshold"] == {"skill": 0.5}
    assert c["created_utc"].endswith("Z")
    assert len(c["model_sha256"]) == 64
    assert c["format"] == "onnx"
    assert reg.save(b"b", card()) == "v0002"
    assert [x["version"] for x in reg.list_versions()] == ["v0001", "v0002"]


def test_no_temp_files_left(reg: FileModelRegistry, tmp_path: Path) -> None:
    reg.save(b"x", card())
    names = sorted(p.name for p in (tmp_path / "models").iterdir())
    assert [n for n in names if n != ".lock"] == ["v0001"]
    assert sorted(p.name for p in (tmp_path / "models" / "v0001").iterdir()) == [
        "model.bin",
        "model_card.json",
    ]


@pytest.mark.parametrize(
    "bad",
    [
        {"metrics": {"skill": float("nan")}},
        {"metrics": {"skill": float("inf")}},
        {"metrics": {}},
        {"threshold": {}},
        {"threshold": {"skill": float("nan")}},
        {"seed": "x"},
        {"seed": True},
        {"dataset_sha256": "zz"},
        {"library_versions": "x"},
        {"metrics": {"skill": "high"}},
    ],
)
def test_save_rejects_bad_card(reg: FileModelRegistry, bad: dict[str, Any]) -> None:
    with pytest.raises(ModelRegistryError):
        reg.save(b"x", card(**bad))


def test_save_rejects_empty_or_oversized_model(tmp_path: Path) -> None:
    r = FileModelRegistry(tmp_path / "m", max_model_bytes=10)
    with pytest.raises(ModelRegistryError):
        r.save(b"", card())
    with pytest.raises(ModelRegistryError):
        r.save(b"x" * 11, card())


def test_caller_cannot_forge_status(reg: FileModelRegistry) -> None:
    v = reg.save(b"x", card(status="promoted", version="v9999", model_sha256="0" * 64))
    _, c = reg.load(v)
    assert c["status"] == "candidate"
    assert c["version"] == v
    assert c["model_sha256"] != "0" * 64


def test_promote_requires_approval_flag(reg: FileModelRegistry) -> None:
    v = reg.save(b"x", card())
    with pytest.raises(PromotionRefused):
        reg.promote(v, approver="alice")
    with pytest.raises(PromotionRefused):
        reg.promote(v, approver="alice", approved=False)
    assert reg.promoted_version() is None
    assert reg.load(v)[1]["status"] == "candidate"


@pytest.mark.parametrize("approver", ["", "   ", "x" * 65, "bad\nname"])
def test_promote_requires_valid_approver(reg: FileModelRegistry, approver: str) -> None:
    v = reg.save(b"x", card())
    with pytest.raises(PromotionRefused):
        reg.promote(v, approver=approver, approved=True)


def test_promote_refused_below_threshold(reg: FileModelRegistry) -> None:
    v = reg.save(b"x", card(metrics={"skill": 0.49}, threshold={"skill": 0.5}))
    with pytest.raises(PromotionRefused):
        reg.promote(v, approver="alice", approved=True)
    assert reg.promoted_version() is None


def test_promote_refused_when_metric_missing(reg: FileModelRegistry) -> None:
    v = reg.save(b"x", card(metrics={"other": 1.0}, threshold={"skill": 0.5}))
    with pytest.raises(PromotionRefused):
        reg.promote(v, approver="alice", approved=True)


def test_promote_at_threshold_ok(reg: FileModelRegistry) -> None:
    v = reg.save(b"x", card(metrics={"skill": 0.5}, threshold={"skill": 0.5}))
    c = reg.promote(v, approver="alice", approved=True)
    assert c["status"] == "promoted"
    assert c["approved_by"] == "alice"
    assert c["promoted_utc"].endswith("Z")
    assert reg.promoted_version() == v
    assert reg.load(v)[1]["status"] == "promoted"


def test_promote_twice_is_refused(reg: FileModelRegistry) -> None:
    v = reg.save(b"x", card())
    reg.promote(v, approver="alice", approved=True)
    with pytest.raises(PromotionRefused):
        reg.promote(v, approver="alice", approved=True)


def test_rollback_to_previous_promoted(reg: FileModelRegistry) -> None:
    v1 = reg.save(b"1", card())
    v2 = reg.save(b"2", card())
    reg.promote(v1, approver="a", approved=True)
    reg.promote(v2, approver="a", approved=True)
    assert reg.promoted_version() == v2
    assert reg.rollback(approver="a") == v1
    assert reg.promoted_version() == v1
    assert reg.load(v2)[1]["status"] == "rolled_back"
    assert reg.load(v1)[1]["status"] == "promoted"
    with pytest.raises(PromotionRefused):
        reg.rollback(approver="a")  # nessuna versione precedente
    assert reg.promoted_version() == v1


def test_rollback_requires_valid_approver_and_history(reg: FileModelRegistry) -> None:
    with pytest.raises(PromotionRefused):
        reg.rollback(approver="a")
    v1 = reg.save(b"1", card())
    v2 = reg.save(b"2", card())
    reg.promote(v1, approver="a", approved=True)
    reg.promote(v2, approver="a", approved=True)
    with pytest.raises(PromotionRefused):
        reg.rollback(approver="")
    assert reg.promoted_version() == v2


def test_rolled_back_version_cannot_be_repromoted(reg: FileModelRegistry) -> None:
    v1 = reg.save(b"1", card())
    v2 = reg.save(b"2", card())
    reg.promote(v1, approver="a", approved=True)
    reg.promote(v2, approver="a", approved=True)
    reg.rollback(approver="a")
    with pytest.raises(PromotionRefused):
        reg.promote(v2, approver="a", approved=True)


def test_state_persists_across_instances(tmp_path: Path) -> None:
    r1 = FileModelRegistry(tmp_path / "m")
    v = r1.save(b"x", card())
    r1.promote(v, approver="a", approved=True)
    assert FileModelRegistry(tmp_path / "m").promoted_version() == v


def test_corrupted_model_refused(reg: FileModelRegistry, tmp_path: Path) -> None:
    v = reg.save(b"good-bytes", card())
    (tmp_path / "models" / v / "model.bin").write_bytes(b"evil-bytes")
    with pytest.raises(ModelIntegrityError):
        reg.load(v)
    with pytest.raises(ModelIntegrityError):
        reg.promote(v, approver="a", approved=True)


def test_tampered_card_version_mismatch_refused(reg: FileModelRegistry, tmp_path: Path) -> None:
    v = reg.save(b"x", card())
    p = tmp_path / "models" / v / "model_card.json"
    data = json.loads(p.read_text())
    data["version"] = "v0099"
    p.write_text(json.dumps(data))
    with pytest.raises(ModelIntegrityError):
        reg.load(v)


def test_malformed_card_refused(reg: FileModelRegistry, tmp_path: Path) -> None:
    v = reg.save(b"x", card())
    (tmp_path / "models" / v / "model_card.json").write_text("{not json")
    with pytest.raises(ModelIntegrityError):
        reg.load(v)


def test_symlinked_model_refused(reg: FileModelRegistry, tmp_path: Path) -> None:
    v = reg.save(b"x", card())
    target = tmp_path / "secret.bin"
    target.write_bytes(b"x")
    m = tmp_path / "models" / v / "model.bin"
    m.unlink()
    m.symlink_to(target)
    with pytest.raises(ModelIntegrityError):
        reg.load(v)


@pytest.mark.parametrize(
    "bad",
    [
        "../x",
        "..",
        ".",
        "v0001/../v0001",
        "/etc/passwd",
        "v0001\x00",
        "V0001",
        "v1",
        "v00000000001",
        "v0001 ",
        "",
        "v0001/model.bin",
        "..\\v0001",
    ],
)
def test_traversal_and_bad_ids_refused(reg: FileModelRegistry, bad: str) -> None:
    reg.save(b"x", card())
    with pytest.raises(InvalidVersion):
        reg.load(bad)
    with pytest.raises(InvalidVersion):
        reg.promote(bad, approver="a", approved=True)


def test_unknown_version_not_found(reg: FileModelRegistry) -> None:
    with pytest.raises(ModelNotFound):
        reg.load("v0042")


def test_list_skips_broken_entries(reg: FileModelRegistry, tmp_path: Path) -> None:
    reg.save(b"x", card())
    (tmp_path / "models" / "garbage").mkdir()
    (tmp_path / "models" / "v0002").mkdir()  # senza card
    assert [c["version"] for c in reg.list_versions()] == ["v0001"]
