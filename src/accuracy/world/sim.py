"""The world: brands and their real facts, the web pages written about them, AI engines that answer prompts from those
pages and from memory, and the truth about every claim an engine makes.

Only scripts/evaluate.py and the tests read this package. The pipeline sees what a monitoring company sees: the
vault the brand filled in, the answers the engines return, and the pages it can fetch."""

from __future__ import annotations

import hashlib
import random
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from ..schema import ATTRIBUTES, CATEGORIES
from ..vault import Fact, Product, Vault
from . import templates as T


def rng(*key) -> random.Random:
    digest = hashlib.blake2b(repr(key).encode(), digest_size=8).digest()
    return random.Random(int.from_bytes(digest, "big"))


SYLLABLES_A = [
    "Sono",
    "Vel",
    "Aur",
    "Nor",
    "Kest",
    "Lum",
    "Brio",
    "Tal",
    "Fen",
    "Mar",
    "Quin",
    "Zeph",
    "Orb",
    "Hal",
    "Pell",
    "Cor",
    "Dax",
    "Ely",
    "Fjor",
    "Grav",
    "Ixi",
    "Jun",
    "Ven",
    "Rho",
    "Sil",
    "Tor",
    "Ulm",
    "Wex",
]
SYLLABLES_B = ["ra", "ix", "on", "eta", "ova", "um", "ant", "is", "o", "ex", "elle", "ari", "yn", "ost"]
CARD_TIERS = ["Travel", "Platinum", "Everyday", "Gold", "Student", "Rewards", "Business"]
SUFFIXES = ["", " Pro", " Air", " Max", " S"]
FEE_TIERS = {"US": [0, 95, 250, 550, 695], "DE": [0, 49, 99, 149, 299]}
PRICE = {"headphones": (79, 449), "laptop": (599, 2499), "ebike": (1499, 5999), "coffee_machine": (149, 1299)}
REVIEW_SITES = {
    "en": ["gearwire.example", "testlab.example", "reviewdesk.example"],
    "de": ["kaufberater.example", "techblatt.example", "testheft.example"],
}
CARD_SITES = {"en": ["cardcompare.example", "pointsguide.example"], "de": ["kartenvergleich.example"]}
FORUMS = {"en": "talkboard.example", "de": "forum-de.example"}
RETAIL = {"en": "dealhub.example", "de": "preisradar.example"}
# how far a value may be from the truth before a claim about it is wrong (the annotation guideline)
FLOOR = {"money": 20.0, "h": 2.0, "month": 6.0, "km": 5.0, "kg": 0.5, "l": 0.3, "bar": 2.0, "%": 0.5}
EXACT_TOLERANCE, APPROX_TOLERANCE = 0.03, 0.10


def nice_price(x: float) -> float:
    step = 50 if x >= 1000 else 10
    return float(max(step, round(x / step) * step) - 1)


@dataclass
class Page:
    id: str
    url: str
    product_id: str
    kind: str  # official | review | forum | retail | spam
    owner: str  # "brand" or "third_party"
    lang: str
    day: int


@dataclass
class Prompt:
    id: str
    split: str
    locale: str
    products: list[str]
    attrs: dict[str, list[str]]


@dataclass
class Answer:
    id: str
    week: int
    prompt_id: str
    engine: str
    locale: str
    text: str
    citations: list[str]


@dataclass
class TruthClaim:
    start: int
    end: int
    product_id: str
    attribute: str
    label: str  # accurate | inaccurate | unverifiable
    cause: str  # page id, or "model" when the engine answered from memory or made it up
    claimed: float
    currency: str
    style: str


@dataclass
class State:
    pages: dict[str, dict[str, dict[str, float]]]  # page id -> attribute -> market ("*" if none) -> stated value
    feed: set = field(default_factory=set)  # (engine, product, attribute) the engine has learned from a brand feed
    fixes: list = field(default_factory=list)


class World:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.seed = cfg["seed"]
        self.style_set = cfg.get("templates", "dev")
        self.engines = cfg["engines"]
        self.products: dict[str, Product] = {}
        self.truth_facts: dict[tuple[str, str], dict] = {}
        self.pages: dict[str, Page] = {}
        self.by_url: dict[str, Page] = {}
        self._initial: dict[str, dict[str, dict[str, float]]] = {}
        self._truth: dict[str, list[TruthClaim]] = {}
        self._build()

    @classmethod
    def load(cls, path: Path) -> World:
        return cls(tomllib.loads(path.read_text()))

    # ---------------------------------------------------------------- building
    def _build(self) -> None:
        r = rng(self.seed, "brands")
        names: set[str] = set()
        codes: set[str] = set()
        cats = self.cfg["categories"]
        vault_products, vault_facts = [], []
        for b in range(self.cfg["brands"]):
            while True:
                brand = r.choice(SYLLABLES_A) + r.choice(SYLLABLES_B)
                if brand not in names:
                    names.add(brand)
                    break
            cat = cats[b % len(cats)]
            lo, hi = self.cfg["products_per_brand"]
            tiers = r.sample(CARD_TIERS, hi)
            for j in range(r.randint(lo, hi)):
                if cat == "credit_card":
                    name, aliases = f"{brand} {tiers[j]} Card", [f"{brand} {tiers[j]}"]
                else:
                    while True:
                        code = r.choice("ABCDEFGHKLMNPQRSTVXZ") + str(r.randint(10, 99))
                        if code not in codes:
                            codes.add(code)
                            break
                    suffix = r.choice(SUFFIXES)
                    name = f"{brand} {code}{suffix}"
                    aliases = [f"{brand} {code}", code] if suffix else [code]
                pid = f"{brand.lower()}-{j}"
                product = Product(pid, brand, name, cat, aliases)
                self.products[pid] = product
                vault_products.append(product)
                for attr in CATEGORIES[cat]:
                    fr = rng(self.seed, "fact", pid, attr)
                    values = self._value(fr, cat, attr)
                    previous, changed = None, None
                    if ATTRIBUTES[attr].kind != "flag" and fr.random() < self.cfg["change_share"]:
                        previous = self._other(fr, attr, values, stale=True)
                        changed = -fr.randint(5, 400)
                    self.truth_facts[(pid, attr)] = {"values": values, "previous": previous, "changed": changed}
                    if fr.random() < self.cfg["vault_coverage"]:
                        prev = previous if previous and fr.random() < self.cfg["vault_history"] else {}
                        vault_facts.append(Fact(pid, attr, dict(values), dict(prev)))
                self._make_pages(product)
        self.vault = Vault(vault_products, vault_facts)

    def _value(self, r: random.Random, cat: str, attr: str) -> dict[str, float]:
        if attr == "price":
            us = nice_price(r.uniform(*PRICE[cat]))
            return {"US": us, "DE": nice_price(us * r.uniform(0.86, 1.02))}
        if attr == "annual_fee":
            tier = r.randrange(5)
            return {m: float(FEE_TIERS[m][tier]) for m in FEE_TIERS}
        v = {
            "battery": lambda: float(r.randint(18, 60) if cat == "headphones" else r.randint(8, 24)),
            "warranty": lambda: float(r.choice([24, 36, 60] if cat == "ebike" else [12, 24, 36])),
            "weight": lambda: round(r.uniform(0.9, 2.6) if cat == "laptop" else r.uniform(18, 32), 1),
            "range": lambda: float(r.randint(8, 32) * 5),
            "pressure": lambda: float(r.choice([9, 15, 19, 20])),
            "tank": lambda: round(r.uniform(1.0, 2.5), 1),
            "apr": lambda: float(f"{r.randint(15, 29)}.99"),
            "cashback": lambda: float(r.choice([1, 1.5, 2, 3, 4, 5])),
            "foreign_fee": lambda: float(r.choice([0, 1.5, 1.75, 2.5, 3])),
            "anc": lambda: 1.0 if r.random() < 0.7 else 0.0,
        }[attr]()
        return {"*": v}

    def _other(self, r: random.Random, attr: str, values: dict[str, float], stale: bool) -> dict[str, float]:
        """A value that is clearly not the current one: an old value (stale) or a wrong one."""
        out = {}
        for m, v in values.items():
            for _ in range(50):
                if attr == "annual_fee":
                    w = float(r.choice([t for t in FEE_TIERS[m] if t != v]))
                elif attr == "warranty":
                    w = float(r.choice([t for t in (12, 24, 36, 60) if t != v]))
                elif attr in ("cashback", "foreign_fee", "pressure"):
                    opts = {
                        "cashback": [1, 1.5, 2, 3, 4, 5],
                        "foreign_fee": [0, 1.5, 1.75, 2.5, 3],
                        "pressure": [9, 15, 19, 20],
                    }[attr]
                    w = float(r.choice([t for t in opts if t != v]))
                elif attr == "anc":
                    w = 1.0 - v
                elif attr == "apr":
                    w = float(f"{int(v) + r.choice([-4, -3, -2, 2, 3, 4])}.99")
                else:
                    lo, hi = ((0.75, 0.93), (1.08, 1.3)) if stale else ((0.55, 0.85), (1.18, 1.6))
                    f = r.uniform(*r.choice([lo, hi]))
                    w = v * f
                    if attr == "price":
                        w = nice_price(w)
                    elif attr in ("weight", "tank"):
                        w = round(w, 1)
                    else:
                        w = float(round(w))
                if w != v and w >= 0:
                    break
            out[m] = w
        return out

    def _as_of(self, pid: str, attr: str, day: int) -> dict[str, float]:
        f = self.truth_facts[(pid, attr)]
        if f["previous"] and f["changed"] is not None and day < f["changed"]:
            return dict(f["previous"])
        return dict(f["values"])

    def _make_pages(self, p: Product) -> None:
        r = rng(self.seed, "pages", p.id)
        attrs = CATEGORIES[p.category]
        slug = p.name.lower().replace(" ", "-")
        domain = p.brand.lower() + ".example"
        card = p.category == "credit_card"

        def add(kind: str, lang: str, day: int, stated: dict[str, dict[str, float]], host: str, owner: str):
            pid = f"{p.id}/{kind}{sum(1 for x in self.pages.values() if x.product_id == p.id)}"
            url = f"https://{host}/{'de/' if lang == 'de' and owner == 'brand' else ''}{slug}" + (
                "" if owner == "brand" else f"-{len(self.pages)}"
            )
            page = Page(pid, url, p.id, kind, owner, lang, day)
            self.pages[pid] = page
            self.by_url[url] = page
            self._initial[pid] = stated

        def market(lang: str) -> str:
            return "DE" if lang == "de" else "US"

        def stated(attr: str, lang: str, values: dict[str, float]) -> dict[str, float]:
            if ATTRIBUTES[attr].kind == "money":
                return {market(lang): values[market(lang)]}
            return {"*": values["*"]}

        for lang in ("en", "de"):
            add(
                "official",
                lang,
                0,
                {a: stated(a, lang, self.truth_facts[(p.id, a)]["values"]) for a in attrs},
                domain,
                "brand",
            )
        for _ in range(r.randint(2, 3)):
            lang = "de" if r.random() < 0.35 else "en"
            day = -r.randint(5, 400)
            host = r.choice((CARD_SITES if card else REVIEW_SITES)[lang])
            chosen = r.sample(attrs, r.randint(2, 3))
            add(
                "review",
                lang,
                day,
                {a: stated(a, lang, self._as_of(p.id, a, day)) for a in chosen},
                host,
                "third_party",
            )
        for _ in range(r.randint(1, 2)):
            lang = "de" if r.random() < 0.35 else "en"
            day = -r.randint(1, 300)
            values = {}
            for a in r.sample(attrs, r.randint(1, 2)):
                v = self._as_of(p.id, a, day)
                if r.random() < 0.35:
                    v = self._other(r, a, v, stale=False)
                values[a] = stated(a, lang, v)
            add("forum", lang, day, values, FORUMS[lang], "third_party")
        money = next(a for a in attrs if ATTRIBUTES[a].kind == "money")
        for lang in ("en", "de"):
            if r.random() < 0.6:
                f = self.truth_facts[(p.id, money)]
                v = f["previous"] if f["previous"] and r.random() < 0.5 else f["values"]
                add("retail", lang, -r.randint(1, 200), {money: stated(money, lang, v)}, RETAIL[lang], "third_party")
        if r.random() < self.cfg["spam_share"]:
            a = r.choice([x for x in attrs if ATTRIBUTES[x].kind != "flag"])
            wrong = self._other(r, a, self.truth_facts[(p.id, a)]["values"], stale=False)
            add("spam", "en", -r.randint(1, 60), {a: stated(a, "en", wrong)}, "best-picks.example", "third_party")

    # ---------------------------------------------------------------- what the monitor can see
    def new_state(self) -> State:
        return State({k: {a: dict(m) for a, m in v.items()} for k, v in self._initial.items()})

    def prompts(self, split: str) -> list[Prompt]:
        n = self.cfg["prompts_train" if split == "train" else "prompts_eval"]
        de_share = self.cfg["german_share_train" if split == "train" else "german_share"]
        pids = sorted(self.products)
        out = []
        for i in range(n):
            r = rng(self.seed, "prompt", split, i)
            x = r.random()
            locale = "de-DE" if x < de_share else ("en-DE" if x < de_share + self.cfg["en_de_share"] else "en-US")
            first = r.choice(pids)
            cat = self.products[first].category
            products = [first]
            same = [q for q in pids if q != first and self.products[q].category == cat]
            if same and r.random() < 0.3:
                products.append(r.choice(same))
            attrs = r.sample(CATEGORIES[cat], 2 if len(products) == 2 else r.randint(2, 4))
            out.append(Prompt(f"{split}{i}", split, locale, products, {q: list(attrs) for q in products}))
        return out

    def search(self, product_id: str) -> list[str]:
        """What a web search for the product name returns: every page about it."""
        return [p.url for p in self.pages.values() if p.product_id == product_id]

    def fetch(self, state: State, url: str) -> tuple[str, str] | None:
        page = self.by_url.get(url)
        if page is None:
            return None
        return T.page_text(self, page, state.pages[page.id], rng(self.seed, "pagetext", page.id)), page.lang

    def answers(self, state: State, week: int, split: str = "eval") -> list[Answer]:
        out = []
        for prompt in self.prompts(split):
            for eng in sorted(self.engines):
                out.append(self._answer(state, week, prompt, eng))
        return out

    # ---------------------------------------------------------------- engines
    def _retrieve(self, state: State, week: int, prompt: Prompt, eng: str) -> list[Page]:
        e = self.engines[eng]
        lang = prompt.locale[:2]
        cands = [p for p in self.pages.values() if p.product_id in prompt.products]
        scored = []
        for p in cands:
            lang_factor = 1.0 if p.lang == lang else (0.5 if lang == "de" else 0.2)
            u = rng(self.seed, "retrieve", week, prompt.id, eng, p.id).uniform(0.6, 1.4)
            scored.append((e["weights"][p.kind] * lang_factor * u, p.id, p))
        scored.sort(key=lambda x: (-x[0], x[1]))
        return [p for _, _, p in scored[: e["k"] * len(prompt.products)]]

    def _claim(
        self, state: State, week: int, prompt: Prompt, eng: str, pid: str, attr: str, retrieved: list[Page]
    ) -> dict:
        e = self.engines[eng]
        r = rng(self.seed, "claim", week, prompt.id, eng, pid, attr)
        kind = ATTRIBUTES[attr].kind
        market = "DE" if prompt.locale.endswith("DE") else "US"
        if kind == "money" and prompt.locale == "en-DE" and r.random() < e["dollar_in_en_de"]:
            market = "US"
        key = market if kind == "money" else "*"
        sources = [p for p in retrieved if p.product_id == pid and key in state.pages[p.id].get(attr, {})]
        from_memory = r.random() < e["memory"]
        if sources and not from_memory:
            page = r.choices(sources, [e["weights"][p.kind] for p in sources])[0]
            value, cause = state.pages[page.id][attr][key], page.id
        else:
            cause = "model"
            if (eng, pid, attr) in state.feed:
                value = self.truth_facts[(pid, attr)]["values"][key]
            else:
                value = self._as_of(pid, attr, e["cutoff_day"])[key]
                if r.random() < e["invent"]:
                    value = self._other(r, attr, {key: value}, stale=False)[key]
        style = "exact"
        if kind != "flag":
            x, s = r.random(), e["style"]
            style = "exact" if x < s["exact"] else ("approx" if x < s["exact"] + s["approx"] else "bound")
            if style == "bound":
                style = "lt" if (r.random() < 0.7 or value == 0) else "gt"
            if value == 0 and style != "exact":
                style = "exact"
        return {"pid": pid, "attr": attr, "market": market, "value": value, "style": style, "cause": cause}

    def _answer(self, state: State, week: int, prompt: Prompt, eng: str) -> Answer:
        retrieved = self._retrieve(state, week, prompt, eng)
        claims = [
            self._claim(state, week, prompt, eng, pid, a, retrieved)
            for pid in prompt.products
            for a in prompt.attrs[pid]
        ]
        r = rng(self.seed, "compose", week, prompt.id, eng)
        text, truth = T.compose(self, r, prompt, claims)
        aid = f"w{week}-{prompt.id}-{eng}"
        for t in truth:
            t.label = self.label(t)
        self._truth[aid] = truth
        e = self.engines[eng]
        causes = {c["cause"] for c in claims}
        cites = []
        for p in retrieved:
            cr = rng(self.seed, "cite", week, prompt.id, eng, p.id).random()
            if cr < (e["cite_cause"] if p.id in causes else e["cite_other"]):
                cites.append(p.url)
        rng(self.seed, "cite-order", week, prompt.id, eng).shuffle(cites)
        return Answer(aid, week, prompt.id, eng, prompt.locale, text, cites)

    # ---------------------------------------------------------------- truth (evaluation only)
    def label(self, t: TruthClaim) -> str:
        if self.vault.fact(t.product_id, t.attribute) is None:
            return "unverifiable"
        values = self.truth_facts[(t.product_id, t.attribute)]["values"]
        a = ATTRIBUTES[t.attribute]
        if a.kind == "flag":
            return "accurate" if t.claimed == values["*"] else "inaccurate"
        truth = values["US" if t.currency == "USD" else "DE"] if a.kind == "money" else values["*"]
        if t.style == "lt":
            return "accurate" if truth < t.claimed else "inaccurate"
        if t.style == "gt":
            return "accurate" if truth > t.claimed else "inaccurate"
        floor = FLOOR["money" if a.kind == "money" else a.unit]
        rel = abs(t.claimed - truth) / max(abs(truth), floor)
        tol = APPROX_TOLERANCE if t.style == "approx" else EXACT_TOLERANCE
        return "accurate" if rel <= tol + 1e-9 else "inaccurate"

    def truth(self, answer_id: str) -> list[TruthClaim]:
        return self._truth[answer_id]

    def annotate(
        self, answer_id: str, start: int, end: int, product_id: str, attribute: str, noise: float | None = None
    ) -> str:
        """What an annotator answers for one extracted claim. Annotators make mistakes at the configured rate."""
        noise = self.cfg["annotator_noise"] if noise is None else noise
        match = next(
            (
                t
                for t in self._truth.get(answer_id, [])
                if t.product_id == product_id and t.attribute == attribute and t.start < end and start < t.end
            ),
            None,
        )
        if match is None:
            return "not_a_claim"
        r = rng(self.seed, "annotate", answer_id, start, noise)
        if r.random() < noise:
            return r.choice([x for x in ("accurate", "inaccurate", "unverifiable") if x != match.label])
        return match.label

    def apply(self, state: State, action: tuple, week: int) -> bool:
        """A correction lands (or not). Brand pages always change; third parties often do not."""
        r = rng(self.seed, "apply", week, action)
        odds = self.cfg["fix_success"]
        if action[0] == "page":
            page = self.by_url.get(action[1])
            if page is None:
                return False
            if r.random() >= odds["brand" if page.owner == "brand" else page.kind]:
                return False
            for attr, stated in state.pages[page.id].items():
                for m in stated:
                    stated[m] = self.truth_facts[(page.product_id, attr)]["values"][m]
            state.fixes.append((week, action))
            return True
        if action[0] == "feed":
            _, eng, pid, attr = action
            if r.random() >= odds["feed"]:
                return False
            state.feed.add((eng, pid, attr))
            state.fixes.append((week, action))
            return True
        raise ValueError(action)
