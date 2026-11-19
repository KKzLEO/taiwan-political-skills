"""Turn a finished run directory into report.md. Pure formatting — no judgement happens here."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from . import detect, io, media
from .labels import CONTEXT_FLAGS, FACTORS, TIER_NAMES, UNSCORED_TYPES, ZH_LABELS
from .score import not_scored, round_half_up, time_effect

WIDTH = 30
ISOLATION = {"full": "完整隔離", "partial": "部分隔離", "unknown": "未確認", "host": "主模型"}
LENS = {"evidence": "反方 A：證據", "counter": "反方 B：反證", "stance": "反方 C：立場", "external": "外部反方"}
PUBLISHER = {"news": "新聞媒體", "public_figure": "公眾人物", "official": "官方", "anonymous": "匿名",
             "content_farm": "內容農場", "private_individual": "一般民眾", "unknown": "不明"}
BYLINE = {"present": "有署名", "absent": "沒有署名", "n/a": "不適用"}
ACCESS = {"full": "全文", "paywall": "付費牆", "blocked": "被擋", "archived": "存檔", "snippet": "只有摘要",
          "not_original": "未直接核對原始貼文", "no_transcript": "沒有逐字稿"}


def _cell(text) -> str:
    return str(text or "").replace("|", "／").replace("\n", " ").strip()


def _first_sentence(text, limit=120) -> str:
    text = _cell(text)
    cut = text.find("。")
    first = text[:cut + 1] if cut >= 0 else text
    return first if len(first) <= limit else first[:limit] + "…"


def _spectrum(score) -> list:
    pos = round_half_up(score * WIDTH / 100)
    bar = "━" * pos + "▲" + "━" * (WIDTH - pos)
    return ["```text", f"錯誤 {bar} 正確", " " * (5 + pos) + str(score), "```"]


def _title(source) -> str:
    if source.get("url"):
        return source["url"]
    text = (source.get("original_text") or "").strip().replace("\n", " ")
    return text[:30] + ("…" if len(text) > 30 else "")


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


def render(run, outlets=None, tactics=None) -> str:
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
    out = [f"# 查核報告：{_title(source)}", ""]

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
    core = sorted([c for c in content if claims[c["claim_id"]]["core"]],
                  key=lambda c: (-c["importance"], c["claim_id"]))
    # A time claim is listed only when it did something: judged wrong, or left unsettled.
    for c in [c for c in timed if time_effect(c)] + (core or content):
        out.append(f"- **{c['claim_id']}「{_cell(claims[c['claim_id']]['original'])}」：{ZH_LABELS[c['label']]}"
                   f"{'（時間命題）' if c.get('time') else '（不計分）' if not_scored(c) else ''}。**"
                   f"{_first_sentence(c['reasoning'])}")
    out.append("")

    # 範圍與限制
    out += ["## 查核範圍和限制", "",
            f"- 查核時間：{rj.get('created_at', '')}；{mode}；主體：{models['host']}",
            f"- 輸入類型：{source.get('input_type')}" + (f"；網址：{source['url']}" if source.get("url") else ""),
            "", "| 席位 | 角色 | 模型 | 狀態 | 跨模型 | 能上網 | 隔離 |", "|---|---|---|---|---|---|---|"]
    for s in seats:
        out.append(f"| {s['seat']} | {LENS.get(s['lens'], s['lens'])} | {s['engine']} | "
                   f"{ {'ok': '成功', 'missing': '沒有執行'}.get(s['status'], '失敗')} | {'是' if s['cross_model'] else '否'} | "
                   f"{'是' if s['can_search'] else '否'} | {ISOLATION.get(s['isolation'], s['isolation'])} |")
    if timed:
        out.append(f"- 時間命題：{'、'.join(c['claim_id'] + '（' + TIME_KINDS[c['time']] + '）' for c in timed)}。"
                   "判對不加分；判錯時，期限前提讓可信度不高於它的正確度，暗示的時間讓可信度最高 79。")
    else:
        out.append("- 時間命題：沒有（拆題沒有標出期限前提或暗示的時間）。")
    if not any(c["time"] == "relative" for c in timed) and not str(source.get("published_at") or "").strip():
        said = next((w for w in JUST_NOW if w in (source.get("original_text") or "")), None)
        if said:
            out.append(f"  - 訊息裡有「{said}」，如果這其實是舊消息，結論沒有反映這一點。")
    limits = list(trace.get("limits", []))
    if trace.get("set_aside_tactics"):
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
        status = {"passed": "（覆核通過）", "failed": "（覆核未通過）"}.get(c["review_status"], "")
        if c.get("time"):
            status += "（時間命題）"
        elif not_scored(c):
            status += "（不計分）"
            unscored_ids.append(c["claim_id"])
        weight = "—" if c.get("time") else \
            str(c["importance"]) + (f"（辯論後由 {c['importance_from']} 調整）" if "importance_from" in c else "")
        out.append(f"| {c['claim_id']} | {_cell(meta['original'])} | {weight} | {ZH_LABELS[c['label']]}{status} | "
                   f"{_cell(c['reasoning'])} | {', '.join(c.get('evidence_ids', [])) or '—'} |")
    if unscored_ids:
        out += ["", f"- {'、'.join(unscored_ids)} 是意見、預測或模糊到無法查證的說法，判定只供參考，不算進可信度。"]
    adjusted = [c for c in verdicts["claims"] if "importance_from" in c or (c.get("time") and c.get("importance_attacks"))]
    if adjusted:
        out.append("")
        for c in adjusted:
            seats = "、".join(sorted({a["seat"] for a in c.get("importance_attacks", [])}))
            why = "；".join(_cell(a["ruling_reason"]) for a in c.get("importance_attacks", []))
            if c.get("time"):
                out.append(f"- {c['claim_id']} 是時間命題，重要性不影響計分；反方 {seats} 的重要性挑戰（成立）沒有套用。")
                continue
            out.append(f"- {c['claim_id']} 的重要性由 {c['importance_from']} 調為 {c['importance']}"
                       f"（反方 {seats} 提出）。裁判：{why}")
    out.append("")

    # 溯源
    out += ["## 溯源", ""]
    fs = trace.get("first_seen")
    out.append(f"- 最早出現：{fs.get('date', '')} {fs.get('platform', '')} {fs.get('url', '')}".rstrip()
               if fs else "- 最早出現：查不到")
    for v in trace.get("variants", []):
        out.append(f"- 變體：{v.get('date', '')} {_cell(v.get('difference'))} {v.get('url', '')}")
    for s in trace.get("spread_signals", []):
        out.append(f"- 傳播跡象：{_cell(s['signal'])}（{s['evidence_url']}）")
    if trace.get("attribution"):
        for a in trace["attribution"]:
            out.append(f"- 正式報告：{a['report_org']} 指出「{_cell(a['statement'])}」（{a['report_url']}）")
    else:
        out.append("- 背後是誰：沒有政府、研究機構或平台的正式報告點名這個案例，不做推斷。")
    out.append("")

    # 報導品質
    pub = trace.get("publisher", {})
    out += ["## 報導品質（不影響可信度）", "",
            f"- 發布者：{PUBLISHER.get(pub.get('kind'), pub.get('kind', '不明'))}"
            + (f"・{pub['name']}" if pub.get("name") else "")]
    if pub.get("byline"):
        out.append(f"- 署名：{BYLINE.get(pub['byline'], pub['byline'])}")
    outlet = next((o for o in outlets if o.get("id") == pub.get("outlet_id")), None) if pub.get("outlet_id") else None
    if outlet:
        t = outlet.get("trust")
        out.append(f"- 信任度：{t['score']}%（{t['source']}，{t['year']}）" if t else "- 信任度：沒有調查資料")
        if outlet.get("lean"):
            for ln in outlet["lean"]:
                out.append(f"- 立場研究：{ln['label']}（{ln['source']}，{ln['year']}）")
        else:
            out.append("- 立場研究：目前沒有可引用的研究")
        if outlet.get("ownership"):
            out.append(f"- 所有權：{_cell(outlet['ownership'])}")
        for r in outlet.get("record", []):
            out.append(f"- 紀錄：{r.get('date', '')} {_cell(r.get('summary'))}（{r.get('url', '')}）")
    issues = pub.get("wording_issues", [])
    out.append("- 用詞：" + ("；".join(f"「{_cell(w['quote'])}」{_cell(w['issue'])}" for w in issues) if issues else "沒有發現明顯不中立的用詞"))
    for f in pub.get("flagged", []):
        out.append(f"- 被點名或更正：{_cell(f.get('note'))}（{f.get('url', '')}）")
    out.append("")

    # 操弄手法（裁判逐項檢查後撤回的標記不列為已辨識）
    if trace.get("tactics"):
        removed = {w["tactic_id"]: w.get("reason", "") for w in verdicts.get("removed_tactics", [])}
        out += ["## 操弄手法（不影響可信度）", "", "> 這一段還沒通過跨陣營一致性驗證，不要引用在公開貼文。", ""]
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
        out += ["## 和既有查核的比對", "",
                "| 機構 | 對方的結論 | 我們的最終判定 | 正方重驗 | 說明 |", "|---|---|---|---|---|"]
        for p in rechecked:
            ids = [i for i in p.get("claim_ids", []) if i in final]
            ours = "、".join(f"{i} {ZH_LABELS[final[i]]}" for i in ids) or "—"
            changed = any(initial.get(i) != final[i] for i in ids)
            check = ("一致" if p.get("agree") else "不一致") + ("（辯論後改判）" if changed else "")
            out.append(f"| [{_cell(p['org'])}]({p['url']}) | {_cell(p.get('their_label'))} | {ours} | "
                       f"{check} | {_cell(p.get('note'))} |")
        out.append("")

    # 辯論後的修正（成立的溯源和手法攻擊；上面的溯源內容是辯論前寫的）
    if verdicts.get("trace_attacks_upheld"):
        out += ["## 辯論後的修正", "",
                "前面的溯源、報導品質、操弄手法、和既有查核的比對，以及查核範圍裡關於溯源的說明，都是辯論前寫的。"
                "以下是裁判判定成立的修正，和前文不同時以這裡為準。", ""]
        for a in verdicts["trace_attacks_upheld"]:
            out.append(f"- 反方 {a['seat']} 的質疑成立（{a['attack_id']}）：{_cell(a['ruling_reason'])}")
        out.append("")

    # 爭議點
    if verdicts.get("disputes"):
        out += ["## 爭議點", ""]
        for d in verdicts["disputes"]:
            if d.get("label_kept"):
                out.append(f"- **{d['claim_id']}**：判定維持「{ZH_LABELS[d['judge_label']]}」（{_cell(d['judge_reasoning'])}）。"
                           "覆核同意這個判定，但認為理由或證據還有缺漏。")
            else:
                out.append(f"- **{d['claim_id']}**：裁判原本判「{ZH_LABELS[d['judge_label']]}」（{_cell(d['judge_reasoning'])}），"
                           "覆核沒有通過，所以改判「無法證實」。")
            if d.get("proponent_label"):
                out.append(f"  - 這個命題沒有任何會改判的成立攻擊（重要性挑戰、溯源和手法攻擊不算），"
                           f"是裁判自己把正方判「{ZH_LABELS[d['proponent_label']]}」改成「{ZH_LABELS[d['judge_label']]}」，"
                           "所以每個反方席位都要覆核。")
            for o in d["objections"]:
                out.append(f"  - 反方 {o['seat']}：{_cell(o['argument'])}")
            for r in d["review_reasons"]:
                out.append(f"  - 覆核：{_cell(r)}")
        out.append("")

    # 已檢驗的質疑
    if verdicts.get("checked_objections"):
        out += ["## 已檢驗的質疑", ""]
        for o in verdicts["checked_objections"]:
            where = o["claim_id"] or "溯源"
            out.append(f"- （{where}）{_cell(o['argument'])} → 不成立：{_cell(o['ruling_reason'])}")
        out.append("")

    # 法條
    legal = [c for c in verdicts["claims"] if c.get("legal")]
    if legal:
        out += ["## 法條（非法律意見）", "",
                "以下只整理條文原文。超出條文字面的解讀有爭議時，建議諮詢律師。", ""]
        for c in legal:
            status = "已取得條文原文" if c.get("law_text_obtained") else "沒有取得條文原文，判定為無法證實"
            out.append(f"- {c['claim_id']}：{status}")
            for eid in c.get("evidence_ids", []):
                e = ledger[eid]
                if e["tier"] == 1:
                    out.append(f"  - 「{_cell(e['excerpt'])}」（{e['url']}）")
        out.append("")

    # 評分拆解
    out += ["## 評分拆解", ""]
    if cred:
        flags = "、".join(CONTEXT_FLAGS[f] for f in cred["context_flags"]) or "無"
        out += [f"- 主要說法（計分命題裡重要性最高的一層）：{'、'.join(cred['main_claims'])}",
                f"- 可信度 = 100 × 兩者中較低的（主要說法的平均正確度 {cred['main_accuracy']:.4f}、"
                f"全部計分命題依重要性加權的正確度 {cred['overall_accuracy']:.4f}）= {cred['raw']} → {cred['score']}"]
        for c in timed:
            if time_effect(c) == "void":
                factor = FACTORS[c["label"]]
                out.append(f"- 期限前提 {c['claim_id']} 判「{ZH_LABELS[c['label']]}」：可信度不高於 "
                           f"100 × {float(factor):g} = {round_half_up(100 * factor)}。")
        if cred.get("capped"):
            out.append("- 有命題判錯誤、誤導或部分錯誤，所以可信度上限 79，最高是「大致符合」。")
        out.append(f"- 脈絡問題：{flags}（已反映在「誤導」等判定裡，不另外扣分）")
    else:
        out.append("- 沒有可以計分的事實命題。")
    out.append(f"- 信心度：{conf['score']}（{conf['level']}）")
    for d in conf["deductions"]:
        out.append(f"  - −{d['points']}：{d['reason']}")
    out.append("")

    # 來源
    out += ["## 來源", "", "| 編號 | 來源 | 層級 | 存取 | 日期 |", "|---|---|---|---|---|"]
    for e in ledger.values():
        out.append(f"| {e['id']} | [{_cell(e.get('title') or e.get('publisher'))}]({e['url']}) | "
                   f"{TIER_NAMES.get(e['tier'], e['tier'])} | {ACCESS.get(e.get('access_note', 'full'))} | {e.get('accessed', '')} |")
    out += ["", "引用查核機構與 Cofacts 的內容時，只附連結和簡短摘錄，著作權屬原機構。", ""]

    out += ["## 執行紀錄", "", f"- 資料夾：`{run.name}`", f"- skill 版本：{rj.get('skill_version', '')}", ""]
    return "\n".join(out)


def _load_tactics():
    path = io.DATA_DIR / "tw" / "tactics.toml"
    return io.read_toml(path).get("tactic", []) if path.exists() else []
