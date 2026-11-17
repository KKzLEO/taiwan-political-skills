"""Turn a finished run directory into report.md. Pure formatting — no judgement happens here."""

from __future__ import annotations

from pathlib import Path

from . import detect, io, media
from .labels import CONTEXT_FLAGS, TIER_NAMES, ZH_LABELS
from .score import round_half_up

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
    out.append(f"**結果：{sc['result']}｜{cred_text}｜信心度 {conf['level']}（{conf['score']}）｜"
               f"{mode}・跨模型 {len(ok_cross)} 席｜{'可公開' if sc['publishable'] else '不可公開'}**")
    out.append("")
    if sc.get("result_reason"):
        out += [f"> {sc['result_reason']}", ""]
    if claims_doc.get("prompt_was_leading"):
        out += ["> 提問已改寫為中立命題。", ""]

    # 一句話結論
    out += ["## 結論", ""]
    core = sorted([c for c in verdicts["claims"] if claims[c["claim_id"]]["core"]],
                  key=lambda c: (-c["importance"], c["claim_id"]))
    for c in core or verdicts["claims"]:
        out.append(f"- **{c['claim_id']}「{_cell(claims[c['claim_id']]['original'])}」：{ZH_LABELS[c['label']]}。**"
                   f"{_first_sentence(c['reasoning'])}")
    out.append("")

    # 範圍與限制
    out += ["## 查核範圍和限制", "",
            f"- 查核時間：{rj.get('created_at', '')}；{mode}；主體：{models['host']}",
            f"- 輸入類型：{source.get('input_type')}" + (f"；網址：{source['url']}" if source.get("url") else ""),
            "", "| 席位 | 角色 | 模型 | 狀態 | 跨模型 | 能上網 | 隔離 |", "|---|---|---|---|---|---|---|"]
    for s in seats:
        out.append(f"| {s['seat']} | {LENS.get(s['lens'], s['lens'])} | {s['engine']} | "
                   f"{'成功' if s['status'] == 'ok' else '失敗'} | {'是' if s['cross_model'] else '否'} | "
                   f"{'是' if s['can_search'] else '否'} | {ISOLATION.get(s['isolation'], s['isolation'])} |")
    limits = list(trace.get("limits", []))
    for e in ledger.values():
        if e.get("access_note", "full") != "full":
            limits.append(f"{e['id']}（{_cell(e.get('publisher'))}）：{ACCESS.get(e['access_note'], e['access_note'])}")
    if limits:
        out += ["", "限制："] + [f"- {_cell(x)}" for x in limits]
    out.append("")

    # 逐項判定
    out += ["## 逐項判定", "", "| 命題 | 原文說法 | 判定 | 理由 | 證據 |", "|---|---|---|---|---|"]
    for c in verdicts["claims"]:
        meta = claims[c["claim_id"]]
        status = {"passed": "（覆核通過）", "failed": "（覆核未通過）"}.get(c["review_status"], "")
        out.append(f"| {c['claim_id']} | {_cell(meta['original'])} | {ZH_LABELS[c['label']]}{status} | "
                   f"{_cell(c['reasoning'])} | {', '.join(c.get('evidence_ids', [])) or '—'} |")
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

    # 操弄手法
    if trace.get("tactics"):
        out += ["## 操弄手法（不影響可信度）", ""]
        for t in trace["tactics"]:
            info = tactics.get(t["tactic_id"], {})
            line = f"- **{info.get('name', t['tactic_id'])}**（{t['tactic_id']}）：「{_cell(t['quote'])}」{_cell(t.get('explanation'))}"
            if info.get("layer") == "attribution" and not trace.get("attribution"):
                line += "。特徵相符，但無法確認背後是誰。"
            out.append(line)
            if info.get("how_to_spot"):
                out.append(f"  - 怎麼辨認：{info['how_to_spot']}")
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

    # 爭議點
    if verdicts.get("disputes"):
        out += ["## 爭議點", ""]
        for d in verdicts["disputes"]:
            out.append(f"- **{d['claim_id']}**：裁判原本判「{ZH_LABELS[d['judge_label']]}」（{_cell(d['judge_reasoning'])}），"
                       "覆核沒有通過，所以改判「無法證實」。")
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
        out += [f"- 可信度 = 100 × 命題正確度 {cred['accuracy']:.4f} = {cred['raw']} → {cred['score']}",
                f"- 脈絡問題：{flags}（已反映在「誤導」等判定裡，不另外扣分）"]
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
