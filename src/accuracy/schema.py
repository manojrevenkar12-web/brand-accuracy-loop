"""What a brand fact can be about. Shared by the world and the pipeline: this is the product schema a brand fills in
when it sets up its vault, not knowledge of which claims are true."""

from __future__ import annotations

from dataclasses import dataclass

MARKETS = ("US", "DE")
CURRENCY_MARKET = {"USD": "US", "EUR": "DE"}
MARKET_CURRENCY = {m: c for c, m in CURRENCY_MARKET.items()}


@dataclass(frozen=True)
class Attribute:
    name: str
    kind: str  # "money" (one value per market), "quantity" (one value, canonical unit) or "flag"
    unit: str  # canonical unit for quantities: h, month, km, kg, l, bar, %
    words: str  # plain words used in reasons and tickets


ATTRIBUTES = {
    a.name: a
    for a in (
        Attribute("price", "money", "", "price"),
        Attribute("annual_fee", "money", "", "annual fee"),
        Attribute("battery", "quantity", "h", "battery life"),
        Attribute("warranty", "quantity", "month", "warranty"),
        Attribute("weight", "quantity", "kg", "weight"),
        Attribute("range", "quantity", "km", "range"),
        Attribute("pressure", "quantity", "bar", "pump pressure"),
        Attribute("tank", "quantity", "l", "water tank"),
        Attribute("apr", "quantity", "%", "APR"),
        Attribute("cashback", "quantity", "%", "cashback"),
        Attribute("foreign_fee", "quantity", "%", "foreign transaction fee"),
        Attribute("anc", "flag", "", "active noise cancelling"),
    )
}

CATEGORIES: dict[str, tuple[str, ...]] = {
    "headphones": ("price", "battery", "warranty", "anc"),
    "laptop": ("price", "battery", "weight", "warranty"),
    "ebike": ("price", "range", "weight", "warranty"),
    "coffee_machine": ("price", "pressure", "tank", "warranty"),
    "credit_card": ("annual_fee", "apr", "cashback", "foreign_fee"),
}


def money_attribute(category: str) -> str:
    return next(a for a in CATEGORIES[category] if ATTRIBUTES[a].kind == "money")
