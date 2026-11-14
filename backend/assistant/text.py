# SPDX-License-Identifier: Apache-2.0
"""Tokenizzazione italiano/inglese senza dipendenze: accenti, stemming leggero, sinonimi IT<->EN."""

import re
import unicodedata

_STOP_IT = [
    "il",
    "lo",
    "la",
    "i",
    "gli",
    "le",
    "un",
    "uno",
    "una",
    "di",
    "a",
    "da",
    "in",
    "con",
    "su",
    "per",
    "tra",
    "fra",
    "e",
    "ed",
    "o",
    "ma",
    "che",
    "chi",
    "cui",
    "non",
    "sono",
    "come",
    "cosa",
    "cos",
    "quale",
    "quali",
    "quando",
    "dove",
    "perche",
    "del",
    "dello",
    "della",
    "dei",
    "degli",
    "delle",
    "al",
    "allo",
    "alla",
    "ai",
    "agli",
    "alle",
    "dal",
    "dallo",
    "dalla",
    "dai",
    "dalle",
    "nel",
    "nello",
    "nella",
    "nei",
    "negli",
    "nelle",
    "sul",
    "sullo",
    "sulla",
    "sui",
    "sugli",
    "sulle",
    "si",
    "mi",
    "ti",
    "ci",
    "vi",
    "ne",
    "questo",
    "questa",
    "questi",
    "queste",
    "quello",
    "quella",
    "puoi",
    "puo",
    "fare",
    "fa",
    "fai",
    "piu",
    "molto",
    "anche",
    "se",
    "io",
    "tu",
    "noi",
    "voi",
    "loro",
    "mio",
    "mia",
    "suo",
    "sua",
    "ha",
    "hanno",
    "essere",
    "stato",
    "spiega",
    "spiegami",
    "spiegare",
    "dimmi",
    "dammi",
    "vorrei",
    "voglio",
    "sapere",
    "dire",
    "mostra",
    "mostrami",
    "parlami",
    "posso",
    "possibile",
    "sezione",
    "c",
    "e",
]
_STOP_EN = [
    "the",
    "a",
    "an",
    "of",
    "to",
    "in",
    "on",
    "for",
    "and",
    "or",
    "but",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "what",
    "which",
    "who",
    "how",
    "why",
    "when",
    "where",
    "does",
    "do",
    "did",
    "can",
    "could",
    "would",
    "should",
    "with",
    "from",
    "by",
    "as",
    "at",
    "it",
    "its",
    "this",
    "that",
    "these",
    "those",
    "i",
    "you",
    "we",
    "they",
    "me",
    "my",
    "your",
    "please",
    "explain",
    "tell",
    "about",
    "give",
    "show",
    "s",
]
STOPWORDS = frozenset(_STOP_IT + _STOP_EN)

_PRE = (
    (re.compile(r"\bg\s*/\s*t\b"), "gt"),
    (re.compile(r"\beb\s*/\s*n0\b"), "ebn0"),
    (re.compile(r"\bc\s*/\s*n0\b"), "cn0"),
    (re.compile(r"\bes\s*/\s*n0\b"), "esn0"),
    (re.compile(r"\bn\s*/\s*0\b"), "n0"),
)
_TOKEN = re.compile(r"[a-z0-9]+")
_SUFFIXES = (
    "amenti", "amento", "mente", "zioni", "zione", "ioni", "ione", "ando", "endo", "ing",
    "are", "ere", "ire", "ato", "ata", "ati", "ate", "ano", "ono", "ers", "er", "ed", "es",
)  # fmt: skip

_SYNONYM_GROUPS = (
    ("distanza", "distance"),
    ("frequenza", "frequency"),
    ("perdita", "loss", "attenuazione", "attenuation"),
    ("azimut", "azimuth"),
    ("elevazione", "elevation"),
    ("margine", "margin"),
    ("guadagno", "gain"),
    ("potenza", "power"),
    ("formula", "equazione", "equation"),
    ("simulazione", "simulation"),
    ("controllore", "controller", "regolatore"),
    ("errore", "error"),
    ("segnale", "signal"),
    ("rumore", "noise"),
    ("pacchetto", "packet"),
    ("intestazione", "header"),
    ("sensore", "sensor"),
    ("assetto", "attitude", "orientamento", "orientation"),
    ("giroscopio", "gyroscope", "gyro"),
    ("accelerometro", "accelerometer"),
    ("magnetometro", "magnetometer"),
    ("modello", "model"),
    ("addestramento", "training"),
    ("promozione", "promotion", "promuovere", "promote"),
    ("telemetria", "telemetry"),
    ("unita", "unit", "units"),
    ("calcolo", "calcolare", "calcola", "calculate", "compute", "computed"),
    ("tempo", "time"),
    ("velocita", "speed", "velocity"),
    ("sole", "sun"),
    ("terra", "earth"),
    ("luna", "moon"),
    ("esempio", "example"),
    ("limite", "limit", "limitazione", "limitation"),
    ("ipotesi", "assumption", "assunzione"),
    ("avviare", "avvio", "start", "lanciare", "eseguire", "run"),
    ("consegna", "delivery"),
    ("duplicato", "duplicate", "dedup", "deduplicazione"),
    ("variabile", "variable"),
    ("passo", "step"),
    ("sito", "site"),
    ("rete", "network"),
    ("linea", "line"),
    ("collegamento", "link"),
    ("dimostrazione", "demo"),
    ("orizzonte", "horizon"),
    ("cielo", "sky"),
    ("sistema", "system"),
    ("piattaforma", "platform"),
    ("scopo", "purpose", "obiettivo", "goal"),
    ("problema", "problem"),
    ("soluzione", "solution"),
    ("spazio", "space"),
    ("angolo", "angle"),
    ("significato", "significa", "mean", "meaning", "means"),
    ("apprendimento", "learning"),
    ("rinforzo", "reinforcement"),
    ("chiave", "key"),
    ("parametro", "parameter", "ingresso", "input"),
    ("libero", "free"),
)


def fold(s: str) -> str:
    """Minuscolo e senza accenti (NFKD)."""
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def stem(t: str) -> str:
    if len(t) <= 4 or t.isdigit():
        return t
    if t.endswith("ies") and len(t) > 5:
        return t[:-3] + "y"
    for suf in _SUFFIXES:
        if t.endswith(suf) and len(t) - len(suf) >= 3:
            t = t[: -len(suf)]
            break
    if len(t) >= 5 and t[-1] in "iaeo" or (len(t) >= 5 and t[-1] == "s" and t[-2] != "s"):
        t = t[:-1]
    return t


_CANON: dict[str, str] = {}
for _g in _SYNONYM_GROUPS:
    _head = stem(fold(_g[0]))
    for _w in _g:
        _CANON[stem(fold(_w))] = _head


def tokens(text: str, *, keep_stop: bool = False) -> list[str]:
    """Token normalizzati (accenti, stem, sinonimi); le stopword si scartano di default."""
    s = fold(text)
    for rx, rep in _PRE:
        s = rx.sub(rep, s)
    out: list[str] = []
    for raw in _TOKEN.findall(s):
        if not keep_stop and raw in STOPWORDS:
            continue
        if len(raw) == 1 and not raw.isdigit():
            continue
        st = stem(raw)
        out.append(_CANON.get(st, st))
    return out


_EN_HINT = frozenset(
    [
        "the",
        "what",
        "how",
        "is",
        "are",
        "does",
        "do",
        "why",
        "which",
        "explain",
        "this",
        "of",
        "and",
        "with",
        "for",
        "can",
    ]
)
_IT_HINT = frozenset(
    [
        "il",
        "lo",
        "la",
        "che",
        "come",
        "cosa",
        "perche",
        "quale",
        "quali",
        "sono",
        "spiega",
        "della",
        "dei",
        "per",
        "con",
        "una",
        "un",
        "non",
    ]
)


def detect_lang(text: str, default: str = "it") -> str:
    """Euristica a stopword: 'en' solo se le parole inglesi prevalgono chiaramente."""
    words = _TOKEN.findall(fold(text))
    en = sum(w in _EN_HINT for w in words)
    it = sum(w in _IT_HINT for w in words)
    if en > it:
        return "en"
    if it > en:
        return "it"
    return default
