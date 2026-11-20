#!/usr/bin/env python3
"""Time and usage of the cases in one batch, and the reviews by seat (not pass conditions).

    python3 usage_stats.py --base <output folder of run_cases.py>
"""
import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--base", required=True)
base = Path(ap.parse_args().base)
results = list({r["name"]: r for r in json.loads((base / "results.json").read_text())}.values())
cases = [r for r in results if r.get("kind") == "case" and r["status"] == "ok"]
usd, tokens, by_step = defaultdict(float), defaultdict(int), defaultdict(list)
for line in (base / "usage.jsonl").read_text().splitlines():
    u = json.loads(line)
    usd[u["tag"]] += u.get("total_cost_usd") or 0
    tokens[u["tag"]] += sum((u.get("usage") or {}).get(k) or 0 for k in
                            ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens"))
    if u["tag"].startswith("case-") and u.get("code") == 0:
        by_step[(u.get("out") or "?").split(".")[0].split("-")[0]].append(((u.get("secs") or 0) / 60, u.get("total_cost_usd") or 0))
codex = defaultdict(int)
for line in (base / "usage-codex.jsonl").read_text().splitlines():
    u = json.loads(line)
    codex[u["tag"]] += u.get("tokens_used") or 0
spread = lambda xs: f"最少 {min(xs):.1f}、中位數 {statistics.median(xs):.1f}、最多 {max(xs):.1f}"  # noqa: E731
print(f"案例 {len(cases)} 則")
print("每則分鐘：", spread([r["minutes"] for r in cases]))
print("每則 API 等值美元（claude）：", spread([usd[r["name"]] for r in cases]))
print("每則 token（claude，含快取，百萬）：", spread([tokens[r["name"]] / 1e6 for r in cases]))
print("每則 token（codex，千）：", spread([codex[r["name"]] / 1e3 for r in cases]))
print("\n| 輸出檔 | 次數 | 分鐘中位數 | 美元中位數 |\n|---|---|---|---|")
for step, rows in by_step.items():
    print(f"| {step} | {len(rows)} | {statistics.median(m for m, _ in rows):.1f} | {statistics.median(c for _, c in rows):.2f} |")
print(f"\n整個資料夾合計（含中斷和重跑的）：claude 呼叫 {sum(1 for _ in (base / 'usage.jsonl').read_text().splitlines())} 次、"
      f"{sum(usd.values()):.2f} 美元、{sum(tokens.values()) / 1e6:.1f} 百萬 token；codex {sum(codex.values()) / 1e6:.2f} 百萬 token")
seats = defaultdict(lambda: [0, 0, 0])
for r in results:
    if r["status"] != "ok":
        continue
    for p in sorted(Path(r["run"]).glob("review-*.json")):
        d = json.loads(p.read_text())
        kind = "外部模型（X 開頭的席位）" if d["seat"].startswith("X") else "主模型（A、B、C）"
        for x in d.get("reviews", []):
            seats[kind][0] += 1
            seats[kind][1] += not x["pass"]
            seats[kind][2] += (not x["pass"]) and x.get("label_ok") is True
print("\n| 覆核的席位 | 覆核的命題數 | 不通過 | 其中同意判定、只對理由有意見 |\n|---|---|---|---|")
for kind, (n, failed, label_ok) in seats.items():
    print(f"| {kind} | {n} | {failed} | {label_ok} |")
