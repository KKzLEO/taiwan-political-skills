"""Structural checks for every JSON file in a run directory.

Model output is never trusted: each stage file must pass here before the
next stage reads it. Returns a list of human-readable errors (empty = valid).
"""

from __future__ import annotations

import re
from pathlib import Path

from . import io
from .labels import (ACCESS_NOTES, ATTACK_TARGETS, CLAIM_TYPES, CONTEXT_FLAGS, FACTORS,
                     HOSTS, MODES, PUBLISHER_KINDS, REVIEW_STATUSES, STANCES)

EVIDENCE_REQUIRED_TARGETS = {"label", "evidence"}


def _nonempty(v) -> bool:
    return isinstance(v, str) and v.strip() != ""


def _is_url(v) -> bool:
    return isinstance(v, str) and re.match(r"^https?://\S+$", v) is not None


class _Errors(list):
    def need(self, ok, msg):
        if not ok:
            self.append(msg)


def _claim_ids(run: Path):
    data = io.read_json_or_none(run / "claims.json") or {}
    return [c.get("id") for c in data.get("claims", [])]


def _attacks(run: Path):
    """attack_id -> (seat, attack) for every successful opponent seat."""
    out = {}
    for path in sorted(run.glob("opponent-*.json")):
        data = io.read_json_or_none(path) or {}
        if data.get("status", "ok") != "ok":
            continue
        for a in data.get("attacks", []):
            out[a.get("id")] = (data.get("seat"), a)
    return out


def _check_ledger(err, ledger, where):
    ids = set()
    if not isinstance(ledger, list):
        err.append(f"{where}.ledger 必須是陣列")
        return ids
    for i, e in enumerate(ledger):
        p = f"{where}.ledger[{i}]"
        eid = e.get("id")
        err.need(_nonempty(eid), f"{p}.id 不能是空的")
        err.need(eid not in ids, f"{p}.id {eid} 重複")
        ids.add(eid)
        err.need(_is_url(e.get("url")), f"{p}.url 必須是 http(s) 網址，不能只寫搜尋結果")
        err.need(_nonempty(e.get("excerpt")), f"{p} 沒有原文摘錄，這筆證據不算數")
        err.need(_nonempty(e.get("chain")), f"{p}.chain 不能是空的")
        err.need(e.get("tier") in range(1, 7), f"{p}.tier 必須是 1–6")
        err.need(e.get("stance") in STANCES, f"{p}.stance 必須是 {sorted(STANCES)}")
        err.need(e.get("access_note", "full") in ACCESS_NOTES, f"{p}.access_note 必須是 {sorted(ACCESS_NOTES)}")
    return ids


def _check_verdicts(err, verdicts, claim_ids, ledger_ids, where):
    seen = []
    for i, v in enumerate(verdicts or []):
        p = f"{where}.verdicts[{i}]"
        cid = v.get("claim_id")
        seen.append(cid)
        err.need(cid in claim_ids, f"{p}.claim_id {cid} 不在 claims.json")
        label = v.get("label")
        err.need(label in FACTORS, f"{p}.label {label!r} 不是合法的判定")
        err.need(_nonempty(v.get("reasoning")), f"{p}.reasoning 不能是空的")
        for f in v.get("context_flags", []):
            err.need(f in CONTEXT_FLAGS, f"{p}.context_flags 有未知的值 {f!r}")
        for eid in v.get("evidence_ids", []):
            err.need(eid in ledger_ids, f"{p} 引用的證據 {eid} 不在證據表裡")
        if label in FACTORS and label not in ("not_factual", "unverified"):
            err.need(bool(v.get("evidence_ids")), f"{p} 判定 {label} 但沒有引用任何證據")
        law = v.get("law_text_obtained")
        err.need(law in (None, True, False), f"{p}.law_text_obtained 必須是 true/false/null")
    for cid in claim_ids:
        n = seen.count(cid)
        err.need(n == 1, f"{where}：{cid} 需要剛好一個判定（目前 {n} 個）")


def _source(d, run, ctx):
    err = _Errors()
    err.need(d.get("input_type") in {"url", "text", "image", "video"}, "input_type 必須是 url/text/image/video")
    err.need(_nonempty(d.get("original_text")) or _is_url(d.get("url")), "original_text 和 url 至少要有一個")
    err.need(_nonempty(d.get("retrieved_at")), "retrieved_at 不能是空的")
    return err


def _claims(d, run, ctx):
    err = _Errors()
    claims = d.get("claims")
    if not isinstance(claims, list) or not claims:
        return ["claims 必須是至少一項的陣列"]
    ids = set()
    for i, c in enumerate(claims):
        p = f"claims[{i}]"
        cid = c.get("id")
        err.need(isinstance(cid, str) and re.match(r"^C\d+$", cid or "") is not None, f"{p}.id 必須是 C1、C2…")
        err.need(cid not in ids, f"{p}.id {cid} 重複")
        ids.add(cid)
        err.need(_nonempty(c.get("original")), f"{p}.original 不能是空的")
        err.need(_nonempty(c.get("neutral")), f"{p}.neutral（中立改寫）不能是空的")
        err.need(c.get("type") in CLAIM_TYPES, f"{p}.type 必須是 {sorted(CLAIM_TYPES)}")
        imp = c.get("importance")
        err.need(isinstance(imp, int) and not isinstance(imp, bool) and 1 <= imp <= 5, f"{p}.importance 必須是 1–5 的整數")
        err.need(isinstance(c.get("core"), bool), f"{p}.core 必須是 true/false")
        err.need(isinstance(c.get("legal", False), bool), f"{p}.legal 必須是 true/false")
    err.need(isinstance(d.get("prompt_was_leading", False), bool), "prompt_was_leading 必須是 true/false")
    return err


def _trace(d, run, ctx):
    err = _Errors()
    pub = d.get("publisher") or {}
    err.need(pub.get("kind") in PUBLISHER_KINDS, f"publisher.kind 必須是 {sorted(PUBLISHER_KINDS)}")
    for i, s in enumerate(d.get("spread_signals", [])):
        err.need(_is_url(s.get("evidence_url")) and _nonempty(s.get("excerpt")),
                 f"spread_signals[{i}] 要附 evidence_url 和 excerpt，只能描述看得到的現象")
    for i, a in enumerate(d.get("attribution", [])):
        err.need(_is_url(a.get("report_url")) and _nonempty(a.get("report_org")),
                 f"attribution[{i}] 必須引用政府、研究機構或平台的正式報告（report_url、report_org）")
    known = ctx.get("known_tactics")
    for i, t in enumerate(d.get("tactics", [])):
        tid = t.get("tactic_id")
        err.need(_nonempty(tid), f"tactics[{i}].tactic_id 不能是空的；手法庫沒有的手法不要列")
        if known is not None:
            err.need(tid in known, f"tactics[{i}].tactic_id {tid} 不在手法庫裡")
        err.need(_nonempty(t.get("quote")), f"tactics[{i}] 要引用原文是哪一段")
    for i, f in enumerate(d.get("prior_factchecks", [])):
        err.need(_is_url(f.get("url")), f"prior_factchecks[{i}].url 必須是網址")
    return err


def _proponent(d, run, ctx):
    err = _Errors()
    ledger_ids = _check_ledger(err, d.get("ledger"), "proponent")
    _check_verdicts(err, d.get("verdicts"), _claim_ids(run), ledger_ids, "proponent")
    return err


def _opponent(d, run, ctx):
    err = _Errors()
    seat = ctx["seat"]
    err.need(d.get("seat") == seat, f"seat 必須是 {seat}（和檔名一致）")
    err.need(_nonempty(d.get("engine")), "engine 不能是空的")
    status = d.get("status", "ok")
    err.need(status in {"ok", "failed"}, "status 必須是 ok/failed")
    if status == "failed":
        return err
    claim_ids = _claim_ids(run)
    ids = set()
    for i, a in enumerate(d.get("attacks", [])):
        p = f"attacks[{i}]"
        aid = a.get("id")
        err.need(_nonempty(aid), f"{p}.id 不能是空的")
        err.need(aid not in ids, f"{p}.id {aid} 重複")
        ids.add(aid)
        cid = a.get("claim_id")
        err.need(cid is None or cid in claim_ids, f"{p}.claim_id {cid} 不在 claims.json")
        target = a.get("target")
        err.need(target in ATTACK_TARGETS, f"{p}.target 必須是 {sorted(ATTACK_TARGETS)}")
        err.need(_nonempty(a.get("argument")), f"{p}.argument 不能是空的")
        pl = a.get("proposed_label")
        err.need(pl is None or pl in FACTORS, f"{p}.proposed_label {pl!r} 不是合法的判定")
        evidence = a.get("evidence", [])
        for j, e in enumerate(evidence):
            err.need(_is_url(e.get("url")) and _nonempty(e.get("excerpt")), f"{p}.evidence[{j}] 要有網址和原文摘錄")
        if target in EVIDENCE_REQUIRED_TARGETS:
            err.need(bool(evidence), f"{p} 攻擊的是 {target}，必須附證據（網址和摘錄）")
    return err


def _rebuttal(d, run, ctx):
    err = _Errors()
    answered = [r.get("attack_id") for r in d.get("responses", [])]
    for aid in _attacks(run):
        err.need(answered.count(aid) == 1, f"攻擊 {aid} 需要剛好一則答辯")
    for i, r in enumerate(d.get("responses", [])):
        err.need(isinstance(r.get("accept"), bool), f"responses[{i}].accept 必須是 true/false")
        err.need(_nonempty(r.get("response")), f"responses[{i}].response 不能是空的")
    return err


def _judgment(d, run, ctx):
    err = _Errors()
    attacks = _attacks(run)
    ruled = [r.get("attack_id") for r in d.get("rulings", [])]
    for aid in attacks:
        err.need(ruled.count(aid) == 1, f"攻擊 {aid} 需要剛好一個裁決")
    for i, r in enumerate(d.get("rulings", [])):
        aid = r.get("attack_id")
        err.need(aid in attacks, f"rulings[{i}].attack_id {aid} 不存在")
        err.need(isinstance(r.get("upheld"), bool), f"rulings[{i}].upheld 必須是 true/false")
        err.need(_nonempty(r.get("reason")), f"rulings[{i}].reason 不能是空的")
        if r.get("upheld") is True and aid in attacks and attacks[aid][1].get("evidence"):
            err.need(bool(r.get("verified_urls")),
                     f"rulings[{i}] 判定攻擊成立，但沒有列出實際打開核對過的 verified_urls")
    ledger_ids = _check_ledger(err, d.get("ledger"), "judgment")
    _check_verdicts(err, d.get("verdicts"), _claim_ids(run), ledger_ids, "judgment")
    _check_withdrawals(err, d, run, attacks)
    return err


def _check_withdrawals(err, d, run, attacks):
    """Every upheld trace/tactic ruling lists the tags it withdraws (`withdraw_tactics`, [] to keep them).
    A withdrawn tag must be one the tracer made, and must be named in that attack or ruling."""
    tagged = None
    for i, r in enumerate(d.get("rulings", [])):
        aid = r.get("attack_id")
        attack = attacks[aid][1] if isinstance(aid, str) and aid in attacks else {}
        upheld = r.get("upheld") is True
        on_trace = attack.get("target") in ("trace", "tactic")
        p = f"rulings[{i}].withdraw_tactics"
        if upheld and on_trace and "withdraw_tactics" not in r:
            err.append(f"{p}：判成立的溯源或手法攻擊要列出撤回哪些標記，不撤就填 []")
            continue
        w = r.get("withdraw_tactics")
        if w is None or w == []:
            continue
        if not (upheld and on_trace):
            err.append(f"{p}：只有判定成立的溯源或手法攻擊可以撤回標記")
            continue
        if not isinstance(w, list) or not all(isinstance(x, str) for x in w):
            err.append(f"{p} 必須是手法編號的陣列，不撤就填 []")
            continue
        if tagged is None:
            tagged = {t.get("tactic_id") for t in (io.read_json_or_none(run / "trace.json") or {}).get("tactics", [])}
        text = f"{attack.get('argument', '')} {r.get('reason', '')}"
        for tid in w:
            err.need(tid in tagged, f"{p}：{tid} 不在 trace.json 的 tactics 裡")
            err.need(tid in text, f"{p}：{tid} 要寫在這條攻擊的論點或裁決理由裡")

def _review(d, run, ctx):
    err = _Errors()
    err.need(d.get("seat") == ctx["seat"], f"seat 必須是 {ctx['seat']}（和檔名一致）")
    claim_ids = _claim_ids(run)
    for i, r in enumerate(d.get("reviews", [])):
        err.need(r.get("claim_id") in claim_ids, f"reviews[{i}].claim_id 不在 claims.json")
        err.need(isinstance(r.get("pass"), bool), f"reviews[{i}].pass 必須是 true/false")
        err.need(_nonempty(r.get("reason")), f"reviews[{i}].reason 不能是空的")
        if r.get("pass") is False:
            err.need(isinstance(r.get("label_ok"), bool),
                     f"reviews[{i}].label_ok 必須是 true/false（不通過時要說明標籤本身對不對）")
        elif r.get("pass") is True:
            err.need(r.get("label_ok", True) is True, f"reviews[{i}].label_ok：通過就代表同意標籤，不能是 false")
    return err


def _verdicts(d, run, ctx):
    err = _Errors()
    ledger_ids = _check_ledger(err, d.get("ledger"), "verdicts")
    for i, c in enumerate(d.get("claims", [])):
        err.need(c.get("label") in FACTORS, f"claims[{i}].label 不合法")
        err.need(c.get("review_status") in REVIEW_STATUSES, f"claims[{i}].review_status 不合法")
        for eid in c.get("evidence_ids", []):
            err.need(eid in ledger_ids, f"claims[{i}] 引用的證據 {eid} 不在證據表裡")
    return err


def _run(d, run, ctx):
    err = _Errors()
    err.need(d.get("mode") in MODES, f"mode 必須是 {sorted(MODES)}")
    err.need(d.get("host") in HOSTS, f"host 必須是 {sorted(HOSTS)}")
    return err


def _models(d, run, ctx):
    err = _Errors()
    err.need(d.get("host") in HOSTS, f"host 必須是 {sorted(HOSTS)}")
    err.need(isinstance(d.get("engines"), list), "engines 必須是陣列")
    return err


FIXED = {
    "run.json": _run, "models.json": _models, "source.json": _source, "claims.json": _claims,
    "trace.json": _trace, "proponent.json": _proponent, "rebuttal.json": _rebuttal,
    "judgment.json": _judgment, "verdicts.json": _verdicts,
}


def validate_file(run: Path, name: str, known_tactics=None) -> list:
    run = Path(run)
    ctx = {"known_tactics": known_tactics}
    m = re.match(r"^(opponent|review)-([A-Za-z0-9]+)\.json$", name)
    if m:
        fn = _opponent if m.group(1) == "opponent" else _review
        ctx["seat"] = m.group(2)
    elif name in FIXED:
        fn = FIXED[name]
    else:
        return [f"不認得的檔名 {name}"]
    try:
        data = io.read_json(run / name)
    except io.ReadError as exc:
        return [str(exc)]
    if not isinstance(data, dict):
        return [f"{name} 最外層必須是 JSON 物件"]
    return list(fn(data, run, ctx))
