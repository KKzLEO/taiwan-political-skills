"""Apply the re-review rule and produce verdicts.json.

Rule: a claim with at least one upheld attack is re-reviewed by every seat that
raised an upheld attack (review-<seat>.json). A claim whose label the judge
changed although no attack that revises a label was upheld on it (importance,
trace and tactic attacks do not) is re-reviewed by every seat that ran. If any
review is missing or fails, the claim is listed as a dispute. It becomes
`unverified` unless every failing reviewer explicitly accepted the label
(`label_ok: true`) and only objected to the reasoning or sourcing; then the
judge's label stays.
"""

from __future__ import annotations

from pathlib import Path

from . import io
from .labels import ZH_LABELS


def _successful_attacks(run: Path):
    out = {}
    for path in sorted(run.glob("opponent-*.json")):
        data = io.read_json(path)
        if data.get("status", "ok") != "ok":
            continue
        for a in data.get("attacks", []):
            out[a["id"]] = {**a, "seat": data["seat"]}
    return out


def _claim_of(attack):
    """The claim an attack revises. Trace and tactic attacks never revise a claim, even when the
    opponent filled in a related claim_id: tactics do not affect the score."""
    return None if attack.get("target") in ("trace", "tactic") else attack.get("claim_id")


NOT_CHECKED = "裁判沒有完成手法檢查（格式驗證沒有通過），這個標記不列為已辨識。"


def _removed(judgment, trace):
    """Tags that do not appear as identified: the judge's checks with keep false, or every tag when the
    judge's checks had to be set aside."""
    if "tactic_checks_set_aside" in judgment:
        return [{"tactic_id": t.get("tactic_id"), "reason": NOT_CHECKED}
                for t in trace.get("tactics", []) if isinstance(t, dict)]
    return [{"tactic_id": c["tactic_id"], "reason": c["reason"]}
            for c in judgment.get("tactic_checks", []) if c.get("keep") is False]


def _weight_only(attack):
    """An importance challenge: neutral_rewrite with a proposed one-step change and nothing else."""
    return attack.get("target") == "neutral_rewrite" and "proposed_importance" in attack


def _importance(orig, weight_attacks, attacks):
    """Upheld importance challenges move the weight to the adjacent level they proposed; opposite
    directions cancel. The judge never sets the value, so one ruling cannot swing it further."""
    directions = {(attacks[a]["proposed_importance"] > orig) - (attacks[a]["proposed_importance"] < orig)
                  for a in weight_attacks} - {0}
    return orig + directions.pop() if len(directions) == 1 else orig


def _ok_seats(run: Path) -> list:
    return [d["seat"] for d in map(io.read_json, sorted(run.glob("opponent-*.json"))) if d.get("status", "ok") == "ok"]


def judge_only_changes(run) -> dict:
    """claim id -> the proponent's verdict, for claims whose label the judge changed although no attack that
    revises a label was upheld on them. judge.md says to keep the proponent's label then; nothing else checks it."""
    run = Path(run)
    judgment = io.read_json(run / "judgment.json")
    attacks = _successful_attacks(run)
    revised = {_claim_of(attacks[r["attack_id"]]) for r in judgment.get("rulings", [])
               if r["upheld"] and r["attack_id"] in attacks and not _weight_only(attacks[r["attack_id"]])}
    # Red-team: a missing proponent.json must stop the run, not switch this check off.
    proponent = {v["claim_id"]: v for v in io.read_json(run / "proponent.json")["verdicts"]}
    return {v["claim_id"]: proponent[v["claim_id"]] for v in judgment["verdicts"]
            if v["claim_id"] not in revised and proponent[v["claim_id"]]["label"] != v["label"]}


def reviewers_needed(run) -> dict:
    """seat -> claim ids that seat must re-review: claims where its attack was upheld, and every judge-only
    change. Importance challenges never question the label, so they open no review that could fail."""
    run = Path(run)
    attacks = _successful_attacks(run)
    out = {}
    for r in io.read_json(run / "judgment.json").get("rulings", []):
        a = attacks.get(r["attack_id"])
        if r["upheld"] and a and _claim_of(a) and not _weight_only(a):
            out.setdefault(a["seat"], set()).add(_claim_of(a))
    seats = _ok_seats(run)
    for cid in judge_only_changes(run):
        for seat in seats:
            out.setdefault(seat, set()).add(cid)
    return {seat: sorted(ids) for seat, ids in sorted(out.items())}


def finalize(run) -> dict:
    run = Path(run)
    claims_doc = io.read_json(run / "claims.json")
    claims_meta = {c["id"]: c for c in claims_doc["claims"]}
    # Which claim is the deadline premise or the implied time (validate._check_time_claims). score.time_effect
    # decides what they do; their importance plays no part, so a challenge to it is recorded but not applied.
    time_of = {cid: kind for kind, cid in (claims_doc.get("time_claims") or {}).items() if cid}
    judgment = io.read_json(run / "judgment.json")
    attacks = _successful_attacks(run)
    rulings = {r["attack_id"]: r for r in judgment.get("rulings", []) if r["attack_id"] in attacks}

    upheld_by_claim, rejected_by_claim, weight_by_claim = {}, {}, {}
    checked, trace_upheld = [], []
    for aid, ruling in rulings.items():
        a = attacks[aid]
        bucket = upheld_by_claim if ruling["upheld"] else rejected_by_claim
        if ruling["upheld"] and _weight_only(a):
            weight_by_claim.setdefault(a.get("claim_id"), []).append(aid)
        elif _claim_of(a) is None:
            if ruling["upheld"]:
                trace_upheld.append({"attack_id": aid, "seat": a["seat"], "argument": a["argument"],
                                     "ruling_reason": ruling["reason"]})
        else:
            bucket.setdefault(_claim_of(a), []).append(aid)
        if not ruling["upheld"]:
            checked.append({"attack_id": aid, "seat": a["seat"], "claim_id": _claim_of(a),
                            "target": a["target"], "argument": a["argument"],
                            "ruling_reason": ruling["reason"]})

    reviews = {}
    for path in sorted(run.glob("review-*.json")):
        data = io.read_json(path)
        reviews[data["seat"]] = {r["claim_id"]: r for r in data.get("reviews", [])}

    judge_only, ok_seats = judge_only_changes(run), set(_ok_seats(run))
    claims_out, disputes = [], []
    for v in judgment["verdicts"]:
        cid = v["claim_id"]
        meta = claims_meta[cid]
        upheld = sorted(upheld_by_claim.get(cid, []))
        status, label, reasons, reasoning = "none", v["label"], [], v["reasoning"]
        if upheld or cid in judge_only:
            status, label_kept = "passed", True
            seats = ok_seats if cid in judge_only else {attacks[aid]["seat"] for aid in upheld}
            if not seats:
                status, label_kept = "failed", False
                reasons.append("沒有可以覆核的反方席位")
            for seat in sorted(seats):
                r = reviews.get(seat, {}).get(cid)
                if r is None:
                    status, label_kept = "failed", False
                    reasons.append(f"席位 {seat}：覆核未完成")
                elif not r["pass"]:
                    status = "failed"
                    label_kept = label_kept and r.get("label_ok") is True
                    reasons.append(f"席位 {seat}：{r['reason']}")
            if status == "failed":
                if not label_kept:
                    if label != "unverified":  # the judge's reasoning argues for a label the claim no longer has
                        reasoning = f"覆核沒有通過，改列「無法證實」；裁判原本判「{ZH_LABELS[label]}」，理由是：{reasoning}"
                    label = "unverified"
                disputes.append({
                    "claim_id": cid,
                    "judge_label": v["label"],
                    "label_kept": label_kept,
                    "judge_reasoning": v["reasoning"],
                    "objections": [{"attack_id": aid, "seat": attacks[aid]["seat"],
                                    "argument": attacks[aid]["argument"]} for aid in upheld],
                    "review_reasons": reasons,
                    **({"proponent_label": judge_only[cid]["label"]} if cid in judge_only else {}),
                })
        weight = sorted(weight_by_claim.get(cid, []))
        importance = meta["importance"] if cid in time_of else _importance(meta["importance"], weight, attacks)
        claims_out.append({
            "claim_id": cid,
            "label": label,
            "importance": importance,
            **({"importance_from": meta["importance"]} if importance != meta["importance"] else {}),
            **({"importance_attacks": [{"attack_id": aid, "seat": attacks[aid]["seat"],
                                        "proposed": attacks[aid]["proposed_importance"],
                                        "ruling_reason": rulings[aid]["reason"]} for aid in weight]} if weight else {}),
            "type": meta.get("type"),
            "time": time_of.get(cid),
            "core": meta["core"],
            "legal": meta.get("legal", False),
            "law_text_obtained": v.get("law_text_obtained"),
            "context_flags": v.get("context_flags", []),
            "evidence_ids": v.get("evidence_ids", []),
            "reasoning": reasoning,
            "review_status": status,
            "upheld_attacks": upheld,
            "rejected_attacks": sorted(rejected_by_claim.get(cid, [])),
        })

    # Upheld rulings whose checked URLs the judge still left out after a retry (validate.fallback):
    # the ruling stands; score blocks publishing and render says so under the result line.
    unverified = [{"attack_id": aid, "seat": attacks[aid]["seat"], "claim_id": _claim_of(attacks[aid]),
                   "target": attacks[aid]["target"]}
                  for aid in sorted(set(judgment.get("rulings_unverified") or []))
                  if aid in rulings and rulings[aid]["upheld"]]

    return {
        "claims": claims_out,
        "unverified_rulings": unverified,
        "ledger": judgment["ledger"],
        "disputes": disputes,
        "checked_objections": checked,
        "trace_attacks_upheld": trace_upheld,
        "removed_tactics": _removed(judgment, io.read_json_or_none(run / "trace.json") or {}),
    }
