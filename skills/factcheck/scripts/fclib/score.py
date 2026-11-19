"""Credibility, result and confidence — pure functions of the final verdicts.

Same input always gives the same output. Rules are documented in
references/scoring.md and must change together with this file.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from .labels import ACCESS_NOTES, CONTEXT_FLAGS, DIRECT_STANCES, FACTORS, PRIMARY_TIERS, UNSCORED_TYPES

UNVERIFIED_SHARE_LIMIT = Decimal("0.5")
QUICK_CAP = 60


class ScoreError(ValueError):
    pass


def round_half_up(x) -> int:
    return int(Decimal(str(x)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def result_label(score: int) -> str:
    if score >= 80:
        return "符合"
    if score >= 60:
        return "大致符合"
    if score >= 40:
        return "部分符合"
    return "不符"


def confidence_level(score: int) -> str:
    if score >= 75:
        return "高"
    if score >= 50:
        return "中"
    return "低"


def _check(claims, ledger_by_id):
    for c in claims:
        if c["label"] not in FACTORS:
            raise ScoreError(f"{c['claim_id']}：未知的判定 {c['label']!r}")
        for f in c.get("context_flags", []):
            if f not in CONTEXT_FLAGS:
                raise ScoreError(f"{c['claim_id']}：未知的脈絡問題 {f!r}")
        for eid in c.get("evidence_ids", []):
            if eid not in ledger_by_id:
                raise ScoreError(f"{c['claim_id']}：證據 {eid} 不在證據表裡")


def _evidence_quality(claim, ledger_by_id) -> Decimal:
    direct = [ledger_by_id[e] for e in claim.get("evidence_ids", [])
              if ledger_by_id[e]["stance"] in DIRECT_STANCES]
    q = Decimal("0")
    if any(e["tier"] in PRIMARY_TIERS for e in direct):
        q += Decimal("0.5")
    if len({e["chain"] for e in direct}) >= 2:
        q += Decimal("0.5")
    return q


def _weighted(items, value):
    total = sum(Decimal(c["importance"]) for c in items)
    if total == 0:
        return Decimal("0")
    return sum(Decimal(c["importance"]) * value(c) for c in items) / total


def _counts(c) -> bool:
    """Opinion, prediction and vague claims never count, whatever the judge labelled them (labels.UNSCORED_TYPES)."""
    return FACTORS[c["label"]] is not None and c.get("type") not in UNSCORED_TYPES


def not_scored(c) -> bool:
    """An opinion, prediction or vague claim the judge still gave a scoring label: shown, not counted."""
    return c.get("type") in UNSCORED_TYPES and FACTORS[c["label"]] is not None


def _scored(claims):
    return [c for c in claims if _counts(c)]


def _credibility(claims):
    """How true the message is. Only the verdicts count; how well we sourced them is confidence."""
    scored = _scored(claims)
    if not scored:
        return None, "全部是意見、預測或口號，沒有可以查證的事實命題"

    accuracy = _weighted(scored, lambda c: FACTORS[c["label"]])
    flags = sorted({f for c in claims for f in c.get("context_flags", [])})
    raw = Decimal("100") * accuracy
    total_w = sum(Decimal(c["importance"]) for c in scored)
    unverified_w = sum(Decimal(c["importance"]) for c in scored if c["label"] == "unverified")
    undetermined = total_w > 0 and unverified_w / total_w >= UNVERIFIED_SHARE_LIMIT

    cred = {
        "score": round_half_up(raw),
        "raw": float(round(raw, 2)),
        "accuracy": float(round(accuracy, 4)),
        "context_flags": flags,
        "show_on_spectrum": not undetermined,
    }
    reason = "一半以上的重要性落在「無法證實」，查不到不等於假的" if undetermined else None
    return cred, reason


def _confidence(claims, ledger_by_id, run, seats):
    deductions = []

    def deduct(points, reason):
        deductions.append({"points": points, "reason": reason})

    scored = _scored(claims)
    evidence = None
    if scored:
        core = [c for c in scored if c.get("core")] or scored
        evidence = _weighted(core, lambda c: _evidence_quality(c, ledger_by_id))
        missing = round_half_up(Decimal("20") * (Decimal("1") - evidence))
        if missing:
            deduct(missing, f"證據品質 {float(round(evidence, 2))}：核心命題缺少第一手直接證據，或缺少第二條獨立證據鏈")

    ok_cross = [s for s in seats if s.get("cross_model") and s.get("status") == "ok"]
    if not ok_cross:
        deduct(20, "沒有任何執行成功的跨模型反方")
    elif not any(s.get("can_search") for s in ok_cross):
        deduct(10, "跨模型反方都不能上網，只能當審稿人")

    for c in claims:
        if c.get("review_status") == "failed" and c.get("type") not in UNSCORED_TYPES:
            deduct(10, f"{c['claim_id']} 覆核沒有通過")

    limited = []
    for c in claims:
        if not c.get("core") or not _counts(c):
            continue
        direct = [ledger_by_id[e] for e in c.get("evidence_ids", [])
                  if ledger_by_id[e]["stance"] in DIRECT_STANCES]
        if direct and not any(e.get("access_note", "full") == "full" for e in direct):
            limited.append(c["claim_id"])
    if limited:
        n = min(3, len(limited))
        deduct(10 * n, f"核心命題只有存取受限的直接證據（付費牆、被擋、只有摘要、未核對原始貼文等）：{', '.join(limited)}"
                       + ("（最多扣 3 項）" if len(limited) > 3 else ""))

    if any(c.get("legal") and c.get("law_text_obtained") is not True and c.get("type") not in UNSCORED_TYPES
           for c in claims):
        deduct(15, "涉及法條，但沒有取得條文原文")

    value = max(0, 100 - sum(d["points"] for d in deductions))
    if run.get("mode") == "quick" and value > QUICK_CAP:
        deductions.append({"points": value - QUICK_CAP, "reason": f"快速模式，信心度上限 {QUICK_CAP}"})
        value = QUICK_CAP
    return {"score": value, "level": confidence_level(value), "deductions": deductions,
            "evidence_quality": None if evidence is None else float(round(evidence, 4))}, bool(ok_cross)


def _publish_blocks(verdicts, claims, run, seats) -> list:
    """Reasons a report cannot be publishable even though its scores stand. Each is shown under the result line."""
    blocks = []
    for u in verdicts.get("unverified_rulings") or []:
        about = u.get("claim_id") or ("手法標記" if u.get("target") == "tactic" else "溯源")
        blocks.append(f"反方 {u['seat']} 的攻擊（{u['attack_id']}，{about}）判成立，但裁判沒有列出實際核對過的網址，判決照用")
    # Red-team: typing a damaging fact as vague hides it from the score. If counting the claims the judge
    # still labelled would change the result, the result hangs on that classification.
    contested = [c["claim_id"] for c in claims if not_scored(c)]
    if contested:
        counted = _result_of([{**c, "type": None} if not_scored(c) else c for c in claims])[2]
        if counted != _result_of(claims)[2]:
            blocks.append(f"{'、'.join(contested)} 被分成意見、預測或模糊說法，所以不計分，但裁判照事實判了；"
                          f"算進去的話，結果會是「{counted}」")
    if run.get("mode") == "full":
        for s in seats:
            if not str(s.get("seat", "")).startswith("X") and s.get("status") != "ok":
                blocks.append(f"反方 {s['seat']} 沒有跑成功，完整模式少了一席")
    return blocks


def _result_of(claims):
    cred, reason = _credibility(claims)
    result = "無法判定" if cred is None or not cred["show_on_spectrum"] else result_label(cred["score"])
    return cred, reason, result


def compute(verdicts: dict, run: dict, seats: list) -> dict:
    claims = verdicts.get("claims") or []
    if not claims:
        raise ScoreError("verdicts.json 沒有任何命題")
    ledger_by_id = {e["id"]: e for e in verdicts.get("ledger", [])}
    for e in ledger_by_id.values():
        if e.get("access_note", "full") not in ACCESS_NOTES:
            raise ScoreError(f"證據 {e['id']}：未知的 access_note {e['access_note']!r}")
    _check(claims, ledger_by_id)

    cred, reason, result = _result_of(claims)

    confidence, has_cross = _confidence(claims, ledger_by_id, run, seats)
    blocks = _publish_blocks(verdicts, claims, run, seats)
    publishable = run.get("mode") == "full" and confidence["level"] == "高" and has_cross and not blocks

    without = None
    if any("importance_from" in c for c in claims):
        original = [{**c, "importance": c.get("importance_from", c["importance"])} for c in claims]
        alt = compute({**verdicts, "claims": [{k: v for k, v in c.items() if k != "importance_from"} for c in original]},
                      run, seats)
        if (alt["result"], alt["publishable"]) != (result, publishable):
            without = {"result": alt["result"], "credibility": (alt["credibility"] or {}).get("score"),
                       "publishable": alt["publishable"]}
        if alt["result"] != result:
            publishable = False  # the conclusion hangs on a contested weight
        elif publishable and not alt["publishable"]:
            blocks.append("辯論中調整了命題的重要性；不調整的話，這份報告不能公開")
            publishable = False  # so does publishing

    return {
        "credibility": cred,
        "result": result,
        "result_reason": reason,
        "confidence": confidence,
        "publishable": publishable,
        "publish_blocks": blocks,
        "without_importance_changes": without,
        "claims": [
            {"claim_id": c["claim_id"], "label": c["label"], "importance": c["importance"],
             "factor": float(FACTORS[c["label"]]) if _counts(c) else None}
            for c in claims
        ],
    }
