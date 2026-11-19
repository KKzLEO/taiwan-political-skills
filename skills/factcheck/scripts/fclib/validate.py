"""Structural checks for every JSON file in a run directory.

Model output is never trusted: each stage file must pass here before the
next stage reads it. Returns a list of human-readable errors (empty = valid).
"""

from __future__ import annotations

import copy
import re
from pathlib import Path

from . import finalize, io, spans
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


def _items(err, value, where, kind=None) -> list:
    """A list field; the caller passes [] for a key that was left out. Anything else, null included, is one error
    that names the field, and so is an item that is not a `kind`: later steps index these without checking again."""
    ok = isinstance(value, list) and (kind is None or all(isinstance(x, kind) for x in value))
    err.need(ok, f"{where} 必須是{'物件的' if kind is dict else ''}陣列（沒有就寫 []，不要寫 null）")
    return value if ok else []


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
        for f in _items(err, v.get("context_flags", []), f"{p}.context_flags"):
            err.need(f in CONTEXT_FLAGS, f"{p}.context_flags 有未知的值 {f!r}")
        for eid in _items(err, v.get("evidence_ids", []), f"{p}.evidence_ids"):
            err.need(eid in ledger_ids, f"{p} 引用的證據 {eid} 不在證據表裡")
        if label in FACTORS and label not in ("not_factual", "unverified"):
            err.need(bool(v.get("evidence_ids")), f"{p} 判定 {label} 但沒有引用任何證據")
        law = v.get("law_text_obtained")
        err.need(law in (None, True, False), f"{p}.law_text_obtained 必須是 true/false/null")
    for cid in claim_ids:
        n = seen.count(cid)
        err.need(n == 1, f"{where}：{cid} 需要剛好一個判定（目前 {n} 個）")


INPUT_TYPES = {"url", "text", "image", "video"}


def _input(d, run, ctx):
    """What the host collected for step 1 (fc.py input); the isolated prep role turns it into source and claims."""
    err = _Errors()
    err.need(d.get("input_type") in INPUT_TYPES, "input_type 必須是 url/text/image/video")
    err.need(_nonempty(d.get("content")), "content 不能是空的")
    if d.get("input_type") == "url":
        err.need(_is_url(d.get("content")), "網址輸入的 content 必須是 http(s) 網址")
    err.need(d.get("url") is None or _is_url(d.get("url")), "url 必須是 http(s) 網址或 null")
    err.need(isinstance(d.get("prompt"), str), "prompt 必須是字串（使用者這次怎麼問）")
    extra = sorted(set(d) - {"input_type", "content", "prompt", "url"})
    err.need(not extra, f"input.json 只能有 input_type、content、prompt、url，多了 {extra}")
    return err


def input_errors(data) -> list:
    return list(_input(data, None, {}))


def _source(d, run, ctx):
    err = _Errors()
    err.need(d.get("input_type") in {"url", "text", "image", "video"}, "input_type 必須是 url/text/image/video")
    err.need(_nonempty(d.get("original_text")) or _is_url(d.get("url")), "original_text 和 url 至少要有一個")
    err.need(_nonempty(d.get("retrieved_at")), "retrieved_at 不能是空的")
    # A publication time switches the time claims off (_check_time_claims), so "14:15" or 「不明」 must not count as one.
    published = d.get("published_at")
    err.need(published in (None, "") or (isinstance(published, str) and re.match(r"^\d{4}-\d{2}-\d{2}", published)),
             "published_at 必須是 YYYY-MM-DD 開頭的日期；內容本身看不出發布日期（只有時刻、或完全沒有）就填 null")
    return err


STATED, IMPLIED = {"F", "S"}, {"I"}


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
    _check_time_claims(err, d.get("time_claims"), claims, run)
    _check_claim_spans(err, claims, run)
    return err


TIME_KINDS = ("deadline", "relative")


def _check_time_claims(err, marks, claims, run):
    """Which implied claim is the deadline premise and which the implied time (neutralize.md rule 6). Both keys
    are required, so "none" is an answer the model wrote down rather than something it may have skipped."""
    if not isinstance(marks, dict) or set(marks) != set(TIME_KINDS):
        err.append('time_claims 必須是 {"deadline": 命題編號或 null, "relative": 命題編號或 null}，兩個鍵都要有；'
                   "沒有這種時間命題就填 null")
        return
    implied = {c.get("id") for c in claims if isinstance(c, dict) and c.get("type") in IMPLIED}
    for kind in TIME_KINDS:
        err.need(marks[kind] is None or (isinstance(marks[kind], str) and marks[kind] in implied),
                 f"time_claims.{kind} 必須是 null，或一條隱含命題（type 是 I）的編號")
    marked = [v for v in marks.values() if v is not None]
    err.need(len(marked) == len(set(map(str, marked))), "time_claims：同一條命題不能同時是期限前提和暗示的時間；"
                                                        "同一句話兩種都符合時，只填 deadline")
    published = (io.read_json_or_none(run / "source.json") or {}).get("published_at")
    err.need(not marked or not str(published or "").strip(),
             f"time_claims：內容有發布時間（{published}），讀者看得到日期，不用時間命題；兩個都填 null，"
             "那兩條隱含命題也一起刪掉，相對時間照發布時間換算成日期")




def _library(ctx):
    """tactic_id -> {layer, features: {id: kind}}; a plain set of ids only checks the ids; None skips both."""
    known = ctx.get("known_tactics")
    if known is None or isinstance(known, dict):
        return known
    return {tid: None for tid in known}


def tactic_errors(trace, run, lib, only=None):
    """Errors for trace.json's tactic tags, each starting with "tactics". `only` limits to one entry index."""
    tactics = trace.get("tactics", [])
    if not isinstance(tactics, list):
        return ["tactics 必須是陣列"]
    hay = spans.literal((io.read_json_or_none(run / "source.json") or {}).get("original_text"))
    has_report = bool(trace.get("attribution"))
    errs, first = [], {}
    for i, t in enumerate(tactics):
        if only is not None and i != only:
            continue
        tid = t.get("tactic_id") if isinstance(t, dict) else None
        if tid in first and _nonempty(tid):
            errs.append(f"tactics[{i}]：{tid} 標了兩次。同一個手法只列一次，把特徵合併、引文用「……」接起來")
            continue
        first.setdefault(tid, i)
        errs.extend(_tag_errors(i, t, lib, hay, has_report))
    return errs


_TAG_INDEX = re.compile(r"^tactics\[(\d+)\]")
_RULING_URL_MSG = "判定攻擊成立，但沒有列出實際打開核對過的 verified_urls"
_RULING_URL = re.compile(r"^rulings\[(\d+)\] " + _RULING_URL_MSG + "$")


def set_aside_tactics(obj, run, name, lib, errors):
    """Last resort once a role has retried: move the tags (trace.json) or tag checks (judgment.json)
    that still break the rules out of the way, keeping their content and errors in the file.
    Returns the new object, or None when anything other than tags is wrong."""
    if not errors or not isinstance(obj, dict):
        return None
    new = copy.deepcopy(obj)
    if name == "trace.json":
        found = [_TAG_INDEX.match(e) for e in errors]
        if not all(found) or not isinstance(obj.get("tactics"), list):
            return None
        bad = {}
        for e, m in zip(errors, found):
            bad.setdefault(int(m.group(1)), []).append(e)
        new["tactics"] = [t for i, t in enumerate(obj["tactics"]) if i not in bad]
        new["set_aside_tactics"] = list(obj.get("set_aside_tactics", [])) + [
            {"entry": obj["tactics"][i], "errors": bad[i]} for i in sorted(bad) if i < len(obj["tactics"])]
        return new
    if name == "judgment.json" and all(e.startswith("tactic_checks") for e in errors):
        new.pop("tactic_checks", None)
        new["tactic_checks_set_aside"] = list(errors)
        return new
    return None


def fallback(obj, run, name, lib, errors):
    """Last resort once a role has retried; returns the new object, or None when anything else is wrong.

    - Tags (trace.json) or tag checks (judgment.json) that still break the rules are set aside: tags
      never affect the score.
    - Upheld rulings whose checked URLs the judge still leaves out stay upheld but are listed in
      `rulings_unverified`: finalize discloses them and score blocks publishing. Regression (round 2,
      case-011): one missing URL list stopped the whole check at its most expensive step.
    """
    if not errors or not isinstance(obj, dict):
        return None
    if name != "judgment.json":
        return set_aside_tactics(obj, run, name, lib, errors)
    tags = [e for e in errors if e.startswith("tactic_checks")]
    urls = [_RULING_URL.match(e) for e in errors if not e.startswith("tactic_checks")]
    if not all(urls):
        return None
    new = set_aside_tactics(obj, run, name, lib, tags) if tags else copy.deepcopy(obj)
    if urls:
        rulings = obj.get("rulings") or []
        new["rulings_unverified"] = sorted({rulings[int(m.group(1))].get("attack_id") for m in urls})
    return new


def _tag_errors(i, t, lib, hay, has_report):
    p = f"tactics[{i}]"
    if not isinstance(t, dict) or not _nonempty(t.get("tactic_id")):
        return [f"{p}.tactic_id 不能是空的；手法庫沒有的手法不要列"]
    tid = t["tactic_id"]
    if lib is None:
        return []
    if tid not in lib:
        return [f"{p}.tactic_id {tid} 不在手法庫裡"]
    if lib[tid] is None:
        return []
    kinds, errs = lib[tid]["features"], []
    feats = t.get("features")
    if not isinstance(feats, list) or not feats or not all(isinstance(f, str) for f in feats):
        return [f"{p}.features 要列出符合的特徵代號（例如 [\"a\", \"c\"]），不能是空的"]
    unknown = [f for f in feats if f not in kinds]
    if unknown:
        errs.append(f"{p}.features：{tid} 沒有特徵 {'、'.join(unknown)}")
    if len(set(feats)) != len(feats):
        errs.append(f"{p}.features 有重複的代號")
    cited = {kinds[f] for f in feats if f in kinds}
    if cited and cited <= {"clue"}:
        errs.append(f"{p}：{tid} 只列了「只是線索」的特徵，至少要有一項「看得到」或「查證得到」的特徵成立")
    quote = t.get("quote")
    if "visible" in cited and not _nonempty(quote):
        errs.append(f"{p}.quote 必填：列了「看得到」的特徵，就要逐字引用訊息原文")
    if _nonempty(quote):
        parts = [x for x in (spans.literal(q) for q in spans.pieces(quote)) if x]
        if not parts:
            errs.append(f"{p}.quote 不能只有刪節號或空白")
        for x in parts:
            if hay and x not in hay:
                errs.append(f"{p}.quote 的「{x[:30]}」在訊息原文裡找不到：要逐字照抄，包括標點；幾段之間用「……」連接")
    if "verified" in cited:
        ev = t.get("evidence")
        ok = isinstance(ev, list) and bool(ev) and all(
            isinstance(e, dict) and _is_url(e.get("url")) and _nonempty(e.get("excerpt")) for e in ev)
        if not ok:
            errs.append(f"{p}.evidence：列了「查證得到」的特徵，就要附網址和逐字摘錄")
    if lib[tid].get("layer") == "attribution" and not has_report:
        errs.append(f"{p}：{tid} 是歸因層的手法，attribution 要有政府、研究機構或平台的正式報告才能標")
    return errs


def _check_claim_spans(err, claims, run):
    """Every claim quotes the message, and two stated (or two implied) claims never share words,
    so one sentence cannot be scored both whole and in fragments. Skipped when only a URL was given."""
    source = io.read_json_or_none(run / "source.json") or {}
    hay = spans.content(source.get("original_text"))
    if not hay:
        return
    found = {}
    for c in claims:
        if not isinstance(c, dict) or not _nonempty(c.get("original")):
            continue
        cid = c.get("id")
        needle = spans.content(c["original"])
        if not needle:
            err.append(f"{cid} 的原文只有標點或空白，要照抄訊息裡的一段文字")
            continue
        where = spans.occurrences(needle, hay)
        if where:
            found[cid] = where
        else:
            err.append(f"{cid} 的原文在訊息裡找不到，要逐字照抄訊息的一段")
    for kind, types in (("明說", STATED), ("隱含", IMPLIED)):
        group = {c.get("id"): found[c.get("id")] for c in claims
                 if isinstance(c, dict) and c.get("type") in types and c.get("id") in found}
        ok, groups = spans.clash_groups(group)
        if not ok:
            err.append(f"{'；'.join('、'.join(g) for g in groups)} 的原文在訊息裡重疊（分號隔開的是不同組）："
                       f"同一段話只能有一個{kind}的命題。請合併成一條；只有那句話真的有幾個能各自成立的主張時，"
                       "才切成不重疊的幾段（見中立化的拆題規則）")


def _trace(d, run, ctx):
    err = _Errors()
    pub = d.get("publisher") or {}
    err.need(pub.get("kind") in PUBLISHER_KINDS, f"publisher.kind 必須是 {sorted(PUBLISHER_KINDS)}")
    # render reads every field below without checking, so a shape it cannot read has to be sent back here, not
    # found at the last step. null in place of a list reads as empty (render does the same): nothing is missing.
    err.need(not d.get("first_seen") or isinstance(d["first_seen"], dict), "first_seen 必須是物件；查不到就填 null")
    err.need(not pub.get("byline") or isinstance(pub["byline"], str), "publisher.byline 必須是文字：present、absent 或 n/a")
    _items(err, d.get("variants") or [], "variants", dict)
    _items(err, d.get("limits") or [], "limits")
    _items(err, pub.get("flagged") or [], "publisher.flagged", dict)
    for i, w in enumerate(_items(err, pub.get("wording_issues") or [], "publisher.wording_issues", dict)):
        err.need(_nonempty(w.get("quote")) and _nonempty(w.get("issue")),
                 f"publisher.wording_issues[{i}] 要有 quote（原句）和 issue（為什麼不中立）")
    for i, s in enumerate(_items(err, d.get("spread_signals") or [], "spread_signals", dict)):
        err.need(_nonempty(s.get("signal")) and _is_url(s.get("evidence_url")) and _nonempty(s.get("excerpt")),
                 f"spread_signals[{i}] 要有 signal，並附 evidence_url 和 excerpt，只能描述看得到的現象")
    for i, a in enumerate(_items(err, d.get("attribution") or [], "attribution", dict)):
        err.need(_nonempty(a.get("statement")) and _is_url(a.get("report_url")) and _nonempty(a.get("report_org")),
                 f"attribution[{i}] 必須引用政府、研究機構或平台的正式報告（statement、report_url、report_org）")
    err.extend(tactic_errors(d, run, _library(ctx)))
    for i, f in enumerate(_items(err, d.get("prior_factchecks") or [], "prior_factchecks", dict)):
        err.need(_is_url(f.get("url")), f"prior_factchecks[{i}].url 必須是網址")
    return err


def _proponent(d, run, ctx):
    err = _Errors()
    ledger_ids = _check_ledger(err, d.get("ledger"), "proponent")
    _check_verdicts(err, d.get("verdicts"), _claim_ids(run), ledger_ids, "proponent")
    # Read by render for the comparison table, without checking (see _trace).
    rechecked = _items(err, d.get("prior_factchecks_rechecked") or [], "prior_factchecks_rechecked", dict)
    for i, p in enumerate(rechecked):
        err.need(_nonempty(p.get("org")) and _is_url(p.get("url")),
                 f"prior_factchecks_rechecked[{i}] 要有 org（機構名稱）和 url（http(s) 網址）")
        ids = p.get("claim_ids") or []
        err.need(isinstance(ids, list) and all(isinstance(c, str) for c in ids),
                 f"prior_factchecks_rechecked[{i}].claim_ids 必須是命題編號的陣列，例如 [\"C1\"]")
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
    importance = {c.get("id"): c.get("importance")
                  for c in (io.read_json_or_none(run / "claims.json") or {}).get("claims", [])}
    tags = {t.get("tactic_id") for t in (io.read_json_or_none(run / "trace.json") or {}).get("tactics", [])
            if isinstance(t, dict)}
    ids = set()
    # No default: a broken reply parses as a fragment without `attacks`, which must not pass as a seat that found nothing.
    for i, a in enumerate(_items(err, d.get("attacks"), "attacks", dict)):
        p = f"attacks[{i}]"
        aid = a.get("id")
        # Every later step keys on the id across seats, so two seats must never share one (fullmatch: no line break).
        err.need(isinstance(aid, str) and re.fullmatch(re.escape(seat) + r"-\d+", aid) is not None,
                 f"{p}.id 必須是 {seat}-1、{seat}-2…（席位加流水號）")
        err.need(aid not in ids, f"{p}.id {aid} 重複")
        ids.add(aid)
        cid = a.get("claim_id")
        err.need(cid is None or cid in claim_ids, f"{p}.claim_id {cid} 不在 claims.json")
        target = a.get("target")
        err.need(target in ATTACK_TARGETS, f"{p}.target 必須是 {sorted(ATTACK_TARGETS)}")
        err.need(_nonempty(a.get("argument")), f"{p}.argument 不能是空的")
        pl = a.get("proposed_label")
        err.need(pl is None or pl in FACTORS, f"{p}.proposed_label {pl!r} 不是合法的判定")
        evidence = a.get("evidence") or []  # null reads as none; no later step indexes an attack's evidence
        for j, e in enumerate(evidence):
            err.need(_is_url(e.get("url")) and _nonempty(e.get("excerpt")), f"{p}.evidence[{j}] 要有網址和原文摘錄")
        if target in EVIDENCE_REQUIRED_TARGETS:
            err.need(bool(evidence), f"{p} 攻擊的是 {target}，必須附證據（網址和摘錄）")
        if target == "tactic":
            err.need(a.get("tactic_id") in tags, f"{p}.tactic_id：攻擊手法標記要填 trace.json 裡標的手法編號")
        if "proposed_importance" in a:
            _check_importance_proposal(err, p, a, importance)
    return err


def _check_importance_proposal(err, p, a, importance):
    """Importance is challenged through neutral_rewrite on one claim; finalize moves it one step if upheld."""
    v = a.get("proposed_importance")
    cur = importance.get(a.get("claim_id"))
    ok = (a.get("target") == "neutral_rewrite" and isinstance(cur, int)
          and isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 5 and abs(v - cur) == 1)
    err.need(ok, f"{p}.proposed_importance：只能用在 target 是 neutral_rewrite、有 claim_id 的攻擊，"
                 "而且只能提相鄰的一級（現在是 3 就只能提 2 或 4）")


def _rebuttal(d, run, ctx):
    err = _Errors()
    responses = d.get("responses") or []  # null reads as none, so the errors name the attacks left unanswered
    answered = [r.get("attack_id") for r in responses]
    for aid in _attacks(run):
        err.need(answered.count(aid) == 1, f"攻擊 {aid} 需要剛好一則答辯")
    for i, r in enumerate(responses):
        err.need(isinstance(r.get("accept"), bool), f"responses[{i}].accept 必須是 true/false")
        err.need(_nonempty(r.get("response")), f"responses[{i}].response 不能是空的")
    return err


def _judgment(d, run, ctx):
    err = _Errors()
    attacks = _attacks(run)
    ruled = [r.get("attack_id") for r in d.get("rulings", [])]
    excused = _unverified_rulings(err, d, attacks)
    for aid in attacks:
        err.need(ruled.count(aid) == 1, f"攻擊 {aid} 需要剛好一個裁決")
    for i, r in enumerate(d.get("rulings", [])):
        aid = r.get("attack_id")
        err.need(aid in attacks, f"rulings[{i}].attack_id {aid} 不存在")
        err.need(isinstance(r.get("upheld"), bool), f"rulings[{i}].upheld 必須是 true/false")
        err.need(_nonempty(r.get("reason")), f"rulings[{i}].reason 不能是空的")
        if r.get("upheld") is True and aid in attacks and attacks[aid][1].get("evidence") and aid not in excused:
            urls = r.get("verified_urls")  # the message stays as it is: fallback() recognises this error by it
            err.need(isinstance(urls, list) and bool(urls) and all(_is_url(u) for u in urls),
                     f"rulings[{i}] {_RULING_URL_MSG}")
    ledger_ids = _check_ledger(err, d.get("ledger"), "judgment")
    _check_verdicts(err, d.get("verdicts"), _claim_ids(run), ledger_ids, "judgment")
    _check_tactic_checks(err, d, run, attacks, _library(ctx))
    return err


def _unverified_rulings(err, d, attacks):
    """`rulings_unverified` is written only by fallback(): upheld attacks that carry evidence."""
    listed = d.get("rulings_unverified", [])
    upheld = {r.get("attack_id") for r in d.get("rulings", []) if r.get("upheld") is True}
    ok = isinstance(listed, list) and all(
        isinstance(a, str) and a in upheld and a in attacks and attacks[a][1].get("evidence") for a in listed)
    err.need(ok, "rulings_unverified 由程式填寫，只能列出判成立、而且附了證據的攻擊編號")
    return set(listed) if ok else set()


def _check_tactic_checks(err, d, run, attacks, lib):
    """The judge checks every tag in trace.json, attacked or not: which non-clue features hold, and
    keep it only if at least one does. An upheld attack on a tag means the tag goes."""
    if "tactic_checks_set_aside" in d:
        return
    tags = {t.get("tactic_id"): t for t in (io.read_json_or_none(run / "trace.json") or {}).get("tactics", [])
            if isinstance(t, dict)}
    checks = d.get("tactic_checks", [])
    if not isinstance(checks, list) or not all(isinstance(c, dict) for c in checks):
        err.append("tactic_checks 必須是陣列，每個標記一筆")
        return
    seen = [c.get("tactic_id") for c in checks]
    for tid in tags:
        err.need(seen.count(tid) == 1, f"tactic_checks：{tid} 需要剛好一筆檢查（trace.json 的每個標記都要檢查，不論有沒有被攻擊）")
    for tid in seen:
        err.need(tid in tags, f"tactic_checks：{tid} 不在 trace.json 的標記裡")
    struck = {attacks[r["attack_id"]][1].get("tactic_id"): r["attack_id"] for r in d.get("rulings", [])
              if r.get("upheld") is True and r.get("attack_id") in attacks
              and attacks[r["attack_id"]][1].get("target") == "tactic"}
    for i, c in enumerate(checks):
        tid = c.get("tactic_id")
        if tid not in tags:
            continue
        p = f"tactic_checks[{i}]"
        kinds = ((lib or {}).get(tid) or {}).get("features") or {}
        cited = tags[tid].get("features") if isinstance(tags[tid].get("features"), list) else []
        expected = {f for f in cited if kinds.get(f, "visible") != "clue"}
        feats = c.get("features")
        ok = isinstance(feats, dict) and set(feats) == expected and all(isinstance(v, bool) for v in feats.values())
        err.need(ok, f"{p}.features 要剛好列出 {tid} 每一項非線索的特徵（{'、'.join(sorted(expected))}），值是 true/false")
        keep = c.get("keep")
        err.need(isinstance(keep, bool), f"{p}.keep 必須是 true/false")
        err.need(_nonempty(c.get("reason")), f"{p}.reason 不能是空的，會刊在報告裡")
        if ok and isinstance(keep, bool):
            err.need(keep == any(feats.values()), f"{p}.keep：至少一項特徵成立才保留，全部不成立就撤回")
        if keep is True and tid in struck:
            err.append(f"{p}：攻擊 {struck[tid]} 判成立，{tid} 就要撤回（keep: false）")
        held = [f for f, v in (feats or {}).items() if v is True] if ok else []
        if keep is True and held and all(kinds.get(f) == "verified" for f in held):
            urls = c.get("verified_urls")
            allowed = {e.get("url") for e in tags[tid].get("evidence", []) if isinstance(e, dict)}
            err.need(isinstance(urls, list) and bool(urls) and all(u in allowed for u in urls),
                     f"{p}.verified_urls：只靠查證得到的特徵保留時，要列出你實際打開核對過的溯源員證據網址")


def _review(d, run, ctx):
    err = _Errors()
    err.need(d.get("seat") == ctx["seat"], f"seat 必須是 {ctx['seat']}（和檔名一致）")
    claim_ids = _claim_ids(run)
    try:  # finalize reads a review that was left out as a failed one, so the seat is sent back for it here
        needed = finalize.reviewers_needed(run).get(ctx["seat"], [])
    except (io.ReadError, KeyError, TypeError, AttributeError):
        needed = []  # the judgment or an opponent file cannot be read; their own checks say so
    reviews = _items(err, d.get("reviews", []), "reviews", dict)  # finalize iterates it, so null is refused here
    reviewed = [r.get("claim_id") for r in reviews]
    for cid in needed:
        err.need(reviewed.count(cid) == 1, f"reviews：{cid} 需要剛好一筆覆核（任務區列出的命題每條都要寫，而且只寫一筆）")
    for i, r in enumerate(reviews):
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
    "run.json": _run, "models.json": _models, "input.json": _input, "source.json": _source, "claims.json": _claims,
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
    try:
        return list(fn(data, run, ctx))
    except (TypeError, AttributeError, KeyError, ValueError) as exc:
        # Skeptic review: e.g. claims given as plain strings made the checks raise, crashing run-model and status.
        return [f"{name} 的結構不對（{type(exc).__name__}：{exc}），照格式重寫"]
