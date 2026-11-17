import copy
import unittest

from tests import fixtures as fx
from tests.helpers import make_run
from fclib import finalize


def run_finalize(**overrides):
    return finalize.finalize(make_run(fx.run_files(**overrides)))


def claim(result, cid):
    return next(c for c in result["claims"] if c["claim_id"] == cid)


class FinalizeTest(unittest.TestCase):
    def test_upheld_attack_with_passing_review_keeps_judge_label(self):
        c1 = claim(run_finalize(), "C1")
        self.assertEqual(c1["label"], "misleading")
        self.assertEqual(c1["review_status"], "passed")
        self.assertEqual(c1["upheld_attacks"], ["B-1"])
        self.assertEqual(c1["rejected_attacks"], ["A-1"])

    def test_claim_without_upheld_attacks_needs_no_review(self):
        c2 = claim(run_finalize(), "C2")
        self.assertEqual(c2["review_status"], "none")
        self.assertEqual(c2["label"], "not_factual")

    def test_failed_review_forces_unverified_and_records_dispute(self):
        review = {"seat": "B", "reviews": [{"claim_id": "C1", "pass": False, "reason": "還是低估了"}]}
        r = run_finalize(review__B_json=review)
        c1 = claim(r, "C1")
        self.assertEqual(c1["label"], "unverified")
        self.assertEqual(c1["review_status"], "failed")
        self.assertEqual(r["disputes"][0]["claim_id"], "C1")
        self.assertEqual(r["disputes"][0]["judge_label"], "misleading")
        self.assertIn("還是低估了", r["disputes"][0]["review_reasons"][0])

    def test_missing_review_counts_as_failed(self):
        r = run_finalize(review__B_json=None)
        c1 = claim(r, "C1")
        self.assertEqual(c1["review_status"], "failed")
        self.assertIn("覆核未完成", r["disputes"][0]["review_reasons"][0])

    def test_every_reviewing_seat_must_pass(self):
        judgment = copy.deepcopy(fx.JUDGMENT)
        judgment["rulings"][0]["upheld"] = True  # A-1 now upheld too (reasoning attack)
        r = run_finalize(judgment_json=judgment)  # review-A.json is missing
        self.assertEqual(claim(r, "C1")["review_status"], "failed")

    def test_claim_metadata_comes_from_claims_json(self):
        c1 = claim(run_finalize(), "C1")
        self.assertEqual((c1["importance"], c1["core"], c1["legal"]), (5, True, False))

    def test_rejected_attacks_become_checked_objections(self):
        r = run_finalize()
        ids = [o["attack_id"] for o in r["checked_objections"]]
        self.assertEqual(ids, ["A-1"])
        self.assertEqual(r["checked_objections"][0]["seat"], "A")

    def test_ledger_comes_from_judgment(self):
        r = run_finalize()
        self.assertIn("S3", [e["id"] for e in r["ledger"]])

    def test_failed_opponent_seat_is_ignored(self):
        failed = {"seat": "B", "engine": "claude", "lens": "counter", "status": "failed",
                  "error": "timeout", "attacks": []}
        judgment = copy.deepcopy(fx.JUDGMENT)
        judgment["rulings"] = judgment["rulings"][:1]
        r = run_finalize(opponent__B_json=failed, judgment_json=judgment)
        self.assertEqual(claim(r, "C1")["review_status"], "none")



class ReviewersTest(unittest.TestCase):
    def test_lists_seats_with_upheld_claim_attacks(self):
        run = make_run(fx.run_files())
        self.assertEqual(finalize.reviewers_needed(run), {"B": ["C1"]})

    def test_no_upheld_attacks(self):
        judgment = copy.deepcopy(fx.JUDGMENT)
        judgment["rulings"][1]["upheld"] = False
        run = make_run(fx.run_files(judgment_json=judgment))
        self.assertEqual(finalize.reviewers_needed(run), {})


if __name__ == "__main__":
    unittest.main()
