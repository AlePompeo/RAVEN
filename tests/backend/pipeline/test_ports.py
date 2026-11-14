# SPDX-License-Identifier: Apache-2.0
import subprocess
import sys
from pathlib import Path

from backend.core.ports import (
    IngestSource,
    Processor,
    QueryEngine,
    Queue,
    Scheduler,
    Store,
)

ROOT = Path(__file__).resolve().parents[3]


def test_ports_are_runtime_protocols() -> None:
    for proto in (IngestSource, Queue, Processor, Store, QueryEngine, Scheduler):
        assert getattr(proto, "_is_runtime_protocol", False), proto


def test_structural_conformance() -> None:
    class Src:
        source_id = "s"

        def read(self):  # type: ignore[no-untyped-def]
            raise NotImplementedError

    class Proc:
        def process(self, message):  # type: ignore[no-untyped-def]
            return []

    assert isinstance(Src(), IngestSource)
    assert isinstance(Proc(), Processor)
    assert not isinstance(object(), Queue)


def test_core_and_app_import_without_data_libraries() -> None:
    code = (
        "import sys\n"
        "for m in ('pyarrow','duckdb','polars','pandas','astropy'):\n"
        "    sys.modules[m] = None\n"  # import -> ImportError
        "from backend.bootstrap import build_app\n"
        "import backend.api.pipeline_routes\n"
        "app = build_app()\n"
        "import backend.core.ports\n"
        "print('ok')\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "ok"
