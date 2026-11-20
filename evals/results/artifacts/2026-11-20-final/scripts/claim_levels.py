#!/usr/bin/env python3
"""How each answer-key claim compares with the claim the run matched it to (not a pass condition).

    python3 claim_levels.py --base <output folder of run_cases.py> --repo <snapshot the batch ran from>
"""
import argparse
import json
import sys
import tomllib
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--base", required=True)
ap.add_argument("--repo", required=True)
a = ap.parse_args()
base, repo = Path(a.base), Path(a.repo)
sys.path.insert(0, str(repo / "skills/factcheck/scripts"))
from fclib import evalcmp, io  # noqa: E402  the snapshot's own matching

SIDE = {"true": "對", "mostly_true": "對", "false": "錯", "misleading": "錯", "mixed": "錯", "unverified": "查不到",
        "not_factual": "非事實"}
results = list({r["name"]: r for r in json.loads((base / "results.json").read_text())}.values())
total = dict(key=0, matched=0, exact=0, same_side=0, other_side=0, unmatched=0)
print("| 案例 | 答案卷的命題 | 對得上 | 判定完全相同 | 同一邊 | 不同邊的 | 對不上的（開頭） |")
print("|---|---|---|---|---|---|---|")
for r in sorted((x for x in results if x.get("kind") == "case" and x["status"] == "ok"), key=lambda x: x["name"]):
    case = tomllib.load(open(repo / "evals/cases" / f"{r['name']}.toml", "rb"))
    run = Path(r["run"])
    cmp = evalcmp.compare(case, io.read_json(run / "claims.json"), io.read_json(run / "verdicts.json"),
                          io.read_json(run / "score.json"))
    matched = [d for d in cmp["details"] if d["run_claim"]]
    same = [d for d in matched if SIDE[d["got"]] == SIDE[d["expected"]]]
    other = [f"{d['run_claim']}：答案 {d['expected']}、工具 {d['got']}" for d in matched if SIDE[d["got"]] != SIDE[d["expected"]]]
    missing = [d["expected_original"][:12] for d in cmp["details"] if not d["run_claim"]]
    for k, n in (("key", cmp["total"]), ("matched", len(matched)), ("exact", cmp["label_correct"]),
                 ("same_side", len(same)), ("other_side", len(other)), ("unmatched", len(missing))):
        total[k] += n
    print(f"| {r['name']} | {cmp['total']} | {len(matched)} | {cmp['label_correct']} | {len(same)} | "
          f"{'；'.join(other) or '—'} | {'／'.join(missing) or '—'} |")
print(f"\n合計：答案卷 {total['key']} 條，對得上 {total['matched']} 條；判定完全相同 {total['exact']}、"
      f"判定不同但同一邊 {total['same_side'] - total['exact']}、不同邊 {total['other_side']}；對不上 {total['unmatched']}")
