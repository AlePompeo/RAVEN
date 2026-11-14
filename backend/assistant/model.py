# SPDX-License-Identifier: Apache-2.0
"""Modello dei documenti di conoscenza (front-matter YAML + corpo markdown)."""

from dataclasses import dataclass, field
from typing import Any

KINDS = ("concept", "formula", "method", "simulation", "page", "glossary", "problem", "decision")
LEVELS = ("principiante", "intermedio", "tecnico")
LANGS = ("it", "en")


@dataclass(frozen=True)
class Source:
    ref: str  # URL, percorso di repository o id di documento
    supports: str  # che cosa la fonte sostiene


@dataclass(frozen=True)
class Variable:
    symbol: str
    name: str
    unit: str
    range: str = ""


@dataclass(frozen=True)
class KnowledgeDoc:
    id: str
    title: str
    kind: str
    summary: str
    body: str = ""
    tags: tuple[str, ...] = ()
    sources: tuple[Source, ...] = ()
    applies_to: tuple[str, ...] = ()
    related: tuple[str, ...] = ()
    level: str = "intermedio"
    lang: str = "it"
    last_verified: str = ""
    origin: str = "manual"  # manual | manifest | contract
    path: str = ""
    # solo kind == formula
    expression: str = ""
    variables: tuple[Variable, ...] = ()
    assumptions: tuple[str, ...] = ()
    limits: tuple[str, ...] = ()
    worked_example: dict[str, Any] = field(default_factory=dict)
    derivation: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "kind": self.kind,
            "summary": self.summary,
            "tags": list(self.tags),
            "applies_to": list(self.applies_to),
            "related": list(self.related),
            "level": self.level,
            "lang": self.lang,
            "last_verified": self.last_verified,
            "origin": self.origin,
            "sources": [{"ref": s.ref, "supports": s.supports} for s in self.sources],
            "body": self.body,
        }
        if self.kind == "formula":
            d.update(
                expression=self.expression,
                variables=[
                    {"symbol": v.symbol, "name": v.name, "unit": v.unit, "range": v.range}
                    for v in self.variables
                ],
                assumptions=list(self.assumptions),
                limits=list(self.limits),
                worked_example=self.worked_example,
                derivation=list(self.derivation),
            )
        return d
