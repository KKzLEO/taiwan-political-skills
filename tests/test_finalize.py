import copy
import unittest

from tests import fixtures as fx
from tests.helpers import make_run
from fclib import finalize, io


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

    def test_reasoning_of_an_overturned_label_says_whose_reasoning_it_is(self):
        """Audit: the label became 無法證實 but the reasoning was still the judge's case for 誤導, so the report's
        conclusion read "無法證實。部長說的是…，訊息改成…"."""
        judged = fx.JUDGMENT["verdicts"][0]["reasoning"]
        for review in ({"seat": "B", "reviews": [{"claim_id": "C1", "pass": False, "label_ok": False, "reason": "改過頭"}]},
                       None):  # a missing review overturns the label the same way
            r = run_finalize(review__B_json=review)
            self.assertEqual(claim(r, "C1")["reasoning"],
                             "覆核沒有通過，改列「無法證實」；裁判原本判「誤導」，理由是：" + judged)
            self.assertEqual(r["disputes"][0]["judge_reasoning"], judged)

    def test_reasoning_is_the_judges_own_when_the_label_did_not_change(self):
        kept = {"seat": "B", "reviews": [{"claim_id": "C1", "pass": False, "label_ok": True, "reason": "只引了一半"}]}
        self.assertEqual(claim(run_finalize(review__B_json=kept), "C1")["reasoning"], fx.JUDGMENT["verdicts"][0]["reasoning"])
        self.assertEqual(claim(run_finalize(), "C1")["reasoning"], fx.JUDGMENT["verdicts"][0]["reasoning"])
        # the judge already said 無法證實: a failed review changes nothing, so there is nothing to explain
        judgment = copy.deepcopy(fx.JUDGMENT)
        judgment["verdicts"][0].update({"label": "unverified", "reasoning": "找不到完整影片。", "evidence_ids": []})
        r = run_finalize(judgment_json=judgment, review__B_json=None)
        self.assertEqual((claim(r, "C1")["label"], claim(r, "C1")["reasoning"]), ("unverified", "找不到完整影片。"))

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
        judgment["verdicts"][0]["label"] = "false"  # no upheld attack left, so the proponent's label stays
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
        judgment["verdicts"][0]["label"] = "false"  # keeps the proponent's label, as judge.md says
        run = make_run(fx.run_files(judgment_json=judgment))
        self.assertEqual(finalize.reviewers_needed(run), {})


FAILED = {"engine": "claude", "lens": "evidence", "status": "failed", "error": "逾時"}


class JudgeOnlyChangeTest(unittest.TestCase):
    """A label the judge changed although no attack on that claim was upheld. judge.md tells the judge to
    keep the proponent's label then, but nothing checked it (0 of 294 claims in rounds 1-3 did this).
    Every seat that ran now reviews such a change."""

    @staticmethod
    def reviews(passed=True, label_ok=None, seats=("A", "B", "C", "X1")):
        out = {}
        for s in seats:
            r = {"claim_id": "C1", "pass": passed, "reason": "改判有證據支持" if passed else "證據撐不起誤導"}
            if label_ok is not None:
                r["label_ok"] = label_ok
            out[f"review__{s}_json"] = {"seat": s, "reviews": [r]}
        return out

    def test_every_seat_that_ran_reviews_the_change(self):
        run = make_run(fx.run_files(**fx.judge_only_overrides()))
        self.assertEqual(finalize.reviewers_needed(run), {"A": ["C1"], "B": ["C1"], "C": ["C1"], "X1": ["C1"]})

    def test_failed_seat_does_not_review(self):
        run = make_run(fx.run_files(**fx.judge_only_overrides(), opponent__C_json={"seat": "C", **FAILED}))
        self.assertEqual(sorted(finalize.reviewers_needed(run)), ["A", "B", "X1"])

    def test_change_stands_when_every_review_passes(self):
        r = run_finalize(**{**fx.judge_only_overrides(), **self.reviews()})
        c1 = claim(r, "C1")
        self.assertEqual(c1["label"], "misleading")
        self.assertEqual(c1["review_status"], "passed")
        self.assertEqual(r["disputes"], [])

    def test_missing_review_turns_the_change_unverified(self):
        """Same rule as any re-review: an unconfirmed change becomes `unverified`. Going back to the proponent's
        verdict was refuted in review: its evidence ids may point at other sources in the judge's ledger, and it
        undid corrections the rules require of the judge (a legal claim without the law text)."""
        r = run_finalize(**{**fx.judge_only_overrides(), **self.reviews(seats=("A", "B", "C"))})
        c1 = claim(r, "C1")
        self.assertEqual(c1["label"], "unverified")
        self.assertEqual(c1["review_status"], "failed")
        d = r["disputes"][0]
        self.assertEqual(d["proponent_label"], "false")
        self.assertEqual(d["objections"], [])
        self.assertIn("席位 X1：覆核未完成", d["review_reasons"])

    def test_rejected_change_turns_unverified(self):
        r = run_finalize(**{**fx.judge_only_overrides(), **self.reviews(passed=False, label_ok=False)})
        self.assertEqual(claim(r, "C1")["label"], "unverified")
        self.assertFalse(r["disputes"][0]["label_kept"])

    def test_review_that_accepts_the_label_keeps_it(self):
        r = run_finalize(**{**fx.judge_only_overrides(), **self.reviews(passed=False, label_ok=True)})
        self.assertEqual(claim(r, "C1")["label"], "misleading")
        self.assertTrue(r["disputes"][0]["label_kept"])

    def test_no_seat_left_to_review_turns_the_change_unverified(self):
        o = fx.judge_only_overrides()
        o.update({f"opponent__{s}_json": {"seat": s, **FAILED} for s in ("A", "B", "C", "X1")})
        r = run_finalize(**o)
        self.assertEqual(claim(r, "C1")["label"], "unverified")
        self.assertEqual(r["disputes"][0]["review_reasons"], ["沒有可以覆核的反方席位"])

    def test_missing_proponent_file_stops_instead_of_skipping_the_check(self):
        """Red-team: reading a missing proponent.json as empty silently switched the check off."""
        run = make_run(fx.run_files(**fx.judge_only_overrides(), proponent_json=None))
        with self.assertRaises(io.ReadError):
            finalize.reviewers_needed(run)

    def test_change_with_only_an_importance_challenge_upheld_is_reviewed(self):
        o = fx.importance_attack_overrides()
        o["judgment_json"]["rulings"][1]["upheld"] = False  # B-1 rejected; only the importance challenge stands
        run = make_run(fx.run_files(**o))
        self.assertEqual(finalize.reviewers_needed(run), {"A": ["C1"], "B": ["C1"], "C": ["C1"], "X1": ["C1"]})

    def test_change_with_only_a_tactic_attack_upheld_is_reviewed(self):
        o = fx.tactic_attack_overrides()
        o["opponent__C_json"]["attacks"][0]["claim_id"] = "C2"
        o["judgment_json"]["verdicts"][1]["label"] = "unverified"  # proponent said not_factual
        run = make_run(fx.run_files(**o))
        self.assertEqual(finalize.reviewers_needed(run),
                         {"A": ["C2"], "B": ["C1", "C2"], "C": ["C2"], "X1": ["C2"]})

    def test_unchanged_label_needs_no_extra_review(self):
        run = make_run(fx.run_files())
        self.assertEqual(finalize.judge_only_changes(run), {})


class TimeClaimTest(unittest.TestCase):
    def test_each_verdict_carries_its_time_mark(self):
        r = run_finalize(**fx.time_claim_overrides("deadline"))
        self.assertEqual({c["claim_id"]: c["time"] for c in r["claims"]}, {"C1": None, "C2": None, "C3": "deadline"})
        self.assertEqual(claim(run_finalize(**fx.time_claim_overrides("relative")), "C3")["time"], "relative")

    def test_runs_from_before_time_claims_still_finalize(self):
        claims = copy.deepcopy(fx.CLAIMS)
        del claims["time_claims"]
        self.assertIsNone(claim(run_finalize(claims_json=claims), "C1")["time"])

    def test_an_upheld_importance_challenge_does_not_move_a_time_claim(self):
        """Its importance plays no part in the score; the ruling is kept so the report can say it was not applied."""
        o = fx.time_claim_overrides("deadline", importance=3)
        opp_c = copy.deepcopy(fx.OPP_C)
        opp_c["attacks"] = [{"id": "C-1", "claim_id": "C3", "target": "neutral_rewrite", "argument": "這是主旨",
                             "proposed_label": None, "evidence": [], "proposed_importance": 4}]
        o["judgment_json"]["rulings"].append({"attack_id": "C-1", "upheld": True, "reason": "依量表是關鍵前提",
                                              "verified_urls": []})
        rebuttal = copy.deepcopy(fx.REBUTTAL)
        rebuttal["responses"].append({"attack_id": "C-1", "accept": True, "response": "同意", "evidence": []})
        c3 = claim(run_finalize(**o, opponent__C_json=opp_c, rebuttal_json=rebuttal), "C3")
        self.assertEqual(c3["importance"], 3)
        self.assertNotIn("importance_from", c3)
        self.assertEqual([a["attack_id"] for a in c3["importance_attacks"]], ["C-1"])


if __name__ == "__main__":
    unittest.main()
