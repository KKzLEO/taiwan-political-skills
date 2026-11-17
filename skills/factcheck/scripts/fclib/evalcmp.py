"""Compare a finished run against an evals/cases/*.toml case with known answers."""

from __future__ import annotations

import unicodedata
from difflib import SequenceMatcher

MATCH_THRESHOLD = 0.4


def similarity(a: str, b: str) -> float:
    norm = lambda x: unicodedata.normalize("NFKC", x)
    return SequenceMatcher(None, norm(a), norm(b)).ratio()


def compare(case, claims_doc, verdicts_doc, score_doc):
    labels = {v["claim_id"]: v["label"] for v in verdicts_doc["claims"]}
    pool = [(c["id"], c["original"]) for c in claims_doc["claims"]]
    used, details = set(), []
    for exp in case.get("claim", []):
        best, best_ratio = None, 0.0
        for cid, text in pool:
            if cid in used:
                continue
            ratio = similarity(exp["original"], text)
            if ratio > best_ratio:
                best, best_ratio = cid, ratio
        if best is not None and best_ratio >= MATCH_THRESHOLD:
            used.add(best)
            got = labels.get(best)
        else:
            best, got = None, None
        details.append({"expected_original": exp["original"], "run_claim": best, "expected": exp["expected_label"],
                        "got": got, "correct": got == exp["expected_label"]})
    return {
        "case": case.get("id"),
        "matched": sum(1 for d in details if d["run_claim"]),
        "label_correct": sum(1 for d in details if d["correct"]),
        "total": len(details),
        "result_expected": case.get("expected_result"),
        "result_got": score_doc.get("result"),
        "result_correct": case.get("expected_result") == score_doc.get("result"),
        "details": details,
    }
