# SPDX-License-Identifier: Apache-2.0
"""Post-validazione delle risposte: citazioni [id] ammesse, numeri non ancorati al contesto."""

import re
from collections.abc import Iterable

from backend.assistant.prompt import (
    GENERAL_LABEL,
    REFUSAL_EN,
    REFUSAL_IT,
    SYSTEM_RULES,
    has_general_label,
    is_refusal,
)
from backend.assistant.text import fold

INVALID_MARK = "[fonte non valida]"
_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)+$")  # id "sospetto": minuscolo con almeno un trattino
_NUM = re.compile(r"(?<![\w.])-?\d+(?:[.,]\d+)?")
_MAX_PENDING = 90


def _norm(t: str) -> str:
    return " ".join(fold(t).split())


_RULES = _norm(SYSTEM_RULES)
for _allowed in (REFUSAL_IT, REFUSAL_EN, GENERAL_LABEL):
    _RULES = _RULES.replace(_norm(_allowed), "")
_WINDOWS = [_RULES[i : i + 40] for i in range(0, max(len(_RULES) - 40, 1), 20)]


def leaks_system_prompt(answer: str) -> bool:
    """True se la risposta ripete (anche in parte) le regole del system prompt."""
    n = _norm(answer)
    return any(w in n for w in _WINDOWS)


class CitationFilter:
    """Filtro in streaming: tiene in sospeso solo un eventuale '[...' non ancora chiuso.

    Una citazione `[id]` (o `[a, b]`) con id fuori dall'insieme recuperato viene sostituita con
    `[fonte non valida]` e registrata in `dropped`; le valide in `cited` (ordine di comparsa).
    Un gruppo tra parentesi quadre e' una citazione solo se ogni parte e' un id noto della base
    di conoscenza o ha la forma di un id (minuscolo con trattino, es. `ghost-doc`): `[out_min, out_max]`
    o `[0, 1000]` restano testo. Un id inventato senza trattino non viene rilevato (limite noto)."""

    def __init__(self, allowed: Iterable[str], known: Iterable[str] = ()) -> None:
        self.allowed = set(allowed)
        self.known = set(known) | self.allowed
        self.cited: list[str] = []
        self.dropped: list[str] = []
        self._buf = ""

    def _group(self, inner: str) -> str | None:
        parts = [p.strip() for p in re.split(r"[,;]", inner)]
        if not parts or not all(p in self.known or _ID.match(p) for p in parts):
            return None  # non e' una citazione: testo normale
        good = [p for p in parts if p in self.allowed]
        for p in parts:
            if p in self.allowed:
                if p not in self.cited:
                    self.cited.append(p)
            elif p not in self.dropped:
                self.dropped.append(p)
        if not good:
            return INVALID_MARK
        return (
            "".join(f"[{p}]" for p in good)
            if len(good) == len(parts)
            else " ".join(f"[{p}]" for p in good)
        )

    def feed(self, text: str) -> str:
        self._buf += text
        out: list[str] = []
        while True:
            i = self._buf.find("[")
            if i < 0:
                out.append(self._buf)
                self._buf = ""
                break
            out.append(self._buf[:i])
            rest = self._buf[i:]
            j = rest.find("]")
            if j < 0:
                if len(rest) > _MAX_PENDING:
                    out.append("[")
                    self._buf = rest[1:]
                    continue
                self._buf = rest
                break
            inner = rest[1:j]
            if "[" in inner:  # '[' annidata: la prima e' letterale
                out.append("[")
                self._buf = rest[1:]
                continue
            rep = self._group(inner)
            out.append(rep if rep is not None else rest[: j + 1])
            self._buf = rest[j + 1 :]
        return "".join(out)

    def flush(self) -> str:
        rest, self._buf = self._buf, ""
        return rest


def _numbers(text: str) -> set[str]:
    return {n.replace(",", ".").lstrip("-") for n in _NUM.findall(text)}


def check_answer(
    answer: str,
    *,
    cited: list[str],
    dropped: list[str],
    context_text: str,
    question_text: str,
    has_context: bool,
) -> list[str]:
    """Codici di avviso (lista vuota = nessun problema rilevato). Euristiche, non prove."""
    warnings: list[str] = []
    refusal = is_refusal(answer)
    if leaks_system_prompt(answer):
        warnings.append("possible_prompt_leak")
    if dropped:
        warnings.append("invalid_citation_dropped")
    if has_context and not cited and not refusal and not has_general_label(answer):
        warnings.append("no_citation")
    if not has_context and not refusal and not has_general_label(answer):
        warnings.append("no_context_unlabelled")
    body = re.sub(r"\[[^\[\]]{1,80}\]", " ", answer)
    known = _numbers(context_text) | _numbers(question_text)
    odd = sorted(n for n in _numbers(body) if n not in known and not (n.isdigit() and int(n) <= 10))
    if odd and not has_general_label(answer):
        warnings.append("numbers_not_in_context")
    return warnings
