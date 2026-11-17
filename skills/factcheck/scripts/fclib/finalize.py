"""Apply the re-review rule and produce verdicts.json.

Rule: a claim with at least one upheld attack keeps the judge's revised label
only if every seat that raised an upheld attack passes it in review-<seat>.json.
Otherwise the claim becomes `unverified` and is listed as a dispute.
"""

from __future__ import annotations

from pathlib import Path

from . import io


def _successful_attacks(run: Path):
    out = {}
    for path in sorted(run.glob("opponent-*.json")):
        data = io.read_json(path)
        if data.get("status", "ok") != "ok":
            continue
        for a in data.get("attacks", []):
            out[a["id"]] = {**a, "seat": data["seat"]}
    return out


def reviewers_needed(run) -> dict:
    """seat -> claim ids that seat must re-review (claims where its attack was upheld)."""
    run = Path(run)
    attacks = _successful_attacks(run)
    out = {}
    for r in io.read_json(run / "judgment.json").get("rulings", []):
        a = attacks.get(r["attack_id"])
        if r["upheld"] and a and a.get("claim_id"):
            out.setdefault(a["seat"], set()).add(a["claim_id"])
    return {seat: sorted(ids) for seat, ids in sorted(out.items())}


def finalize(run) -> dict:
    run = Path(run)
    claims_meta = {c["id"]: c for c in io.read_json(run / "claims.json")["claims"]}
    judgment = io.read_json(run / "judgment.json")
    attacks = _successful_attacks(run)
    rulings = {r["attack_id"]: r for r in judgment.get("rulings", []) if r["attack_id"] in attacks}

    upheld_by_claim, rejected_by_claim = {}, {}
    checked, trace_upheld = [], []
    for aid, ruling in rulings.items():
        a = attacks[aid]
        bucket = upheld_by_claim if ruling["upheld"] else rejected_by_claim
        if a.get("claim_id") is None:
            if ruling["upheld"]:
                trace_upheld.append({"attack_id": aid, "seat": a["seat"], "argument": a["argument"],
                                     "ruling_reason": ruling["reason"]})
        else:
            bucket.setdefault(a["claim_id"], []).append(aid)
        if not ruling["upheld"]:
            checked.append({"attack_id": aid, "seat": a["seat"], "claim_id": a.get("claim_id"),
                            "target": a["target"], "argument": a["argument"],
                            "ruling_reason": ruling["reason"]})

    reviews = {}
    for path in sorted(run.glob("review-*.json")):
        data = io.read_json(path)
        reviews[data["seat"]] = {r["claim_id"]: r for r in data.get("reviews", [])}

    claims_out, disputes = [], []
    for v in judgment["verdicts"]:
        cid = v["claim_id"]
        meta = claims_meta[cid]
        upheld = sorted(upheld_by_claim.get(cid, []))
        status, label, reasons = "none", v["label"], []
        if upheld:
            status = "passed"
            for seat in sorted({attacks[aid]["seat"] for aid in upheld}):
                r = reviews.get(seat, {}).get(cid)
                if r is None:
                    status = "failed"
                    reasons.append(f"席位 {seat}：覆核未完成")
                elif not r["pass"]:
                    status = "failed"
                    reasons.append(f"席位 {seat}：{r['reason']}")
            if status == "failed":
                label = "unverified"
                disputes.append({
                    "claim_id": cid,
                    "judge_label": v["label"],
                    "judge_reasoning": v["reasoning"],
                    "objections": [{"attack_id": aid, "seat": attacks[aid]["seat"],
                                    "argument": attacks[aid]["argument"]} for aid in upheld],
                    "review_reasons": reasons,
                })
        claims_out.append({
            "claim_id": cid,
            "label": label,
            "importance": meta["importance"],
            "core": meta["core"],
            "legal": meta.get("legal", False),
            "law_text_obtained": v.get("law_text_obtained"),
            "context_flags": v.get("context_flags", []),
            "evidence_ids": v.get("evidence_ids", []),
            "reasoning": v["reasoning"],
            "review_status": status,
            "upheld_attacks": upheld,
            "rejected_attacks": sorted(rejected_by_claim.get(cid, [])),
        })

    return {
        "claims": claims_out,
        "ledger": judgment["ledger"],
        "disputes": disputes,
        "checked_objections": checked,
        "trace_attacks_upheld": trace_upheld,
    }
