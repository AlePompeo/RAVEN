# SPDX-License-Identifier: Apache-2.0
"""Identity of the RAVEN model: version, stage order, registry hash (numpy-free, for the API)."""

import hashlib
from typing import Final

from backend.domain.raven.export import params_json

__all__ = ["MODEL_VERSION", "STAGE_ORDER", "registry_sha256"]

MODEL_VERSION: Final = "raven-core-1.4"
# (stage, what it reads): each stage reads only stages that come before it in this list.
STAGE_ORDER: Final[tuple[tuple[str, tuple[str, ...]], ...]] = (
    ("s0", ()),
    ("s1", ("s0",)),
    ("s2", ("s0", "s1")),
    ("s3", ("s1", "s2")),
    ("s5", ("s1", "s2")),
    ("s6", ("s1",)),
    ("s4", ("s3", "s5", "s6")),
    ("s7", ("s4", "s5", "s6")),
)


def registry_sha256() -> str:
    """Hash of the exported registry: a pre-computed demo is tied to the parameters that made it."""
    return hashlib.sha256(params_json().encode("utf-8")).hexdigest()
