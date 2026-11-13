"""Measure every design against the world's truth.

python3 scripts/evaluate.py            dev world: trains the verifier (models/verifier.json), reports/dev.json
python3 scripts/evaluate.py --heldout  held-out world, once, with the dev-trained verifier; writes the lock
"""

from __future__ import annotations

import argparse
import copy
import json
import random
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from accuracy import judge  # noqa: E402
from accuracy import settings as settings_mod  # noqa: E402
from accuracy.attribute import Attributor, ClosestCitation, FirstCitation, SourceIndex  # noqa: E402
from accuracy.corrections import plan  # noqa: E402
from accuracy.extract import Extractor  # noqa: E402
from accuracy.schema import ATTRIBUTES  # noqa: E402
from accuracy.train import Example, train  # noqa: E402
from accuracy.verify import Rules, StringMatch, Trained  # noqa: E402
from accuracy.world.sim import EXACT_TOLERANCE, FLOOR, World  # noqa: E402

ATTRIBUTORS = {"first_citation": FirstCitation, "closest_citation": ClosestCitation, "value_match": Attributor}


def overlaps(t, c) -> bool:
    return t.product_id == c.product_id and t.attribute == c.attribute and t.start < c.end and c.start < t.end


def pair(truth, claims):
    """Each truth claim with the extracted claim that found it (or None), and the extracted claims nothing matches."""
    used, out = set(), []
    for t in truth:
        k = next((i for i, c in enumerate(claims) if i not in used and overlaps(t, c)), None)
        if k is not None:
            used.add(k)
        out.append((t, None if k is None else claims[k]))
    return out, [c for i, c in enumerate(claims) if i not in used]


def pct(x: float) -> float:
    return round(100 * x, 2)


def page_is_innocent(world: World, state, url: str, attr: str) -> bool:
    page = world.by_url.get(url)
    if page is None:
        return True
    stated = state.pages[page.id].get(attr)
    if not stated:
        return True
    truth = world.truth_facts[(page.product_id, attr)]["values"]
    a = ATTRIBUTES[attr]
    for m, v in stated.items():
        ref = truth[m]
        if a.kind == "flag":
            if v != ref:
                return False
            continue
        floor = FLOOR["money" if a.kind == "money" else a.unit]
        if abs(v - ref) / max(abs(ref), floor) > EXACT_TOLERANCE:
            return False
    return True


def annotations(world: World, extractor: Extractor, settings: dict) -> list[Example]:
    state = world.new_state()
    pool = []
    for a in world.answers(state, 0, "train"):
        for c in extractor.extract(a.text, a.locale):
            pool.append((a.id, c))
    random.Random(0).shuffle(pool)
    out = []
    for aid, c in pool[: settings["train"]["annotation_budget"]]:
        ex = Example(c, world.annotate(aid, c.start, c.end, c.product_id, c.attribute))
        ex.answer_id = aid
        out.append(ex)
    return out


def alarm_kind(c, locale: str) -> str:
    if c.qualifier == "approx":
        return "hedged number"
    if c.qualifier in ("lt", "gt"):
        return "bound"
    if c.kind == "money" and c.market != ("DE" if locale.endswith("DE") else "US"):
        return "price in another market's currency"
    if c.converted:
        return "converted unit"
    return "other"


def verification(world, extractor, settings, verifiers, answers):
    review_noise = world.cfg["reviewer_noise"]
    results = {}
    for name, v in verifiers.items():
        correct = total = caught = wrong_total = false_alarm = flagged = reviewed = 0
        by_lang = defaultdict(lambda: [0, 0])
        by_engine = defaultdict(lambda: [0, 0])
        confusion = Counter()
        alarm_kinds = Counter()
        cpu = 0.0
        for a in answers:
            t0 = time.process_time()
            claims = extractor.extract(a.text, a.locale)
            verdicts = [v.verdict(c) for c in claims]
            cpu += time.process_time() - t0
            labels = []
            for c, vd in zip(claims, verdicts, strict=True):
                label = vd.label
                if label == "review":
                    reviewed += 1
                    label = world.annotate(a.id, c.start, c.end, c.product_id, c.attribute, noise=review_noise)
                labels.append(label)
            paired, spurious = pair(world.truth(a.id), claims)
            index = {id(c): lab for c, lab in zip(claims, labels, strict=True)}
            for t, c in paired:
                pred = "missed" if c is None else index[id(c)]
                ok = pred == t.label
                correct += ok
                total += 1
                lang = "de" if a.locale.startswith("de") else "en"
                by_lang[lang][0] += not ok
                by_lang[lang][1] += 1
                by_engine[a.engine][0] += not ok
                by_engine[a.engine][1] += 1
                confusion[(t.label, pred)] += 1
                if t.label == "inaccurate":
                    wrong_total += 1
                    caught += pred == "inaccurate"
                if pred == "inaccurate":
                    flagged += 1
                    false_alarm += t.label != "inaccurate"
                    if t.label != "inaccurate":
                        alarm_kinds[alarm_kind(c, a.locale)] += 1
            for c in spurious:
                if index[id(c)] == "inaccurate":
                    flagged += 1
                    false_alarm += 1
        minutes = reviewed * settings["review"]["minutes_per_claim"]
        results[name] = {
            "accuracy": pct(correct / total),
            "wrong_claims_caught": pct(caught / wrong_total),
            "flag_precision": pct((flagged - false_alarm) / max(1, flagged)),
            "false_alarms_per_1k_claims": round(1000 * false_alarm / total, 1),
            "error_by_language": {k: pct(e / n) for k, (e, n) in sorted(by_lang.items())},
            "error_by_engine": {k: pct(e / n) for k, (e, n) in sorted(by_engine.items())},
            "sent_to_people": pct(reviewed / total),
            "review_eur_per_1k_answers": round(
                minutes / 60 * settings["review"]["eur_per_hour"] * 1000 / len(answers), 2
            ),
            "compute_usd_per_1k_answers": round(
                cpu / 3600 * settings["cost"]["vcpu_hour_usd"] * 1000 / len(answers), 5
            ),
            "ms_per_answer": round(1000 * cpu / len(answers), 3),
            "confusion": {f"{k[0]}->{k[1]}": n for k, n in sorted(confusion.items())},
            "false_alarm_kinds": dict(sorted(alarm_kinds.items())),
        }
    return results


def judge_cost(extractor, answers, vault, settings):
    toks = claims = 0
    for a in answers:
        for c in extractor.extract(a.text, a.locale):
            toks += judge.tokens(c, vault.fact(c.product_id, c.attribute))
            claims += 1
    return {
        "input_tokens_per_claim": round(toks / claims, 1),
        "usd_per_1k_answers": round(judge.cost_usd(toks, claims, settings) * 1000 / len(answers), 3),
    }


def attribution(world, extractor, settings, verifier, answers, state):
    vault = world.vault
    index = SourceIndex(vault, extractor, world.search, lambda u: world.fetch(state, u))
    methods = {k: cls(vault, index, settings) for k, cls in ATTRIBUTORS.items()}
    stats = {k: Counter() for k in methods}
    for a in answers:
        claims = extractor.extract(a.text, a.locale)
        paired, _ = pair(world.truth(a.id), claims)
        for t, c in paired:
            if c is None or t.label != "inaccurate":
                continue
            truth_cause = "model" if t.cause == "model" else world.pages[t.cause].url
            for k, m in methods.items():
                d = m.diagnose(c, a.citations)
                s = stats[k]
                s["n"] += 1
                s["model_cases"] += truth_cause == "model"
                s["correct"] += d.cause == truth_cause
                if d.cause != "model" and page_is_innocent(world, state, d.cause, c.attribute):
                    s["innocent_blamed"] += 1
                if truth_cause == "model" and d.cause != "model":
                    s["memory_blamed_on_page"] += 1
    return {
        k: {
            "cause_found": pct(s["correct"] / s["n"]),
            "innocent_page_blamed": pct(s["innocent_blamed"] / s["n"]),
            "engine_memory_blamed_on_a_page": pct(s["memory_blamed_on_page"] / max(1, s["model_cases"])),
            "wrong_claims": s["n"],
        }
        for k, s in stats.items()
    }


def loop(world, extractor, settings, verifier, weeks: int):
    vault = world.vault
    budget = settings["corrections"]["fixes_per_week"]
    out = {}
    for design in ["none", *ATTRIBUTORS]:
        state = world.new_state()
        rates, landed, sent = [], 0, Counter()
        for week in range(weeks):
            answers = world.answers(state, week)
            truth = [t for a in answers for t in world.truth(a.id)]
            rates.append(pct(sum(t.label == "inaccurate" for t in truth) / len(truth)))
            if design == "none" or week == weeks - 1:
                continue
            index = SourceIndex(vault, extractor, world.search, lambda u, s=state: world.fetch(s, u))
            attributor = ATTRIBUTORS[design](vault, index, settings)
            findings = []
            for a in answers:
                for c in extractor.extract(a.text, a.locale):
                    if verifier.verdict(c).label == "inaccurate":
                        findings.append((a.engine, c, attributor.diagnose(c, a.citations).cause))
            for t in plan(findings, vault, budget):
                sent[t.kind] += 1
                landed += world.apply(state, t.action, week)
        out[design] = {"weekly_wrong_rate": rates, "fixes_landed": landed, "tickets": dict(sorted(sent.items()))}
    return out


def examples(world, extractor, verifiers, answers, state, k: int = 6):
    index = SourceIndex(world.vault, extractor, world.search, lambda u: world.fetch(state, u))
    attributor = Attributor(world.vault, index, settings_mod.load())
    trained, rules = verifiers["trained"], verifiers["rules"]
    picked, seen = [], set()
    for a in answers:
        claims = extractor.extract(a.text, a.locale)
        paired, _ = pair(world.truth(a.id), claims)
        kinds = set()
        rows = []
        for t, c in paired:
            if c is None:
                continue
            vt, vr = trained.verdict(c), rules.verdict(c)
            d = attributor.diagnose(c, a.citations) if vt.label == "inaccurate" else None
            if t.label == "inaccurate" and t.cause == "model":
                kinds.add("memory")
            if t.label == "inaccurate" and t.cause != "model":
                kinds.add("page")
            if vr.label != t.label and vt.label == t.label:
                kinds.add("rules_wrong")
            if t.label == "unverifiable":
                kinds.add("unverifiable")
            rows.append(
                {
                    "start": c.start,
                    "end": c.end,
                    "attribute": ATTRIBUTES[c.attribute].words,
                    "truth": t.label,
                    "verdict": vt.label,
                    "rules": vr.label,
                    "p_wrong": vt.p_wrong,
                    "verified": vt.verified,
                    "reasons": vt.reasons,
                    "source": d.cause if d else None,
                    "source_why": d.why if d else None,
                }
            )
        key = (a.locale[:2], frozenset(kinds))
        if len(kinds) >= 2 and key not in seen and len(rows) >= 2:
            seen.add(key)
            picked.append(
                {
                    "id": a.id,
                    "engine": a.engine,
                    "locale": a.locale,
                    "text": a.text,
                    "citations": a.citations,
                    "claims": rows,
                }
            )
        if len(picked) >= k:
            break
    return picked


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--heldout", action="store_true")
    args = ap.parse_args()
    lock = ROOT / "config" / "heldout.lock"
    if args.heldout and lock.exists():
        sys.exit(f"the held-out world already ran ({lock.read_text().strip()}); see AGENTS.md")
    settings = settings_mod.load()
    world = World.load(ROOT / "config" / ("heldout.toml" if args.heldout else "world.toml"))
    vault = world.vault
    extractor = Extractor(vault, settings["lexicon"])
    model_path = ROOT / "models" / "verifier.json"
    report: dict = {"world": "heldout" if args.heldout else "dev"}

    training = None
    if not args.heldout:
        base = annotations(world, extractor, settings)

        def second_reader(ex):
            return world.annotate(
                ex.answer_id,
                ex.claim.start,
                ex.claim.end,
                ex.claim.product_id,
                ex.claim.attribute,
                noise=world.cfg["reviewer_noise"],
            )

        def truly(ex):
            return world.annotate(
                ex.answer_id, ex.claim.start, ex.claim.end, ex.claim.product_id, ex.claim.attribute, noise=0.0
            )

        noisy = sum(ex.label != truly(ex) for ex in base)
        variants = {}
        for name, clean, reweight in (
            ("plain", False, False),
            ("cleaned", True, False),
            ("reweighted", False, True),
            ("cleaned_and_reweighted", True, True),
        ):
            exs = copy.deepcopy(base)
            model, rep = train(exs, vault, settings, clean=clean, reweight=reweight, second_reader=second_reader)
            if clean:
                rep["flagged_truly_wrong"] = sum(base[i].label != truly(base[i]) for i in rep["flagged"])
            rep.pop("flagged", None)
            variants[name] = (model, rep)
        chosen = "cleaned_and_reweighted" if settings["train"]["reweight_language"] else "cleaned"
        model, rep = variants[chosen]
        model_path.parent.mkdir(exist_ok=True)
        model_path.write_text(json.dumps(model, indent=1) + "\n")
        vault.dump(ROOT / "examples" / "vault.json")  # what a brand would upload; the API container serves it
        training = {
            "annotated": len(base),
            "labels_wrong_before_cleaning": noisy,
            "chosen": chosen,
            **rep,
            "variants": {},
        }

    state = world.new_state()
    answers = world.answers(state, 0)
    verifiers = {
        "string_match": StringMatch(vault, settings),
        "rules": Rules(vault, settings),
        "trained": Trained.from_file(vault, settings, model_path),
        "trained_review": Trained.from_file(vault, settings, model_path, review=True),
    }

    truth = [t for a in answers for t in world.truth(a.id)]
    extracted = [c for a in answers for c in extractor.extract(a.text, a.locale)]
    found = sum(
        1 for a in answers for t, c in pair(world.truth(a.id), extractor.extract(a.text, a.locale))[0] if c is not None
    )
    report["counts"] = {
        "answers": len(answers),
        "engines": sorted(world.engines),
        "claims": len(truth),
        "labels": dict(sorted(Counter(t.label for t in truth).items())),
        "german_claims": sum(1 for a in answers if a.locale.startswith("de") for _ in world.truth(a.id)),
    }
    report["extraction"] = {"recall": pct(found / len(truth)), "precision": pct(found / max(1, len(extracted)))}
    report["verification"] = verification(world, extractor, settings, verifiers, answers)
    report["llm_judge_estimate"] = judge_cost(extractor, answers, vault, settings)
    if training is not None:
        for name, (m, _rep) in variants.items():
            v = Trained(vault, settings, m)
            r = verification(world, extractor, settings, {name: v}, answers)[name]
            training["variants"][name] = {
                "accuracy": r["accuracy"],
                "wrong_claims_caught": r["wrong_claims_caught"],
                "false_alarms_per_1k_claims": r["false_alarms_per_1k_claims"],
                "error_by_language": r["error_by_language"],
            }
        report["training"] = training
    report["attribution"] = attribution(world, extractor, settings, verifiers["trained"], answers, state)
    report["loop"] = loop(world, extractor, settings, verifiers["trained"], world.cfg["weeks"])
    report["loop_settings"] = {"weeks": world.cfg["weeks"], "fixes_per_week": settings["corrections"]["fixes_per_week"]}

    t0 = time.process_time()
    index = SourceIndex(vault, extractor, world.search, lambda u: world.fetch(state, u))
    attributor = Attributor(vault, index, settings)
    for a in answers:
        for c in extractor.extract(a.text, a.locale):
            if verifiers["trained"].verdict(c).label == "inaccurate":
                attributor.diagnose(c, a.citations)
    cpu = time.process_time() - t0
    report["throughput"] = {
        "answers_per_cpu_second": int(len(answers) / cpu),
        "vcpus_for_5m_answers_a_day": round(5_000_000 / 86400 / (len(answers) / cpu), 2),
    }
    report["examples"] = examples(world, extractor, verifiers, answers, state)

    findings = []
    for a in answers:
        for c in extractor.extract(a.text, a.locale):
            if verifiers["trained"].verdict(c).label == "inaccurate":
                findings.append((a.engine, c, attributor.diagnose(c, a.citations).cause))
    report["tickets"] = [
        {
            "kind": t.kind,
            "product": t.product,
            "attribute": t.attribute,
            "wrong_claims": t.wrong_claims,
            "engines": t.engines,
            "draft": t.draft,
        }
        for t in plan(findings, vault, 8)
    ]

    out = ROOT / "reports" / ("heldout.json" if args.heldout else "dev.json")
    out.parent.mkdir(exist_ok=True)
    # timings vary between machines; they go to a separate file so the committed report reproduces exactly
    timing = {
        "throughput": report.pop("throughput"),
        "ms_per_answer": {k: v.pop("ms_per_answer") for k, v in report["verification"].items()},
        "compute_usd_per_1k_answers": {
            k: v.pop("compute_usd_per_1k_answers") for k, v in report["verification"].items()
        },
    }
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n")
    (ROOT / "reports" / ("heldout_timing.json" if args.heldout else "dev_timing.json")).write_text(
        json.dumps(timing, indent=1) + "\n"
    )
    if args.heldout:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
        lock.write_text(f"ran at commit {commit or 'uncommitted'}\n")
    v = report["verification"]
    print(
        json.dumps(
            {
                k: {
                    x: v[k][x]
                    for x in ("accuracy", "wrong_claims_caught", "false_alarms_per_1k_claims", "error_by_language")
                }
                for k in v
            },
            indent=1,
        )
    )
    print(json.dumps(report["attribution"], indent=1))
    print({k: (x["weekly_wrong_rate"], x["fixes_landed"]) for k, x in report["loop"].items()})
    if training:
        print(json.dumps({k: x for k, x in training.items() if k != "variants"}, indent=1))
        print(json.dumps(training["variants"], indent=1))
    print(json.dumps(timing, indent=1))


if __name__ == "__main__":
    main()
