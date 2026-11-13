"""Finding the page behind a wrong claim.

A page is a suspect only if it says the same wrong thing the answer said and disagrees with the vault. Among suspects,
a cited page outranks an uncited one, then the page whose sentence reads most like the answer's. If no page says it,
the engine got it from its own memory, and the fix is to send the engine the verified fact, not to blame a publisher."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from .extract import Claim, Extractor
from .features import rel_err
from .schema import ATTRIBUTES
from .vault import Vault

WORD = re.compile(r"[a-zäöüß0-9]+")


def tokens(s: str) -> set[str]:
    return set(WORD.findall(s.lower()))


def overlap(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    return len(ta & tb) / max(1, len(ta | tb))


@dataclass
class PageClaim:
    url: str
    claim: Claim


@dataclass
class Diagnosis:
    cause: str  # a URL, or "model"
    suspects: list[str] = field(default_factory=list)
    why: str = ""


class SourceIndex:
    """What every page about a product says, read with the same extractor as the answers."""

    def __init__(
        self,
        vault: Vault,
        extractor: Extractor,
        search: Callable[[str], list[str]],
        fetch: Callable[[str], tuple[str, str] | None],
    ):
        self.vault = vault
        self.by_fact: dict[tuple[str, str], list[PageClaim]] = {}
        self.text: dict[str, str] = {}
        for pid in vault.products:
            for url in search(pid):
                got = fetch(url)
                if got is None:
                    continue
                body, lang = got
                self.text[url] = body
                for c in extractor.extract(body, "de-DE" if lang == "de" else "en-US"):
                    self.by_fact.setdefault((c.product_id, c.attribute), []).append(PageClaim(url, c))


class Attributor:
    name = "value_match"

    def __init__(self, vault: Vault, index: SourceIndex, settings: dict):
        self.vault = vault
        self.index = index
        s = settings["attribution"]
        self.exact_tol, self.approx_tol, self.cited_bonus = (
            s["exact_tolerance"],
            s["approx_tolerance"],
            s["cited_bonus"],
        )
        self.floors = settings["features"]["floor"]

    def _floor(self, attr: str) -> float:
        a = ATTRIBUTES[attr]
        return self.floors["money" if a.kind == "money" else a.unit] if a.kind != "flag" else 1.0

    def _says_same(self, answer: Claim, page: Claim) -> bool:
        if answer.kind == "flag":
            return page.amount == answer.amount
        if answer.kind == "money" and page.currency != answer.currency:
            return False
        if answer.qualifier == "lt":
            return page.amount < answer.amount
        if answer.qualifier == "gt":
            return page.amount > answer.amount
        tol = self.approx_tol if answer.qualifier == "approx" or page.qualifier == "approx" else self.exact_tol
        return rel_err(page.amount, answer.amount, self._floor(answer.attribute)) <= tol

    def _page_wrong(self, page: Claim) -> bool:
        fact = self.vault.fact(page.product_id, page.attribute)
        if fact is None:
            return True
        if page.kind == "flag":
            return fact.values.get("*") != page.amount
        ref = fact.values.get(page.market if page.kind == "money" else "*")
        if ref is None:
            return True
        tol = self.approx_tol if page.qualifier == "approx" else self.exact_tol
        return rel_err(page.amount, ref, self._floor(page.attribute)) > tol

    def diagnose(self, claim: Claim, citations: list[str]) -> Diagnosis:
        suspects = [
            pc
            for pc in self.index.by_fact.get((claim.product_id, claim.attribute), [])
            if self._says_same(claim, pc.claim) and self._page_wrong(pc.claim)
        ]
        if not suspects:
            return Diagnosis("model", [], "no page says this; the engine answered from memory")
        cited = set(citations)

        def score(pc: PageClaim) -> float:
            return (self.cited_bonus if pc.url in cited else 0.0) + overlap(claim.text, pc.claim.text)

        ranked = sorted({pc.url: pc for pc in suspects}.values(), key=lambda pc: (-score(pc), pc.url))
        top = ranked[0]
        why = "cited, and says the same wrong value" if top.url in cited else "says the same wrong value"
        return Diagnosis(top.url, [pc.url for pc in ranked], why)


class FirstCitation:
    """Blame whatever the answer cited first."""

    name = "first_citation"

    def __init__(self, *_):
        pass

    def diagnose(self, claim: Claim, citations: list[str]) -> Diagnosis:
        return Diagnosis(citations[0], citations[:1], "first citation") if citations else Diagnosis("model")


class ClosestCitation:
    """Blame the cited page whose text reads most like the answer: an influence score over citations."""

    name = "closest_citation"

    def __init__(self, vault: Vault, index: SourceIndex, settings: dict):
        self.index = index

    def diagnose(self, claim: Claim, citations: list[str]) -> Diagnosis:
        if not citations:
            return Diagnosis("model")
        best = max(citations, key=lambda u: (overlap(claim.text, self.index.text.get(u, "")), u))
        return Diagnosis(best, [best], "closest cited page")
