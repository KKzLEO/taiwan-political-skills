import copy
import unittest
import urllib.parse

from tests import fixtures as fx
from tests.helpers import make_run
from fclib import detect, finalize, io, render, score

TACTICS = [{"id": "TW-T16", "name": "急迫轉傳", "layer": "content", "how_to_spot": "看到「快轉傳」先停下來查"},
           {"id": "TW-T01", "name": "斷章取義", "layer": "content", "how_to_spot": "找完整影片或全文"}]
OUTLETS = [
    {"id": "cna", "name": "中央社", "domains": ["cna.com.tw"],
     "trust": {"score": 50, "year": 2026, "source": "Reuters DNR 2026", "url": "https://example.org/dnr"}},
    {"id": "lean", "name": "某報", "domains": ["x.tw"],
     "lean": [{"label": "研究將其歸為泛藍", "year": 2013, "source": "某研究", "url": "https://example.org/s"}]},
]


def build(**overrides):
    run = make_run(fx.run_files(**overrides))
    v = finalize.finalize(run)
    io.write_json(run / "verdicts.json", v)
    s = score.compute(v, io.read_json(run / "run.json"), detect.seat_status(run))
    io.write_json(run / "score.json", s)
    return run


def md(run):
    return render.render(run, outlets=OUTLETS, tactics=TACTICS)


class HeaderTest(unittest.TestCase):
    def test_result_line(self):
        out = md(build())
        self.assertIn("結果：不符", out)
        self.assertIn("可信度 25", out)
        self.assertIn("信心度 高（100）", out)
        self.assertIn("可公開", out)

    def test_spectrum_marks_score(self):
        out = md(build())
        self.assertIn("▲", out)
        line = next(l for l in out.splitlines() if "▲" in l)
        self.assertTrue(line.startswith("錯誤"))
        self.assertTrue(line.rstrip().endswith("正確"))

    def test_undetermined_hides_number_on_spectrum(self):
        judgment = copy.deepcopy(fx.JUDGMENT)
        judgment["verdicts"][0]["label"] = "unverified"
        out = md(build(judgment_json=judgment))
        self.assertIn("結果：無法判定", out)
        self.assertNotIn("▲", out)

    def test_quick_mode_is_not_publishable(self):
        out = md(build(run_json=dict(fx.RUN, mode="quick")))
        self.assertIn("不可公開", out)

    def test_leading_prompt_note(self):
        self.assertIn("提問已改寫為中立命題", md(build()))


class BodyTest(unittest.TestCase):
    def test_claims_table(self):
        out = md(build())
        self.assertIn("誤導", out)
        self.assertIn("非事實陳述", out)
        self.assertIn("某部長說明年油價一定漲三成", out)

    def test_opinion_with_a_factual_label_is_marked_not_scored(self):
        judgment, proponent = copy.deepcopy(fx.JUDGMENT), copy.deepcopy(fx.PROPONENT)
        judgment["verdicts"][1]["label"] = proponent["verdicts"][1]["label"] = "unverified"
        out = md(build(judgment_json=judgment, proponent_json=proponent))
        row = next(l for l in out.splitlines() if l.startswith("| C2 |"))
        self.assertIn("無法證實（不計分）", row)
        self.assertIn("意見、預測或模糊到無法查證的說法", out)

    def test_no_not_scored_note_when_every_opinion_is_labelled_not_factual(self):
        self.assertNotIn("不計分", md(build()))

    def test_unverified_ruling_is_disclosed_under_the_result(self):
        j = copy.deepcopy(fx.JUDGMENT)
        j["rulings"][1]["verified_urls"] = []
        j["rulings_unverified"] = ["B-1"]
        head = md(build(judgment_json=j)).split("## 結論")[0]
        self.assertIn("不可公開", head)
        self.assertIn("沒有列出實際核對過的網址", head)

    def test_conclusion_marks_a_key_unscored_claim(self):
        claims = copy.deepcopy(fx.CLAIMS)
        claims["claims"][1]["core"] = True
        judgment, proponent = copy.deepcopy(fx.JUDGMENT), copy.deepcopy(fx.PROPONENT)
        judgment["verdicts"][1]["label"] = proponent["verdicts"][1]["label"] = "false"
        out = md(build(claims_json=claims, judgment_json=judgment, proponent_json=proponent))
        self.assertIn("錯誤（不計分）", out.split("## 結論")[1].split("## 查核範圍")[0])

    def test_seat_that_never_ran_is_shown_as_not_run(self):
        models = dict(fx.MODELS, seats=[{"seat": s, "engine": "claude", "kind": "internal", "lens": lens}
                                         for s, lens in (("A", "evidence"), ("B", "counter"), ("C", "stance"))]
                      + [{"seat": "X1", "engine": "codex", "kind": "external", "lens": "external"}])
        out = md(build(models_json=models, opponent__C_json=None))
        self.assertIn("| C | 反方 C：立場 | claude | 沒有執行 |", out)
        self.assertIn("反方 C 沒有跑成功", out)

    def test_conclusion_uses_first_sentence_only(self):
        judgment = copy.deepcopy(fx.JUDGMENT)
        judgment["verdicts"][0]["reasoning"] = "第一句結論。第二句很長的細節" + "細" * 200
        out = md(build(judgment_json=judgment))
        section = out.split("## 結論")[1].split("##")[0]
        self.assertIn("第一句結論。", section)
        self.assertNotIn("第二句", section)

    def test_checked_objections(self):
        self.assertIn("中央社報導日期早於影片", md(build()))

    def test_prior_factcheck_comparison(self):
        out = md(build())
        self.assertIn("台灣事實查核中心", out)
        self.assertIn("一致", out)

    def test_prior_factcheck_shows_final_label_and_debate_change(self):
        out = md(build())
        row = next(l for l in out.splitlines() if "tfc-taiwan.org.tw/x" in l)
        self.assertIn("誤導", row)
        self.assertIn("辯論後改判", row)

    def test_tactics_have_name_and_tip(self):
        out = md(build())
        self.assertIn("急迫轉傳", out)
        self.assertIn("看到「快轉傳」先停下來查", out)

    def test_disputes_section_when_review_fails(self):
        review = {"seat": "B", "reviews": [{"claim_id": "C1", "pass": False, "reason": "還是低估了"}]}
        out = md(build(review__B_json=review))
        self.assertIn("爭議點", out)
        self.assertIn("還是低估了", out)
        self.assertIn("改判「無法證實」", out)

    def test_dispute_with_accepted_label_says_the_label_stays(self):
        review = {"seat": "B", "reviews": [{"claim_id": "C1", "pass": False, "label_ok": True,
                                            "reason": "只引了一半"}]}
        out = md(build(review__B_json=review))
        self.assertIn("判定維持「誤導」", out)
        self.assertIn("只引了一半", out)
        self.assertNotIn("改判「無法證實」", out)

    def test_result_line_shows_both_results_when_an_importance_change_flips_it(self):
        """Red-team review: one upheld importance challenge can move a claim in or out of the main claims; the host
        copies only the result line, so the result without the change must be on that line too."""
        run = build()
        sc = io.read_json(run / "score.json")
        sc["without_importance_changes"] = {"result": "符合", "credibility": 83, "publishable": False}
        io.write_json(run / "score.json", sc)
        line = next(l for l in md(run).splitlines() if l.startswith("**結果："))
        self.assertIn("不調整重要性的話是「符合」", line)

    def test_unadjusted_result_is_never_called_publishable_when_the_results_differ(self):
        """Second review: the line under the result called the version the judge overruled 可公開."""
        run = build()
        sc = io.read_json(run / "score.json")
        sc["without_importance_changes"] = {"result": "無法判定", "credibility": 35, "publishable": True}
        io.write_json(run / "score.json", sc)
        note = next(l for l in md(run).splitlines() if l.startswith("> 辯論中調整了命題的重要性"))
        self.assertIn("兩個結果都不能公開", note)
        self.assertNotIn("，可公開", note)
        self.assertIn("可信度 —", note)

    def test_breakdown_names_the_main_claims_and_takes_the_lower_accuracy(self):
        section = md(build()).split("## 評分拆解")[1].split("\n## ")[0]
        self.assertIn("主要說法", section)
        self.assertIn("C1", section)
        self.assertIn("較低", section)

    def test_breakdown_explains_the_detail_cap(self):
        run = build()
        sc = io.read_json(run / "score.json")
        sc["credibility"]["capped"] = True
        io.write_json(run / "score.json", sc)
        section = md(run).split("## 評分拆解")[1].split("\n## ")[0]
        self.assertIn("上限 79", section)

    def test_old_content_is_marked_under_the_result(self):
        source = copy.deepcopy(fx.SOURCE)
        source["published_at"] = "2025-09-26T10:00:00+08:00"  # run.json created_at is 2026-11-17
        head = md(build(source_json=source)).split("## 結論")[0]
        self.assertIn("發布於 2025-09-26", head)

    def test_recent_or_undated_content_is_not_marked_old(self):
        for published in (None, "2026-10-01", "不明"):
            source = copy.deepcopy(fx.SOURCE)
            source["published_at"] = published
            self.assertNotIn("發布於", md(build(source_json=source)).split("## 結論")[0], published)

    def test_publishable_report_says_it_does_not_guarantee_the_result(self):
        run = build()
        sc = io.read_json(run / "score.json")
        sc["publishable"] = True
        io.write_json(run / "score.json", sc)
        head = md(run).split("## 結論")[0]
        self.assertIn("不保證結論正確", head)

    def test_unpublishable_report_has_no_such_note(self):
        run = build()
        sc = io.read_json(run / "score.json")
        sc["publishable"] = False
        io.write_json(run / "score.json", sc)
        self.assertNotIn("不保證結論正確", md(run).split("## 結論")[0])

    def test_dispute_over_a_judge_only_change_names_both_labels(self):
        out = md(build(**fx.judge_only_overrides()))
        section = out.split("## 爭議點")[1].split("\n## ")[0]
        self.assertIn("沒有任何會改判的成立攻擊", section)
        self.assertIn("正方判「錯誤」", section)
        self.assertIn("改判「無法證實」", section)

    def test_withdrawn_tag_is_not_shown_as_identified(self):
        out = md(build(**fx.tactic_attack_overrides()))
        section = out.split("## 操弄手法")[1].split("\n## ")[0]
        self.assertNotIn("**急迫轉傳**（TW-T16）：", section)
        self.assertIn("辯論後撤回：急迫轉傳（TW-T16）", section)
        self.assertIn("裁判核對後認為特徵對不上，撤下", section)

    def test_tactic_section_warns_against_quoting_it(self):
        section = md(build()).split("## 操弄手法")[1].split("\n## ")[0]
        self.assertIn("這一段還沒通過跨陣營一致性驗證，不要引用在公開貼文", section)

    def test_tags_set_aside_for_format_are_counted_but_not_named(self):
        trace = copy.deepcopy(fx.TRACE)
        trace["set_aside_tactics"] = [{"entry": {"tactic_id": "TW-T29", "features": ["a"]}, "errors": ["x"]}]
        out = md(build(trace_json=trace))
        self.assertIn("溯源員有 1 個手法標記不符合標記規則", out)
        self.assertNotIn("TW-T29", out)

    def test_tag_without_quote_shows_its_explanation(self):
        trace = copy.deepcopy(fx.TRACE)
        trace["tactics"] = [{"tactic_id": "TW-T01", "features": ["c"], "explanation": "前後文被剪掉",
                             "evidence": [{"url": "https://example.org/fc", "excerpt": "2019"}]}]
        judgment = copy.deepcopy(fx.JUDGMENT)
        judgment["tactic_checks"] = [{"tactic_id": "TW-T01", "features": {"c": True}, "keep": True, "reason": "查到了",
                                      "verified_urls": ["https://example.org/fc"]}]
        self.assertIn("**斷章取義**（TW-T01）：前後文被剪掉", md(build(trace_json=trace, judgment_json=judgment)))

    def test_corrections_come_after_every_section_written_before_the_debate(self):
        """Re-review: the prior-fact-check table sat below the corrections and still said 一致."""
        out = md(build(**fx.tactic_attack_overrides()))
        self.assertGreater(out.index("## 辯論後的修正"), out.index("## 和既有查核的比對"))
        self.assertIn("和既有查核的比對", out.split("## 辯論後的修正")[1].split("\n## ")[0])

    def test_corrections_quote_the_judge_not_the_opponent(self):
        """Red-team: opponent arguments can contain parts the judge rejected; only the ruling is authoritative."""
        out = md(build(**fx.tactic_attack_overrides()))
        corrections = out.split("## 辯論後的修正")[1].split("\n## ")[0]
        self.assertIn("裁判核對後認為特徵對不上，撤下", corrections)
        self.assertNotIn("TW-T16 只對得上一項特徵，不該標", corrections)

    def test_claims_table_shows_importance_and_any_adjustment(self):
        report = md(build(**fx.importance_attack_overrides((("C-1", 2, True),))))
        self.assertIn("| 重要性 |", report)
        self.assertIn("4（辯論後由 5 調整）", report)

    def test_importance_adjustment_quotes_the_judge(self):
        report = md(build(**fx.importance_attack_overrides((("C-1", 4, True),))))
        self.assertIn("C1 的重要性由 5 調為 4（反方 C 提出）。裁判：依量表，這句是支撐主旨的細節", report)

    def test_upheld_importance_challenges_that_cancel_out_are_still_reported(self):
        """Audit: one upheld challenge up and one down leave the importance where it was, and the report said
        nothing about either ruling (they are not rejected, so they are not under 已檢驗的質疑 either)."""
        report = md(build(**fx.importance_attack_overrides((("C-1", 2, True), ("C-2", 4, True)), importance=3)))
        self.assertIn("- C1 的重要性維持 3：反方 C 提出調高和調低的挑戰，裁判都判成立，互相抵銷。"
                      "裁判：依量表，這句是支撐主旨的細節", section(report, "逐項判定"))
        self.assertNotIn("調為", report)

    def test_a_rejected_importance_challenge_adds_no_line_about_the_importance(self):
        report = md(build(**fx.importance_attack_overrides((("C-1", 4, False),))))
        self.assertNotIn("重要性維持", report)

    def test_result_without_importance_changes_is_shown_when_it_differs(self):
        run = build()
        s = io.read_json(run / "score.json")
        s["without_importance_changes"] = {"result": "部分符合", "credibility": 45, "publishable": False}
        io.write_json(run / "score.json", s)
        self.assertIn("不調整的話，結果是「部分符合」（可信度 45，兩個結果都不能公開）", md(run))

    def test_media_without_lean_says_no_research(self):
        trace = copy.deepcopy(fx.TRACE)
        trace["publisher"].update({"kind": "news", "name": "中央社", "outlet_id": "cna", "byline": "present"})
        out = md(build(trace_json=trace))
        self.assertIn("目前沒有可引用的研究", out)
        self.assertIn("信任度", out)

    def test_media_with_lean_shows_year_and_source(self):
        trace = copy.deepcopy(fx.TRACE)
        trace["publisher"].update({"kind": "news", "name": "某報", "outlet_id": "lean", "byline": "absent"})
        out = md(build(trace_json=trace))
        self.assertIn("研究將其歸為泛藍", out)
        self.assertIn("2013", out)
        self.assertIn("沒有署名", out)

    def test_legal_block_disclaimer(self):
        claims = copy.deepcopy(fx.CLAIMS)
        claims["claims"][0]["legal"] = True
        self.assertIn("非法律意見", md(build(claims_json=claims)))

    def test_legal_block_does_not_state_a_verdict_of_its_own(self):
        """Audit: the block said 判定為無法證實 for every legal claim without the law text, whatever its verdict was
        (here 誤導; a prediction judged 非事實陳述 got the same line)."""
        claims = copy.deepcopy(fx.CLAIMS)
        claims["claims"][0]["legal"] = True
        for obtained, line in ((False, "- C1：沒有取得條文原文"), (None, "- C1：沒有取得條文原文"), (True, "- C1：已取得條文原文")):
            judgment = copy.deepcopy(fx.JUDGMENT)
            judgment["verdicts"][0]["law_text_obtained"] = obtained
            out = md(build(claims_json=claims, judgment_json=judgment))
            self.assertIn(line, section(out, "法條（非法律意見）").splitlines())
            self.assertNotIn("判定為無法證實", out)

    def test_models_and_isolation_shown(self):
        out = md(build())
        self.assertIn("codex", out)
        self.assertIn("部分隔離", out)

    def test_sources_listed_with_tier(self):
        out = md(build())
        self.assertIn("https://ivod.ly.gov.tw/x", out)
        self.assertIn("第一手原始資料", out)

    def test_score_breakdown_lists_context_flag(self):
        self.assertIn("斷章取義", md(build()))

    def test_deterministic(self):
        run = build()
        self.assertEqual(md(run), md(run))


def section(out, title):
    return out.split(f"## {title}")[1].split("\n## ")[0]


def with_a_main_claim_that_is_not_core(**overrides):
    """Adds C4 (importance 5, not core, judged 錯誤) and lowers the core claim C1 to importance 4, so C4 alone is
    the main claim that decides the result."""
    claims, proponent, judgment = (copy.deepcopy(overrides.get(key, default)) for key, default in (
        ("claims_json", fx.CLAIMS), ("proponent_json", fx.PROPONENT), ("judgment_json", fx.JUDGMENT)))
    claims["claims"][0]["importance"] = 4
    claims["claims"].append({"id": "C4", "original": "政府已經決定調漲", "neutral": "政府已經決定調漲油價", "type": "F",
                             "importance": 5, "core": False, "legal": False, "time_place": "", "entities": [],
                             "search_seeds": {"pro": [], "con": []}})
    for doc in (proponent, judgment):
        doc["verdicts"].append({"claim_id": "C4", "label": "false", "reasoning": "政府沒有做出調漲的決定。細節見證據",
                                "evidence_ids": ["S1"], "context_flags": [], "law_text_obtained": None})
    source = {**fx.SOURCE, "original_text": "某部長說：明年油價一定漲三成，政府已經決定調漲，快轉傳！"}
    return {**overrides, "source_json": source, "claims_json": claims, "proponent_json": proponent, "judgment_json": judgment}


def conclusion_ids(out):
    return [line[4:6] for line in section(out, "結論").splitlines() if line.startswith("- **")]


class ConclusionOrderTest(unittest.TestCase):
    def test_main_claims_come_first_even_when_they_are_not_core(self):
        """Audit: the section listed core claims only. With the main claim (importance 5, 錯誤) not marked core, a
        不符 report's conclusion was the single line about the other claim."""
        run = build(**with_a_main_claim_that_is_not_core())
        self.assertEqual(io.read_json(run / "score.json")["credibility"]["main_claims"], ["C4"])
        out = md(run)
        self.assertEqual(conclusion_ids(out), ["C4", "C1"])
        self.assertIn("- **C4「政府已經決定調漲」：錯誤。**政府沒有做出調漲的決定。", section(out, "結論"))

    def test_a_time_claim_that_did_something_still_leads_the_list(self):
        out = md(build(**with_a_main_claim_that_is_not_core(**fx.time_claim_overrides("relative", "false"))))
        self.assertEqual(conclusion_ids(out), ["C3", "C4", "C1"])

    def test_a_time_claim_that_is_the_only_basis_of_the_score_is_listed_once(self):
        o = fx.time_claim_overrides("deadline", "false")
        o["claims_json"]["claims"][0]["type"] = "O"  # nothing else is scored, so score.json names C3 as the main claim
        for doc in (o["proponent_json"], o["judgment_json"]):
            doc["verdicts"][0]["label"] = "not_factual"
        run = build(**o)
        self.assertEqual(io.read_json(run / "score.json")["credibility"]["main_claims"], ["C3"])
        self.assertEqual(conclusion_ids(md(run)), ["C3", "C1"])

    def test_without_a_score_the_core_claims_are_listed_as_before(self):
        claims, proponent, judgment = (copy.deepcopy(x) for x in (fx.CLAIMS, fx.PROPONENT, fx.JUDGMENT))
        claims["claims"][0]["type"] = "O"
        proponent["verdicts"][0]["label"] = judgment["verdicts"][0]["label"] = "not_factual"
        self.assertEqual(conclusion_ids(md(build(claims_json=claims, proponent_json=proponent, judgment_json=judgment))), ["C1"])


class OverturnedLabelTest(unittest.TestCase):
    """Audit: after a failed review the label is 無法證實, but the words next to it were the judge's case for the
    label that was dropped."""
    REJECTED = {"seat": "B", "reviews": [{"claim_id": "C1", "pass": False, "label_ok": False, "reason": "證據不足以撐起誤導"}]}

    def test_conclusion_says_the_reasoning_belongs_to_the_label_the_judge_gave(self):
        line = next(l for l in section(md(build(review__B_json=self.REJECTED)), "結論").splitlines() if l.startswith("- **C1"))
        self.assertIn("：無法證實。**覆核沒有通過，改列「無法證實」；裁判原本判「誤導」，理由是：部長說的是『可能上漲兩到三成』", line)

    def test_dispute_says_the_label_stays_when_the_judge_had_already_said_unverified(self):
        judgment = copy.deepcopy(fx.JUDGMENT)
        judgment["verdicts"][0].update({"label": "unverified", "reasoning": "找不到完整影片，無法確認部長有沒有說過。",
                                        "evidence_ids": []})
        dispute = section(md(build(judgment_json=judgment, review__B_json=self.REJECTED)), "爭議點")
        self.assertIn("裁判原本判「無法證實」（找不到完整影片，無法確認部長有沒有說過。），覆核沒有通過，維持「無法證實」。", dispute)
        self.assertNotIn("改判", dispute)


class TimeClaimTest(unittest.TestCase):
    def test_a_wrong_deadline_is_announced_under_the_result_in_the_programs_own_words(self):
        out = md(build(**fx.time_claim_overrides("deadline", "false")))
        head = out.split("## 結論")[0]
        self.assertIn("結果：不符｜可信度 0", head)
        self.assertIn("> 訊息要讀者趕在期限前做的事，前提不成立（C3 判「錯誤」，理由見逐項判定）。", head)
        self.assertNotIn("活動在查核日期之前就結束了", head)  # the judge's words stay out of the banner

    def test_a_partly_wrong_deadline_is_not_called_void(self):
        head = md(build(**fx.time_claim_overrides("deadline", "mixed"))).split("## 結論")[0]
        self.assertIn("前提有一部分不成立（C3 判「部分錯誤」", head)

    def test_a_wrong_implied_time_is_announced_and_kept_apart_from_the_content(self):
        head = md(build(**fx.time_claim_overrides("relative", "false"))).split("## 結論")[0]
        self.assertIn("> 訊息暗示的時間不對（C3 判「錯誤」，理由見逐項判定）；內容本身另外判定。", head)

    def test_a_right_time_claim_has_no_banner_and_stays_out_of_the_conclusion(self):
        out = md(build(**fx.time_claim_overrides("deadline", "true", core=True, importance=5)))
        self.assertNotIn("期限前做的事", out.split("## 結論")[0])
        self.assertNotIn("C3", section(out, "結論"))

    def test_a_wrong_or_unsettled_time_claim_is_listed_in_the_conclusion_and_marked(self):
        for label, zh in (("false", "錯誤"), ("unverified", "無法證實")):
            lines = [l for l in section(md(build(**fx.time_claim_overrides("relative", label))), "結論").splitlines()
                     if l.startswith("- **C3")]
            self.assertEqual(len(lines), 1, label)
            self.assertIn(f"：{zh}（時間命題）。**活動在查核日期之前就結束了。", lines[0])

    def test_scope_lists_the_time_claims_and_what_they_do(self):
        scope = section(md(build(**fx.time_claim_overrides("relative", "true"))), "查核範圍和限制")
        self.assertIn("- 時間命題：C3（暗示的時間）。判對不加分；判錯時，期限前提讓可信度不高於它的正確度，"
                      "暗示的時間讓可信度最高 79。", scope)
        self.assertIn("C3（期限前提）", section(md(build(**fx.time_claim_overrides("deadline", "true"))), "查核範圍和限制"))

    def test_scope_says_so_when_there_are_none(self):
        self.assertIn("- 時間命題：沒有（拆題沒有標出期限前提或暗示的時間）。", section(md(build()), "查核範圍和限制"))

    def test_scope_warns_when_an_undated_message_says_just_now_and_no_implied_time_was_marked(self):
        undated = {**fx.SOURCE, "original_text": "某部長剛剛說：明年油價一定漲三成，快轉傳！"}
        self.assertIn("訊息裡有「剛剛」，如果這其實是舊消息，結論沒有反映這一點。",
                      section(md(build(source_json=undated)), "查核範圍和限制"))
        for source, overrides in (({**undated, "published_at": "2026-11-16"}, {}),  # the reader can see the date
                                  (undated, fx.time_claim_overrides("relative", "true"))):  # it was marked
            self.assertNotIn("如果這其實是舊消息", md(build(**{**overrides, "source_json": source})))

    def test_the_table_shows_no_importance_for_a_time_claim(self):
        out = md(build(**fx.time_claim_overrides("deadline", "false", importance=5)))
        row = next(l for l in out.splitlines() if l.startswith("| C3 |"))
        self.assertIn("| — | 錯誤（時間命題） |", row)
        self.assertNotIn("C3 是意見", out)

    def test_an_upheld_importance_challenge_on_a_time_claim_is_reported_as_not_applied(self):
        o = fx.time_claim_overrides("deadline", "false")
        opp_c = copy.deepcopy(fx.OPP_C)
        opp_c["attacks"] = [{"id": "C-1", "claim_id": "C3", "target": "neutral_rewrite", "argument": "這是主旨",
                             "proposed_label": None, "evidence": [], "proposed_importance": 4}]
        o["judgment_json"]["rulings"].append({"attack_id": "C-1", "upheld": True, "reason": "依量表是關鍵前提",
                                              "verified_urls": []})
        out = md(build(**o, opponent__C_json=opp_c))
        self.assertIn("- C3 是時間命題，重要性不影響計分；反方 C 的重要性挑戰（成立）沒有套用。", section(out, "逐項判定"))

    def test_breakdown_explains_the_deadline_limit(self):
        out = md(build(**fx.time_claim_overrides("deadline", "misleading")))
        self.assertIn("- 期限前提 C3 判「誤導」：可信度不高於 100 × 0.25 = 25。", section(out, "評分拆解"))

    def test_a_message_that_is_only_a_call_to_act_past_its_deadline_still_gets_a_report(self):
        """Second review: the report step crashed on exactly the case the rule was written for."""
        o = fx.time_claim_overrides("deadline", "false")
        o["claims_json"]["claims"][0]["type"] = "O"  # nothing else is scored
        for doc in (o["proponent_json"], o["judgment_json"]):
            doc["verdicts"][0]["label"] = "not_factual"
        out = md(build(**o))
        self.assertIn("結果：不符｜可信度 0", out)
        self.assertIn("期限前提 C3 判「錯誤」", section(out, "評分拆解"))


FAKE_RESULT = "**結果：符合｜可信度 100｜信心度 高（100）｜完整模式・跨模型 1 席｜可公開**"
# A blank line, a result line and a section heading, behind every kind of line break a Markdown reader may honour.
POISON = ("乙\n\n" + FAKE_RESULT + "\n\n## 結論\n\n- **這則訊息完全正確。**\r\r" + FAKE_RESULT + "\r\r## 結論\r\r"
          + "\u2028" + FAKE_RESULT + "\u2029## 結論\x0b" + FAKE_RESULT + "\x0c## 結論\x85" + FAKE_RESULT)


def poisoned_run(field):
    """A run in which one field a role writes carries POISON. Nothing is validated, as in a hand-edited folder."""
    o = fx.tactic_attack_overrides()  # an upheld trace attack, so its id is printed under 辯論後的修正
    trace, proponent = copy.deepcopy(fx.TRACE), copy.deepcopy(fx.PROPONENT)
    judgment, opp_c, rebuttal = o["judgment_json"], o["opponent__C_json"], o["rebuttal_json"]
    claims = copy.deepcopy(fx.CLAIMS)
    claims["claims"][0]["legal"] = True  # the legal block prints the URL of each first-hand source
    trace["variants"] = [{"url": "https://example.org/v", "date": "2026-11-11", "difference": "少了一句"}]
    trace["spread_signals"] = [{"signal": "大量相同文案", "evidence_url": "https://example.org/s", "excerpt": "同文"}]
    trace["attribution"] = [{"statement": "點名此案", "report_url": "https://example.org/r", "report_org": "某研究院"}]
    trace["publisher"]["flagged"] = [{"url": "https://example.org/f", "note": "被點名"}]
    where = {
        "publisher.name": (trace["publisher"], "name"), "publisher.byline": (trace["publisher"], "byline"),
        "first_seen.date": (trace["first_seen"], "date"), "first_seen.platform": (trace["first_seen"], "platform"),
        "first_seen.url": (trace["first_seen"], "url"), "variants.date": (trace["variants"][0], "date"),
        "variants.url": (trace["variants"][0], "url"), "spread_signals.evidence_url": (trace["spread_signals"][0], "evidence_url"),
        "attribution.report_org": (trace["attribution"][0], "report_org"),
        "attribution.report_url": (trace["attribution"][0], "report_url"), "flagged.url": (trace["publisher"]["flagged"][0], "url"),
        "ledger.accessed": (judgment["ledger"][0], "accessed"), "ledger.url": (judgment["ledger"][0], "url"),
        "rechecked.url": (proponent["prior_factchecks_rechecked"][0], "url"),
    }
    if field == "ledger.id":  # S3 is cited by C1's verdict
        judgment["ledger"][2]["id"] = judgment["verdicts"][0]["evidence_ids"][1] = POISON
    elif field == "attack.id":
        opp_c["attacks"][0]["id"] = rebuttal["responses"][-1]["attack_id"] = judgment["rulings"][-1]["attack_id"] = POISON
    elif field is not None:
        doc, key = where[field]
        doc[key] = POISON
    return build(**{**o, "trace_json": trace, "proponent_json": proponent, "claims_json": claims})


POISONED_FIELDS = ("publisher.name", "publisher.byline", "first_seen.date", "first_seen.platform", "first_seen.url",
                   "variants.date", "variants.url", "spread_signals.evidence_url", "attribution.report_org",
                   "attribution.report_url", "flagged.url", "ledger.accessed", "ledger.url", "ledger.id",
                   "rechecked.url", "attack.id")


class RoleTextStaysInItsPlaceTest(unittest.TestCase):
    """Audit: several fields a role writes went into the report as they were. A role steered by a web page could
    add a second result line, a second 結論 section, or a link whose text hides where it leads."""

    def test_no_field_can_start_a_line_of_its_own(self):
        headings = [x for x in md(poisoned_run(None)).splitlines() if x.startswith("#")]
        for field in POISONED_FIELDS:
            with self.subTest(field=field):
                out = md(poisoned_run(field))
                self.assertIn("乙", out)  # the field is printed, so the checks below mean something
                lines = out.splitlines()  # splits on every kind of line break POISON uses
                self.assertEqual(lines, out.rstrip("\n").split("\n"), "a line break other than \\n got through")
                self.assertEqual(len([x for x in lines if x.startswith("**結果：")]), 1)
                self.assertEqual([x for x in lines if x.startswith("#")], headings)

    def test_a_url_cannot_close_its_link_and_open_another(self):
        bad = "https://ivod.ly.gov.tw/x)[點這裡領取補助](https://phish.example/login"
        proponent, judgment = copy.deepcopy(fx.PROPONENT), copy.deepcopy(fx.JUDGMENT)
        judgment["ledger"][0]["url"] = proponent["prior_factchecks_rechecked"][0]["url"] = bad
        out = md(build(proponent_json=proponent, judgment_json=judgment))
        for row in (next(x for x in out.splitlines() if x.startswith("| S1 ")),
                    next(x for x in out.splitlines() if x.startswith("| [台灣事實查核中心]"))):
            self.assertEqual(row.count("]("), 1, row)
            self.assertIn("](https://ivod.ly.gov.tw/x%29%5B點這裡領取補助%5D%28https://phish.example/login)", row)

    def test_a_link_inside_role_text_shows_where_it_leads(self):
        """Audit: 「詳見[官方說明](網址)」 in the judge's reasoning became a link whose text hid the address."""
        judgment = copy.deepcopy(fx.JUDGMENT)
        judgment["verdicts"][0]["reasoning"] = "部長說的是可能上漲。詳見[官方說明](https://phish.example/b)"
        row = next(x for x in md(build(judgment_json=judgment)).splitlines() if x.startswith("| C1 "))
        self.assertIn("詳見[官方說明] (https://phish.example/b)", row)
        self.assertNotIn("](", row)

    def test_null_in_place_of_a_list_does_not_stop_the_report(self):
        """validate reads these as empty lists (nothing is missing), so render has to as well."""
        trace, proponent = copy.deepcopy(fx.TRACE), copy.deepcopy(fx.PROPONENT)
        trace.update(first_seen=None, variants=None, spread_signals=None, attribution=None, limits=None)
        trace["publisher"].update(wording_issues=None, flagged=None)
        proponent["prior_factchecks_rechecked"][0]["claim_ids"] = None
        out = md(build(trace_json=trace, proponent_json=proponent))
        self.assertIn("- 最早出現：查不到", out)
        self.assertIn("| [台灣事實查核中心](https://tfc-taiwan.org.tw/x) | 錯誤 | — | 一致 |", out)


class CellTest(unittest.TestCase):
    def test_line_breaks_and_control_characters_become_one_space(self):
        """A bare "\\r" ends a line in CommonMark too, and U+2028/U+2029 do in some viewers and terminals."""
        for ch in ("\n", "\r", "\r\n", "\n\n", "\t", "\x0b", "\x0c", "\x1b", "\x00", "\x7f", "\x85", "\u2028", "\u2029",
                   "\u202e", "\u2066"):  # the last two reverse or isolate the text that follows
            self.assertEqual(render._cell(f"甲{ch}乙"), "甲 乙", repr(ch))
        self.assertEqual(render._cell("\r\n 甲 \u2029"), "甲")

    def test_ordinary_text_is_left_alone(self):
        for text in ("記者 王小明\u3000報導（2026）", "罰 1,200–1,500 元，不是 3000 元！", "2⃣0⃣1⃣7⃣年", "a  b"):
            self.assertEqual(render._cell(text), text)
        self.assertEqual(render._cell(None), "")
        self.assertEqual(render._cell(0), "")
        self.assertEqual(render._cell("a|b"), "a／b")

    def test_text_cannot_form_a_link_or_an_image(self):
        self.assertEqual(render._cell("詳見[官方說明](https://phish.example/b)"), "詳見[官方說明] (https://phish.example/b)")
        self.assertEqual(render._cell("![圖](https://t.example/p.png)"), "![圖] (https://t.example/p.png)")
        self.assertEqual(render._cell("[官方說明]\n(https://phish.example/b)"), "[官方說明] (https://phish.example/b)")


class LinkTargetTest(unittest.TestCase):
    def test_characters_that_end_a_link_or_a_table_cell_are_percent_encoded(self):
        bad = 'https://example.org/a)[b](c <d> "e" | f\\g\n\x1bh\u3000i\u202ej'
        target = render._link(bad)
        for ch in '()[]<>"|\\ \n\x1b\u3000\u202e':
            self.assertNotIn(ch, target, repr(ch))
        self.assertEqual(urllib.parse.unquote(target), bad)

    def test_an_ordinary_url_is_not_changed(self):
        for url in ("https://law.moj.gov.tw/LawClass/LawSingle.aspx?pcode=K0040012&flno=33",
                    "https://ly.govapi.tw/v2/laws/02017/bills?屆=11&limit=300",
                    "https://example.org/a_b-c~d/%E5%B1%86;x=1,2+3#frag!$'*@"):
            self.assertEqual(render._link(url), url)

    def test_a_url_with_brackets_keeps_working(self):
        """Why validation does not simply refuse brackets: Wikipedia titles are full of them."""
        self.assertEqual(render._link("https://zh.wikipedia.org/wiki/中華民國_(消歧義)"),
                         "https://zh.wikipedia.org/wiki/中華民國_%28消歧義%29")


class ScopeNoteTest(unittest.TestCase):
    NOTE = "> 結論只涵蓋可以查證的說法。"

    def test_claims_left_out_as_opinion_are_named_under_the_result(self):
        head = md(build()).split("## 結論")[0]
        self.assertIn(self.NOTE + "C2 被分成意見、預測或模糊的說法，或被判成非事實陳述，不在結論內。", head)

    def test_no_note_when_every_claim_is_in_the_result(self):
        claims, proponent, judgment = (copy.deepcopy(x) for x in (fx.CLAIMS, fx.PROPONENT, fx.JUDGMENT))
        claims["claims"].pop()
        proponent["verdicts"].pop()
        judgment["verdicts"].pop()
        self.assertNotIn(self.NOTE, md(build(claims_json=claims, proponent_json=proponent, judgment_json=judgment)))

    def test_no_note_when_the_result_line_already_says_nothing_could_be_checked(self):
        claims, proponent, judgment = (copy.deepcopy(x) for x in (fx.CLAIMS, fx.PROPONENT, fx.JUDGMENT))
        claims["claims"][0]["type"] = "O"
        proponent["verdicts"][0]["label"] = judgment["verdicts"][0]["label"] = "not_factual"
        out = md(build(claims_json=claims, proponent_json=proponent, judgment_json=judgment))
        self.assertIn("沒有可以查證的事實命題", out)
        self.assertNotIn(self.NOTE, out)

    def test_a_time_claim_is_never_called_an_opinion(self):
        head = md(build(**fx.time_claim_overrides("relative", "not_factual"))).split("## 結論")[0]
        self.assertIn(self.NOTE + "C2 被分成", head)


if __name__ == "__main__":
    unittest.main()
