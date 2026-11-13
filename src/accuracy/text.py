"""Reading numbers, money and units out of English and German answer text."""

from __future__ import annotations

import re
from dataclasses import dataclass

ABBREVIATIONS = ("ca.", "bzw.", "z. B.", "z.B.", "u. a.", "inkl.", "approx.", "e.g.", "i.e.", "vs.")

UNITS: dict[str, tuple[str, float]] = {
    # token -> (canonical unit, factor to canonical)
    "hours": ("h", 1),
    "hour": ("h", 1),
    "hrs": ("h", 1),
    "hr": ("h", 1),
    "h": ("h", 1),
    "stunden": ("h", 1),
    "stunde": ("h", 1),
    "std": ("h", 1),
    "months": ("month", 1),
    "month": ("month", 1),
    "monate": ("month", 1),
    "monaten": ("month", 1),
    "monat": ("month", 1),
    "years": ("month", 12),
    "year": ("month", 12),
    "yr": ("month", 12),
    "jahre": ("month", 12),
    "jahren": ("month", 12),
    "jahr": ("month", 12),
    "km": ("km", 1),
    "kilometers": ("km", 1),
    "kilometres": ("km", 1),
    "kilometer": ("km", 1),
    "kilometern": ("km", 1),
    "miles": ("km", 1.609344),
    "mile": ("km", 1.609344),
    "mi": ("km", 1.609344),
    "kg": ("kg", 1),
    "kilograms": ("kg", 1),
    "kilogram": ("kg", 1),
    "kilogramm": ("kg", 1),
    "kilos": ("kg", 1),
    "g": ("kg", 0.001),
    "grams": ("kg", 0.001),
    "gramm": ("kg", 0.001),
    "lbs": ("kg", 0.45359237),
    "lb": ("kg", 0.45359237),
    "pounds": ("kg", 0.45359237),
    "liters": ("l", 1),
    "litres": ("l", 1),
    "liter": ("l", 1),
    "litre": ("l", 1),
    "l": ("l", 1),
    "ml": ("l", 0.001),
    "bar": ("bar", 1),
    "%": ("%", 1),
    "percent": ("%", 1),
    "per cent": ("%", 1),
    "prozent": ("%", 1),
}

CURRENCIES = {
    "$": "USD",
    "usd": "USD",
    "dollars": "USD",
    "dollar": "USD",
    "€": "EUR",
    "eur": "EUR",
    "euro": "EUR",
    "euros": "EUR",
}

NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "eighteen": 18,
    "twenty": 20,
    "thirty": 30,
    "ein": 1,
    "eine": 1,
    "einen": 1,
    "einem": 1,
    "zwei": 2,
    "drei": 3,
    "vier": 4,
    "fünf": 5,
    "sechs": 6,
    "sieben": 7,
    "acht": 8,
    "neun": 9,
    "zehn": 10,
    "elf": 11,
    "zwölf": 12,
    "achtzehn": 18,
    "zwanzig": 20,
    "dreißig": 30,
}

QUALIFIERS = {
    "approx": (
        "about",
        "around",
        "roughly",
        "approximately",
        "nearly",
        "almost",
        "up to",
        "~",
        "some",
        "etwa",
        "rund",
        "ungefähr",
        "ca.",
        "circa",
        "bis zu",
        "knapp",
    ),
    "lt": ("under", "less than", "below", "unter", "weniger als", "unterhalb von"),
    "gt": ("over", "more than", "above", "über", "mehr als", "oberhalb von"),
}

NEGATIONS = (
    "no",
    "not",
    "doesn't",
    "does not",
    "without",
    "lacks",
    "isn't",
    "kein",
    "keine",
    "keinen",
    "nicht",
    "ohne",
)

_EN_NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_DE_NUM = r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?"
_WORDS = "|".join(sorted(NUMBER_WORDS, key=len, reverse=True))
_UNIT_ALT = "|".join(re.escape(u) for u in sorted(UNITS, key=len, reverse=True))


def _num_re(lang: str) -> str:
    return _DE_NUM if lang == "de" else _EN_NUM


def parse_number(token: str, lang: str) -> float:
    t = token.strip()
    if t.lower() in NUMBER_WORDS:
        return float(NUMBER_WORDS[t.lower()])
    if lang == "de":
        t = t.replace(".", "").replace(",", ".")
    else:
        t = t.replace(",", "")
    return float(t)


@dataclass(frozen=True)
class Value:
    start: int
    end: int
    text: str
    kind: str  # "money" | "quantity"
    amount: float  # canonical: currency units for money, canonical unit for quantities
    unit: str  # "USD"/"EUR" for money, canonical unit for quantities
    converted: bool  # written in a unit other than the canonical one
    qualifier: str  # "exact" | "approx" | "lt" | "gt"


def _qualifier(text: str, start: int) -> str:
    window = text[max(0, start - 28) : start].lower()
    for q, words in QUALIFIERS.items():
        for w in words:
            if re.search(r"(?:^|[\s(])" + re.escape(w) + r"\s*$", window):
                return q
    return "exact"


def find_values(text: str, lang: str) -> list[Value]:
    """Every money amount and every number with a unit in a piece of text, left to right."""
    num = _num_re(lang)
    found: list[Value] = []
    taken: list[tuple[int, int]] = []

    def free(s: int, e: int) -> bool:
        return all(e <= a or s >= b for a, b in taken)

    money_patterns = (
        rf"(?P<cur>[$€])\s?(?P<num>{num})(?P<k>k\b)?",
        rf"(?P<num>{num})\s?(?P<cur>€|\$|USD\b|EUR\b|[Ee]uros?\b|[Dd]ollars?\b)",
    )
    for pat in money_patterns:
        for m in re.finditer(pat, text):
            if not free(m.start(), m.end()):
                continue
            amount = parse_number(m.group("num"), lang) * (1000 if m.groupdict().get("k") else 1)
            cur = CURRENCIES[m.group("cur").lower()]
            found.append(
                Value(m.start(), m.end(), m.group(0), "money", amount, cur, False, _qualifier(text, m.start()))
            )
            taken.append((m.start(), m.end()))

    qty = rf"(?<![\w$€])(?P<num>{num}|(?i:{_WORDS}))(?:\s?-\s?|\s)?(?P<unit>(?i:{_UNIT_ALT}))(?![\w])"
    for m in re.finditer(qty, text):
        if not free(m.start(), m.end()):
            continue
        unit_token = m.group("unit").lower()
        canon, factor = UNITS[unit_token]
        try:
            raw = parse_number(m.group("num"), lang)
        except ValueError:
            continue
        found.append(
            Value(
                m.start(),
                m.end(),
                m.group(0),
                "quantity",
                raw * factor,
                canon,
                factor != 1,
                _qualifier(text, m.start()),
            )
        )
        taken.append((m.start(), m.end()))
    return sorted(found, key=lambda v: v.start)


def split_sentences(text: str) -> list[tuple[int, str]]:
    """(offset, sentence) pairs. Does not split after the abbreviations listed above."""
    out: list[tuple[int, str]] = []
    start = 0
    for m in re.finditer(r"(?<=[.!?])\s+(?=[A-ZÄÖÜ\"'(])", text):
        chunk = text[start : m.start()]
        if any(chunk.endswith(a) for a in ABBREVIATIONS):
            continue
        out.append((start, chunk))
        start = m.end()
    if text[start:].strip():
        out.append((start, text[start:].rstrip()))
    return out


CLAUSE_BREAK = re.compile(r",\s+(?:while|whereas|but|während|wohingegen|aber)\s+|;\s+|\s+(?:while|whereas|während)\s+")


def split_clauses(sentence: str) -> list[tuple[int, str]]:
    out, start = [], 0
    for m in CLAUSE_BREAK.finditer(sentence):
        out.append((start, sentence[start : m.start()]))
        start = m.end()
    out.append((start, sentence[start:]))
    return out


def negated(text: str, cue_start: int) -> bool:
    window = text[max(0, cue_start - 30) : cue_start].lower()
    return any(re.search(r"(?:^|\s)" + re.escape(n) + r"(?:\s|$)", window) for n in NEGATIONS)
