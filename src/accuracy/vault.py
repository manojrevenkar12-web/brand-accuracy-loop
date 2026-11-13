"""The brand vault: the facts a brand has verified about its own products, with their history.

This is customer input, not the evaluation truth. A vault can be incomplete: a claim about a fact the brand has not
verified is reported as unverifiable, never as wrong."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Product:
    id: str
    brand: str
    name: str
    category: str
    aliases: list[str] = field(default_factory=list)


@dataclass
class Fact:
    product_id: str
    attribute: str
    values: dict[str, float]  # market -> value for money; "*" -> value otherwise (1.0/0.0 for flags)
    previous: dict[str, float] = field(default_factory=dict)  # values before the last verified change


class Vault:
    def __init__(self, products: list[Product], facts: list[Fact]):
        self.products = {p.id: p for p in products}
        self.facts = {(f.product_id, f.attribute): f for f in facts}
        aliases = [(a.lower(), p.id) for p in products for a in [p.name, *p.aliases]]
        aliases.sort(key=lambda x: -len(x[0]))
        self._aliases = aliases
        self._alias_re = (
            re.compile(r"(?<![\w])(" + "|".join(re.escape(a) for a, _ in aliases) + r")(?![\w])", re.IGNORECASE)
            if aliases
            else None
        )
        self._alias_pid = dict(aliases)

    def fact(self, product_id: str, attribute: str) -> Fact | None:
        return self.facts.get((product_id, attribute))

    def mentions(self, text: str) -> list[tuple[int, int, str]]:
        """(start, end, product id) for every product name or alias in the text, longest match first."""
        if not self._alias_re:
            return []
        return [(m.start(), m.end(), self._alias_pid[m.group(0).lower()]) for m in self._alias_re.finditer(text)]

    def dump(self, path: Path) -> None:
        data = {
            "products": [asdict(p) for p in self.products.values()],
            "facts": [asdict(f) for f in self.facts.values()],
        }
        path.write_text(json.dumps(data, indent=1, sort_keys=True))

    @classmethod
    def load(cls, path: Path) -> Vault:
        data = json.loads(path.read_text())
        return cls([Product(**p) for p in data["products"]], [Fact(**f) for f in data["facts"]])
