import unittest

from tests import helpers  # noqa: F401
from fclib import evalcmp

CASE = {"id": "case-x", "expected_result": "不符", "claim": [
    {"original": "部長說明年油價一定漲三成", "expected_label": "misleading", "core": True, "importance": 5},
    {"original": "快轉傳", "expected_label": "not_factual", "core": False, "importance": 1},
]}
CLAIMS = {"claims": [{"id": "C1", "original": "某部長說明年油價一定漲三成"}, {"id": "C2", "original": "快轉傳！"}]}
VERDICTS = {"claims": [{"claim_id": "C1", "label": "misleading"}, {"claim_id": "C2", "label": "not_factual"}]}


class CompareTest(unittest.TestCase):
    def test_all_correct(self):
        r = evalcmp.compare(CASE, CLAIMS, VERDICTS, {"result": "不符"})
        self.assertEqual((r["matched"], r["label_correct"], r["result_correct"]), (2, 2, True))

    def test_wrong_label_and_result(self):
        v = {"claims": [{"claim_id": "C1", "label": "false"}, {"claim_id": "C2", "label": "not_factual"}]}
        r = evalcmp.compare(CASE, CLAIMS, v, {"result": "部分符合"})
        self.assertEqual((r["label_correct"], r["result_correct"]), (1, False))
        wrong = [d for d in r["details"] if not d["correct"]]
        self.assertEqual((wrong[0]["expected"], wrong[0]["got"]), ("misleading", "false"))

    def test_unmatched_case_claim(self):
        claims = {"claims": [{"id": "C1", "original": "完全無關的句子 ABC"}]}
        verdicts = {"claims": [{"claim_id": "C1", "label": "true"}]}
        r = evalcmp.compare(CASE, claims, verdicts, {"result": "符合"})
        self.assertLess(r["matched"], 2)
        self.assertTrue(any(d["got"] is None for d in r["details"]))

    def test_tie_on_the_same_sentence_prefers_the_matching_reading(self):
        """2026-11-18 case-001: one sentence became an implied fact (C8) and an opinion (C9) with the
        same original text; the case expects the opinion reading, so C9 is the right counterpart."""
        claims = {"claims": [{"id": "C8", "original": "感謝藍白立委守住國會"},
                             {"id": "C9", "original": "感謝藍白立委守住國會"}]}
        verdicts = {"claims": [{"claim_id": "C8", "label": "true"}, {"claim_id": "C9", "label": "not_factual"}]}
        case = {"id": "c", "expected_result": "不符", "claim": [
            {"original": "感謝藍白立委守住國會，大家轉傳", "expected_label": "not_factual"}]}
        d = evalcmp.compare(case, claims, verdicts, {"result": "不符"})["details"][0]
        self.assertEqual((d["run_claim"], d["correct"]), ("C9", True))

    def test_a_closer_sentence_still_wins_over_a_matching_label(self):
        claims = {"claims": [{"id": "C1", "original": "部長說明年油價一定漲三成"},
                             {"id": "C2", "original": "部長說"}]}
        verdicts = {"claims": [{"claim_id": "C1", "label": "false"}, {"claim_id": "C2", "label": "misleading"}]}
        case = {"id": "c", "expected_result": "不符", "claim": [CASE["claim"][0]]}
        self.assertEqual(evalcmp.compare(case, claims, verdicts, {"result": "不符"})["details"][0]["run_claim"], "C1")

    def test_each_run_claim_matches_at_most_once(self):
        claims = {"claims": [{"id": "C1", "original": "部長說明年油價一定漲三成"}]}
        verdicts = {"claims": [{"claim_id": "C1", "label": "misleading"}]}
        case = {"id": "c", "expected_result": "不符", "claim": [CASE["claim"][0], dict(CASE["claim"][0])]}
        self.assertEqual(evalcmp.compare(case, claims, verdicts, {"result": "不符"})["matched"], 1)


class NormalizationTest(unittest.TestCase):
    def test_compatibility_characters_are_normalized(self):
        case = {"id": "c", "expected_result": "不符", "claim": [
            {"original": "判刑二十八年半", "expected_label": "false", "core": True, "importance": 5}]}
        claims = {"claims": [{"id": "C1", "original": "判刑二十八年半"}]}
        verdicts = {"claims": [{"claim_id": "C1", "label": "false"}]}
        r = evalcmp.compare(case, claims, verdicts, {"result": "不符"})
        self.assertEqual(r["details"][0]["run_claim"], "C1")
        self.assertGreater(evalcmp.similarity("判刑二十八年半", "判刑二十八年半"), 0.99)
