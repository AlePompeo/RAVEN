# SPDX-License-Identifier: Apache-2.0
"""Regola di stato del link per lo snapshot a istante singolo."""

import pytest

pytest.importorskip("numpy")

from backend.domain.grazing.snapshot import link_state


@pytest.mark.parametrize(
    ("margin", "geo", "state"),
    [
        (5.0, True, "open"),
        (0.0, True, "open"),
        (3.0, False, "transition"),
        (-0.1, True, "blocked"),
        (-9.0, False, "blocked"),
    ],
)
def test_link_state(margin: float, geo: bool, state: str) -> None:
    assert link_state(margin, geo) == state
