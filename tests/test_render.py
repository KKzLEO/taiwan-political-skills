import copy
import unittest

from tests import fixtures as fx
from tests.helpers import make_run
from fclib import detect, finalize, io, render, score

TACTICS = [{"id": "TW-T01", "name": "急迫轉傳", "layer": "content", "how_to_spot": "看到「快轉傳」先停下來查"}]
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


if __name__ == "__main__":
    unittest.main()
