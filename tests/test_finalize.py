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
        """No label_ok (older review files): stay conservative and treat the label as contested."""
        review = {"seat": "B", "reviews": [{"claim_id": "C1", "pass": False, "reason": "還是低估了"}]}
        r = run_finalize(review__B_json=review)
        c1 = claim(r, "C1")
        self.assertEqual(c1["label"], "unverified")
        self.assertEqual(c1["review_status"], "failed")
        self.assertEqual(r["disputes"][0]["claim_id"], "C1")
        self.assertEqual(r["disputes"][0]["judge_label"], "misleading")
        self.assertFalse(r["disputes"][0]["label_kept"])
        self.assertIn("還是低估了", r["disputes"][0]["review_reasons"][0])

    def test_failed_review_that_accepts_the_label_keeps_it(self):
        """2026-11-18 case-002: the reviewer said the opinion label was right but the sourcing was
        one-sided; turning an opinion into a scored `unverified` dropped the result a whole level."""
        review = {"seat": "B", "reviews": [{"claim_id": "C1", "pass": False, "label_ok": True,
                                            "reason": "標籤沒問題，但只引了一半"}]}
        r = run_finalize(review__B_json=review)
        c1 = claim(r, "C1")
        self.assertEqual(c1["label"], "misleading")
        self.assertEqual(c1["review_status"], "failed")
        self.assertTrue(r["disputes"][0]["label_kept"])
        self.assertIn("只引了一半", r["disputes"][0]["review_reasons"][0])

    def test_failed_review_that_rejects_the_label_forces_unverified(self):
        review = {"seat": "B", "reviews": [{"claim_id": "C1", "pass": False, "label_ok": False,
                                            "reason": "改過頭"}]}
        r = run_finalize(review__B_json=review)
        self.assertEqual(claim(r, "C1")["label"], "unverified")
        self.assertFalse(r["disputes"][0]["label_kept"])

    def test_one_seat_rejecting_the_label_is_enough_to_force_unverified(self):
        judgment = copy.deepcopy(fx.JUDGMENT)
        judgment["rulings"][0]["upheld"] = True  # A-1 upheld too, so seats A and B both review C1
        review_a = {"seat": "A", "reviews": [{"claim_id": "C1", "pass": False, "label_ok": False, "reason": "改過頭"}]}
        review_b = {"seat": "B", "reviews": [{"claim_id": "C1", "pass": False, "label_ok": True, "reason": "只引了一半"}]}
        r = run_finalize(judgment_json=judgment, review__A_json=review_a, review__B_json=review_b)
        self.assertEqual(claim(r, "C1")["label"], "unverified")

    def test_missing_review_never_keeps_the_label(self):
        judgment = copy.deepcopy(fx.JUDGMENT)
        judgment["rulings"][0]["upheld"] = True  # review-A.json is missing
        review_b = {"seat": "B", "reviews": [{"claim_id": "C1", "pass": False, "label_ok": True, "reason": "只引了一半"}]}
        r = run_finalize(judgment_json=judgment, review__B_json=review_b)
        self.assertEqual(claim(r, "C1")["label"], "unverified")

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

    def test_claim_type_comes_from_claims_json(self):
        r = run_finalize()
        self.assertEqual([claim(r, c)["type"] for c in ("C1", "C2")], ["F", "O"])

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



class ImportanceChallengeTest(unittest.TestCase):
    """A neutral_rewrite attack may propose a new importance; if upheld, the program moves one step toward it."""

    def test_upheld_challenge_moves_to_the_proposed_adjacent_level(self):
        c1 = claim(run_finalize(**fx.importance_attack_overrides((("C-1", 4, True),))), "C1")
        self.assertEqual(c1["importance"], 4)
        self.assertEqual(c1["importance_from"], 5)

    def test_rejected_challenge_changes_nothing(self):
        c1 = claim(run_finalize(**fx.importance_attack_overrides((("C-1", 4, False),))), "C1")
        self.assertEqual(c1["importance"], 5)
        self.assertNotIn("importance_from", c1)

    def test_upheld_challenges_in_opposite_directions_cancel(self):
        c1 = claim(run_finalize(**fx.importance_attack_overrides((("C-1", 2, True), ("C-2", 4, True)), importance=3)), "C1")
        self.assertEqual(c1["importance"], 3)
        self.assertNotIn("importance_from", c1)

    def test_two_upheld_challenges_in_the_same_direction_still_move_one_step(self):
        c1 = claim(run_finalize(**fx.importance_attack_overrides((("C-1", 4, True), ("C-2", 4, True)))), "C1")
        self.assertEqual(c1["importance"], 4)

    def test_importance_challenge_needs_no_claim_review(self):
        # A weight dispute never questions the label, so it must not open a review that can fail (-10).
        run = make_run(fx.run_files(**fx.importance_attack_overrides()))
        self.assertEqual(finalize.reviewers_needed(run), {"B": ["C1"]})

    def test_missing_review_for_an_importance_challenge_does_not_touch_the_label(self):
        overrides = {**fx.importance_attack_overrides(), "review__C_json": None}
        c1 = claim(run_finalize(**overrides), "C1")
        self.assertEqual((c1["label"], c1["review_status"]), ("misleading", "passed"))
        self.assertEqual(c1["upheld_attacks"], ["B-1"])
        self.assertEqual([a["attack_id"] for a in c1["importance_attacks"]], ["C-1"])


def unverified_judgment():
    j = copy.deepcopy(fx.JUDGMENT)
    j["rulings"][1]["verified_urls"] = []
    j["rulings_unverified"] = ["B-1"]
    return j


class UnverifiedRulingTest(unittest.TestCase):
    """The judge still left out the URLs it checked after a retry (validate.fallback): the ruling stands and
    is listed once at the top; labels, reviews and disputes are untouched."""

    def test_ruling_is_listed_and_the_verdict_stands(self):
        r = run_finalize(judgment_json=unverified_judgment())
        self.assertEqual(r["unverified_rulings"], [{"attack_id": "B-1", "seat": "B", "claim_id": "C1", "target": "label"}])
        self.assertEqual(claim(r, "C1")["label"], "misleading")
        self.assertEqual(r["disputes"], [])

    def test_nothing_listed_by_default(self):
        self.assertEqual(run_finalize()["unverified_rulings"], [])

    def test_trace_attack_is_listed_without_a_claim(self):
        o = fx.tactic_attack_overrides(upheld=True, keep=False)
        o["opponent__C_json"]["attacks"][0]["evidence"] = [{"url": "https://example.org/t", "excerpt": "原文"}]
        o["judgment_json"]["rulings_unverified"] = ["C-1"]
        r = run_finalize(**o)
        self.assertEqual(r["unverified_rulings"], [{"attack_id": "C-1", "seat": "C", "claim_id": None, "target": "tactic"}])


class RemovedTacticsFinalizeTest(unittest.TestCase):
    def test_withdrawn_tags_come_from_the_judges_checks(self):
        r = run_finalize(**fx.tactic_attack_overrides())
        self.assertEqual(r["removed_tactics"], [{"tactic_id": "TW-T16", "reason": "裁判核對後認為特徵對不上，撤下"}])

    def test_kept_tag_is_not_withdrawn(self):
        self.assertEqual(run_finalize(**fx.tactic_attack_overrides(upheld=False, keep=True))["removed_tactics"], [])

    def test_no_withdrawn_tags_by_default(self):
        self.assertEqual(run_finalize()["removed_tactics"], [])

    def test_tags_the_judge_could_not_check_are_not_listed_as_identified(self):
        j = copy.deepcopy(fx.JUDGMENT)
        j.pop("tactic_checks")
        j["tactic_checks_set_aside"] = ["tactic_checks：缺少 TW-T16"]
        r = run_finalize(judgment_json=j)
        self.assertEqual([t["tactic_id"] for t in r["removed_tactics"]], ["TW-T16"])
        self.assertIn("沒有完成", r["removed_tactics"][0]["reason"])


class TraceAttackRoutingTest(unittest.TestCase):
    """2026-11-18 batch: 13 upheld trace/tactic attacks carried a claim_id and were routed into claim
    review, so a tactic dispute could dock confidence or change a label. Tactics never touch the score."""

    def overrides(self):
        o = fx.tactic_attack_overrides()
        o["opponent__C_json"]["attacks"][0]["claim_id"] = "C2"
        return o

    def test_tactic_attack_with_claim_id_is_a_trace_correction(self):
        r = run_finalize(**self.overrides())
        self.assertIn("C-1", [a["attack_id"] for a in r["trace_attacks_upheld"]])
        self.assertEqual(claim(r, "C2")["upheld_attacks"], [])
        self.assertEqual(claim(r, "C2")["review_status"], "none")

    def test_rejected_tactic_attack_with_claim_id_is_listed_under_the_trace(self):
        o = self.overrides()
        o["judgment_json"]["rulings"][-1].update({"upheld": False, "withdraw_tactics": []})
        r = run_finalize(**o)
        checked = next(c for c in r["checked_objections"] if c["attack_id"] == "C-1")
        self.assertIsNone(checked["claim_id"])
        self.assertEqual(claim(r, "C2")["rejected_attacks"], [])

    def test_tactic_attack_with_claim_id_needs_no_claim_review(self):
        run = make_run(fx.run_files(**self.overrides()))
        self.assertEqual(finalize.reviewers_needed(run), {"B": ["C1"]})


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
