# SPDX-License-Identifier: Apache-2.0
"""The mission brief of the automatic site search: its schema and a rule-based parser for Italian and English prompts.

Honesty rules: a field the text does not state stays None (never a default dressed up as an answer); a request the engine cannot treat
(water, ice) is listed in `unsupported` instead of becoming a variable; a mass is kept as a mass and is NOT mapped to a mission class
(the class masses of `economics.py` are launch masses). The parser is the first level of a cascade (rules, then a model); it needs no
network and costs no tokens. The user always confirms the brief before any calculation.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

SCHEMA_VERSION: Final = 1
Priority = Literal["sun", "earth", "radio", "balanced"]
MissionClass = Literal["rover", "small_lander", "medium_lander", "large_lander"]
MAX_PROMPT_CHARS: Final = 2000
MAX_SITES: Final = 10
POLAR_LAT_DEG: Final = -75.0  # the south-polar disc of the overlays


class MissionBrief(BaseModel):
    """What the user wants from the search. Every field is optional; None means "not stated"."""

    model_config = ConfigDict(extra="forbid")
    schema_version: int = SCHEMA_VERSION
    start_utc: str | None = None
    days: Annotated[float, Field(gt=0, le=366)] | None = None
    priority: Priority | None = None
    min_sun_percent: Annotated[float, Field(ge=0, le=100)] | None = None
    min_rf_percent: Annotated[float, Field(ge=0, le=100)] | None = None
    rate_bps: Annotated[float, Field(ge=1e4, le=3e6)] | None = None
    mission_class: MissionClass | None = None
    mass_kg: Annotated[float, Field(gt=0, le=1e6)] | None = None
    k: Annotated[int, Field(ge=1, le=MAX_SITES)] | None = None
    lat_max_deg: Annotated[float, Field(ge=-90, le=90)] | None = (
        None  # sites at or south of this latitude
    )
    lat_min_deg: Annotated[float, Field(ge=-90, le=90)] | None = None
    max_slope_deg: Annotated[float, Field(ge=0, le=45)] | None = (
        None  # a penalty, not an exclusion (regional slope)
    )
    min_distance_km: Annotated[float, Field(ge=0, le=5000)] | None = None
    reference_site: str | None = Field(default=None, max_length=40)


class ParsedBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")
    brief: MissionBrief
    found: list[str]  # the fields the rules filled
    unsupported: list[str]  # requests the engine cannot treat: water, ice...
    unresolved: list[
        str
    ]  # the fields a model or the user must still fill (the required ones that are None)
    rejected: list[str]  # values the text stated but that are out of range (never clipped silently)


# "give priority to ...": the noun (priorità a) and the verbs people use (privilegiando, favouring, prioritize, prefer)
_PREFER: Final = r"(?:priorit\w*|privilegi\w*|favor\w*|favour\w*|prefer\w*)"
REQUIRED: Final = ("start_utc", "days", "priority", "k")

_MONTHS = {
    "gennaio": 1,
    "january": 1,
    "febbraio": 2,
    "february": 2,
    "marzo": 3,
    "march": 3,
    "aprile": 4,
    "april": 4,
    "maggio": 5,
    "may": 5,
    "giugno": 6,
    "june": 6,
    "luglio": 7,
    "july": 7,
    "agosto": 8,
    "august": 8,
    "settembre": 9,
    "september": 9,
    "ottobre": 10,
    "october": 10,
    "novembre": 11,
    "november": 11,
    "dicembre": 12,
    "december": 12,
}
_NUM = r"(\d+(?:[.,]\d+)?)"
_SUN = r"(?:sole|sun(?:light)?|luce solare|illuminazione|illumination)"
_RF = r"(?:radio|link|collegamento|comunicazion\w*|communication\w*|downlink)"
_UNSUPPORTED = re.compile(
    r"\b(acqua|water|ghiaccio|ice|permafrost|volatili|volatiles?|minerali|minerals?)\b",
    re.IGNORECASE,
)


def _f(text: str) -> float:
    return float(text.replace(",", "."))


def _date(t: str) -> str | None:
    iso = re.search(r"\b(20\d\d)-(\d\d)-(\d\d)\b", t)
    if iso:
        y, m, d = (int(x) for x in iso.groups())
    else:
        named = re.search(
            r"(?:(\d{1,2})\s+(?:di\s+)?)?(" + "|".join(_MONTHS) + r")\s+(?:of\s+)?(20\d\d)\b",
            t,
            re.IGNORECASE,
        )
        if not named:
            return None
        d = int(named.group(1) or 1)
        m, y = _MONTHS[named.group(2).lower()], int(named.group(3))
    try:
        return datetime(y, m, d, tzinfo=UTC).strftime("%Y-%m-%dT00:00:00Z")
    except ValueError:
        return None


def parse_rules(text: str) -> ParsedBrief:
    """Fill what the text states in plain words; leave the rest None. Never raises on odd text (it returns an empty brief)."""
    t = " ".join(text[:MAX_PROMPT_CHARS].split())
    low = t.lower()
    data: dict[str, object] = {}

    if (start := _date(low)) is not None:
        data["start_utc"] = start
    if m := re.search(_NUM + r"\s*(giorn\w*|days?|d\b)", low):
        data["days"] = _f(m.group(1))
    elif m := re.search(
        r"\b(una|one|1|due|two|2|tre|three|3|quattro|four|4)\s+(settiman\w*|weeks?)", low
    ):
        words = {
            "una": 1,
            "one": 1,
            "1": 1,
            "due": 2,
            "two": 2,
            "2": 2,
            "tre": 3,
            "three": 3,
            "3": 3,
            "quattro": 4,
            "four": 4,
            "4": 4,
        }
        data["days"] = 7.0 * words[m.group(1)]
    elif m := re.search(r"\b(un|a|one)\s+mese\b|\bone month\b|\ba month\b", low):
        data["days"] = 30.0

    # percentages tied to a word: "almeno il 60% di sole", "sole almeno 60 %", "at least 60% sunlight"
    for field, word in (("min_sun_percent", _SUN), ("min_rf_percent", _RF)):
        m = re.search(
            _NUM + r"\s*%\s*(?:di\s+|of\s+|del\s+|dei\s+)?(?:\w+\s+)?" + word, low
        ) or re.search(word + r"\W+(?:\w+\W+){0,3}?" + _NUM + r"\s*%", low)
        if m:
            data[field] = _f(m.group(1))

    if m := re.search(_NUM + r"\s*(kbit/s|kbps|kb/s|mbit/s|mbps|mb/s|bit/s|bps)", low):
        v = _f(m.group(1)) * {"k": 1e3, "m": 1e6}.get(m.group(2)[0], 1.0)
        data["rate_bps"] = v
    if m := re.search(_NUM + r"\s*kg\b", low):
        data["mass_kg"] = _f(m.group(1))
    for cls, pattern in (
        ("rover", r"\brover\b"),
        ("small_lander", r"lander piccol\w*|small lander"),
        ("medium_lander", r"lander medi\w*|medium lander"),
        ("large_lander", r"lander grand\w*|large lander"),
    ):
        if re.search(pattern, low):
            data["mission_class"] = cls
            break

    if m := re.search(
        r"\b(?:dammi|trovami|trova|mostrami|elenca|give me|find|show|top)\s+(?:i\s+|gli\s+|the\s+)?(?:migliori\s+|best\s+)?(\d{1,2})\b",
        low,
    ) or re.search(r"\b(\d{1,2})\s+(?:siti|site|sites|luoghi|candidat\w*|candidates?)\b", low):
        data["k"] = min(int(m.group(1)), MAX_SITES) if int(m.group(1)) >= 1 else None
    if "k" in data and data["k"] is None:
        del data["k"]

    if re.search(
        rf"{_PREFER}\s*(?:the\s+|il\s+|lo\s+|la\s+|al\s+|alla\s+|a\s+)?(?:sole|sun)\b|massimizz\w*\s+(?:il\s+)?(?:sole|sun)|sun priority",
        low,
    ):
        data["priority"] = "sun"
    elif re.search(
        rf"{_PREFER}\s*(?:the\s+|la\s+|alla\s+|a\s+)?(?:terra|earth)\b|earth priority", low
    ):
        data["priority"] = "earth"
    elif re.search(
        rf"{_PREFER}\s*(?:the\s+|la\s+|alla\s+|a\s+)?(?:radio|comunicazion\w*|communication\w*|link)\b|radio priority",
        low,
    ):
        data["priority"] = "radio"
    elif re.search(r"\bbilanciat\w*|\bbalanced\b", low):
        data["priority"] = "balanced"

    if m := re.search(
        r"(?:lat\w*|latitude)\s*(?:inferiore a|minore di|sotto|below|south of|a sud di)\s*-?"
        + _NUM
        + r"",
        low,
    ):
        data["lat_max_deg"] = -abs(_f(m.group(1)))
    elif re.search(r"polo sud|south pole|polare|polar\b", low):
        data["lat_max_deg"] = POLAR_LAT_DEG
    if m := re.search(
        r"(?:pendenza|slope)\s*(?:massima|max\w*|al massimo|below|under|sotto|inferiore a)?\s*(?:di\s+)?"
        + _NUM
        + r"\s*(?:°|gradi|deg)",
        low,
    ):
        data["max_slope_deg"] = _f(m.group(1))
    if m := re.search(
        r"(?:distant\w*|lontan\w*|apart|separat\w*)[^.]{0,20}?"
        + _NUM
        + r"\s*km|"
        + _NUM
        + r"\s*km\s*(?:l'uno dall'altro|tra loro|apart)",
        low,
    ):
        data["min_distance_km"] = _f(next(g for g in m.groups() if g))

    unsupported = sorted({m.group(1).lower() for m in _UNSUPPORTED.finditer(low)})
    rejected: list[str] = []
    for key in list(data):
        try:
            MissionBrief.model_validate({key: data[key]})
        except ValidationError:
            rejected.append(key)
            del data[key]
    brief = MissionBrief.model_validate(data)
    found = [
        k
        for k in MissionBrief.model_fields
        if k != "schema_version" and getattr(brief, k) is not None
    ]
    unresolved = [k for k in REQUIRED if getattr(brief, k) is None]
    return ParsedBrief(
        brief=brief, found=found, unsupported=unsupported, unresolved=unresolved, rejected=rejected
    )
