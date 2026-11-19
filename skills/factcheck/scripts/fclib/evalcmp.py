"""Compare a finished run against an evals/cases/*.toml case with known answers."""

from __future__ import annotations

import unicodedata
from difflib import SequenceMatcher

MATCH_THRESHOLD = 0.4


def similarity(a: str, b: str) -> float:
    norm = lambda x: unicodedata.normalize("NFKC", x)
    # autojunk would drop the common characters of a text over 200 characters and score the same sentence 0.0
    return SequenceMatcher(None, norm(a), norm(b), autojunk=False).ratio()


def compare(case, claims_doc, verdicts_doc, score_doc):
    labels = {v["claim_id"]: v["label"] for v in verdicts_doc["claims"]}
    expected = case.get("claim", [])
    pool = [(c["id"], c["original"]) for c in claims_doc["claims"]]
    # The closest pair is matched first, over all pairs, so the order of the answer key does not decide who gets
    # which claim. A run may split one sentence into several readings (an implied fact and an opinion) that quote
    # it identically; among those, take the expected reading. Then the earlier line, so the result is repeatable.
    pairs = [(similarity(exp["original"], text), labels.get(cid) == exp["expected_label"], i, j)
             for i, exp in enumerate(expected) for j, (cid, text) in enumerate(pool)]
    match, used = {}, set()
    for ratio, _, i, j in sorted(pairs, key=lambda p: (-p[0], not p[1], p[2], p[3])):
        if ratio >= MATCH_THRESHOLD and i not in match and j not in used:
            match[i] = pool[j][0]
            used.add(j)
    details = []
    for i, exp in enumerate(expected):
        best = match.get(i)
        got = labels.get(best) if best is not None else None
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
