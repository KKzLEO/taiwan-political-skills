#!/usr/bin/env python3
"""Secondary numbers for the final blind batch (not pass conditions; listed in the pre-registration).

    python3 .work/final/extra_metrics.py --base .work/final/full --repo .work/snap/d838c71
"""
import argparse
import json
import sys
import tomllib
from collections import Counter
from pathlib import Path

# From the pre-registration table: the adjacent level the auditors called defensible, written before the run.
ALSO = {"case-027": "部分符合", "case-028": "符合", "case-029": "不符", "case-030": "大致符合", "case-031": "大致符合",
        "case-033": "部分符合", "case-034": "部分符合", "case-035": "部分符合", "case-036": "部分符合", "case-037": "部分符合"}
EXPECT_TIME = {"case-036": "relative", "case-037": "deadline"}

ap = argparse.ArgumentParser()
ap.add_argument("--base", required=True)
ap.add_argument("--repo", required=True)
a = ap.parse_args()
base, repo = Path(a.base), Path(a.repo)
results = list({r["name"]: r for r in json.loads((base / "results.json").read_text())}.values())
cases = sorted((r for r in results if r.get("kind") == "case"), key=lambda r: r["name"])

exact = lenient = publishable = publishable_right = 0
print("| 案例 | 預期 | 結果 | 可信度 | 內容分數 | 時間標記（判定） | 可公開 | 主要說法 | 命題：類型 重要性 判定 |")
print("|---|---|---|---|---|---|---|---|---|")
levels = Counter()
for r in cases:
    key = tomllib.load(open(repo / "evals/cases" / f"{r['name']}.toml", "rb"))
    exp = key["expected_result"]
    if r["status"] != "ok":
        print(f"| {r['name']} | {exp} | 沒有跑完（{r['status']}） | | | | | | |")
        continue
    run = Path(r["run"])
    sc = json.loads((run / "score.json").read_text())
    v = json.loads((run / "verdicts.json").read_text())
    c = json.loads((run / "claims.json").read_text())
    meta = {x["id"]: x for x in c["claims"]}
    got = sc["result"]
    exact += got == exp
    lenient += got == exp or ALSO.get(r["name"]) == got
    publishable += sc["publishable"]
    publishable_right += sc["publishable"] and got == exp
    levels[(exp, got)] += 1
    labels = {x["claim_id"]: x["label"] for x in v["claims"]}
    marks = "、".join(f"{k}:{cid}（{labels.get(cid)}）" for k, cid in (c.get("time_claims") or {}).items() if cid) or "—"
    want = EXPECT_TIME.get(r["name"])
    if want:
        marks += " ✓" if (c.get("time_claims") or {}).get(want) else f" ✗（預期有 {want}）"
    cred = sc["credibility"] or {}
    listed = "；".join(f"{x['claim_id']} {meta[x['claim_id']]['type']}{x['importance']} {x['label']}" for x in v["claims"])
    print(f"| {r['name']} | {exp} | {got} | {cred.get('score')} | {cred.get('raw')} | {marks} | "
          f"{'是' if sc['publishable'] else '否'} | {'、'.join(cred.get('main_claims') or [])} | {listed} |")

n = len(cases)
print(f"\n完全相同 {exact}/{n}；把開跑前複核員寫的「相鄰一級也講得通」算成對：{lenient}/{n}")
print(f"標可公開 {publishable} 則，其中結論和答案相同 {publishable_right} 則")
print("預期 → 結果：" + "；".join(f"{e}→{g} ×{k}" for (e, g), k in sorted(levels.items())))

# confidence: what kept 符合/不符 results from being publishable
print("\n結論是符合或不符、卻不可公開的原因：")
for r in cases:
    if r["status"] != "ok":
        continue
    sc = json.loads((Path(r["run"]) / "score.json").read_text())
    if sc["result"] in ("符合", "不符") and not sc["publishable"]:
        print(f"- {r['name']}（{sc['result']}，信心度 {sc['confidence']['score']}）：" + "；".join(sc.get("publish_blocks") or []))
        for d in sc["confidence"]["deductions"]:
            print(f"    −{d['points']} {d['reason']}")
sys.exit(0)
