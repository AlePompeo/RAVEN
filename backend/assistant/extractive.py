# SPDX-License-Identifier: Apache-2.0
"""Composizione ESTRATTIVA della risposta: deterministica, senza rete, senza chiavi.

Legge i blocchi di contesto dal prompt (stesso input di un LLM) e assembla la risposta con
frasi e schede-formula copiate dal materiale, ciascuna con la citazione [id]. Non inventa nulla:
ogni numero o simbolo proviene dal contesto.
"""

import re
from collections.abc import AsyncIterator, Mapping, Sequence

from backend.assistant.prompt import (
    REFUSAL_EN,
    REFUSAL_IT,
    ContextDoc,
    parse_context,
    parse_header,
)
from backend.assistant.text import tokens

_LINK = re.compile(r"\[([^\]]+)\]\(kb:[^)]+\)")
_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-Ý0-9`*(])")
_N_BY_LEVEL = {"principiante": 2, "intermedio": 3, "tecnico": 5}
_LABELS = {
    "it": ("Dal materiale del sito:", "Fonti nel sito:"),
    "en": ("From the site's material (written in Italian):", "Sources on the site:"),
}


_BULLET = re.compile(r"^(?:[-*|]|\d+[.)])\s?")


def _units(text: str) -> list[str]:
    """Unita' di testo: voci di elenco/righe di tabella intere, frasi dei paragrafi (righe unite)."""
    out: list[str] = []
    para: list[str] = []
    in_code = False

    def close() -> None:
        if para:
            joined = " ".join(para)
            out.extend(p.strip() for p in _SENT.split(joined) if p.strip())
            para.clear()

    for line in text.splitlines():
        s = line.strip()
        if s.startswith("```"):
            in_code = not in_code
            close()
            continue
        if not s or in_code:
            close()
            continue
        if set(s) <= set("|-: "):
            continue
        s = _LINK.sub(r"\1", s)
        if _BULLET.match(s):
            close()
            out.append(s)
        else:
            para.append(s)
    close()
    return out


def _pick(units: list[str], q: set[str], n: int, *, lead: bool = False) -> list[str]:
    """Frasi piu' pertinenti (ordine originale); elenchi/tabelle: voci intere fino a 12."""
    if not units:
        return []
    listy = sum(bool(_BULLET.match(u)) for u in units) >= 0.6 * len(units)
    if listy:
        return units[:12]
    scored = [(len(q & set(tokens(u))), i) for i, u in enumerate(units)]
    best = sorted((x for x in scored if x[0] > 0), key=lambda x: (-x[0], x[1]))[:n]
    idx = {i for _, i in best} or set(range(min(n, len(units))))
    if lead:
        idx.add(0)  # la prima frase di una scheda e' la definizione
    return [units[i] for i in sorted(idx)]


def _group(docs: Sequence[ContextDoc]) -> list[tuple[ContextDoc, list[ContextDoc]]]:
    order: list[str] = []
    by: dict[str, list[ContextDoc]] = {}
    for d in docs:
        if d.id not in by:
            order.append(d.id)
            by[d.id] = []
        by[d.id].append(d)
    return [(by[i][0], sorted(by[i], key=lambda c: c.anchor != "")) for i in order]


def compose(messages: Sequence[Mapping[str, str]]) -> str:
    system = next((m["content"] for m in messages if m["role"] == "system"), "")
    question = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    head = parse_header(system)
    lang = "en" if head.get("LANG") == "en" else "it"
    level = head.get("LEVEL", "intermedio")
    docs = parse_context(system)
    if not docs:
        return REFUSAL_EN if lang == "en" else REFUSAL_IT
    q = set(tokens(question))
    n = _N_BY_LEVEL.get(level, 3)
    intro, _ = _LABELS[lang]
    parts = [intro]
    for rank, (first, chunks) in enumerate(_group(docs)[:3]):
        parts.append(f"\n**{first.title}** [{first.id}]")
        budget = n if rank == 0 else max(1, n - 1)
        for c in chunks:
            if re.search(r"^Formula:", c.text, re.MULTILINE):
                head_txt, _, card = c.text.partition("Formula:")
                if head_txt.strip():
                    parts.append(head_txt.strip())
                parts.append("Formula:" + card.rstrip() + f" [{c.id}]")
            else:
                picked = _pick(_units(c.text), q, budget, lead=not c.anchor)
                if picked:
                    parts.append(
                        " ".join(picked)
                        if not any(p.startswith("-") for p in picked)
                        else "\n".join(picked)
                    )
                    parts[-1] += f" [{c.id}]"
    return "\n".join(parts).strip()


async def stream_text(text: str) -> AsyncIterator[str]:
    for piece in re.findall(r"\S+\s*|\s+", text):
        yield piece
