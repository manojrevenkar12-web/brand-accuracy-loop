"""Training the verifier from annotated claims: find the labels the annotators probably got wrong and have them read
again, give German claims the same weight as English ones, fit, and export plain numbers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_predict

from .extract import Claim
from .features import ORDER, featurize, vector
from .vault import Vault


@dataclass
class Example:
    claim: Claim
    label: str  # as the annotator gave it


def _xy(examples: list[Example], vault: Vault, floors: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[int]]:
    rows, ys, langs, keep = [], [], [], []
    for i, ex in enumerate(examples):
        fact = vault.fact(ex.claim.product_id, ex.claim.attribute)
        if fact is None or ex.label not in ("accurate", "inaccurate"):
            continue
        rows.append(vector(featurize(ex.claim, fact, floors)))
        ys.append(1 if ex.label == "inaccurate" else 0)
        langs.append(ex.claim.locale[:2])
        keep.append(i)
    return np.array(rows, dtype=float), np.array(ys), np.array(langs), keep


def train(
    examples: list[Example],
    vault: Vault,
    settings: dict,
    *,
    clean: bool = True,
    reweight: bool | None = None,
    second_reader: Callable[[Example], str] | None = None,
) -> tuple[dict, dict]:
    t = settings["train"]
    floors = settings["features"]["floor"]
    reweight = t["reweight_language"] if reweight is None else reweight
    X, y, langs, keep = _xy(examples, vault, floors)
    report = {"examples": len(examples), "usable": int(len(y)), "relabelled": 0, "label_changed": 0, "flagged": []}
    if clean and second_reader is not None and len(set(y)) == 2:
        folds = StratifiedKFold(t["folds"], shuffle=True, random_state=0)
        proba = cross_val_predict(LogisticRegression(C=t["C"], max_iter=2000), X, y, cv=folds, method="predict_proba")
        given = proba[np.arange(len(y)), y]
        for row in np.where(given < t["clean_threshold"])[0]:
            ex = examples[keep[row]]
            again = second_reader(ex)
            report["relabelled"] += 1
            report["flagged"].append(keep[row])
            if again != ex.label:
                report["label_changed"] += 1
                ex.label = again
        X, y, langs, keep = _xy(examples, vault, floors)
    weights = np.ones(len(y))
    if reweight:
        for lang in set(langs):
            mask = langs == lang
            weights[mask] = len(y) / (len(set(langs)) * mask.sum())
    model = LogisticRegression(C=t["C"], max_iter=4000)
    model.fit(X, y, sample_weight=weights)
    report["languages"] = {lang: int((langs == lang).sum()) for lang in sorted(set(langs))}
    exported = {
        "features": ORDER,
        "weights": [round(float(w), 4) for w in model.coef_[0]],
        "intercept": round(float(model.intercept_[0]), 4),
        "threshold": t["threshold"],
        "trained_on": int(len(y)),
        "cleaned": bool(clean),
        "reweighted": bool(reweight),
    }
    return exported, report
