"""Write README.md and the console's data from reports/*.json. Never edit the results by hand."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = "https://github.com/manojrevenkar12-web/brand-accuracy-loop"

DESIGN_NAMES = {
    "string_match": "String match (what simple monitors do)",
    "rules": "Hand-written rules",
    "trained": "Trained verifier",
    "trained_review": "Trained verifier, doubtful claims to a person",
}
ATTR_NAMES = {
    "first_citation": "Blame the first citation",
    "closest_citation": "Blame the cited page closest to the answer",
    "value_match": "Find the page that says the same wrong value",
}
LOOP_NAMES = {"none": "No corrections", **ATTR_NAMES}


def n(x: float) -> str:
    return f"{x:,.0f}" if abs(x) >= 100 else f"{x:g}"


def table(head: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(head) + " |", "|" + "|".join(["---"] + ["--:"] * (len(head) - 1)) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


def detect_table(r: dict) -> str:
    rows = []
    for k, v in r["verification"].items():
        rows.append(
            [
                DESIGN_NAMES[k],
                f"{v['accuracy']}%",
                f"{v['wrong_claims_caught']}%",
                f"{v['flag_precision']}%",
                n(v["false_alarms_per_1k_claims"]),
                f"{v['error_by_language']['en']}%",
                f"{v['error_by_language']['de']}%",
                f"{v['sent_to_people']}%",
            ]
        )
    return table(
        [
            "Design",
            "Claims judged right",
            "Wrong claims caught",
            "Flags that were right",
            "False alarms per 1,000 claims",
            "Error, English",
            "Error, German",
            "Sent to a person",
        ],
        rows,
    )


def attribution_table(r: dict) -> str:
    rows = [
        [
            ATTR_NAMES[k],
            f"{v['cause_found']}%",
            f"{v['innocent_page_blamed']}%",
            f"{v['engine_memory_blamed_on_a_page']}%",
        ]
        for k, v in r["attribution"].items()
    ]
    return table(["Method", "Cause found", "Blamed a page that was right", "Engine memory blamed on a page"], rows)


def loop_table(r: dict) -> str:
    rows = []
    for k, v in r["loop"].items():
        w = v["weekly_wrong_rate"]
        sent = sum(v["tickets"].values())
        rows.append([LOOP_NAMES[k], f"{w[0]}%", f"{w[-1]}%", f"{sent}", f"{v['fixes_landed']}"])
    return table(
        [
            "Diagnosis behind the tickets",
            "Wrong claims, week 1",
            "Wrong claims, last week",
            "Tickets sent",
            "Fixes that landed",
        ],
        rows,
    )


def loop_chart(r: dict) -> str:
    weeks = len(next(iter(r["loop"].values()))["weekly_wrong_rate"])
    lines = [
        "```mermaid",
        "xychart-beta",
        '    title "Share of AI claims that are wrong, by week"',
        f"    x-axis [{', '.join(str(i + 1) for i in range(weeks))}]",
        '    y-axis "% of claims wrong" 0 --> 12',
    ]
    for k in r["loop"]:
        lines.append(f"    line [{', '.join(str(x) for x in r['loop'][k]['weekly_wrong_rate'])}]")
    lines.append("```")
    ranked = sorted(r["loop"], key=lambda k: -r["loop"][k]["weekly_wrong_rate"][-1])
    order = ", ".join(f"{i + 1}. {LOOP_NAMES[k]}" for i, k in enumerate(ranked))
    return "\n".join(lines) + f"\n\nLines, top to bottom at week {weeks}: {order}."


def training_table(r: dict) -> str:
    names = {
        "plain": "As annotated",
        "cleaned": "Doubtful labels read again",
        "reweighted": "German weighted up",
        "cleaned_and_reweighted": "Both",
    }
    rows = []
    for k, v in r["training"]["variants"].items():
        mark = " (used)" if k == r["training"]["chosen"] else ""
        rows.append(
            [
                names[k] + mark,
                f"{v['accuracy']}%",
                f"{v['wrong_claims_caught']}%",
                n(v["false_alarms_per_1k_claims"]),
                f"{v['error_by_language']['en']}%",
                f"{v['error_by_language']['de']}%",
            ]
        )
    return table(
        [
            "Training data",
            "Claims judged right",
            "Wrong claims caught",
            "False alarms per 1,000",
            "Error, English",
            "Error, German",
        ],
        rows,
    )


def main() -> None:
    dev = json.loads((ROOT / "reports" / "dev.json").read_text())
    held_path = ROOT / "reports" / "heldout.json"
    held = json.loads(held_path.read_text()) if held_path.exists() else None
    v, t, c = dev["verification"], dev["training"], dev["counts"]
    rules, trained, review = v["rules"], v["trained"], v["trained_review"]
    loop = dev["loop"]
    best, none = loop["value_match"]["weekly_wrong_rate"], loop["none"]["weekly_wrong_rate"]
    first = loop["first_citation"]["weekly_wrong_rate"]
    att = dev["attribution"]
    judge = dev["llm_judge_estimate"]
    kinds = sorted(rules["false_alarm_kinds"].items(), key=lambda x: -x[1])
    plural = {
        "hedged number": "hedged numbers",
        "bound": 'bounds ("under $300")',
        "converted unit": "converted units",
        "price in another market's currency": "prices in another market's currency",
        "other": "other claims",
    }
    alarms = ", ".join(f"{x} on {plural[k]}" for k, x in kinds)
    weeks = dev["loop_settings"]["weeks"]
    budget = dev["loop_settings"]["fixes_per_week"]

    if held:
        hv, ha, hl = held["verification"], held["attribution"], held["loop"]
        heldout = f"""## Held-out world (run once)

A second world with other brands, a fifth engine that cites less and reads more forums, 40 % German prompts,
and phrasings the extractor was never written for. It ran once, with the verifier trained on the dev world and no
change after (`config/heldout.lock`). {held["counts"]["answers"]:,} answers, {held["counts"]["claims"]:,} claims;
the extractor found {held["extraction"]["recall"]}% of them.

{detect_table(held)}

{attribution_table(held)}

{loop_table(held)}

With the same {budget} tickets a week, value-matched diagnosis took the share of wrong claims from
{hl["value_match"]["weekly_wrong_rate"][0]}% to {hl["value_match"]["weekly_wrong_rate"][-1]}%; blaming the first
citation ended at {hl["first_citation"]["weekly_wrong_rate"][-1]}%. The trained verifier caught
{hv["trained"]["wrong_claims_caught"]}% of wrong claims with {n(hv["trained"]["false_alarms_per_1k_claims"])} false
alarms per 1,000 claims (rules: {n(hv["rules"]["false_alarms_per_1k_claims"])}). Value-matched diagnosis blamed a
correct page {ha["value_match"]["innocent_page_blamed"]}% of the time.

What the held-out run found: most of the trained verifier's false alarms there came from the extractor, not the
verifier. German prices written with a thin space as the thousands separator ("1\u202f999 €", as DIN 5008 allows)
were read as 999 €, and the verifier rightly called 999 € wrong. Most missed claims were card percentages phrased
without a cue word ("gives 2% on every purchase"). The number format is fixed since, with a test; the cue words are
not. The held-out numbers above are as they first came out.
"""
    else:
        heldout = "## Held-out world\n\nNot run yet: `python3 scripts/evaluate.py --heldout` (once).\n"

    readme = f"""# brand-accuracy-loop

**Checks what AI assistants say about a brand against the brand's verified facts, finds the page or the engine
memory behind every wrong claim, and plans the week's corrections.**

When someone asks an assistant what a product costs, how long its battery lasts or what a card charges abroad, the
answer is often stale or wrong: an old review, a forum guess, a model that learned last year's price. A visibility
dashboard shows that the brand was mentioned. A brand team needs three more things: which claims are wrong (without
crying wolf), where each one came from, and which fixes to send first so the next week's answers get better.
This repository does those three steps (detect, diagnose, correct) and measures each against a world whose truth
it never reads.

![Console]({REPO}/raw/main/docs/console.png)

## Results

Dev world: {c["answers"]:,} answers from {len(c["engines"])} engines to {c["answers"] // len(c["engines"])}
prompts, holding {c["claims"]:,} claims, {round(100 * c["german_claims"] / c["claims"])} % of them in German. Every
number below is written by `scripts/evaluate.py` into `reports/dev.json` and copied here by `scripts/readme.py`; CI
regenerates both and fails on any difference.

| | Hand-written rules | Trained verifier |
|---|--:|--:|
| False alarms per 1,000 claims | {n(rules["false_alarms_per_1k_claims"])} \
| **{n(trained["false_alarms_per_1k_claims"])}** |
| Wrong claims caught | {rules["wrong_claims_caught"]}% | {trained["wrong_claims_caught"]}% |
| Error on German answers | {rules["error_by_language"]["de"]}% | {trained["error_by_language"]["de"]}% |

| | Blame the first citation | Value-matched diagnosis |
|---|--:|--:|
| Cause of a wrong claim found | {att["first_citation"]["cause_found"]}% | **{att["value_match"]["cause_found"]}%** |
| Publisher blamed for a page that was right | {att["first_citation"]["innocent_page_blamed"]}% \
| **{att["value_match"]["innocent_page_blamed"]}%** |
| Wrong claims after {weeks} weeks, {budget} tickets a week | {first[-1]}% | **{best[-1]}%** (from {best[0]}%) |

### Detect: is the claim right?

The guideline the annotators follow: exact numbers count as right within 3 % after unit conversion, hedged
numbers ("about", "rund", "up to") within 10 %, "under X" if the verified value is below X, money against the
market of its currency, and a fact the brand has not verified is *unverifiable*, never wrong.

{detect_table(dev)}

The rules use a fixed 2 % tolerance and the market the prompt was asked from; a careful engineer's first version.
They catch {rules["wrong_claims_caught"]}% of wrong claims and raise {n(rules["false_alarms_per_1k_claims"])} false
alarms per 1,000 claims: {alarms}. The trained verifier learns the guideline from
labelled examples and is served as {len(json.loads((ROOT / "models" / "verifier.json").read_text())["weights"])}
weights and an intercept (`models/verifier.json`): no training library at run time, under a millisecond per answer
on one core. Every verdict lists the verified value and the three features that weighed most. The review design
sends the {review["sent_to_people"]}% of claims with a probability between 0.2 and 0.8 to a person, at
€{review["review_eur_per_1k_answers"]} per 1,000 answers (1.5 minutes a claim, €45 an hour).

An LLM judge on every claim would read {n(judge["input_tokens_per_claim"])} input tokens per claim, about
${judge["usd_per_1k_answers"]} per 1,000 answers at $3 / $15 per million tokens. That is an estimate from the
prompt in `src/accuracy/judge.py`; its accuracy is not measured here (no model is called).

### Training the verifier

{t["annotated"]:,} claims labelled by annotators who are wrong \
{round(100 * t["labels_wrong_before_cleaning"] / t["annotated"], 1)} % of the time \
({t["labels_wrong_before_cleaning"]} wrong labels), {t["languages"]["de"]} of the usable ones German.
Five-fold cross-validation flags labels the model finds implausible and a second reader looks at them:
{t["relabelled"]} flagged, {t["flagged_truly_wrong"]} of them really wrong. German examples are then weighted up to
the English ones, because the answers are {round(100 * c["german_claims"] / c["claims"])} % German and the labels
are not. The four ways of training, measured on the dev answers:

{training_table(dev)}

### Diagnose: which page caused it?

A page is a suspect only if it says the same wrong value as the answer and disagrees with the vault; a cited suspect
outranks an uncited one. If no page says it, the engine answered from memory and the ticket goes to the engine's
brand feed instead of a publisher. Measured on the {att["value_match"]["wrong_claims"]} wrong claims of week 1:

{attribution_table(dev)}

The remaining misses are mostly engine memory that happens to match an old review: both say last year's price,
and the review gets the ticket. Fixing that review is still useful; it is counted as a miss.

### Correct: {weeks} weeks, {budget} tickets a week

Each week the trained verifier reads every answer, the diagnosis groups wrong claims by cause, and the
{budget} causes behind the most wrong claims get a ticket: update a brand page, write to a publisher (they fix it
about half the time), or send the verified fact to an engine's brand feed. Every design meets the same answers,
the same engine luck and the same publisher replies; only the tickets differ.

{loop_chart(dev)}

{loop_table(dev)}

Tickets built on the first citation reach publishers whose pages were right, so many "fixes" change nothing. After
{weeks} weeks the share of wrong claims is {best[-1]}% with value-matched diagnosis, {first[-1]}% with the first
citation and {none[-1]}% with no corrections.

{heldout}
## How it works

```mermaid
flowchart LR
  A[Answer from an AI engine] --> X[Extract claims: product, fact, value, hedge, unit, currency]
  V[(Brand vault: verified facts and their history)] --> D
  X --> D{{Trained verifier}}
  D -- right / unverifiable --> R[Report]
  D -- doubtful --> P[Person reviews]
  D -- wrong --> G[Diagnose: which page says the same wrong value?]
  W[(Pages about the product, read with the same extractor)] --> G
  G -- a page --> T1[Ticket: brand page or publisher]
  G -- no page --> T2[Ticket: send the fact to the engine's brand feed]
  T1 & T2 --> Q[Ranked by wrong claims caused, a person approves]
```

- `src/accuracy/extract.py`: products by name, short name or pronoun; values with units, hedges, bounds and
  currencies in English and German ("1.299 €", "a 2-year warranty", "60 miles").
- `src/accuracy/verify.py`: string match, rules, the trained verifier and its review band.
- `src/accuracy/train.py`: cross-validated label cleaning, optional language weighting, exported weights.
- `src/accuracy/attribute.py`: the source index and the three diagnosis methods.
- `src/accuracy/corrections.py`: tickets with drafted outreach, ranked by damage.
- `src/accuracy/service/`: FastAPI: `POST /v1/answers/verify`, `GET /v1/tickets`, `PUT /v1/vault/facts`.
- `src/accuracy/world/`: brands, pages, five engine profiles and the truth. Only the evaluation and the tests read it.
- `infra/terraform/`: AWS (ECS Fargate behind a load balancer, ECR, CloudWatch alarms); validated in CI, not applied.
- `web/`: the console (React, Framer Motion) reading `web/public/data/console.json`.

## Run it

```bash
pip install -e '.[dev]'
python -m pytest -q                       # 30 tests, about 4 s
python3 scripts/evaluate.py               # dev world, about 45 s; trains the verifier, writes reports/dev.json
python3 scripts/readme.py                 # this README and the console data
uvicorn accuracy.service.main:app         # the API with the example vault
cd web && npm ci && npm run dev           # the console
```

## Limits

- The world is simulated. Its engines, pages and annotators follow rules written in `src/accuracy/world/`; real
  engines fail in more ways, and a real guideline has more cases than four.
- The verifier is a logistic model over engineered comparisons, not a fine-tuned language model. It learns
  tolerances and market rules from labels; it does not read free text beyond what the extractor finds.
- English and German only, and five product categories with fixed attributes.
- The LLM judge is priced, not measured.
"""
    (ROOT / "README.md").write_text(readme)

    console = {
        "generated_from": "reports/dev.json" + (" and reports/heldout.json" if held else ""),
        "counts": c,
        "designs": [DESIGN_NAMES[k] for k in v],
        "ledger": [
            {"label": "Claims judged right", "values": [f"{x['accuracy']}%" for x in v.values()]},
            {"label": "Wrong claims caught", "values": [f"{x['wrong_claims_caught']}%" for x in v.values()]},
            {
                "label": "False alarms per 1,000 claims",
                "values": [n(x["false_alarms_per_1k_claims"]) for x in v.values()],
            },
            {"label": "Error on German answers", "values": [f"{x['error_by_language']['de']}%" for x in v.values()]},
            {"label": "Sent to a person", "values": [f"{x['sent_to_people']}%" for x in v.values()]},
        ],
        "attribution": [{"method": ATTR_NAMES[k], **x} for k, x in att.items()],
        "loop": {
            "weeks": weeks,
            "budget": budget,
            "series": [
                {
                    "name": LOOP_NAMES[k],
                    "key": k,
                    "values": x["weekly_wrong_rate"],
                    "landed": x["fixes_landed"],
                    "sent": sum(x["tickets"].values()),
                }
                for k, x in loop.items()
            ],
        },
        "examples": dev["examples"],
        "tickets": dev["tickets"],
        "heldout": None
        if not held
        else {
            "answers": held["counts"]["answers"],
            "claims": held["counts"]["claims"],
            "trained": held["verification"]["trained"]["accuracy"],
            "false_alarms": held["verification"]["trained"]["false_alarms_per_1k_claims"],
            "rules_false_alarms": held["verification"]["rules"]["false_alarms_per_1k_claims"],
            "wrong_after": held["loop"]["value_match"]["weekly_wrong_rate"][-1],
            "wrong_before": held["loop"]["value_match"]["weekly_wrong_rate"][0],
        },
    }
    out = ROOT / "web" / "public" / "data" / "console.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(console, indent=1, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
