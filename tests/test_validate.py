import copy
import unittest

from tests import fixtures as fx
from tests.helpers import make_run
from fclib import validate


def errors_for(name, mutate=None, **overrides):
    files = fx.run_files(**overrides)
    if mutate:
        mutate(files[name])
    run = make_run(files)
    return validate.validate_file(run, name, known_tactics={"TW-T01"})


class ValidRunTest(unittest.TestCase):
    def test_every_fixture_file_is_valid(self):
        run = make_run(fx.run_files())
        for name in fx.run_files():
            with self.subTest(name=name):
                self.assertEqual(validate.validate_file(run, name, known_tactics={"TW-T01"}), [])

    def test_unknown_file_name_is_an_error(self):
        run = make_run(fx.run_files())
        self.assertTrue(validate.validate_file(run, "whatever.json"))


class ClaimsTest(unittest.TestCase):
    def test_duplicate_claim_ids(self):
        def m(c):
            c["claims"][1]["id"] = "C1"
        self.assertTrue(any("重複" in e for e in errors_for("claims.json", m)))

    def test_bad_type_and_importance(self):
        def m(c):
            c["claims"][0]["type"] = "Z"
            c["claims"][0]["importance"] = 9
        errs = errors_for("claims.json", m)
        self.assertTrue(any("type" in e for e in errs))
        self.assertTrue(any("importance" in e for e in errs))

    def test_neutral_rewrite_required(self):
        def m(c):
            c["claims"][0]["neutral"] = " "
        self.assertTrue(errors_for("claims.json", m))


class ProponentTest(unittest.TestCase):
    def test_evidence_without_excerpt_is_rejected(self):
        def m(p):
            p["ledger"][0]["excerpt"] = ""
        self.assertTrue(any("摘錄" in e for e in errors_for("proponent.json", m)))

    def test_evidence_url_must_be_http(self):
        def m(p):
            p["ledger"][0]["url"] = "search results"
        self.assertTrue(any("url" in e for e in errors_for("proponent.json", m)))

    def test_every_claim_needs_exactly_one_verdict(self):
        def m(p):
            p["verdicts"].pop()
        self.assertTrue(any("C2" in e for e in errors_for("proponent.json", m)))

    def test_verdict_evidence_must_exist_in_ledger(self):
        def m(p):
            p["verdicts"][0]["evidence_ids"] = ["S9"]
        self.assertTrue(any("S9" in e for e in errors_for("proponent.json", m)))

    def test_bad_label_and_flag(self):
        def m(p):
            p["verdicts"][0]["label"] = "fake"
            p["verdicts"][0]["context_flags"] = ["nope"]
        errs = errors_for("proponent.json", m)
        self.assertTrue(any("label" in e for e in errs))
        self.assertTrue(any("context_flags" in e for e in errs))

    def test_factual_verdict_without_evidence_is_rejected(self):
        def m(p):
            p["verdicts"][0]["evidence_ids"] = []
        self.assertTrue(errors_for("proponent.json", m))


class OpponentTest(unittest.TestCase):
    def test_label_attack_without_evidence_is_rejected(self):
        def m(o):
            o["attacks"][0]["evidence"] = []
        self.assertTrue(any("證據" in e for e in errors_for("opponent-B.json", m)))

    def test_reasoning_attack_without_evidence_is_fine(self):
        self.assertEqual(errors_for("opponent-A.json"), [])

    def test_attack_on_unknown_claim(self):
        def m(o):
            o["attacks"][0]["claim_id"] = "C9"
        self.assertTrue(any("C9" in e for e in errors_for("opponent-A.json", m)))

    def test_failed_seat_with_no_attacks_is_valid(self):
        failed = {"seat": "X1", "engine": "codex", "lens": "external", "status": "failed",
                  "error": "timeout", "attacks": []}
        self.assertEqual(errors_for("opponent-X1.json", opponent__X1_json=failed), [])

    def test_seat_name_must_match_file(self):
        def m(o):
            o["seat"] = "Z"
        self.assertTrue(errors_for("opponent-A.json", m))


class RebuttalJudgmentTest(unittest.TestCase):
    def test_rebuttal_must_answer_every_attack(self):
        def m(r):
            r["responses"].pop()
        self.assertTrue(any("B-1" in e for e in errors_for("rebuttal.json", m)))

    def test_judgment_must_rule_on_every_attack(self):
        def m(j):
            j["rulings"].pop()
        self.assertTrue(any("B-1" in e for e in errors_for("judgment.json", m)))

    def test_upheld_evidence_attack_needs_verified_url(self):
        def m(j):
            j["rulings"][1]["verified_urls"] = []
        self.assertTrue(any("verified_urls" in e for e in errors_for("judgment.json", m)))

    def test_judgment_verdict_evidence_must_be_in_its_ledger(self):
        def m(j):
            j["verdicts"][0]["evidence_ids"] = ["S1", "S4"]
        self.assertTrue(any("S4" in e for e in errors_for("judgment.json", m)))


class TraceTest(unittest.TestCase):
    def test_unknown_tactic_id(self):
        def m(t):
            t["tactics"][0]["tactic_id"] = "TW-T99"
        self.assertTrue(any("TW-T99" in e for e in errors_for("trace.json", m)))

    def test_null_tactic_id_is_rejected_even_without_library(self):
        files = fx.run_files()
        files["trace.json"]["tactics"][0]["tactic_id"] = None
        run = make_run(files)
        self.assertTrue(validate.validate_file(run, "trace.json", known_tactics=None))

    def test_attribution_requires_report_url(self):
        def m(t):
            t["attribution"] = [{"statement": "這是網軍", "report_url": "", "report_org": ""}]
        self.assertTrue(any("attribution" in e for e in errors_for("trace.json", m)))

    def test_spread_signal_requires_evidence(self):
        def m(t):
            t["spread_signals"] = [{"signal": "大量相同文案", "evidence_url": "", "excerpt": ""}]
        self.assertTrue(errors_for("trace.json", m))

    def test_bad_publisher_kind(self):
        def m(t):
            t["publisher"]["kind"] = "網軍"
        self.assertTrue(errors_for("trace.json", m))


class WithdrawTacticTest(unittest.TestCase):
    """2026-11-18 symmetry probe: the judge withdrew TW-T15 but the report still showed it.
    Every upheld trace/tactic ruling must say which tags it withdraws, so nothing can be forgotten."""

    def errs(self, mutate=None, **kw):
        return errors_for("judgment.json", mutate, **fx.tactic_attack_overrides(**kw))

    def test_withdrawal_on_an_upheld_tactic_attack_is_valid(self):
        self.assertEqual(self.errs(), [])

    def test_upheld_tactic_attack_that_keeps_the_tag_is_valid(self):
        self.assertEqual(self.errs(withdraw=()), [])

    def test_upheld_tactic_attack_must_say_what_it_withdraws(self):
        """Skeptic: an upheld attack with no withdrawal left the tag in the report and contradicted it."""
        self.assertTrue(any("withdraw_tactics" in e for e in self.errs(withdraw="omit")))

    def test_upheld_trace_attack_must_say_what_it_withdraws_too(self):
        """Re-review: injection-injected removed TW-T04 through attacks aimed at the trace."""
        o = fx.tactic_attack_overrides(withdraw="omit")
        o["opponent__C_json"]["attacks"][0]["target"] = "trace"
        self.assertTrue(any("withdraw_tactics" in e for e in errors_for("judgment.json", **o)))

    def test_one_ruling_can_withdraw_several_tags(self):
        o = fx.tactic_attack_overrides(withdraw=("TW-T01", "TW-T25"))
        trace = copy.deepcopy(fx.TRACE)
        trace["tactics"].append({"tactic_id": "TW-T25", "quote": "快轉傳！", "explanation": "只是問問"})
        o["opponent__C_json"]["attacks"][0]["argument"] = "TW-T01 和 TW-T25 都對不上特徵"
        self.assertEqual(errors_for("judgment.json", trace_json=trace, **o), [])

    def test_withdrawn_tag_must_exist_in_the_trace(self):
        self.assertTrue(any("TW-T99" in e for e in self.errs(withdraw=("TW-T99",))))

    def test_withdrawn_tag_must_be_named_by_the_attack_or_the_ruling(self):
        """Red-team: a ruling about the first-seen date could withdraw any tag."""
        def m(j):
            j["rulings"][-1]["reason"] = "最早出現的日期應該更正"
        o = fx.tactic_attack_overrides()
        o["opponent__C_json"]["attacks"][0]["argument"] = "first_seen 日期錯了"
        self.assertTrue(any("TW-T01" in e for e in errors_for("judgment.json", m, **o)))

    def test_rejected_attack_cannot_withdraw_a_tag(self):
        self.assertTrue(any("withdraw_tactics" in e for e in self.errs(upheld=False)))

    def test_claim_attack_cannot_withdraw_a_tag(self):
        """Red-team: any unrelated upheld attack used to be enough to withdraw any tag."""
        def m(j):
            j["rulings"][1]["withdraw_tactics"] = ["TW-T01"]  # B-1 is an upheld label attack
        self.assertTrue(any("withdraw_tactics" in e for e in self.errs(m, withdraw=())))

    def test_malformed_withdrawal_is_an_error_not_a_crash(self):
        for bad in ("TW-T01", [{"id": "TW-T01"}], [1], {"TW-T01": True}):
            with self.subTest(bad=bad):
                self.assertTrue(any("withdraw_tactics" in e for e in self.errs(withdraw=bad)))


class ReviewTest(unittest.TestCase):
    def test_review_pass_must_be_bool(self):
        def m(r):
            r["reviews"][0]["pass"] = "yes"
        self.assertTrue(errors_for("review-B.json", m))

    def test_failed_review_must_say_whether_the_label_is_ok(self):
        def m(r):
            r["reviews"][0]["pass"] = False
        self.assertTrue(any("label_ok" in e for e in errors_for("review-B.json", m)))

    def test_failed_review_with_label_ok_is_valid(self):
        def m(r):
            r["reviews"][0].update({"pass": False, "label_ok": True})
        self.assertEqual(errors_for("review-B.json", m), [])

    def test_passing_review_cannot_reject_the_label(self):
        def m(r):
            r["reviews"][0]["label_ok"] = False
        self.assertTrue(any("label_ok" in e for e in errors_for("review-B.json", m)))


if __name__ == "__main__":
    unittest.main()
