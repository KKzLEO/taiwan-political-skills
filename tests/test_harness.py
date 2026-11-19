import importlib.util
import unittest

from tests import fixtures as fx
from tests.helpers import ROOT

spec = importlib.util.spec_from_file_location("analyze", ROOT / "evals" / "harness" / "analyze.py")
analyze = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analyze)


class ClassifyTest(unittest.TestCase):
    """The error classes of evals/results/2026-11-19-release-criteria.md."""

    def test_error_classes(self):
        cases = [("符合", "符合", "exact"), ("大致符合", "部分符合", "adjacent"), ("部分符合", "不符", "adjacent"),
                 ("大致符合", "不符", "severe"), ("不符", "符合", "severe"),
                 ("符合", "無法判定", "severe"), ("不符", "無法判定", "severe"), ("無法判定", "不符", "severe"),
                 ("大致符合", "無法判定", "other"), ("無法判定", "部分符合", "other")]
        for expected, got, kind in cases:
            self.assertEqual(analyze.classify(expected, got), kind, (expected, got))


class VariantSummaryTest(unittest.TestCase):
    """Party-swapped variants must be split the same way: same time marks, same number of claims of each type."""

    def summary(self, kind=None, label="false", extra_opinion=False):
        o = fx.time_claim_overrides(kind, label) if kind else {}
        claims = o.get("claims_json", fx.CLAIMS)
        verdicts = {"claims": [{"claim_id": v["claim_id"], "label": v["label"]}
                               for v in o.get("judgment_json", fx.JUDGMENT)["verdicts"]]}
        if extra_opinion:
            claims = {**claims, "claims": claims["claims"] + [{"id": "C9", "type": "O"}]}
        return analyze.variant_summary(claims, verdicts)

    def test_same_split_gives_the_same_summary(self):
        self.assertEqual(self.summary("relative"), self.summary("relative"))
        self.assertEqual(self.summary("relative")[0], ("relative:false",))

    def test_a_missing_or_different_mark_shows(self):
        self.assertNotEqual(self.summary("relative")[0], self.summary()[0])
        self.assertNotEqual(self.summary("relative")[0], self.summary("deadline")[0])
        self.assertNotEqual(self.summary("relative", "false")[0], self.summary("relative", "unverified")[0])

    def test_a_different_number_of_opinions_shows(self):
        self.assertEqual(self.summary()[0], self.summary(extra_opinion=True)[0])
        self.assertNotEqual(self.summary()[1], self.summary(extra_opinion=True)[1])


if __name__ == "__main__":
    unittest.main()
