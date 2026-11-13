"""Turning diagnoses into a ranked week of work: fix a brand page, ask a publisher to correct theirs, or send the
verified fact to an engine through the brand feed. A person approves each ticket before anything is sent."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from urllib.parse import urlparse

from .extract import Claim
from .schema import ATTRIBUTES
from .vault import Vault
from .verify import describe


@dataclass
class Ticket:
    action: tuple
    kind: str  # brand_page | publisher | engine_feed
    product: str
    attribute: str
    wrong_claims: int
    engines: list[str]
    draft: str
    evidence: list[str] = field(default_factory=list)


def owner(url: str, vault: Vault, product_id: str) -> str:
    host = urlparse(url).hostname or ""
    return "brand" if host.split(".")[0] == vault.products[product_id].brand.lower() else "third_party"


def plan(findings: list[tuple[str, Claim, str]], vault: Vault, budget: int) -> list[Ticket]:
    """findings: (engine, claim judged wrong, cause url or "model"). The most damaging causes come first."""
    grouped: dict[tuple, list[tuple[str, Claim]]] = defaultdict(list)
    for engine, claim, cause in findings:
        key = ("page", cause) if cause != "model" else ("feed", engine, claim.product_id, claim.attribute)
        grouped[key].append((engine, claim))
    tickets = []
    for action, items in grouped.items():
        engine, claim = items[0]
        product = vault.products[claim.product_id]
        fact = vault.fact(claim.product_id, claim.attribute)
        right = describe(fact, claim.attribute) if fact else "unknown"
        words = ATTRIBUTES[claim.attribute].words
        engines = sorted({e for e, _ in items})
        evidence = sorted({c.text for _, c in items})[:3]
        if action[0] == "feed":
            kind = "engine_feed"
            draft = (
                f"Send the verified {words} of {product.name} ({right}) to the {engine} engine through the "
                f"brand feed. {len(items)} answers stated it wrongly from memory."
            )
        elif owner(action[1], vault, claim.product_id) == "brand":
            kind = "brand_page"
            draft = f"Update {action[1]}: it states an outdated {words} for {product.name}. Verified: {right}."
        else:
            kind = "publisher"
            draft = (
                f"Hello, your page {action[1]} gives a {words} for {product.name} that differs from the "
                f"manufacturer's verified value ({right}). AI assistants are repeating it "
                f"({len(items)} answers this week). Could you update it? Source: {product.brand} product data."
            )
        tickets.append(Ticket(action, kind, product.name, claim.attribute, len(items), engines, draft, evidence))
    tickets.sort(key=lambda t: (-t.wrong_claims, str(t.action)))
    return tickets[:budget]
