"""What the trained verifier looks at: how a claim compares with the verified fact. Every feature has a plain-words
name, so a verdict can say why it was reached."""

from __future__ import annotations

from .extract import Claim
from .schema import ATTRIBUTES
from .vault import Fact

NAMES: dict[str, str] = {
    "bias": "baseline",
    "is_money": "a price or fee",
    "is_flag": "a yes/no feature",
    "approx": "hedged (about, rund, up to)",
    "bound": "stated as a bound (under, über)",
    "german": "German answer",
    "converted": "written in another unit (miles, years, lbs)",
    "currency_not_local": "currency differs from the market asked about",
    "rel_err": "distance from the verified value",
    "local_rel_err": "distance from the verified value in the market asked about",
    **{f"exact_within_{t}": f"exact, within {t} % of the verified value" for t in (1, 2, 3, 5, 10, 15, 20)},
    **{f"approx_within_{t}": f"hedged, within {t} % of the verified value" for t in (1, 2, 3, 5, 10, 15, 20)},
    "local_exact_within_4": "exact, within 4 % of the local verified value",
    "local_approx_within_12": "hedged, within 12 % of the local verified value",
    "bound_holds": "the bound holds for the verified value",
    "local_bound_holds": "the bound holds for the local verified value",
    "bound_fails": "the bound does not hold for the verified value",
    "local_bound_fails": "the bound does not hold for the local verified value",
    "flag_matches": "the yes/no feature matches the vault",
    "matches_old_value": "equals the value before the last verified change",
}
ORDER = list(NAMES)
GRID = (1, 2, 3, 5, 10, 15, 20)  # round percentages


def rel_err(x: float, ref: float, floor: float) -> float:
    return abs(x - ref) / max(abs(ref), floor)


def local_market(locale: str) -> str:
    return "DE" if locale.endswith("DE") else "US"


def featurize(c: Claim, fact: Fact, floors: dict[str, float]) -> dict[str, float]:
    a = ATTRIBUTES[c.attribute]
    f = dict.fromkeys(ORDER, 0.0)
    f["bias"] = 1.0
    f["german"] = float(c.locale.startswith("de"))
    if a.kind == "flag":
        f["is_flag"] = 1.0
        f["flag_matches"] = float(fact.values.get("*") == c.amount)
        return f
    floor = floors["money" if a.kind == "money" else a.unit]
    f["is_money"] = float(a.kind == "money")
    f["approx"] = float(c.qualifier == "approx")
    f["bound"] = float(c.qualifier in ("lt", "gt"))
    f["converted"] = float(c.converted)
    if a.kind == "money":
        own = fact.values.get(c.market)
        local = fact.values.get(local_market(c.locale))
        f["currency_not_local"] = float(c.market != local_market(c.locale))
        prev = fact.previous.get(c.market)
    else:
        own = local = fact.values.get("*")
        prev = fact.previous.get("*")
    big = 2.0
    r = rel_err(c.amount, own, floor) if own is not None else big
    rl = rel_err(c.amount, local, floor) if local is not None else big
    f["rel_err"] = min(r, big)
    f["local_rel_err"] = min(rl, big)
    exact, approx = c.qualifier == "exact", c.qualifier == "approx"
    # a grid of round distances; which ones matter for which qualifier is learned from the labels
    for t in GRID:
        f[f"exact_within_{t}"] = float(exact and r <= t / 100)
        f[f"approx_within_{t}"] = float(approx and r <= t / 100)
    f["local_exact_within_4"] = float(exact and rl <= 0.04)
    f["local_approx_within_12"] = float(approx and rl <= 0.12)

    def holds(ref: float | None) -> float:
        if ref is None:
            return 0.0
        return float((c.qualifier == "lt" and ref < c.amount) or (c.qualifier == "gt" and ref > c.amount))

    f["bound_holds"] = holds(own)
    f["local_bound_holds"] = holds(local)
    bound = c.qualifier in ("lt", "gt")
    f["bound_fails"] = float(bound and own is not None and not f["bound_holds"])
    f["local_bound_fails"] = float(bound and local is not None and not f["local_bound_holds"])
    f["matches_old_value"] = float(prev is not None and rel_err(c.amount, prev, floor) <= 0.03 and r > 0.03)
    return f


def vector(f: dict[str, float]) -> list[float]:
    return [f[k] for k in ORDER]
