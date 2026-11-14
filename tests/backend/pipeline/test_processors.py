# SPDX-License-Identifier: Apache-2.0
import math
from datetime import UTC, datetime
from typing import Any

import pytest

from backend.core.ports import Processor
from backend.pipeline.processors import (
    Deduplicator,
    RecordRejected,
    TelemetryProcessor,
    parse_reason,
)

NOW = datetime(2026, 10, 13, 12, 0, 5, tzinfo=UTC)


def msg(record: dict[str, Any], source: str = "csv-a", **extra: Any) -> dict[str, Any]:
    return {"source_id": source, "received_utc": "2026-10-13T12:00:01Z", "record": record, **extra}


def rec(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "schema_version": "1.0.0",
        "t_utc": "2026-10-13T10:00:00Z",
        "site_id": "shackleton",
        "power_w": 120.5,
    }
    base.update(kw)
    return base


@pytest.fixture
def proc() -> TelemetryProcessor:
    return TelemetryProcessor(now=lambda: NOW)


def reject(proc: TelemetryProcessor, message: Any) -> str:
    with pytest.raises(RecordRejected) as e:
        proc.process(message)
    reason = e.value.reason
    code, field = parse_reason(reason)  # sempre leggibile da macchina
    assert code and (field is None or field)
    return str(reason)


def test_conforms_to_port(proc: TelemetryProcessor) -> None:
    assert isinstance(proc, Processor)


def test_valid_record_becomes_flat_clean_row(proc: TelemetryProcessor) -> None:
    (row,) = proc.process(
        msg(
            rec(
                link_margin_db=3.5,
                sun={"az_deg": 10.0, "el_deg": 20.0},
                earth={"az_deg": 1.0, "el_deg": 2.0},
            )
        )
    )
    assert row["source_id"] == "csv-a" and row["site_id"] == "shackleton"
    assert row["t_utc"] == datetime(2026, 10, 13, 10, 0, tzinfo=UTC)
    assert row["t_utc"].tzinfo is UTC
    assert row["received_utc"] == datetime(2026, 10, 13, 12, 0, 1, tzinfo=UTC)
    assert row["power_w"] == 120.5 and row["link_margin_db"] == 3.5
    assert (row["sun_az_deg"], row["sun_el_deg"]) == (10.0, 20.0)
    assert (row["earth_az_deg"], row["earth_el_deg"]) == (1.0, 2.0)
    assert row["schema_version"] == "1.0.0"


def test_optional_fields_are_none(proc: TelemetryProcessor) -> None:
    (row,) = proc.process(msg(rec()))
    assert row["link_margin_db"] is None and row["sun_az_deg"] is None


def test_timestamp_with_offset_normalised_to_utc(proc: TelemetryProcessor) -> None:
    (row,) = proc.process(msg(rec(t_utc="2026-10-13T12:00:00+02:00")))
    assert row["t_utc"] == datetime(2026, 10, 13, 10, 0, tzinfo=UTC)


def test_epoch_seconds_timestamp_accepted(proc: TelemetryProcessor) -> None:
    (row,) = proc.process(msg(rec(t_utc=1_792_058_400)))
    assert row["t_utc"] == datetime.fromtimestamp(1_792_058_400, UTC)


def test_missing_received_utc_uses_clock(proc: TelemetryProcessor) -> None:
    m = msg(rec())
    del m["received_utc"]
    (row,) = proc.process(m)
    assert row["received_utc"] == NOW


def test_unit_aliases_normalised(proc: TelemetryProcessor) -> None:
    r = rec(sun={"az_rad": math.pi, "el_rad": math.pi / 2})
    del r["power_w"]
    r["power_kw"] = 1.5
    (row,) = proc.process(msg(r))
    assert row["power_w"] == pytest.approx(1500.0)
    assert row["sun_az_deg"] == pytest.approx(180.0)
    assert row["sun_el_deg"] == pytest.approx(90.0)


def test_conflicting_units_rejected(proc: TelemetryProcessor) -> None:
    assert reject(proc, msg(rec(power_kw=1.0))).startswith("conflicting_units")


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_non_finite_rejected(proc: TelemetryProcessor, bad: float) -> None:
    assert reject(proc, msg(rec(power_w=bad))).startswith("non_finite_value:power_w")
    assert reject(proc, msg(rec(sun={"az_deg": bad, "el_deg": 1.0}))).startswith("non_finite_value")
    assert reject(proc, msg(rec(power_w=None, power_kw=bad))).startswith("non_finite_value")


@pytest.mark.parametrize(
    ("record", "code"),
    [
        (rec(power_w="12"), "schema_violation"),
        (rec(power_w=True), "schema_violation"),
        (rec(power_w=None), "schema_violation"),
        (rec(site_id=""), "schema_violation"),
        (rec(schema_version="v1"), "schema_violation"),
        (rec(unknown_field=1), "unknown_field"),
        (rec(t_utc="not a time"), "invalid_timestamp"),
        (rec(t_utc="2026-10-13T10:00:00"), "naive_timestamp"),
        (rec(t_utc=None), "invalid_timestamp"),
        (rec(t_utc=float("nan")), "non_finite_value"),
        (rec(t_utc=10**30), "invalid_timestamp"),
        (rec(sun={"az_deg": 1.0}), "missing_field"),
        (rec(sun="x"), "schema_violation"),
    ],
)
def test_invalid_records_rejected_with_machine_readable_reason(
    proc: TelemetryProcessor, record: dict[str, Any], code: str
) -> None:
    assert reject(proc, msg(record)).split(":")[0] == code


def test_missing_required_field(proc: TelemetryProcessor) -> None:
    r = rec()
    del r["site_id"]
    assert reject(proc, msg(r)) == "missing_field:site_id"


@pytest.mark.parametrize("bad", [None, "str", 5, [], {"source_id": "a"}, {"record": {}}])
def test_malformed_messages(proc: TelemetryProcessor, bad: Any) -> None:
    reject(proc, bad)


def test_bad_source_id_and_record_type(proc: TelemetryProcessor) -> None:
    assert reject(proc, msg(rec(), source="../x")) == "invalid_source_id"
    assert reject(proc, msg(rec(), source="UPPER")) == "invalid_source_id"
    assert reject(proc, {"source_id": "a", "record": [1]}) == "not_an_object"
    assert reject(proc, msg(rec(), received_utc="zzz")) == "invalid_received_utc"


def test_reason_field_is_sanitised(proc: TelemetryProcessor) -> None:
    reason = reject(proc, msg(rec(**{"evil\n'; DROP": 1})))
    assert "\n" not in reason and "'" not in reason and ";" not in reason


def test_parse_reason_roundtrip() -> None:
    assert parse_reason("schema_violation:sun.az_deg") == ("schema_violation", "sun.az_deg")
    assert parse_reason("naive_timestamp") == ("naive_timestamp", None)


# ---- Deduplicator / partizioni ----


def row(source: str = "a", site: str = "s", t: str = "2026-10-13T10:00:00+00:00") -> dict[str, Any]:
    return {"source_id": source, "site_id": site, "t_utc": datetime.fromisoformat(t)}


def test_same_record_twice_is_duplicate() -> None:
    d = Deduplicator()
    assert d.admit(row()).is_new
    assert not d.admit(row()).is_new
    assert d.admit(row(site="other")).is_new
    assert d.admit(row(source="b")).is_new
    assert d.admit(row(t="2026-10-13T10:00:01+00:00")).is_new


def test_out_of_order_is_flagged_per_partition_not_across() -> None:
    d = Deduplicator()
    assert not d.admit(row(t="2026-10-13T10:00:10+00:00")).out_of_order
    late = d.admit(row(t="2026-10-13T10:00:05+00:00"))
    assert late.is_new and late.out_of_order  # accettato, solo segnalato
    assert not d.admit(row(source="b", t="2026-10-13T09:00:00+00:00")).out_of_order
    # un altro giorno e' un'altra partizione: il suo watermark non tocca quello di ieri
    assert not d.admit(row(t="2026-10-14T00:00:01+00:00")).out_of_order
    assert d.admit(row(t="2026-10-13T10:00:09+00:00", site="q")).out_of_order
    assert not d.admit(row(t="2026-10-13T23:59:59+00:00", site="z")).out_of_order


def test_partition_keys_loaded_from_store_on_first_touch() -> None:
    calls: list[tuple[str, str]] = []

    def loader(source: str, day: str) -> set[tuple[str, datetime]]:
        calls.append((source, day))
        return {("s", datetime.fromisoformat("2026-10-13T10:00:00+00:00"))}

    d = Deduplicator(loader=loader)
    assert not d.admit(row()).is_new  # gia' presente su disco (riavvio)
    assert d.admit(row(t="2026-10-13T10:00:02+00:00")).is_new
    assert calls == [("a", "2026-10-13")]


def test_lru_eviction_reloads_partition() -> None:
    loads = 0

    def loader(source: str, day: str) -> set[tuple[str, datetime]]:
        nonlocal loads
        loads += 1
        return set()

    d = Deduplicator(loader=loader, max_partitions=1)
    for r in (row(source="a"), row(source="b"), row(source="a", t="2026-10-13T10:00:03+00:00")):
        d.admit(r)
        d.commit(r)  # durevole: la partizione non e' piu' bloccata e puo' essere espulsa
    assert loads == 3
