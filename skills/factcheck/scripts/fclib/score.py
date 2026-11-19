"""Credibility, result and confidence — pure functions of the final verdicts.

Same input always gives the same output. Rules are documented in
references/scoring.md and must change together with this file.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from .labels import ACCESS_NOTES, CONTEXT_FLAGS, DIRECT_STANCES, FACTORS, PRIMARY_TIERS, UNSCORED_TYPES, ZH_LABELS

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


WRONG_LABELS = {"false", "misleading", "mixed"}
RIGHT_LABELS = {"true", "mostly_true"}
DETAIL_CAP = 79  # a true main point with a wrong detail is at most 大致符合


def time_effect(c):
    """What a time claim does to the result (verdicts' `time`, from claims.json's `time_claims`); None otherwise.
    A time claim is a premise about when, not content: a right one earns nothing, and what a wrong one costs is
    fixed here instead of hanging on an importance the model picked.
      void: the deadline premise is wrong, so what the message asks the reader to do no longer stands
      cap: the implied time is wrong (old news told as new); the content is judged on its own
      unresolved: neither right nor wrong, so the report cannot say which of the above applies"""
    if not c.get("time"):
        return None
    if c["label"] in WRONG_LABELS:
        return "void" if c["time"] == "deadline" else "cap"
    return None if c["label"] in RIGHT_LABELS else "unresolved"


def _weighed(c) -> bool:
    return _counts(c) and not c.get("time")


def _credibility(claims):
    """How true the message is. The main claims (the highest importance among scored claims) decide; the other
    claims can only pull the result down, and a wrong one keeps a true main point below 符合. Time claims are
    never weighed (time_effect). Only the verdicts count; how well we sourced them is confidence."""
    scored = [c for c in claims if _weighed(c)]
    void = [c for c in claims if time_effect(c) == "void"]
    if not scored and not void:
        return None, ("除了時間命題，沒有可以查證的事實命題" if any(c.get("time") for c in claims)
                      else "全部是意見、預測或口號，沒有可以查證的事實命題")

    basis = scored or void  # a message that only asks the reader to act stands or falls with its deadline
    top = max(c["importance"] for c in basis)
    main = [c for c in basis if c["importance"] == top]
    main_accuracy = sum(FACTORS[c["label"]] for c in main) / len(main)
    overall = _weighted(basis, lambda c: FACTORS[c["label"]])
    content = min(main_accuracy, overall)
    limit = min((FACTORS[c["label"]] for c in void), default=None)  # the message is no truer than its deadline
    accuracy = content if limit is None else min(content, limit)
    score = round_half_up(Decimal("100") * accuracy)
    capped = score > DETAIL_CAP and any(  # 符合 = every claim holds, and the news is as new as the message says
        c["label"] in WRONG_LABELS for c in claims if _weighed(c) or time_effect(c) == "cap")
    # A wrong main claim, or a proven-false key fact the main point cannot stand without (importance 4), is a
    # finding even when the main claims cannot be checked. So is a wrong deadline, when it is what sets the score.
    unverified_share = Decimal(sum(c["label"] == "unverified" for c in main)) / len(main)
    settled = any(c["label"] in WRONG_LABELS for c in main) or any(
        c["label"] == "false" for c in basis if c["importance"] >= 4) or (limit is not None and limit <= content)
    undetermined = unverified_share >= UNVERIFIED_SHARE_LIMIT and not settled

    cred = {
        "score": DETAIL_CAP if capped else score,
        "raw": float(round(Decimal("100") * content, 2)),  # the content alone, before the deadline and the cap
        "main_claims": [c["claim_id"] for c in main],
        "main_accuracy": float(round(main_accuracy, 4)),
        "overall_accuracy": float(round(overall, 4)),
        "capped": capped,
        "context_flags": sorted({f for c in claims for f in c.get("context_flags", [])}),
        "show_on_spectrum": not undetermined,
    }
    reason = "主要說法有一半以上無法證實，查不到不等於假的" if undetermined else None
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


def _publish_blocks(verdicts, claims, run, seats, result) -> list:
    """Reasons a report cannot be publishable even though its scores stand. Each is shown under the result line."""
    blocks = []
    if result not in ("符合", "不符"):
        # Evals: wrong results cluster in the middle levels, where the answer keys themselves differ by a level.
        blocks.append(f"結論是「{result}」，只有「符合」或「不符」才標可公開；逐項判定和出處仍然可以引用，引用時請說明是哪一條")
    for u in verdicts.get("unverified_rulings") or []:
        about = u.get("claim_id") or ("手法標記" if u.get("target") == "tactic" else "溯源")
        blocks.append(f"反方 {u['seat']} 的攻擊（{u['attack_id']}，{about}）判成立，但裁判沒有列出實際核對過的網址，判決照用")

    def result_with(labels, base=claims):
        return _result_of([{**c, "label": labels[c["claim_id"]]} if c["claim_id"] in labels else c for c in base])[2]

    # Labels the judge gave that a missing or disagreeing review turned into unverified (finalize).
    judged = {d["claim_id"]: d["judge_label"] for d in verdicts.get("disputes") or []
              if not d.get("label_kept") and d.get("judge_label") not in (None, "unverified")}
    # Red-team: typing a damaging fact as vague hides it from the score. If counting the claims the judge
    # still labelled would change the result, the result hangs on that classification. Checked on the content
    # alone (a wrong deadline pushes both sides to 不符), and also as the judge labelled it (an unconfirmed
    # review must not lift this block).
    content = [c for c in claims if not c.get("time")]
    effects = {c["claim_id"]: time_effect(c) for c in claims if c.get("time")}
    acting = [cid for cid, e in effects.items() if e in ("void", "cap")]
    for base in (content, [{**c, "label": judged.get(c["claim_id"], c["label"])} for c in content]):
        counted = _result_of([{**c, "type": None} if not_scored(c) else c for c in base])[2]
        if counted != _result_of(base)[2]:
            # Skeptic re-review: the label may come from a review that did not confirm a change, not from the judge.
            named = "、".join(f"{c['claim_id']}（{ZH_LABELS[c['label']]}）" for c in base if not_scored(c))
            blocks.append(f"{named}被分成意見、預測或模糊說法，所以不計分，但最後拿到的是會計分的判定；"
                          f"算進去的話，{'不看時間命題的' if acting else ''}結果會是「{counted}」")
            break
    # Red-team: fewer completed reviews must never leave a report easier to publish than one every seat confirmed.
    by_id = {c["claim_id"]: c for c in claims}
    for d in verdicts.get("disputes") or []:
        if d.get("label_kept"):
            continue
        if d.get("proponent_label"):  # a judge-only change (finalize.judge_only_changes)
            blocks.append(f"{d['claim_id']} 沒有任何會改判的成立攻擊，裁判卻自己改了正方的判定，覆核也沒有全部確認，"
                          "所以改判「無法證實」")
        elif d["claim_id"] in judged and by_id.get(d["claim_id"], {}).get("type") not in UNSCORED_TYPES:
            blocks.append(f"{d['claim_id']} 的覆核沒有完成或沒有通過，裁判判的「{ZH_LABELS[d['judge_label']]}」改列「無法證實」；"
                          f"照裁判原本的判定，結果會是「{result_with({d['claim_id']: d['judge_label']})}」")
    # Time claims: say when the result rests on one, and when one was left unsettled that could change it.
    if acting and _result_of(content)[2] != result:
        blocks.append(f"結論受時間命題影響：不看 {'、'.join(acting)} 的話，結果是「{_result_of(content)[2]}」")
    for cid, e in effects.items():
        if e == "unresolved" and cid not in judged and result_with({cid: "false"}) != result:
            blocks.append(f"時間命題 {cid} 判「{ZH_LABELS[by_id[cid]['label']]}」，沒有查清楚；"
                          f"它判錯的話，結果會是「{result_with({cid: 'false'})}」")
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
    blocks = _publish_blocks(verdicts, claims, run, seats, result)
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
             "factor": float(FACTORS[c["label"]]) if _weighed(c) else None}
            for c in claims
        ],
    }
