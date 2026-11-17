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


class ReviewTest(unittest.TestCase):
    def test_review_pass_must_be_bool(self):
        def m(r):
            r["reviews"][0]["pass"] = "yes"
        self.assertTrue(errors_for("review-B.json", m))


if __name__ == "__main__":
    unittest.main()
