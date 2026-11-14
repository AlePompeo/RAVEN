# SPDX-License-Identifier: Apache-2.0
from datetime import UTC, datetime, timedelta, timezone

import pytest

from backend.ephemeris.timeutil import TimeError, parse_utc, utc_grid


def test_parse_ok() -> None:
    assert parse_utc("2027-03-03T03:03:03Z") == datetime(2027, 3, 3, 3, 3, 3, tzinfo=UTC)
    assert parse_utc("2027-03-03T03:03:03.5Z").microsecond == 500000
    assert parse_utc(datetime(2027, 1, 1, tzinfo=timezone(timedelta(0)))).tzinfo is UTC


@pytest.mark.parametrize(
    "bad",
    [
        "2027-03-03T03:03:03",
        "2027-03-03 03:03:03Z",
        "2027-03-03T03:03:03+00:00",
        "2027-03-03T03:03:03Z\n",
        "２０２７-03-03T03:03:03Z",  # cifre non ASCII
        "2027-02-30T00:00:00Z",
        "2027-03-03T24:00:00Z",
        "",
        "x" * 1000,
    ],
)
def test_parse_rejects(bad: str) -> None:
    with pytest.raises(TimeError):
        parse_utc(bad)


def test_parse_rejects_naive_and_offset() -> None:
    with pytest.raises(TimeError):
        parse_utc(datetime(2027, 1, 1))
    with pytest.raises(TimeError):
        parse_utc(datetime(2027, 1, 1, tzinfo=timezone(timedelta(hours=1))))


def test_grid() -> None:
    g = utc_grid("2027-01-01T00:00:00Z", "2027-01-01T01:00:00Z", 1800.0)
    assert len(g) == 3 and g[-1] == datetime(2027, 1, 1, 1, tzinfo=UTC)
    for args in (
        ("2027-01-02T00:00:00Z", "2027-01-01T00:00:00Z", 60.0),
        ("2027-01-01T00:00:00Z", "2027-01-02T00:00:00Z", 0.0),
    ):
        with pytest.raises(TimeError):
            utc_grid(*args)
    with pytest.raises(TimeError):
        utc_grid("2027-01-01T00:00:00Z", "2100-01-01T00:00:00Z", 0.001)
