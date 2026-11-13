"""HTTP API: verify an answer, see this week's correction tickets, update a verified fact."""

from __future__ import annotations

from dataclasses import asdict
from threading import Lock

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from ..attribute import Attributor, SourceIndex
from ..corrections import plan
from ..extract import Extractor
from ..schema import ATTRIBUTES
from ..vault import Fact, Vault
from ..verify import Trained


class AnswerIn(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    engine: str = Field(min_length=1, max_length=50)
    locale: str = Field(pattern=r"^(en-US|en-DE|de-DE)$")
    text: str = Field(min_length=1, max_length=20_000)
    citations: list[str] = Field(default_factory=list, max_length=50)


class FactIn(BaseModel):
    product_id: str
    attribute: str
    values: dict[str, float]
    previous: dict[str, float] = Field(default_factory=dict)


def create_app(vault: Vault, settings: dict, model: dict, index: SourceIndex | None = None) -> FastAPI:
    app = FastAPI(title="brand-accuracy-loop", version="1.0.0")
    extractor = Extractor(vault, settings["lexicon"])
    verifier = Trained(vault, settings, model)
    attributor = Attributor(vault, index, settings) if index else None
    findings: list = []
    seen: set[str] = set()
    lock = Lock()

    @app.get("/healthz")
    def health() -> dict:
        return {"ok": True, "products": len(vault.products), "facts": len(vault.facts)}

    @app.post("/v1/answers/verify")
    def verify(answer: AnswerIn) -> dict:
        claims = []
        for c in extractor.extract(answer.text, answer.locale):
            v = verifier.verdict(c)
            row = {
                "start": c.start,
                "end": c.end,
                "said": answer.text[c.start : c.end],
                "product_id": c.product_id,
                "attribute": c.attribute,
                "verdict": v.label,
                "p_wrong": v.p_wrong,
                "verified": v.verified,
                "reasons": v.reasons,
                "source": None,
            }
            if v.label == "inaccurate" and attributor:
                d = attributor.diagnose(c, answer.citations)
                row["source"] = {"cause": d.cause, "why": d.why, "suspects": d.suspects}
                with lock:
                    if answer.id not in seen:
                        findings.append((answer.engine, c, d.cause))
            claims.append(row)
        with lock:
            seen.add(answer.id)  # the same answer sent twice counts once in the tickets
        return {
            "id": answer.id,
            "claims": claims,
            "summary": {
                k: sum(1 for x in claims if x["verdict"] == k) for k in ("accurate", "inaccurate", "unverifiable")
            },
        }

    @app.get("/v1/tickets")
    def tickets(budget: int = 10) -> list[dict]:
        if not 1 <= budget <= 200:
            raise HTTPException(422, "budget must be between 1 and 200")
        with lock:
            planned = plan(list(findings), vault, budget)
        return [{**asdict(t), "action": list(t.action)} for t in planned]

    @app.put("/v1/vault/facts")
    def put_fact(fact: FactIn) -> dict:
        if fact.product_id not in vault.products:
            raise HTTPException(404, f"unknown product {fact.product_id}")
        if fact.attribute not in ATTRIBUTES:
            raise HTTPException(422, f"unknown attribute {fact.attribute}")
        vault.facts[(fact.product_id, fact.attribute)] = Fact(
            fact.product_id, fact.attribute, fact.values, fact.previous
        )
        return {"stored": True}

    return app
