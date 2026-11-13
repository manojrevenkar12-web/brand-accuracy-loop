"""Numbers, units, qualifiers and claims, in English and German."""

import pytest

from accuracy.text import find_values, negated, parse_number, split_sentences


@pytest.mark.parametrize(
    "token,lang,value",
    [
        ("1,299", "en", 1299),
        ("1.299", "de", 1299),
        ("1,5", "de", 1.5),
        ("19.99", "en", 19.99),
        ("zwei", "de", 2),
    ],
)
def test_numbers(token, lang, value):
    assert parse_number(token, lang) == value


def test_money_and_markets():
    en = find_values("It costs $1,299 or about €1,199 in Germany.", "en")
    assert [(v.amount, v.unit, v.qualifier) for v in en] == [(1299, "USD", "exact"), (1199, "EUR", "approx")]
    de = find_values("Das Gerät kostet unter 1.300 € und rund 279 Euro gebraucht.", "de")
    assert [(v.amount, v.unit, v.qualifier) for v in de] == [(1300, "EUR", "lt"), (279, "EUR", "approx")]


def test_german_thin_space_thousands():
    # found by the held-out run: "1\u202f999 €" was read as 999 €
    assert [v.amount for v in find_values("Das E-Bike kostet 1\u202f999 € oder 2\u00a0099 Euro.", "de")] == [1999, 2099]


def test_units_convert_to_canonical():
    vals = find_values("A range of 60 miles, a 2-year warranty and 3.1 lbs.", "en")
    got = {v.unit: (round(v.amount, 2), v.converted) for v in vals}
    assert got == {"km": (96.56, True), "month": (24, True), "kg": (1.41, True)}
    de = find_values("Es hat zwei Jahre Garantie und einen Sollzins von 19,99 %.", "de")
    assert [(v.amount, v.unit) for v in de] == [(24, "month"), (19.99, "%")]


def test_product_codes_are_not_numbers():
    assert find_values("The Q71 Pro lasts 30 hours.", "en")[0].amount == 30
    assert len(find_values("The Q71 Pro lasts 30 hours.", "en")) == 1


def test_sentences_keep_abbreviations():
    s = split_sentences("Der Akku hält ca. 30 Stunden. Das Gerät wiegt 1,2 kg.")
    assert [x[1] for x in s] == ["Der Akku hält ca. 30 Stunden.", "Das Gerät wiegt 1,2 kg."]


def test_negation():
    text = "It does not have active noise cancelling."
    assert negated(text, text.index("noise"))
    assert not negated("It has active noise cancelling.", 14)


def test_extraction_finds_every_claim_in_dev_answers(world, extractor):
    state = world.new_state()
    missed = total = 0
    for a in world.answers(state, 0):
        claims = extractor.extract(a.text, a.locale)
        for t in world.truth(a.id):
            total += 1
            missed += not any(
                c.product_id == t.product_id and c.attribute == t.attribute and c.start < t.end and t.start < c.end
                for c in claims
            )
    assert total > 500 and missed == 0


def test_percent_claims_go_to_the_right_fact(world, extractor):
    card = next(p for p in world.vault.products.values() if p.category == "credit_card")
    text = f"The {card.name} charges 19.99% APR on purchases and adds a 3% fee on purchases abroad."
    got = {(c.attribute, c.amount) for c in extractor.extract(text, "en-US")}
    assert got == {("apr", 19.99), ("foreign_fee", 3.0)}


def test_pronouns_carry_the_product(world, extractor):
    p = next(p for p in world.vault.products.values() if p.category == "headphones")
    text = f"The {p.name} costs $299. It lasts 30 hours on a charge. It does not have active noise cancelling."
    got = [(c.product_id, c.attribute, c.amount) for c in extractor.extract(text, "en-US")]
    assert got == [(p.id, "price", 299), (p.id, "battery", 30), (p.id, "anc", 0.0)]
