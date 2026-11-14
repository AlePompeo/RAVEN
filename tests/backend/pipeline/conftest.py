# SPDX-License-Identifier: Apache-2.0
"""Senza gli extra [data] (pyarrow, duckdb) i test della pipeline su Parquet/DuckDB non si raccolgono:
si saltano invece di fallire in collezione. Con gli extra installati (CI) girano tutti."""

import importlib.util
import pathlib

_HAVE_DATA = all(importlib.util.find_spec(m) for m in ("pyarrow", "duckdb"))

# test che non importano pyarrow/duckdb nemmeno indirettamente
_ALWAYS = {
    "test_csv_commit_round2.py",
    "test_metrics_scheduler.py",
    "test_ports.py",
    "test_processors.py",
    "test_queues.py",
    "conftest.py",
    "__init__.py",
}

collect_ignore: list[str] = []
if not _HAVE_DATA:
    collect_ignore = [
        p.name for p in pathlib.Path(__file__).parent.glob("*.py") if p.name not in _ALWAYS
    ]
