"""The world's rules, the invariants of the repository, and the HTTP API."""

import json
import re
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from accuracy.judge import MessagesJudge, cost_usd, tokens
from accuracy.service.app import create_app

ROOT = Path(__file__).resolve().parents[1]


def test_only_the_evaluation_reads_the_world():
    for path in (ROOT / "src" / "accuracy").rglob("*.py"):
        if "world" in path.parts:
            assert "pipeline.toml" not in path.read_text(), f"{path} reads the pipeline's settings"
            continue
        assert not re.search(r"(from|import)\s+[.\w]*world", path.read_text()), f"{path} imports the world"


def test_every_design_meets_the_same_luck(world):
    a = world.answers(world.new_state(), 0)
    b = world.answers(world.new_state(), 0)
    assert [x.text for x in a] == [x.text for x in b]


def test_a_fix_changes_only_what_it_fixes(world):
    state = world.new_state()
    before = {x.id: x.text for x in world.answers(state, 1)}

    def wrong(page):
        return any(
            v != world.truth_facts[(page.product_id, a)]["values"][m]
            for a, ms in state.pages[page.id].items()
            for m, v in ms.items()
        )

    page = next(p for p in world.pages.values() if p.kind == "review" and wrong(p))
    assert any(world.apply(state, ("page", page.url), week) for week in range(30))
    assert not wrong(page)
    after = world.answers(state, 1)
    others = [x for x in after if not any(t.product_id == page.product_id for t in world.truth(x.id))]
    assert others and all(x.text == before[x.id] for x in others)


def test_the_guideline(world):
    from accuracy.world.sim import TruthClaim

    pid = next(
        k
        for k, v in world.products.items()
        if v.category == "headphones" and world.vault.fact(k, "battery") is not None
    )
    truth = world.truth_facts[(pid, "battery")]["values"]["*"]

    def lab(claimed, style):
        return world.label(TruthClaim(0, 1, pid, "battery", "", "model", claimed, "", style))

    assert lab(truth * 1.02, "exact") == "accurate" and lab(truth * 1.05, "exact") == "inaccurate"
    assert lab(truth * 1.09, "approx") == "accurate" and lab(truth * 1.12, "approx") == "inaccurate"
    assert lab(truth + 1, "lt") == "accurate" and lab(truth - 1, "lt") == "inaccurate"


def test_api_verifies_counts_each_answer_once_and_plans_tickets(world, settings, model, extractor):
    from accuracy.attribute import SourceIndex

    state = world.new_state()
    index = SourceIndex(world.vault, extractor, world.search, lambda u: world.fetch(state, u))
    client = TestClient(create_app(world.vault, settings, model, index))
    assert client.get("/healthz").json()["ok"]
    wrong = next(
        a
        for a in world.answers(state, 0)
        if any(t.label == "inaccurate" and t.cause != "model" for t in world.truth(a.id))
    )
    body = {
        "id": wrong.id,
        "engine": wrong.engine,
        "locale": wrong.locale,
        "text": wrong.text,
        "citations": wrong.citations,
    }
    out = client.post("/v1/answers/verify", json=body).json()
    assert out["summary"]["inaccurate"] >= 1
    flagged = [c for c in out["claims"] if c["verdict"] == "inaccurate"]
    assert all(c["source"] and c["reasons"] for c in flagged)
    first = client.get("/v1/tickets").json()
    client.post("/v1/answers/verify", json=body)
    assert client.get("/v1/tickets").json() == first
    assert client.post("/v1/answers/verify", json={**body, "locale": "fr-FR"}).status_code == 422
    assert client.get("/v1/tickets?budget=0").status_code == 422
    assert (
        client.put(
            "/v1/vault/facts", json={"product_id": "nope", "attribute": "price", "values": {"US": 1}}
        ).status_code
        == 404
    )


def test_judge_cost_and_adapter(world, extractor):
    a = world.answers(world.new_state(), 0)[0]
    c = extractor.extract(a.text, a.locale)[0]
    fact = world.vault.fact(c.product_id, c.attribute)
    assert 100 < tokens(c, fact) < 400
    assert (
        cost_usd(
            1_000_000,
            0,
            {"cost": {"judge_price_in_per_mtok": 3.0, "judge_price_out_per_mtok": 15.0, "judge_output_tokens": 60}},
        )
        == 3.0
    )

    def handler(request: httpx.Request) -> httpx.Response:
        sent = json.loads(request.content)
        assert sent["system"].startswith("You check one claim")
        return httpx.Response(
            200, json={"content": [{"type": "text", "text": '{"label": "accurate", "reason": "matches"}'}]}
        )

    j = MessagesJudge("https://api.example", "key", "some-model", httpx.Client(transport=httpx.MockTransport(handler)))
    assert j.judge(c, fact)["label"] == "accurate"
