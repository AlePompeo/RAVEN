# SPDX-License-Identifier: Apache-2.0
"""A site whose terrain tile is not cached is reported as unavailable; it must not turn the whole snapshot into a 503."""

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from backend.domain.grazing import snapshot as snap
from backend.domain.grazing.dem import DemUnavailable


def test_missing_tile_marks_only_that_site(monkeypatch: pytest.MonkeyPatch) -> None:
    geometry = SimpleNamespace(
        range_km=[384400.0], az_deg=[0.0], el_deg=[5.0], el_geocentric_deg=[5.0], parallax_deg=[0.9]
    )
    monkeypatch.setattr(snap, "earth_geometry", lambda *a, **k: geometry)

    def boom(**_: Any) -> Any:
        raise DemUnavailable("tile")

    monkeypatch.setattr(snap, "analyze", boom)
    site = SimpleNamespace(id="x", name="X", lat_deg=-86.0, lon_deg_east=10.0)
    out = snap._site_entry(
        site,  # type: ignore[arg-type]
        datetime(2027, 4, 7, tzinfo=UTC),
        SimpleNamespace(),  # type: ignore[arg-type]
        object(),
        object(),  # type: ignore[arg-type]
        False,
        object(),  # type: ignore[arg-type]
        85.0,
    )
    assert out["state"] == "unavailable"
    assert out["margin_db"] is None and out["ridge_el_deg"] is None
    assert out["dem_covered"] is True
