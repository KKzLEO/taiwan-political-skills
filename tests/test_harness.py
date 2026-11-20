import importlib.util
import sys
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

    def test_a_context_flag_one_version_got_and_another_did_not_shows(self):
        """Final delta review: 「斷章取義」「舊聞新炒」 are printed beside a verdict, share their names with tactic
        tags, and were never compared between party versions."""
        plain = {"claims": [{"claim_id": "C1", "label": "false", "context_flags": []}]}
        flagged = {"claims": [{"claim_id": "C1", "label": "false", "context_flags": ["old_news"]}]}
        self.assertEqual(analyze.variant_summary(fx.CLAIMS, plain)[2], ())
        self.assertEqual(analyze.variant_summary(fx.CLAIMS, flagged)[2], ("old_news",))

    def test_only_the_flags_a_report_prints_are_compared(self):
        """Re-review: the report prints a flag only beside a claim judged wrong; one on a claim judged right is
        not there to be seen, and counting it hid a real difference and reported a false one."""
        unseen = {"claims": [{"claim_id": "C1", "label": "false", "context_flags": []},
                             {"claim_id": "C2", "label": "mostly_true", "context_flags": ["old_news"]}]}
        self.assertEqual(analyze.variant_summary(fx.CLAIMS, unseen)[2], ())


class BrokenJobsTest(unittest.TestCase):
    """Delta review: a job that crashed left a record the analysis either crashed on or silently dropped."""

    def run_analyze(self, results):
        import contextlib
        import io
        import json
        import tempfile
        from pathlib import Path
        base = Path(tempfile.mkdtemp(prefix="fc-harness-"))
        (base / "results.json").write_text(json.dumps(results, ensure_ascii=False))
        out = io.StringIO()
        argv = sys.argv
        sys.argv = ["analyze.py", "--base", str(base), "--repo", str(ROOT)]
        try:
            with contextlib.redirect_stdout(out):
                analyze.main()
        finally:
            sys.argv = argv
        return out.getvalue()

    def test_a_case_that_never_ran_is_listed_and_counted(self):
        out = self.run_analyze([{"name": "case-99", "job": "case-99", "kind": "case", "run": "",
                                 "status": "failed: FileNotFoundError", "minutes": 0}])
        self.assertIn("case-99", out)
        self.assertIn("沒跑完 1", out)

    def test_a_probe_variant_that_crashed_is_listed_with_the_others(self):
        job = "probes/symmetry-time/民眾黨"
        out = self.run_analyze([{"name": job, "job": job, "kind": "probe", "run": "", "status": "failed: KeyError",
                                 "minutes": 0}])
        self.assertIn("探測 symmetry-time", out)
        self.assertIn("民眾黨", out)
        self.assertIn("沒有跑完", out)


if __name__ == "__main__":
    unittest.main()
