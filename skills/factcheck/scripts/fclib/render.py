"""Turn a finished run directory into report.md. Pure formatting — no judgement happens here."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from urllib.parse import quote

from . import detect, io, media
from .labels import CONTEXT_FLAGS, FACTORS, TIER_NAMES, UNSCORED_TYPES, ZH_LABELS
from .score import WRONG_LABELS, not_scored, round_half_up, time_effect

WIDTH = 30
ISOLATION = {"full": "完整隔離", "partial": "部分隔離", "unknown": "未確認", "host": "主模型"}
LENS = {"evidence": "反方 A：證據", "counter": "反方 B：反證", "stance": "反方 C：立場", "external": "外部反方"}
PUBLISHER = {"news": "新聞媒體", "public_figure": "公眾人物", "official": "官方", "anonymous": "匿名",
             "content_farm": "內容農場", "private_individual": "一般民眾", "unknown": "不明"}
BYLINE = {"present": "有署名", "absent": "沒有署名", "n/a": "不適用"}
ACCESS = {"full": "全文", "paywall": "付費牆", "blocked": "被擋", "archived": "存檔", "snippet": "只有摘要",
          "not_original": "未直接核對原始出處", "no_transcript": "沒有逐字稿"}
INPUT = {"text": "貼上的文字", "url": "網址", "image": "截圖", "video": "影片"}
# What each kind of input can never tell, printed by the program instead of hoping the prep step notes it.
INPUT_LIMITS = {"url": "網址的內文由子程序用網頁工具讀取，不保證是逐字全文",
                "image": "截圖上的文字由主體照抄；沒有判斷圖片是否偽造",
                "video": "只查逐字稿的內容；沒有判斷影片是否為 AI 合成"}
PRE_DEBATE = "> 這一段是辯論前寫的。裁判判定成立的修正列在後面的「辯論後的修正」，內容不同時以修正為準。"


# Control characters, the two Unicode line separators, and the controls that reverse or isolate text direction.
_UNSAFE = r"\x00-\x1f\x7f-\x9f\u2028\u2029\u202a-\u202e\u2066-\u2069"
_BREAKS = re.compile(f"[{_UNSAFE}]+")
_LINK_UNSAFE = re.compile(rf'[()\[\]<>"|\\\s{_UNSAFE}]')
# A "<" that can open raw HTML (tag, closing tag, comment, declaration); "<5%" and "x < 2" cannot, so they stay.
_TAG_OPEN = re.compile(r"<(?=[A-Za-z/!?])")


def _cell(text) -> str:
    """Text a model wrote, kept inside the line it is printed on: no line break of any kind (a bare "\\r" ends a
    line in CommonMark too), no table bar, no "](" that would turn it into a link hiding its address, and no raw
    HTML (viewers such as GitHub render <a href>, <img> and <h2>), and no "[label]: url" definition that would turn
    every later [label] into a link."""
    text = _BREAKS.sub(" ", str(text or "")).replace("|", "／").replace("](", "] (").replace("]:", "] :")
    return _TAG_OPEN.sub("＜", text).strip()


def _link(url) -> str:
    """A URL as the target of a Markdown link: whatever could end the target, start another link or split the table
    cell is percent-encoded, so a URL with brackets (common on Wikipedia) still works and cannot do any of that."""
    return _LINK_UNSAFE.sub(lambda m: quote(m.group()), str(url or ""))


_RULING_PREFIX = re.compile(r"^(?:攻擊|質疑)?不?成立[。，；：]\s*")


def _ruling(text) -> str:
    """A ruling reason without a leading 「成立。」 or 「不成立：」: the line it goes on already says which.
    「成立一部分：…」 keeps its words, since they say how much."""
    text = _cell(text)
    return _RULING_PREFIX.sub("", text, count=1) or text


def _implied(meta, c) -> str:
    """What was checked for an implied claim: the message never says it, so its quote alone misleads. A rewrite
    the debate revised is not printed, because the judge ruled on the revised question (see the reasoning)."""
    if meta.get("type") != "I":
        return ""
    if c.get("rewrite_revised") is False:
        return f"（訊息沒有明說；這一項查的是它暗示的：{_cell(meta.get('neutral'))}）"
    return "（訊息沒有明說；這一項查的是它暗示的事" + ("，問法在辯論中修正過" if c.get("rewrite_revised") else "") + "，見理由）"


def _first_sentence(text, limit=120, skip=None) -> str:
    text = _cell(text)
    if skip and text.startswith(skip + "。"):  # 「誤導**。誤導。」: the first sentence only repeats the label
        text = text[len(skip) + 1:].lstrip() or text
    cut = text.find("。")
    first = text[:cut + 1] if cut >= 0 else text
    return first if len(first) <= limit else first[:limit] + "…"


def _spectrum(score) -> list:
    pos = round_half_up(score * WIDTH / 100)
    bar = "━" * pos + "▲" + "━" * (WIDTH - pos)
    return ["```text", f"錯誤 {bar} 正確", " " * (5 + pos) + str(score), "```"]


def _subject(source) -> str:
    """What was checked, quoted on a line of its own under a fixed heading: a message that opens with
    「結果：符合…」 must not put its own words in the heading, above the real result line."""
    if source.get("url"):
        return f"> 被查核的網址：{_cell(source['url'])}"
    text = _cell(source.get("original_text"))
    return f"> 被查核的訊息（開頭）：「{text[:30]}{'…' if len(text) > 30 else ''}」"


def _host_isolation(models) -> list:
    """2026-11-18 canary: `codex exec` always reads ~/.codex/AGENTS.md. Not probed for the host, so a custom
    FC_CODEX_CMD (perhaps a clean CODEX_HOME) is reported as unconfirmed rather than as isolated."""
    if models.get("host") != "codex":
        return []
    cmd = next((e.get("cmd") for e in models.get("engines", []) if e.get("engine") == "codex"), None)
    state = ("讀得到使用者的 ~/.codex/AGENTS.md（部分隔離）" if cmd in (None, ["codex"])
             else "用的是自訂的 Codex 指令，隔離程度沒有確認")
    return ["- 主體是 Codex：主模型的角色（讀入與拆題、溯源、正方、主模型負責的反方席位和它們的覆核、答辯、裁判）"
            f"都由 codex exec 執行，{state}。"]


OLD_CONTENT_DAYS = 183


def _old_content(published_at, checked_at):
    """The publication date when it is more than half a year before the check date; relative times in the
    content refer to that date (neutralize.md rule 6). None when either date is missing or not ISO."""
    try:
        published = date.fromisoformat(str(published_at)[:10])
        checked = date.fromisoformat(str(checked_at)[:10])
    except ValueError:
        return None
    return published.isoformat() if (checked - published).days > OLD_CONTENT_DAYS else None


TIME_KINDS = {"deadline": "期限前提", "relative": "暗示的時間"}
# Words that tell the reader "this just happened". Only used for a reminder in the scope section when an undated
# message has one and the split marked no implied time; it never changes a score or blocks publishing.
JUST_NOW = ("剛剛", "剛才", "最新", "快訊", "今天", "今日", "昨天")


def _time_banner(c):
    """The program's own words about a wrong time claim; the judge's reasoning stays in the table."""
    where = f"（{c['claim_id']} 判「{ZH_LABELS[c['label']]}」，理由見逐項判定）"
    if time_effect(c) == "void":
        return f"> 訊息要讀者趕在期限前做的事，前提{'有一部分' if c['label'] == 'mixed' else ''}不成立{where}。"
    return f"> 訊息暗示的時間不對{where}；內容本身另外判定。"


TACTICS_HIDDEN = [
    "## 操弄手法（實驗功能，這份報告沒有列出）", "",
    "- 這一版預設不列出操弄手法。2026-11-20 實測：同一則訊息只換政黨、或原封不動重跑一次，標出來的手法就可能不同。"
    "在它通過跨陣營一致性驗證之前，不把它當成查核結果。",
    "- 想看的話，用 `fc.py render --with-tactics` 重新產生報告。看到的標記只當成提醒自己留意的線索，不要引用，"
    "也不要拿來比較不同陣營的訊息。這份報告其他段落的說明文字如果提到手法名稱，也一樣。", ""]
TACTICS_SHOWN = ("> 這一段是實驗功能，還沒通過跨陣營一致性驗證：同一則訊息只換政黨、或重跑一次，標出來的手法就可能不同"
                 "（2026-11-20 實測）。只當成提醒自己留意的線索，不要引用在公開貼文，也不要拿來比較不同陣營的訊息。")


def render(run, outlets=None, tactics=None, with_tactics=False) -> str:
    """with_tactics: list the tactic tags. Off by default: tags differed between party-swapped versions of one
    message and between reruns, so nothing about them is printed unless asked for (not even that a tag was
    withdrawn), and the note that replaces them is the same in every report."""
    run = Path(run)
    rj = io.read_json(run / "run.json")
    models = io.read_json(run / "models.json")
    source = io.read_json(run / "source.json")
    claims = {c["id"]: c for c in io.read_json(run / "claims.json")["claims"]}
    claims_doc = io.read_json(run / "claims.json")
    trace = io.read_json_or_none(run / "trace.json") or {}
    proponent = io.read_json_or_none(run / "proponent.json") or {}
    verdicts = io.read_json(run / "verdicts.json")
    sc = io.read_json(run / "score.json")
    seats = detect.seat_status(run)
    outlets = media.load() if outlets is None else outlets
    tactics = {t["id"]: t for t in (_load_tactics() if tactics is None else tactics)}
    ledger = {e["id"]: e for e in verdicts.get("ledger", [])}

    cred, conf = sc.get("credibility"), sc["confidence"]
    ok_cross = [s for s in seats if s["cross_model"] and s["status"] == "ok"]
    mode = "完整模式" if rj["mode"] == "full" else "快速模式"
    out = ["# 查核報告", "", _subject(source), ""]

    if cred and cred["show_on_spectrum"]:
        out += _spectrum(cred["score"]) + [""]
    cred_text = f"可信度 {cred['score']}" if cred and cred["show_on_spectrum"] else "可信度 —"
    alt = sc.get("without_importance_changes")
    flip = f"（不調整重要性的話是「{alt['result']}」）" if alt and alt["result"] != sc["result"] else ""
    out.append(f"**結果：{sc['result']}{flip}｜{cred_text}｜信心度 {conf['level']}（{conf['score']}）｜"
               f"{mode}・跨模型 {len(ok_cross)} 席｜{'可公開' if sc['publishable'] else '不可公開'}**")
    out.append("")
    if sc.get("result_reason"):
        out += [f"> {sc['result_reason']}", ""]
    timed = [c for c in verdicts["claims"] if c.get("time")]
    for c in timed:
        if time_effect(c) in ("void", "cap"):
            out += [_time_banner(c), ""]
    left_out = [c["claim_id"] for c in verdicts["claims"]
                if not c.get("time") and (c.get("type") in UNSCORED_TYPES or c["label"] == "not_factual")]
    if left_out and cred:  # with no score at all, the reason above already says nothing could be checked
        out += [f"> 結論只涵蓋可以查證的說法。{'、'.join(left_out)} 被分成意見、預測或模糊的說法，或被判成非事實陳述，不在結論內。", ""]
    if sc["publishable"]:
        out += ["> 「可公開」只代表查核流程完整、信心度高，不保證結論正確。公開貼文前，請先看過下面的證據。", ""]
    old = _old_content(source.get("published_at"), rj.get("created_at"))
    if old:
        out += [f"> 這篇內容發布於 {old}，距離查核日已經超過半年；裡面的「明年」「最近」這類說法，指的是發布當時。", ""]
    if not sc["publishable"]:  # score gives every such report a reason: a block below, or the unadjusted result
        out += ["> 「不可公開」的意思是這次查核沒有達到公開引用的條件，不要把整則結論拿去公開貼文；"
                "不是說這份報告要保密。原因見下面幾行。", ""]
    for b in sc.get("publish_blocks") or []:
        out += [f"> {b}。這份報告不能標可公開。", ""]
    if alt:
        shown = alt.get("credibility") is not None and alt["result"] != "無法判定"
        alt_cred = f"可信度 {alt['credibility']}" if shown else "可信度 —"
        # Second review: when the results differ neither is publishable, whatever the unadjusted run alone would be.
        status = "兩個結果都不能公開" if alt["result"] != sc["result"] else ("可公開" if alt["publishable"] else "不可公開")
        out += [f"> 辯論中調整了命題的重要性。不調整的話，結果是「{alt['result']}」（{alt_cred}，{status}）。", ""]
    if claims_doc.get("prompt_was_leading"):
        out += ["> 提問已改寫為中立命題。", ""]

    # 一句話結論
    out += ["## 結論", ""]
    content = [c for c in verdicts["claims"] if not c.get("time")]
    main = (cred or {}).get("main_claims") or []  # the claims that decide the result (score.py); not always core
    dispute = {d["claim_id"]: d for d in verdicts.get("disputes") or []}

    def rank(c):  # main claims, then core claims, then any other scored claim judged wrong (often the stale one)
        if c["claim_id"] in main:
            return 0
        if claims[c["claim_id"]]["core"]:
            return 1
        return 2 if c["label"] in WRONG_LABELS and c.get("type") not in UNSCORED_TYPES else None

    listed = sorted([c for c in content if rank(c) is not None], key=lambda c: (rank(c), -c["importance"], c["claim_id"]))
    # A time claim is listed only when it did something: judged wrong, or left unsettled.
    for c in [c for c in timed if time_effect(c)] + (listed or content):
        cid, meta = c["claim_id"], claims[c["claim_id"]]
        flags = "、".join(CONTEXT_FLAGS[f] for f in c.get("context_flags", [])) if c["label"] in WRONG_LABELS else ""
        kept = "（覆核對理由或證據有意見，見「爭議點」）" if dispute.get(cid, {}).get("label_kept") else ""
        # The full stop goes outside the bold: CommonMark does not close ** between 「。」 and a letter.
        out.append(f"- **{cid}{'（主要說法）' if cid in main else ''}「{_cell(meta['original'])}」{_implied(meta, c)}："
                   f"{ZH_LABELS[c['label']]}{'（時間命題）' if c.get('time') else '（不計分）' if not_scored(c) else ''}"
                   f"{f'（{flags}）' if flags else ''}**。{_first_sentence(c['reasoning'], skip=ZH_LABELS[c['label']])}{kept}")
    out.append("")

    # 範圍與限制
    out += ["## 查核範圍和限制", "",
            f"- 查核時間：{rj.get('created_at', '')}；{mode}；主體：{models['host']}",
            f"- 輸入類型：{INPUT.get(source.get('input_type'), source.get('input_type'))}"
            + (f"；網址：{_cell(source['url'])}" if source.get("url") else ""),
            "", "| 席位 | 角色 | 模型 | 狀態 | 搜尋次數 | 攻擊數 | 跨模型 | 能上網 | 隔離 |", "|---|---|---|---|---|---|---|---|---|"]
    for s in seats:
        # What the seat says it did: "succeeded" alone cannot tell a seat that found nothing from one that did not look.
        work = io.read_json_or_none(run / f"opponent-{s['seat']}.json") or {}
        searched = work.get("searches_run") if isinstance(work.get("searches_run"), int) else "沒有回報"
        attacks = len(work["attacks"]) if isinstance(work.get("attacks"), list) else "—"
        out.append(f"| {s['seat']} | {LENS.get(s['lens'], s['lens'])} | {_model_cell(models, s)} | "
                   f"{ {'ok': '成功', 'missing': '沒有執行'}.get(s['status'], '失敗')} | "
                   f"{searched if s['status'] == 'ok' else '—'} | {attacks if s['status'] == 'ok' else '—'} | "
                   f"{'是' if s['cross_model'] else '否'} | "
                   f"{'是' if s['can_search'] else '否'} | {ISOLATION.get(s['isolation'], s['isolation'])} |")
    out.append("")  # a list item right under a table row is read as part of the table by some viewers
    dated = str(source.get("published_at") or "").strip()
    if dated:  # the two time claims are for undated content only; say so, and show the date they are judged from
        out.append(f"- 內容的發布時間：{_cell(dated)}。裡面的期限和相對時間照發布當時判，沒有檢查現在是否已經過期。")
    if timed:
        out.append(f"- 時間命題：{'、'.join(c['claim_id'] + '（' + TIME_KINDS[c['time']] + '）' for c in timed)}。"
                   "判對不加分；判錯時，期限前提讓可信度不高於它的正確度，暗示的時間讓可信度最高 79。")
    elif dated:
        out.append("- 時間命題：不適用（內容有發布時間）。")
    else:
        out.append("- 時間命題：沒有（拆題沒有標出期限前提或暗示的時間）。")
    if not any(c["time"] == "relative" for c in timed) and not dated:
        said = next((w for w in JUST_NOW if w in (source.get("original_text") or "")), None)
        if said:
            out.append(f"  - 訊息裡有「{said}」，如果這其實是舊消息，結論沒有反映這一點。")
    out += _host_isolation(models)
    # An upheld correction to the trace (a withdrawn tag already shows where the tag was). Verdicts written before
    # `target` was carried count as trace corrections.
    corrected = any(a.get("target", "trace") != "tactic" for a in verdicts.get("trace_attacks_upheld") or [])
    pre = [PRE_DEBATE, ""] if corrected else []
    limits = [INPUT_LIMITS[source["input_type"]]] if source.get("input_type") in INPUT_LIMITS else []
    if isinstance(source.get("notes"), str) and source["notes"].strip():
        limits.append(f"讀入時的備註：{source['notes']}")
    traced = list(trace.get("limits") or [])
    if traced and corrected:  # the lines after them come from the judge's ledger, written after the debate
        limits.append(f"接下來 {len(traced)} 項是溯源員在辯論前寫的；裁判判定成立的修正列在後面的「辯論後的修正」，內容不同時以修正為準")
    limits += traced
    if with_tactics and trace.get("set_aside_tactics"):
        limits.append(f"溯源員有 {len(trace['set_aside_tactics'])} 個手法標記不符合標記規則，已移出（原內容保留在 trace.json），報告不列出")
    for e in ledger.values():
        if e.get("access_note", "full") != "full":
            limits.append(f"{e['id']}（{_cell(e.get('publisher'))}）：{ACCESS.get(e['access_note'], e['access_note'])}")
    if limits:
        out += ["", "限制："] + [f"- {_cell(x)}" for x in limits]
    out.append("")

    # 逐項判定
    out += ["## 逐項判定", "", "| 命題 | 原文說法 | 重要性 | 判定 | 理由 | 證據 |", "|---|---|---|---|---|---|"]
    unscored_ids = []
    for c in verdicts["claims"]:
        meta = claims[c["claim_id"]]
        status = {"passed": "（覆核通過）", "failed": "（覆核未完成或未通過）"}.get(c["review_status"], "")
        d = dispute.get(c["claim_id"])
        if c["review_status"] == "failed" and d:  # which kind: a kept label means every review ran and objected
            status = ("（覆核未通過：同意判定，對理由或證據有意見）" if d.get("label_kept") else
                      "（覆核未完成或未通過：判定沒有獲得確認）" if d["judge_label"] == "unverified" else
                      f"（覆核未完成或未通過：裁判原判「{ZH_LABELS[d['judge_label']]}」）")
        if c.get("time"):
            status += "（時間命題）"
        elif not_scored(c):
            status += "（不計分）"
            unscored_ids.append(c["claim_id"])
        weight = "—" if c.get("time") else \
            str(c["importance"]) + (f"（辯論後由 {c['importance_from']} 調整）" if "importance_from" in c else "")
        out.append(f"| {c['claim_id']} | {_cell(meta['original'])}{_implied(meta, c)} | {weight} | {ZH_LABELS[c['label']]}{status} | "
                   f"{_cell(c['reasoning'])} | {_cell(', '.join(c.get('evidence_ids', []))) or '—'} |")
    if unscored_ids:
        out += ["", f"- {'、'.join(unscored_ids)} 是意見、預測或模糊到無法查證的說法，判定只供參考，不算進可信度。"]
    adjusted = [c for c in verdicts["claims"] if "importance_from" in c or c.get("importance_attacks")]
    if adjusted:
        out.append("")
        for c in adjusted:
            seats = "、".join(sorted({a["seat"] for a in c.get("importance_attacks", [])}))
            why = "；".join(_cell(a["ruling_reason"]) for a in c.get("importance_attacks", []))
            if c.get("time"):
                out.append(f"- {c['claim_id']} 是時間命題，重要性不影響計分；反方 {seats} 的重要性挑戰（成立）沒有套用。")
                continue
            if "importance_from" not in c:  # upheld challenges in both directions cancel (finalize._importance)
                out.append(f"- {c['claim_id']} 的重要性維持 {c['importance']}：反方 {seats} 提出調高和調低的挑戰，"
                           f"裁判都判成立，互相抵銷。裁判：{why}")
                continue
            out.append(f"- {c['claim_id']} 的重要性由 {c['importance_from']} 調為 {c['importance']}"
                       f"（反方 {seats} 提出）。裁判：{why}")
    out.append("")

    # 溯源
    out += ["## 溯源", ""] + pre
    fs = trace.get("first_seen")
    out.append(f"- 最早出現：{_cell(fs.get('date'))} {_cell(fs.get('platform'))} {_cell(fs.get('url'))}".rstrip()
               if fs else "- 最早出現：查不到")
    for v in trace.get("variants") or []:  # null reads as an empty list here and in validate
        out.append(f"- 變體：{_cell(v.get('date'))} {_cell(v.get('difference'))} {_cell(v.get('url'))}")
    for s in trace.get("spread_signals") or []:
        out.append(f"- 傳播跡象：{_cell(s['signal'])}（{_cell(s['evidence_url'])}）")
    if trace.get("attribution"):
        for a in trace["attribution"]:
            out.append(f"- 正式報告：{_cell(a['report_org'])} 指出「{_cell(a['statement'])}」（{_cell(a['report_url'])}）")
    else:
        out.append("- 背後是誰：沒有政府、研究機構或平台的正式報告點名這個案例，不做推斷。")
    out.append("")

    # 報導品質
    pub = trace.get("publisher", {})
    kind, name = str(PUBLISHER.get(pub.get("kind"), pub.get("kind", "不明"))), _cell(pub.get("name"))
    out += ["## 報導品質（不影響可信度）", ""] + pre + [
        # 「不明・不明（LINE 轉傳…）」: the name often starts with the kind already
        f"- 發布者：{name if name.startswith(kind) else kind + ('・' + name if name else '')}"]
    if pub.get("byline"):
        out.append(f"- 署名：{BYLINE.get(pub['byline']) or _cell(pub['byline'])}")
    # The checked URL decides the outlet when the table knows its domain: a wrong id from the tracer would label one
    # outlet with another's lean. The tracer's id is used only when the URL cannot tell.
    try:
        by_url = media.lookup(source["url"], outlets) if source.get("url") else None
    except ValueError:  # 「https://[某網址]/」 passes the input check but not urlparse: a URL that cannot tell
        by_url = None
    outlet = by_url or (next((o for o in outlets if o.get("id") == pub.get("outlet_id")), None)
                        if pub.get("outlet_id") else None)
    if outlet:
        out.append(f"- 媒體背景：以下是對照表裡「{_cell(outlet.get('name'))}」的資料"
                   + ("（依查核的網址）" if by_url else "（溯源員比對出來的，不是從網址認出來的）"))
        t = outlet.get("trust")
        out.append(f"- 信任度：{t['score']}%（{t['source']}，{t['year']}）" if t else "- 信任度：沒有調查資料")
        if outlet.get("lean"):
            for ln in outlet["lean"]:
                out.append(f"- 立場研究：{ln['label']}（{ln['source']}，{ln['year']}）")
        else:
            out.append("- 立場研究：目前沒有可引用的研究")
        if outlet.get("ownership"):
            out.append(f"- 所有權：{_cell(outlet['ownership'])}")
        # media.toml's `record` is not printed until there is a written standard and every outlet has been checked
        # against it: only one outlet has one today, so printing it would single that outlet out.
    issues = pub.get("wording_issues", [])
    out.append("- 用詞：" + ("；".join(f"「{_cell(w['quote'])}」{_cell(w['issue'])}" for w in issues) if issues else "沒有發現明顯不中立的用詞"))
    for f in pub.get("flagged") or []:
        out.append(f"- 被點名或更正：{_cell(f.get('note'))}（{_cell(f.get('url'))}）")
    out.append("")

    # 操弄手法（裁判逐項檢查後撤回的標記不列為已辨識）
    if not with_tactics:
        out += TACTICS_HIDDEN
    elif trace.get("tactics"):
        removed = {w["tactic_id"]: w.get("reason", "") for w in verdicts.get("removed_tactics", [])}
        unchecked = [w for w in verdicts.get("removed_tactics", []) if w.get("not_checked")]
        out += ["## 操弄手法（不影響可信度）", "", TACTICS_SHOWN, ""] + pre
        for t in trace["tactics"]:
            if t["tactic_id"] in removed:
                continue
            info = tactics.get(t["tactic_id"], {})
            said = f"「{_cell(t['quote'])}」" if t.get("quote") else ""
            line = f"- **{info.get('name', t['tactic_id'])}**（{t['tactic_id']}）：{said}{_cell(t.get('explanation'))}"
            if info.get("layer") == "attribution" and not trace.get("attribution"):
                line += "。特徵相符，但無法確認背後是誰。"
            out.append(line)
            if info.get("how_to_spot"):
                out.append(f"  - 怎麼辨認：{info['how_to_spot']}")
            # The section is called 操弄; this says what a tag does not prove. Attribution entries speak to the tagger.
            if info.get("cannot_infer") and info.get("layer") != "attribution":
                out.append(f"  - 不代表什麼：{info['cannot_infer']}")
        if unchecked:  # a format failure, not a debate outcome: counted, never named (as for the tracer's set-aside tags)
            out.append(f"- 溯源員標了 {len(unchecked)} 個手法，但裁判逐項檢查的結果格式不合規定，程式無法採用，"
                       "所以這次都不列出（溯源員原本的標記保留在 trace.json）。這是格式問題，不是辯論的結論。")
        else:
            if removed and all(t["tactic_id"] in removed for t in trace["tactics"]):
                out.append("- 辯論後沒有留下任何手法標記。")
            for tid in sorted(removed):
                out.append(f"- 辯論後撤回：{tactics.get(tid, {}).get('name', tid)}（{tid}）。裁判：{_cell(removed[tid])}")
        out.append("")

    # 既有查核
    rechecked = proponent.get("prior_factchecks_rechecked", [])
    if rechecked:
        final = {c["claim_id"]: c["label"] for c in verdicts["claims"]}
        initial = {v["claim_id"]: v["label"] for v in proponent.get("verdicts", [])}
        out += ["## 和既有查核的比對", ""] + pre + [
                "| 機構 | 對方的結論 | 我們的最終判定 | 正方重驗 | 說明 |", "|---|---|---|---|---|"]
        for p in rechecked:
            ids = [i for i in p.get("claim_ids") or [] if i in final]
            ours = "、".join(f"{i} {ZH_LABELS[final[i]]}" for i in ids) or "—"
            changed = any(initial.get(i) != final[i] for i in ids)
            agree = p.get("agree")  # null when the other side's page could not be read
            check = ("無法比對" if not isinstance(agree, bool)
                     else ("一致" if agree else "不一致") + ("（辯論後改判）" if changed else ""))
            out.append(f"| [{_cell(p['org'])}]({_link(p['url'])}) | {_cell(p.get('their_label'))} | {ours} | "
                       f"{check} | {_cell(p.get('note'))} |")
        out.append("")

    # 辯論後的修正（成立的溯源和手法攻擊；上面的溯源內容是辯論前寫的）
    upheld = [a for a in verdicts.get("trace_attacks_upheld") or [] if with_tactics or a.get("target", "trace") != "tactic"]
    if upheld:
        out += ["## 辯論後的修正", "",
                f"前面的溯源、報導品質、{'操弄手法、' if with_tactics else ''}和既有查核的比對，以及查核範圍裡關於溯源的說明，都是辯論前寫的。"
                "以下是裁判判定成立的修正，和前文不同時以這裡為準。", ""]
        for a in upheld:
            out.append(f"- 反方 {a['seat']} 的質疑成立：{_ruling(a['ruling_reason'])}")
        out.append("")

    # 爭議點
    if verdicts.get("disputes"):
        out += ["## 爭議點", ""]
        for d in verdicts["disputes"]:
            judged = ZH_LABELS[d["judge_label"]]
            # The judge's reasoning is in the table; pasting it here again buried the point of the line.
            # "完成或": a seat with no review file is in the last two branches too (its reason is listed below).
            if d.get("label_kept"):
                first = f"判定維持「{judged}」。覆核同意這個判定，但認為理由或證據還有缺漏。"
            elif d["judge_label"] == "unverified":  # nothing changed, so 「改判」 would be wrong
                first = "裁判判「無法證實」，覆核沒有完成或沒有通過；判定沒有變，但沒有獲得確認。"
            else:
                first = f"裁判原本判「{judged}」，覆核沒有完成或沒有通過，所以改判「無法證實」。"
            out.append(f"- **{d['claim_id']}**：{first}裁判的理由見「逐項判定」。")
            if d.get("proponent_label"):
                out.append(f"  - 這個命題沒有任何會改判的成立攻擊（重要性挑戰、溯源和手法攻擊不算），"
                           f"是裁判自己把正方判「{ZH_LABELS[d['proponent_label']]}」改成「{ZH_LABELS[d['judge_label']]}」，"
                           "所以每個反方席位都要覆核。")
            for o in d["objections"]:
                # The ruling, not the opponent's words: they were aimed at the proponent's verdict and can hold parts
                # the judge rejected, as in 辯論後的修正.
                ruling = _ruling(o.get("ruling_reason"))
                out.append(f"  - 辯論時反方 {o['seat']} 的質疑成立" + (f"。裁判：{ruling}" if ruling else "。"))
            for r in d["review_reasons"]:
                out.append(f"  - 覆核：{_cell(r)}")
        out.append("")

    # 已檢驗的質疑
    checked = [o for o in verdicts.get("checked_objections") or [] if with_tactics or o.get("target") != "tactic"]
    if checked:
        out += ["## 已檢驗的質疑", ""]
        for o in checked:
            where = o["claim_id"] or ("手法標記" if o.get("target") == "tactic" else "溯源")
            out.append(f"- （{where}）{_cell(o['argument'])} → 不成立：{_ruling(o['ruling_reason'])}")
        out.append("")

    # 法條
    legal = [c for c in verdicts["claims"] if c.get("legal")]
    if legal:
        out += ["## 法條（非法律意見）", "",
                "以下是法條命題引用的第一手資料摘錄，每筆標明出處；不一定是條文，也可能是草案、議事紀錄、判決或官方統計。"
                "超出條文字面的解讀有爭議時，建議諮詢律師。", ""]
        for c in legal:
            # Only whether the law text was obtained: the verdict is in the table, and nothing forces it to be 無法證實.
            status = "已取得條文原文" if c.get("law_text_obtained") else "沒有取得條文原文"
            out.append(f"- {c['claim_id']}：{status}")
            for eid in c.get("evidence_ids", []):
                e = ledger[eid]
                if e["tier"] == 1:  # the title says which article or draft it is; tier 1 is not only law text
                    out.append(f"  - {_cell(eid)}（{_cell(e.get('title') or e.get('publisher'))}）："
                               f"「{_cell(e['excerpt'])}」（{_cell(e['url'])}）")
        out.append("")

    # 評分拆解
    out += ["## 評分拆解", "",
            "- 可信度是訊息本身有多正確，只看每個命題的判定；信心度是這次查得多扎實（證據、跨模型反方、覆核）。兩者分開算。"]
    if cred:
        by_flag = {}  # only claims still judged wrong: a flag on one a failed review made unverified reflects nothing
        for c in verdicts["claims"]:
            for f in c.get("context_flags", []) if c["label"] in WRONG_LABELS else []:
                by_flag.setdefault(f, []).append(c["claim_id"])
        flags = "、".join(f"{CONTEXT_FLAGS[f]}（{'、'.join(by_flag[f])}）" for f in cred["context_flags"] if f in by_flag)
        out.append(f"- 主要說法（計分命題裡重要性最高的一層）：{'、'.join(cred['main_claims'])}")
        if cred["show_on_spectrum"]:
            out.append(f"- 可信度 = 100 × 兩者中較低的（主要說法的平均正確度 {cred['main_accuracy']:.4f}、"
                       f"全部計分命題依重要性加權的正確度 {cred['overall_accuracy']:.4f}）= {cred['raw']} → {cred['score']}")
        else:  # the result line says 可信度 —; a number here reads as a result (35 is 不符)
            out.append(f"- 可信度：不給分數。{sc.get('result_reason') or ''}")
        for c in timed:
            if time_effect(c) == "void":
                factor = FACTORS[c["label"]]
                out.append(f"- 期限前提 {c['claim_id']} 判「{ZH_LABELS[c['label']]}」：可信度不高於 "
                           f"100 × {float(factor):g} = {round_half_up(100 * factor)}。")
        if cred.get("capped"):
            out.append("- 有命題判錯誤、誤導或部分錯誤，所以可信度上限 79，最高是「大致符合」。")
        out.append("- 脈絡問題：" + (f"{flags}。已經反映在這些命題的判定裡，不另外扣分" if flags else "無"))
    else:
        out.append("- 沒有可以計分的事實命題。")
    out.append(f"- 信心度：{conf['score']}（{conf['level']}）")
    for d in conf["deductions"]:
        out.append(f"  - −{d['points']}：{d['reason']}")
    out.append("")

    # 來源
    out += ["## 來源", "", "| 編號 | 來源 | 層級 | 存取 | 查閱日期 |", "|---|---|---|---|---|"]
    for e in ledger.values():
        out.append(f"| {_cell(e['id'])} | [{_cell(e.get('title') or e.get('publisher'))}]({_link(e['url'])}) | "
                   f"{TIER_NAMES.get(e['tier'], e['tier'])} | {ACCESS.get(e.get('access_note', 'full'))} | {_cell(e.get('accessed'))} |")
    out += ["", "引用查核機構與 Cofacts 的內容時，只附連結和簡短摘錄，著作權屬原機構。", ""]

    out += ["## 執行紀錄", "", f"- 資料夾：`{run.name}`", f"- skill 版本：{rj.get('skill_version', '')}", ""]
    return "\n".join(out)


def _load_tactics():
    path = io.DATA_DIR / "tw" / "tactics.toml"
    return io.read_toml(path).get("tactic", []) if path.exists() else []


def _model_cell(models, s):
    """The seat table's 模型 cell: the model and reasoning effort detect recorded for the seat's engine (Codex roles
    do not read the user's own Codex settings, so these are what ran)."""
    seat = next((x for x in models.get("seats", []) if x.get("seat") == s["seat"]), {})
    engine = next((e for e in models.get("engines", []) if e.get("engine") == s["engine"]
                   and (not seat.get("model") or e.get("model") == seat.get("model"))), {})
    model = seat.get("model") or engine.get("model")
    return f"{_cell(s['engine'])}（{_cell(model) or '預設模型'}，推理強度 {_cell(engine.get('effort')) or '預設'}）"
