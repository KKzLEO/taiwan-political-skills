#!/usr/bin/env python3
"""Compare a finished batch (run_cases.py --base <folder>) with the answer keys.

    python3 evals/harness/analyze.py --base <output folder> [--repo <repo or snapshot>]

Prints, for cases: the result against expected_result, classified as exact / adjacent (one level apart) /
severe / other, using the definitions in evals/results/2026-11-19-release-criteria.md; whether a wrong result was
marked publishable; claim-level label matches (fc.py's evalcmp). For probes: whether the variants of one probe got
the same result, the same surviving tactic tags, the same time marks and claim types, how far apart their
credibility is, and whether they match the expectations written in the probe file. Then the usage totals.
"""
import argparse
import json
import sys
import tomllib
from collections import Counter, defaultdict
from pathlib import Path

LEVEL = {"符合": 3, "大致符合": 2, "部分符合": 1, "不符": 0}
UNDETERMINED = "無法判定"


def classify(expected, got):
    """exact, adjacent, severe or other (wrong but not severe), as the release criteria define them."""
    if got == expected:
        return "exact"
    if UNDETERMINED in (expected, got):
        definite = got if expected == UNDETERMINED else expected
        return "severe" if definite in ("符合", "不符") else "other"
    return "adjacent" if abs(LEVEL[expected] - LEVEL[got]) == 1 else "severe"


def variant_summary(claims_doc, verdicts):
    """How one probe variant was split: its time marks with their final labels, how many claims of each type, and
    the context flags printed beside its verdicts. Party-swapped variants of one message should give the same summary."""
    labels = {c["claim_id"]: c["label"] for c in verdicts["claims"]}
    marks = tuple(sorted(f"{kind}:{labels.get(cid)}" for kind, cid in (claims_doc.get("time_claims") or {}).items() if cid))
    types = tuple(sorted(Counter(c["type"] for c in claims_doc["claims"]).items()))
    # The report prints a flag only beside a claim judged wrong (render.py), so only those are compared.
    flags = tuple(sorted(f for c in verdicts["claims"] if c["label"] in ("false", "misleading", "mixed")
                         for f in c.get("context_flags") or []))
    return marks, types, flags


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", required=True)
    ap.add_argument("--repo", default=str(Path(__file__).resolve().parents[2]))
    args = ap.parse_args()
    base, repo = Path(args.base), Path(args.repo)
    sys.path.insert(0, str(repo / "skills/factcheck/scripts"))
    from fclib import evalcmp, io  # the snapshot's own comparison code

    listed = json.loads((base / "results.json").read_text())
    results = list({r["name"]: r for r in listed}.values())  # a job run again counts once, by its last run
    again = sorted({r["name"] for r in listed if sum(x["name"] == r["name"] for x in listed) > 1})
    batch = json.loads((base / "batch.json").read_text()) if (base / "batch.json").exists() else {}
    print(f"程式：{batch.get('commit', '?')}；主模型：{batch.get('host_model', '?')}，推理強度 {batch.get('host_effort', '?')}\n")
    if again:
        print(f"重跑過、只算最後一次的：{'、'.join(again)}\n")

    cases = sorted((r for r in results if r.get("kind") == "case" and r["status"] != "stopped after prep"),
                   key=lambda r: r["name"])  # split-only runs are listed in their own table
    tally = Counter()
    if cases:
        print("| 案例 | 預期 | 結果 | 比對 | 可信度 | 信心度 | 可公開 | 沒成功的席位、沒交的覆核 | 命題判對 | 分鐘 |")
        print("|---|---|---|---|---|---|---|---|---|---|")
    reasons = []
    for r in cases:
        path = repo / "evals/cases" / f"{r['name']}.toml"
        case = tomllib.load(open(path, "rb")) if path.exists() else {}  # a mistyped job leaves a record too
        exp = case.get("expected_result", "（找不到案例檔）")
        if r["status"] != "ok" or not case:
            tally["failed"] += 1
            print(f"| {r['name']} | {exp} | 沒有跑完（{r['status']}） | | | | | | | {r['minutes']} |")
            continue
        run = Path(r["run"])
        sc, v = io.read_json(run / "score.json"), io.read_json(run / "verdicts.json")
        kind = classify(exp, sc["result"])
        tally[kind] += 1
        tally["wrong_publishable_" + kind] += bool(sc["publishable"] and kind != "exact")
        cmp = evalcmp.compare(case, io.read_json(run / "claims.json"), v, sc)
        # A run with a seat that failed is not the full delivered flow, even when it produced a report.
        seats = [f"反方 {p.name[9:-5]} 失敗" for p in sorted(run.glob("opponent-*.json")) if io.read_json(p).get("status", "ok") != "ok"]
        seats += [f"覆核 {s} 沒交" for s in r.get("unreviewed_seats") or []]
        tally["incomplete_seats"] += bool(seats)
        reasons.append((r["name"], sc.get("publish_blocks") or []))
        print(f"| {r['name']} | {exp} | {sc['result']} | {kind} | {(sc['credibility'] or {}).get('score')} | "
              f"{sc['confidence']['score']} | {'是' if sc['publishable'] else '否'} | {'、'.join(seats) or '—'} | "
              f"{cmp['label_correct']}/{cmp['total']} | {r['minutes']} |")
    n = sum(tally[k] for k in ("exact", "adjacent", "severe", "other"))
    if cases:  # the share is of every case asked for, so a run that did not finish counts against it
        print(f"\n要跑 {len(cases)} 則，跑完 {n} 則：完全相同 {tally['exact']}（占全部的 {tally['exact'] / len(cases):.0%}）、"
              f"差一級 {tally['adjacent']}、嚴重錯誤 {tally['severe']}、其他錯誤 {tally['other']}；沒跑完 {tally['failed']}；"
              f"有席位失敗或覆核沒交的 {tally['incomplete_seats']} 則")
        print(f"結論錯卻標可公開：嚴重 {tally['wrong_publishable_severe']}、差一級 {tally['wrong_publishable_adjacent']}、"
              f"其他 {tally['wrong_publishable_other']}")
        print("\n不能公開的原因（每則全文）：")
        for name, blocks in reasons:
            print(f"- {name}：" + ("；".join(blocks) if blocks else "可公開"))

    probes = defaultdict(list)
    for r in results:
        if r.get("kind") == "probe":  # a job that crashed has only its name: probes/<file stem>/<target>
            parts = r["job"].split("/", 2)
            probes[r.get("probe") or parts[1]].append({**r, "target": r.get("target") or parts[-1]})
    for stem, rows in sorted(probes.items()):
        if all(r["status"] == "stopped after prep" for r in rows):  # split only: listed in the table below
            continue
        expect = tomllib.load(open(repo / "evals/probes" / f"{stem}.toml", "rb")).get("expect", {})
        print(f"\n| 探測 {stem} | 結果 | 可信度 | 不看時間的內容分數 | 信心度 | 可公開 | 留下的手法標記 | 計分命題的判定 | 時間標記 | 各類型的命題數 | 判定旁的脈絡標記 |"
              "\n|---|---|---|---|---|---|---|---|---|---|---|")
        seen = []
        for r in sorted(rows, key=lambda r: r["target"]):
            if r["status"] != "ok":
                print(f"| {r['target']} | 沒有跑完（{r['status']}） | | | | | | | | | |")
                continue
            run = Path(r["run"])
            sc, v = io.read_json(run / "score.json"), io.read_json(run / "verdicts.json")
            trace = io.read_json_or_none(run / "trace.json") or {}
            removed = {x["tactic_id"] for x in v.get("removed_tactics", [])}
            tags = tuple(sorted(t["tactic_id"] for t in trace.get("tactics", []) if t["tactic_id"] not in removed))
            labels = sorted(c["label"] for c in sc["claims"] if c.get("factor") is not None)
            cred = (sc["credibility"] or {}).get("score")
            marks, types, flags = variant_summary(io.read_json(run / "claims.json"), v)
            raw = (sc["credibility"] or {}).get("raw")  # the content alone: a wrong deadline sets every variant to 0
            seen.append((sc["result"], tags, cred, sc["publishable"], marks, types, raw, tuple(labels), flags))
            print(f"| {r['target']} | {sc['result']} | {cred} | {raw} | {sc['confidence']['score']} | "
                  f"{'是' if sc['publishable'] else '否'} | {'、'.join(tags) or '—'} | {'、'.join(labels) or '—'} | "
                  f"{'、'.join(marks) or '—'} | {'、'.join(f'{t}×{n}' for t, n in types)} | {'、'.join(flags) or '—'} |")
        if len(seen) != len(rows):
            print(f"{len(rows)} 版裡只有 {len(seen)} 版跑完，下面只比跑完的；沒跑完的不能當成一致。")
        if len(seen) > 1:
            same = lambda i: "是" if len({s[i] for s in seen}) == 1 else "否"  # noqa: E731
            creds = [s[2] for s in seen if s[2] is not None]
            raws = [s[6] for s in seen if s[6] is not None]
            print(f"結論相同：{same(0)}；手法標記相同：{same(1)}；可公開相同：{same(3)}；時間標記相同：{same(4)}；"
                  f"各類型的命題數相同：{same(5)}；計分命題的判定相同：{same(7)}；判定旁的脈絡標記相同：{same(8)}；"
                  f"可信度差距：{max(creds) - min(creds) if creds else '—'}；"
                  f"不看時間的內容分數差距：{round(max(raws) - min(raws), 1) if raws else '—'}")
            if expect.get("expected_result"):
                hit = sum(s[0] == expect["expected_result"] for s in seen)
                print(f"預先寫好的預期結論「{expect['expected_result']}」：{hit}/{len(seen)} 版相同")
            missing = [t for t in expect.get("required_tactics", []) if any(t not in s[1] for s in seen)]
            if expect.get("required_tactics"):
                print(f"預期要有的手法標記 {'、'.join(expect['required_tactics'])}：{'都有' if not missing else '缺 ' + '、'.join(missing)}")

    split_only = sorted((r for r in results if r["status"] == "stopped after prep"), key=lambda r: r["name"])
    if split_only:
        print("\n| 只跑到拆題 | 提問有預設立場 | 時間標記 | 各類型的命題數 | 命題（類型、重要性、中立改寫的開頭） |\n|---|---|---|---|---|")
        for r in split_only:
            doc = io.read_json(Path(r["run"]) / "claims.json")
            marks = "、".join(f"{k}:{v}" for k, v in (doc.get("time_claims") or {}).items() if v) or "—"
            types = "、".join(f"{t}×{n}" for t, n in sorted(Counter(c["type"] for c in doc["claims"]).items()))
            listed = "；".join(f"{c['id']} {c['type']}{c['importance']} {c['neutral'][:18]}" for c in doc["claims"])
            print(f"| {r['name']} | {'是' if doc.get('prompt_was_leading') else '否'} | {marks} | {types} | {listed} |")

    usage = defaultdict(Counter)
    for name, kind in (("usage.jsonl", "claude"), ("usage-codex.jsonl", "codex")):
        p = base / name
        for line in (p.read_text().splitlines() if p.exists() else []):
            rec = json.loads(line)
            t = usage[rec["tag"]]
            if kind == "claude":
                u = rec.get("usage") or {}
                t["calls"] += 1
                t["usd"] += rec.get("total_cost_usd") or 0
                t["tokens"] += sum(u.get(k) or 0 for k in ("input_tokens", "cache_creation_input_tokens",
                                                            "cache_read_input_tokens", "output_tokens"))
            else:
                t["codex_tokens"] += rec.get("tokens_used") or 0
    if usage:
        print("\n| 工作 | claude 呼叫 | API 等值美元 | token（含快取） | Codex token |\n|---|---|---|---|---|")
        for tag, t in sorted(usage.items()):
            print(f"| {tag} | {t['calls']} | {t['usd']:.2f} | {t['tokens']:,} | {t['codex_tokens']:,} |")
        total = lambda k: sum(t[k] for t in usage.values())  # noqa: E731
        print(f"| 合計 | {total('calls')} | {total('usd'):.2f} | {total('tokens'):,} | {total('codex_tokens'):,} |")


if __name__ == "__main__":
    main()
