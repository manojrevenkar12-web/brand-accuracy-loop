"""Turning an AI answer into atomic claims: which product, which fact, what value, how it was qualified."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .schema import ATTRIBUTES, CATEGORIES, CURRENCY_MARKET
from .text import find_values, negated, split_clauses, split_sentences
from .vault import Vault

AND = re.compile(r"\s(?:and|und)\s")


@dataclass
class Claim:
    sentence: int
    start: int  # absolute span of the value (or of the feature words, for flags)
    end: int
    product_id: str
    attribute: str
    kind: str
    amount: float  # canonical units; for money, in the currency below; for flags 1.0 or 0.0
    currency: str  # "USD"/"EUR" for money, "" otherwise
    converted: bool
    qualifier: str
    text: str  # the sentence it came from
    locale: str

    @property
    def market(self) -> str:
        return CURRENCY_MARKET.get(self.currency, "")


class Extractor:
    def __init__(self, vault: Vault, lexicon: dict[str, list[str]]):
        self.vault = vault
        self.cues = {a: sorted(ws, key=len, reverse=True) for a, ws in lexicon.items()}
        self._cue_re = {
            a: re.compile(r"(?<![\w])(" + "|".join(re.escape(w) for w in ws) + r")(?![\w])", re.IGNORECASE)
            for a, ws in self.cues.items()
        }

    def _cue_positions(self, clause: str, attrs: tuple[str, ...]) -> dict[str, list[int]]:
        return {a: [m.start() for m in self._cue_re[a].finditer(clause)] for a in attrs if a in self._cue_re}

    def extract(self, text: str, locale: str) -> list[Claim]:
        lang = locale[:2]
        claims: list[Claim] = []
        last: str | None = None
        mentions = self.vault.mentions(text)
        for s_idx, (s_off, sentence) in enumerate(split_sentences(text)):
            for c_off, clause in split_clauses(sentence):
                base = s_off + c_off
                here = [(s - base, pid) for s, e, pid in mentions if base <= s < base + len(clause)]
                values = find_values(clause, lang)
                default = here[0][1] if here else last
                for v in values:
                    pid = min(here, key=lambda h: abs(h[0] - v.start))[1] if here else last
                    if pid is None:
                        continue
                    attr = self._attribute_for(pid, v, clause)
                    if attr is None:
                        continue
                    claims.append(
                        Claim(
                            s_idx,
                            base + v.start,
                            base + v.end,
                            pid,
                            attr,
                            v.kind,
                            v.amount,
                            v.unit if v.kind == "money" else "",
                            v.converted,
                            v.qualifier,
                            sentence,
                            locale,
                        )
                    )
                if default is not None:
                    category = self.vault.products[default].category
                    flags = [a for a in CATEGORIES[category] if ATTRIBUTES[a].kind == "flag"]
                    for attr, positions in self._cue_positions(clause, tuple(flags)).items():
                        for p in positions[:1]:
                            end = p + self._cue_re[attr].match(clause, p).end() - p
                            claims.append(
                                Claim(
                                    s_idx,
                                    base + p,
                                    base + end,
                                    default,
                                    attr,
                                    "flag",
                                    0.0 if negated(clause, p) else 1.0,
                                    "",
                                    False,
                                    "exact",
                                    sentence,
                                    locale,
                                )
                            )
                if here:
                    last = here[-1][1]
        return claims

    def _attribute_for(self, pid: str, v, clause: str) -> str | None:
        category = self.vault.products[pid].category
        attrs = CATEGORIES[category]
        if v.kind == "money":
            return next((a for a in attrs if ATTRIBUTES[a].kind == "money"), None)
        same_unit = [a for a in attrs if ATTRIBUTES[a].kind == "quantity" and ATTRIBUTES[a].unit == v.unit]
        if len(same_unit) == 1:
            return same_unit[0]
        if not same_unit:
            return None
        lo, hi = 0, len(clause)
        for m in AND.finditer(clause):  # "... 19.99% APR and a 3% fee abroad": each part has its own cue
            if m.end() <= v.start:
                lo = m.end()
            elif m.start() >= v.end:
                hi = min(hi, m.start())
        segment = clause[lo:hi]
        cues = self._cue_positions(segment, tuple(same_unit))
        best, dist = None, 10**9
        for a, positions in cues.items():
            for p in positions:
                d = abs(lo + p - v.start)
                if d < dist:
                    best, dist = a, d
        return best
