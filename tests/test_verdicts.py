"""The verifiers, the training loop and the reasons a verdict gives."""

import copy

import pytest

from accuracy.extract import Claim
from accuracy.train import Example, train
from accuracy.vault import Fact, Product, Vault
from accuracy.verify import Rules, StringMatch, Trained


@pytest.fixture()
def vault():
    p = Product("acme-0", "Acme", "Acme Q10", "headphones", ["Q10"])
    facts = [Fact("acme-0", "price", {"US": 279.0, "DE": 259.0}, {"US": 329.0}), Fact("acme-0", "battery", {"*": 32.0})]
    return Vault([p], facts)


def claim(attr, amount, qualifier="exact", currency="", locale="en-US", kind=None, text="x"):
    kind = kind or ("money" if currency else "quantity")
    return Claim(0, 0, 1, "acme-0", attr, kind, amount, currency, False, qualifier, text, locale)


def test_unverified_facts_are_never_called_wrong(vault, settings, model):
    c = claim("warranty", 24)
    for v in (StringMatch(vault, settings), Rules(vault, settings), Trained(vault, settings, model)):
        assert v.verdict(c).label == "unverifiable"


def test_hedged_numbers_get_the_guideline_tolerance(vault, settings, model):
    hedged = claim("battery", 30, "approx", text="It lasts about 30 hours.")
    assert Rules(vault, settings).verdict(hedged).label == "inaccurate"  # the fixed 2 % tolerance
    assert Trained(vault, settings, model).verdict(hedged).label == "accurate"
    assert Trained(vault, settings, model).verdict(claim("battery", 24, "approx")).label == "inaccurate"


def test_bounds_and_currency_markets(vault, settings, model):
    t = Trained(vault, settings, model)
    assert t.verdict(claim("price", 300, "lt", "USD")).label == "accurate"
    assert t.verdict(claim("price", 250, "lt", "USD")).label == "inaccurate"
    usd_in_germany = claim("price", 279, "exact", "USD", locale="en-DE")
    assert t.verdict(usd_in_germany).label == "accurate"  # judged against the US price, as the guideline says
    assert Rules(vault, settings).verdict(usd_in_germany).label == "inaccurate"


def test_an_old_price_is_wrong_and_says_why(vault, settings, model):
    v = Trained(vault, settings, model).verdict(claim("price", 329, "exact", "USD"))
    assert v.label == "inaccurate" and v.p_wrong > 0.9
    assert v.verified == "$279 / €259"
    assert len(v.reasons) == 3


def test_string_match_misses_paraphrase(vault, settings):
    v = StringMatch(vault, settings).verdict(claim("battery", 32, text="It runs thirty-two hours."))
    assert v.label == "inaccurate"


def test_a_model_from_another_feature_list_is_refused(vault, settings, model):
    old = dict(model, features=model["features"][:-1])
    with pytest.raises(ValueError):
        Trained(vault, settings, old)


def test_cleaning_finds_labels_the_annotator_got_wrong(world, extractor, settings):
    state = world.new_state()
    examples, truth = [], []
    for a in world.answers(state, 0, "train"):
        for c in extractor.extract(a.text, a.locale):
            label = world.annotate(a.id, c.start, c.end, c.product_id, c.attribute, noise=0.0)
            if label in ("accurate", "inaccurate"):
                examples.append(Example(c, label))
                truth.append(label)
    flipped = set(range(0, len(examples), 9))
    for i in flipped:
        examples[i].label = "accurate" if examples[i].label == "inaccurate" else "inaccurate"
    noisy = copy.deepcopy(examples)
    _, rep = train(
        noisy, world.vault, settings, clean=True, reweight=False, second_reader=lambda ex: truth[noisy.index(ex)]
    )
    flagged = set(rep["flagged"])
    assert len(flagged & flipped) / len(flagged) > 0.9
    assert len(flagged & flipped) / len(flipped) > 0.4
    model, _ = train(copy.deepcopy(examples), world.vault, settings, clean=False, reweight=True)
    assert model["reweighted"] and len(model["weights"]) == len(model["features"])
