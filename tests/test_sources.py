"""Finding the page behind a wrong claim, and turning it into work."""

from accuracy.attribute import Attributor, FirstCitation, SourceIndex
from accuracy.corrections import plan
from accuracy.extract import Claim
from accuracy.vault import Fact, Product, Vault

PAGES = {
    "https://acme.example/q10": ("Meet the Acme Q10. It costs $279. It lasts 32 hours on a charge.", "en"),
    "https://gearwire.example/q10-1": ("Our review of the Acme Q10. It costs $329.", "en"),
    "https://talkboard.example/q10-2": ("Anyone own the Acme Q10? It lasts 32 hours on a charge.", "en"),
}


def setup(settings):
    from accuracy.extract import Extractor

    vault = Vault(
        [Product("acme-0", "Acme", "Acme Q10", "headphones", ["Q10"])],
        [Fact("acme-0", "price", {"US": 279.0, "DE": 259.0}), Fact("acme-0", "battery", {"*": 32.0})],
    )
    ex = Extractor(vault, settings["lexicon"])
    index = SourceIndex(vault, ex, lambda pid: list(PAGES), lambda url: PAGES.get(url))
    return vault, ex, index


def test_the_page_that_says_the_wrong_price_is_blamed_even_uncited(settings):
    vault, ex, index = setup(settings)
    c = ex.extract("The Acme Q10 costs $329.", "en-US")[0]
    d = Attributor(vault, index, settings).diagnose(c, ["https://talkboard.example/q10-2"])
    assert d.cause == "https://gearwire.example/q10-1"
    assert FirstCitation().diagnose(c, ["https://talkboard.example/q10-2"]).cause == "https://talkboard.example/q10-2"


def test_no_page_says_it_means_the_engine_remembered_it(settings):
    vault, ex, index = setup(settings)
    c = ex.extract("The Acme Q10 lasts 20 hours on a charge.", "en-US")[0]
    d = Attributor(vault, index, settings).diagnose(c, list(PAGES))
    assert d.cause == "model" and d.suspects == []


def test_tickets_rank_by_damage_and_respect_the_budget(settings):
    vault, ex, index = setup(settings)
    wrong = Claim(0, 0, 1, "acme-0", "price", "money", 329.0, "USD", False, "exact", "It costs $329.", "en-US")
    memory = Claim(0, 0, 1, "acme-0", "battery", "quantity", 20.0, "", False, "exact", "20 hours", "en-US")
    findings = [("chat", wrong, "https://gearwire.example/q10-1")] * 3 + [("chat", memory, "model")]
    tickets = plan(findings, vault, budget=5)
    assert [t.kind for t in tickets] == ["publisher", "engine_feed"]
    assert tickets[0].wrong_claims == 3 and "$279" in tickets[0].draft
    assert plan(findings, vault, budget=1)[0].kind == "publisher"
    own = plan([("chat", wrong, "https://acme.example/q10")], vault, 5)
    assert own[0].kind == "brand_page"
