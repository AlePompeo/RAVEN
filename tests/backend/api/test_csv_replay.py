# SPDX-License-Identifier: Apache-2.0
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from backend.api.routes import TelemetryHub, csv_replay

ROOT = Path(__file__).parents[3]
SCHEMA = json.loads((ROOT / "contracts/telemetry.schema.json").read_text())
FIXTURE = ROOT / "contracts/examples/telemetry.sample.json"


def _validate(sample: Any) -> None:
    jsonschema.Draft202012Validator(SCHEMA, format_checker=jsonschema.FormatChecker()).validate(
        sample
    )


async def _replay(
    tmp_path: Path, text: str, **kw: Any
) -> tuple[list[dict[str, Any]], TelemetryHub]:
    f = tmp_path / "t.csv"
    f.write_text(text)
    hub = TelemetryHub()
    q = hub.subscribe()
    await csv_replay(hub, f, interval_s=0, loop=False, **kw)
    return [q.get_nowait() for _ in range(q.qsize())], hub


def test_shared_fixture_is_valid() -> None:
    _validate(json.loads(FIXTURE.read_text()))


async def test_full_columns_pass_through_and_validate(tmp_path: Path) -> None:
    csv = (
        "t_utc,site_id,power_w,link_margin_db,sun_az_deg,sun_el_deg,earth_az_deg,earth_el_deg\n"
        "2026-10-12T12:00:00Z,shackleton,12.5,6.2,120.5,35,250,5.5\n"
    )
    got, hub = await _replay(tmp_path, csv)
    assert len(got) == 1
    _validate(got[0])
    assert got[0]["t_utc"] == "2026-10-12T12:00:00Z" and got[0]["site_id"] == "shackleton"
    assert got[0]["sun"] == {"az_deg": 120.5, "el_deg": 35.0}
    assert got[0]["earth"] == {"az_deg": 250.0, "el_deg": 5.5}
    assert got[0]["schema_version"] == "1.0.0"
    assert hub.invalid_rows == 0


async def test_missing_time_and_site_are_synthesised(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv("TELEMETRY_SITE_ID", "site-x")
    now = datetime(2026, 10, 12, 8, 30, tzinfo=UTC)
    got, _ = await _replay(tmp_path, "power_w\n1.5\n2.5\n", now=lambda: now)
    assert len(got) == 2
    for g in got:
        _validate(g)
        assert g["t_utc"] == "2026-10-12T08:30:00Z" and g["site_id"] == "site-x"


async def test_default_site_is_demo(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.delenv("TELEMETRY_SITE_ID", raising=False)
    got, _ = await _replay(tmp_path, "power_w\n1\n")
    assert got[0]["site_id"] == "demo"
    _validate(got[0])


@pytest.mark.parametrize(
    "row",
    [
        "2026-10-12T12:00:00Z,nan",
        "2026-10-12T12:00:00Z,inf",
        "2026-10-12T12:00:00Z,abc",
        "not-a-date,1.0",
        "2026-10-12,1.0",
        "2026-10-12T12:00:00,1.0",  # senza fuso orario
        "1234567890,1.0",
        ",1.0",
    ],
)
async def test_invalid_rows_are_dropped_and_counted(tmp_path: Path, row: str) -> None:
    good = "2026-10-12T12:00:00Z,2.0"
    got, hub = await _replay(tmp_path, f"t_utc,power_w\n{row}\n{good}\n")
    assert [g["power_w"] for g in got] == [2.0]
    assert hub.invalid_rows == 1


async def test_nan_in_nested_and_unknown_column_dropped(tmp_path: Path) -> None:
    csv = "power_w,sun_az_deg,sun_el_deg\n1,nan,3\n1,4,5\n2,4,\n"
    got, hub = await _replay(tmp_path, csv)
    assert len(got) == 1 and got[0]["sun"] == {"az_deg": 4.0, "el_deg": 5.0}
    assert hub.invalid_rows == 2
    got2, hub2 = await _replay(tmp_path, "power_w,temp_c\n1,20\n")  # colonna fuori contratto
    assert got2 == [] and hub2.invalid_rows == 1


async def test_incomplete_nested_pair_dropped(tmp_path: Path) -> None:
    got, hub = await _replay(tmp_path, "power_w,sun_az_deg\n1,4\n")
    assert got == [] and hub.invalid_rows == 1
