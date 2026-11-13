"""Three ways to decide whether a claim is right, and the one that sends doubtful claims to a person."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from .extract import Claim
from .features import NAMES, ORDER, featurize, local_market, rel_err, vector
from .schema import ATTRIBUTES
from .vault import Fact, Vault


@dataclass
class Verdict:
    label: str  # accurate | inaccurate | unverifiable | review
    p_wrong: float | None = None
    reasons: list[str] = field(default_factory=list)
    verified: str = ""


def describe(fact: Fact, attribute: str) -> str:
    a = ATTRIBUTES[attribute]
    if a.kind == "flag":
        return "yes" if fact.values.get("*") == 1.0 else "no"
    if a.kind == "money":
        sym = {"US": "$", "DE": "€"}
        return " / ".join(f"{sym[m]}{v:,.0f}" for m, v in sorted(fact.values.items(), key=lambda x: x[0] != "US"))
    unit = {"h": " hours", "month": " months", "km": " km", "kg": " kg", "l": " l", "bar": " bar", "%": " %"}[a.unit]
    return f"{fact.values['*']:g}{unit}"


class StringMatch:
    """What a simple monitor does: the claim is right if the verified number appears in the sentence."""

    name = "string_match"

    def __init__(self, vault: Vault, settings: dict):
        self.vault = vault

    def verdict(self, c: Claim) -> Verdict:
        fact = self.vault.fact(c.product_id, c.attribute)
        if fact is None:
            return Verdict("unverifiable", reasons=["the brand has not verified this fact"])
        if c.kind == "flag":
            ok = fact.values.get("*") == c.amount
            return Verdict("accurate" if ok else "inaccurate", verified=describe(fact, c.attribute))
        forms = set()
        for v in fact.values.values():
            for s in (f"{v:,.0f}", f"{v:.0f}", f"{v:g}", f"{v:,.0f}".replace(",", "."), f"{v:g}".replace(".", ",")):
                forms.add(s)
        hit = any(re.search(r"(?<![\d.,])" + re.escape(s) + r"(?![\d])", c.text) for s in forms)
        return Verdict("accurate" if hit else "inaccurate", verified=describe(fact, c.attribute))


class Rules:
    """A careful hand-written verifier: units converted, bounds understood, a fixed tolerance, the local market."""

    name = "rules"

    def __init__(self, vault: Vault, settings: dict):
        self.vault = vault
        self.tol = settings["rules"]["tolerance"]
        self.floors = settings["features"]["floor"]

    def verdict(self, c: Claim) -> Verdict:
        fact = self.vault.fact(c.product_id, c.attribute)
        if fact is None:
            return Verdict("unverifiable", reasons=["the brand has not verified this fact"])
        a = ATTRIBUTES[c.attribute]
        if a.kind == "flag":
            ok = fact.values.get("*") == c.amount
        else:
            truth = fact.values.get(local_market(c.locale) if a.kind == "money" else "*")
            if truth is None:
                return Verdict("unverifiable", reasons=["no verified value for this market"])
            if c.qualifier == "lt":
                ok = truth < c.amount
            elif c.qualifier == "gt":
                ok = truth > c.amount
            else:
                ok = rel_err(c.amount, truth, self.floors["money" if a.kind == "money" else a.unit]) <= self.tol
        return Verdict("accurate" if ok else "inaccurate", verified=describe(fact, c.attribute))


class Trained:
    """A logistic model trained on annotated claims. Served with plain arithmetic: no training library at run time."""

    name = "trained"

    def __init__(self, vault: Vault, settings: dict, model: dict, review_band: tuple[float, float] | None = None):
        if model["features"] != ORDER:
            raise ValueError("the model was trained on a different feature list; retrain it")
        self.vault = vault
        self.floors = settings["features"]["floor"]
        self.w = model["weights"]
        self.b = model["intercept"]
        self.threshold = model["threshold"]
        self.band = review_band
        if review_band:
            self.name = "trained_review"

    @classmethod
    def from_file(cls, vault: Vault, settings: dict, path: Path, review: bool = False) -> Trained:
        band = tuple(settings["review"]["band"]) if review else None
        return cls(vault, settings, json.loads(path.read_text()), band)

    def p_wrong(self, c: Claim, fact: Fact) -> tuple[float, list[tuple[str, float]]]:
        x = vector(featurize(c, fact, self.floors))
        parts = [(ORDER[i], self.w[i] * x[i]) for i in range(len(x)) if x[i]]
        z = self.b + sum(v for _, v in parts)
        return 1.0 / (1.0 + math.exp(-z)), parts

    def verdict(self, c: Claim) -> Verdict:
        fact = self.vault.fact(c.product_id, c.attribute)
        if fact is None:
            return Verdict("unverifiable", reasons=["the brand has not verified this fact"])
        p, parts = self.p_wrong(c, fact)
        parts = sorted((x for x in parts if x[0] != "bias"), key=lambda x: -abs(x[1]))[:3]
        reasons = [f"{NAMES[k]} ({'points to wrong' if v > 0 else 'points to right'})" for k, v in parts]
        if self.band and self.band[0] <= p < self.band[1]:
            label = "review"
        else:
            label = "inaccurate" if p >= self.threshold else "accurate"
        return Verdict(label, round(p, 4), reasons, describe(fact, c.attribute))


def make(name: str, vault: Vault, settings: dict, model_path: Path | None = None):
    if name == "string_match":
        return StringMatch(vault, settings)
    if name == "rules":
        return Rules(vault, settings)
    if name in ("trained", "trained_review"):
        return Trained.from_file(vault, settings, model_path, review=name == "trained_review")
    raise ValueError(name)
