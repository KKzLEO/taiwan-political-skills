#!/usr/bin/env python3
"""Write site/assets/run-data.js from the worked example, so the run the front page plays is the real one.

    python3 site/tools/build_run.py

Every string the window shows is taken from the files of examples/<run>/; long passages are cut at a
sentence end and marked with an ellipsis. The counts in the one-line summaries are counted here.
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills/factcheck/scripts"))
from fclib.labels import CLAIM_TYPES, TIER_NAMES, ZH_LABELS  # noqa: E402
from fclib.render import INPUT, LENS  # noqa: E402

RUN = ROOT / "examples/20261120-1441-機車大燈罰三千"
OUT = ROOT / "site/assets/run-data.js"
SEATS = ("A", "B", "C", "X1")
MODES = {"full": "完整模式", "quick": "快速模式"}
HOSTS = {"claude": "Claude Code", "codex": "Codex"}
TARGETS = {"label": "判定", "evidence": "證據", "reasoning": "理由", "neutral_rewrite": "問法", "trace": "溯源", "tactic": "手法標記"}
REVIEWED = {"none": "不需覆核", "passed": "覆核通過", "failed": "覆核沒過"}
BLOB = "https://github.com/KKzLEO/taiwan-political-skills/blob/main/examples/"
RAW_LINES, RAW_WIDTH = 16, 92


def load(name):
    return json.loads((RUN / name).read_text(encoding="utf-8"))


def cut(text, limit):
    """The start of a passage, ended at a sentence or clause if one closes in the second half of the room."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    head = text[:limit]
    for mark in "。；，":
        at = head.rfind(mark)
        if at >= limit // 2:
            return head[:at] + "…"
    return head + "…"


def raw(name):
    """The top of a file exactly as it was left, long lines cut short, so the window can show the thing itself."""
    lines = (RUN / name).read_text(encoding="utf-8").splitlines()
    return {"file": name, "href": BLOB + f"{RUN.name}/{name}", "total": len(lines),
            "lines": [ln if len(ln) <= RAW_WIDTH else ln[:RAW_WIDTH] + "…" for ln in lines[:RAW_LINES]]}


def build():
    run, claims, trace = load("run.json"), load("claims.json"), load("trace.json")
    proponent, rebuttal, judgment = load("proponent.json"), load("rebuttal.json"), load("judgment.json")
    verdicts, score = load("verdicts.json"), load("score.json")
    opponents = {seat: load(f"opponent-{seat}.json") for seat in SEATS}
    reviews = {p.stem.split("-")[1]: json.loads(p.read_text(encoding="utf-8")) for p in sorted(RUN.glob("review-*.json"))}
    asked = {c["id"]: c["neutral"] for c in claims["claims"]}

    attacks = [dict(a, seat=seat) for seat in SEATS for a in opponents[seat]["attacks"]]
    outside = sum(1 for a in attacks if opponents[a["seat"]]["lens"] == "external")
    accepted = Counter(r["accept"] for r in rebuttal["responses"])
    upheld = Counter(r["upheld"] for r in judgment["rulings"])
    checks = [dict(r, seat=seat) for seat, file in reviews.items() for r in file["reviews"]]
    tiers = Counter(s["tier"] for s in proponent["ledger"])
    unscored = [c["id"] for c in claims["claims"] if c["type"] in ("O", "P", "U")]

    steps = [
        {"id": "input", "name": "讀入", "file": "input.json",
         "does": "收下來的時候一個字都不改。",
         "summary": f'{INPUT[load("input.json")["input_type"]]}，{MODES[run["mode"]]}',
         "kind": "message", "text": load("input.json")["content"].strip()},
        {"id": "claims", "name": "拆題", "file": "claims.json",
         "does": "由一個看不到你怎麼問的獨立程序，拆成可以查證的說法，改寫成不帶立場的句子。",
         "summary": f'拆成 {len(claims["claims"])} 條說法' + (f'，其中 {len(unscored)} 條是意見，不計分' if unscored else ""),
         "kind": "claims",
         "rows": [{"id": c["id"], "quote": c["original"], "text": c["neutral"], "type": CLAIM_TYPES[c["type"]],
                   "importance": c["importance"]} for c in claims["claims"]]},
        {"id": "trace", "name": "溯源", "file": "trace.json",
         "does": "最早在哪裡出現、有沒有別的版本、有沒有人查過。查核機構的結論只當線索。",
         "summary": ("查不到最早的出處" if not trace["first_seen"] else "找到最早的出處")
                    + f'；有 {len(trace["variants"])} 個相近的舊版本、{len(trace["prior_factchecks"])} 份別人的查核報告',
         "kind": "notes",
         "rows": [{"tag": "相近的舊版本", "when": v["date"], "text": cut(v["difference"], 96)} for v in trace["variants"]]
                 + [{"tag": p["org"], "when": p["date"], "text": cut(p["label"], 96)} for p in trace["prior_factchecks"]]},
        {"id": "proponent", "name": "正方查證", "file": "proponent.json",
         "does": "逐句去找第一手資料：法條原文、立法院紀錄、官方說明。",
         "summary": f'{len(proponent["ledger"])} 筆來源，其中 {tiers[1]} 筆是{TIER_NAMES[1]}',
         "kind": "sources",
         "rows": [{"id": s["id"], "title": cut(s["title"], 44), "by": cut(s["publisher"], 22), "tier": TIER_NAMES[s["tier"]]}
                  for s in proponent["ledger"][:7]],
         "more": len(proponent["ledger"]) - 7},
        {"id": "opponents", "name": "反方", "file": "opponent-*.json",
         "does": "三席各自檢查證據、找反證、看有沒有偏向哪一方；再請另一家公司的模型從頭挑一次。",
         "summary": f'四席共搜尋 {sum(o["searches_run"] for o in opponents.values())} 次，提出 {len(attacks)} 條質疑，'
                    f'其中 {outside} 條來自另一家公司的模型',
         "kind": "attacks",
         "seats": [{"seat": seat, "role": LENS[o["lens"]], "engine": o["engine"], "searches": o["searches_run"],
                    "attacks": len(o["attacks"])} for seat, o in opponents.items()],
         "rows": [{"id": a["id"], "seat": a["seat"], "on": a.get("claim_id") or TARGETS[a["target"]],
                   "text": cut(a["argument"], 92)} for a in attacks]},
        {"id": "rebuttal", "name": "正方答辯", "file": "rebuttal.json",
         "does": "每一條質疑都要回應：接受，或是拿出證據反駁。",
         "summary": f'{len(rebuttal["responses"])} 條質疑：接受 {accepted[True]} 條，反駁 {accepted[False]} 條',
         "kind": "rulings",
         "rows": [{"id": r["attack_id"], "yes": r["accept"], "word": "接受" if r["accept"] else "反駁",
                   "text": cut(r["response"], 92)} for r in rebuttal["responses"]]},
        {"id": "judgment", "name": "裁判", "file": "judgment.json",
         "does": "一個沒有參與辯論的 AI 逐條裁決。判質疑成立時，要列出自己實際打開核對過的網址。",
         "summary": f'質疑成立 {upheld[True]} 條，不成立 {upheld[False]} 條；來源增加到 {len(judgment["ledger"])} 筆',
         "kind": "rulings",
         "rows": [{"id": r["attack_id"], "yes": r["upheld"], "word": "成立" if r["upheld"] else "不成立",
                   "text": cut(r["reason"], 92)} for r in judgment["rulings"]]},
        {"id": "review", "name": "覆核", "file": "review-*.json",
         "does": "提出質疑的那幾席回頭檢查裁判改過的地方。沒有通過的，那一條改列「無法證實」。",
         "summary": f'回頭檢查了 {len(checks)} 處，' + ("全部通過" if all(c["pass"] for c in checks) else f'{sum(not c["pass"] for c in checks)} 處沒有通過'),
         "kind": "rulings",
         "rows": [{"id": f'{c["seat"]} → {c["claim_id"]}', "yes": c["pass"], "word": "通過" if c["pass"] else "不通過",
                   "text": cut(c["reason"], 92)} for c in checks]},
        {"id": "score", "name": "程式算分", "file": "score.json、report.md",
         "does": "可信度、信心度、能不能公開引用，都由程式照固定規則算，不是 AI 給的。",
         "summary": "同一份判定，每次算出來都是同樣的分數",
         "kind": "report",
         "result": score["result"], "credibility": score["credibility"]["score"],
         "confidence": score["confidence"]["score"], "level": score["confidence"]["level"],
         "publishable": score["publishable"],
         "rows": [{"id": c["claim_id"], "text": asked[c["claim_id"]], "label": ZH_LABELS[c["label"]],
                   "revised": c["rewrite_revised"], "reviewed": REVIEWED[c["review_status"]],
                   "scored": c["label"] != "not_factual" and c["type"] not in ("O", "P", "U")} for c in verdicts["claims"]]},
    ]
    files = ["input.json", "claims.json", "trace.json", "proponent.json", "opponent-X1.json", "rebuttal.json",
             "judgment.json", "review-X1.json", "score.json"]
    for step, name in zip(steps, files):
        step["raw"] = raw(name)
    return {"folder": RUN.name, "host": HOSTS[run["host"]], "mode": MODES[run["mode"]],
            "at": run["created_at"][:16].replace("T", " "), "steps": steps}


TEXT = "// Written by site/tools/build_run.py from examples/. Do not edit by hand.\nwindow.FACTCHECK_RUN = " + \
    json.dumps(build(), ensure_ascii=False, indent=1) + ";\n"

if __name__ == "__main__":
    OUT.write_text(TEXT, encoding="utf-8")
    data = build()
    print(OUT.relative_to(ROOT), len(TEXT), "chars")
    for s in data["steps"]:
        print(" ", s["name"], "|", s["summary"])
