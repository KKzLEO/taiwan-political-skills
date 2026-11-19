import unittest

from tests import helpers  # noqa: F401  (sets sys.path)
from fclib import score


def ev(id, tier=1, chain=None, stance="supports", access="full"):
    return {"id": id, "claim_ids": [], "url": f"https://example.org/{id}", "title": id,
            "publisher": "x", "accessed": "2026-11-17", "tier": tier,
            "chain": chain or id, "stance": stance, "excerpt": "...", "access_note": access}


def claim(cid, label, importance=3, core=True, evidence=("S1", "S2"), flags=(),
          legal=False, law=None, review="none"):
    return {"claim_id": cid, "label": label, "importance": importance, "core": core,
            "legal": legal, "law_text_obtained": law, "context_flags": list(flags),
            "evidence_ids": list(evidence), "review_status": review, "reasoning": "r",
            "upheld_attacks": [], "rejected_attacks": []}


FULL_LEDGER = [ev("S1", tier=1, chain="a"), ev("S2", tier=3, chain="b")]
OK_SEAT = [{"seat": "X1", "engine": "codex", "cross_model": True, "can_search": True, "status": "ok"}]
FULL_RUN = {"mode": "full", "host": "claude"}


def compute(claims, ledger=FULL_LEDGER, run=FULL_RUN, seats=OK_SEAT):
    return score.compute({"claims": claims, "ledger": ledger}, run, seats)


class CredibilityTest(unittest.TestCase):
    def test_all_true_with_full_evidence_scores_100(self):
        r = compute([claim("C1", "true")])
        self.assertEqual(r["credibility"]["score"], 100)
        self.assertEqual(r["result"], "符合")

    def test_accuracy_is_importance_weighted(self):
        r = compute([claim("C1", "false", importance=5), claim("C2", "true", importance=1)])
        self.assertAlmostEqual(r["credibility"]["accuracy"], 1 / 6, places=4)
        self.assertEqual(r["credibility"]["score"], 17)
        self.assertEqual(r["result"], "不符")

    def test_well_refuted_false_message_scores_zero(self):
        """Regression: strong refuting evidence must not raise the credibility of a false message."""
        r = compute([claim("C1", "false", importance=5), claim("C2", "false", importance=3)])
        self.assertEqual(r["credibility"]["score"], 0)
        self.assertEqual(r["result"], "不符")

    def test_misleading_core_claim_is_not_credible(self):
        r = compute([claim("C1", "misleading", importance=5, flags=["out_of_context"])])
        self.assertEqual(r["credibility"]["score"], 25)
        self.assertEqual(r["result"], "不符")

    def test_not_factual_claims_are_excluded(self):
        r = compute([claim("C1", "true"), claim("C2", "not_factual", importance=5, core=False)])
        self.assertEqual(r["credibility"]["score"], 100)

    def test_unverified_majority_gives_undetermined_and_hides_spectrum(self):
        r = compute([claim("C1", "unverified", importance=3), claim("C2", "true", importance=3)])
        self.assertEqual(r["result"], "無法判定")
        self.assertFalse(r["credibility"]["show_on_spectrum"])

    def test_unverified_minority_is_scored_normally(self):
        r = compute([claim("C1", "unverified", importance=2), claim("C2", "true", importance=3)])
        self.assertNotEqual(r["result"], "無法判定")
        self.assertTrue(r["credibility"]["show_on_spectrum"])

    def test_all_opinion_gives_undetermined(self):
        r = compute([claim("C1", "not_factual")])
        self.assertEqual(r["result"], "無法判定")
        self.assertIn("意見", r["result_reason"])

    def test_opinion_prediction_and_vague_claims_never_count_whatever_their_label(self):
        """They may share text with scored claims, so scoring them would count one sentence twice.
        Regression (round 2, case-013): an opinion judged unverified and a vague claim judged misleading were scored."""
        for t in ("O", "P", "U"):
            r = compute([claim("C1", "true"), {**claim("C2", "misleading", importance=5, core=False), "type": t}])
            self.assertEqual(r["credibility"]["score"], 100, t)
            self.assertIsNone(next(c for c in r["claims"] if c["claim_id"] == "C2")["factor"], t)

    def test_unscored_types_do_not_count_toward_the_unverified_share(self):
        r = compute([claim("C1", "true", importance=3), {**claim("C2", "unverified", importance=5, core=False), "type": "O"}])
        self.assertEqual(r["result"], "符合")

    def test_message_with_only_unscored_types_is_undetermined(self):
        r = compute([{**claim("C1", "false"), "type": "P"}])
        self.assertEqual(r["result"], "無法判定")

    def test_context_flags_are_listed_but_not_double_counted(self):
        r = compute([claim("C1", "true", flags=["out_of_context"]),
                     claim("C2", "true", flags=["out_of_context", "time_shift"])])
        self.assertEqual(r["credibility"]["context_flags"], ["out_of_context", "time_shift"])
        self.assertEqual(r["credibility"]["score"], 100)

    def test_unknown_context_flag_is_rejected(self):
        with self.assertRaises(score.ScoreError):
            compute([claim("C1", "true", flags=["made_up"])])

    def test_evidence_quality_does_not_change_credibility(self):
        weak = [ev("S1", tier=3, chain="a"), ev("S2", tier=3, chain="a")]
        self.assertEqual(compute([claim("C1", "true")], ledger=weak)["credibility"]["score"], 100)

    def test_unknown_label_is_rejected(self):
        with self.assertRaises(score.ScoreError):
            compute([claim("C1", "probably")])

    def test_missing_evidence_id_is_rejected(self):
        with self.assertRaises(score.ScoreError):
            compute([claim("C1", "true", evidence=["S99"])])


class ImportanceChangeTest(unittest.TestCase):
    def adjusted(self, c, original):
        return {**c, "importance_from": original}

    def test_result_without_the_change_is_reported_when_it_differs(self):
        # adjusted: (0*4 + 1*3)/7 = 43 部分符合; original: (0*5 + 1*3)/8 = 38 不符
        r = compute([self.adjusted(claim("C1", "false", 4), 5), claim("C2", "true", 3)])
        self.assertEqual(r["result"], "部分符合")
        self.assertEqual(r["without_importance_changes"], {"result": "不符", "credibility": 38, "publishable": True})
        self.assertFalse(r["publishable"])  # a conclusion that hangs on a contested weight is not publishable

    def test_nothing_extra_when_no_importance_changed(self):
        self.assertIsNone(compute([claim("C1", "false", 4), claim("C2", "true", 3)]).get("without_importance_changes"))

    def test_nothing_extra_when_the_change_does_not_matter(self):
        r = compute([self.adjusted(claim("C1", "true", 4), 5), claim("C2", "true", 3)])
        self.assertIsNone(r.get("without_importance_changes"))


class RoundingAndBandsTest(unittest.TestCase):
    def test_round_half_up(self):
        self.assertEqual(score.round_half_up(79.5), 80)
        self.assertEqual(score.round_half_up(80.5), 81)
        self.assertEqual(score.round_half_up(79.49), 79)

    def test_result_bands(self):
        cases = {100: "符合", 80: "符合", 79: "大致符合", 60: "大致符合", 59: "部分符合",
                 40: "部分符合", 39: "不符", 0: "不符"}
        for s, expected in cases.items():
            self.assertEqual(score.result_label(s), expected, s)

    def test_confidence_levels(self):
        cases = {100: "高", 75: "高", 74: "中", 50: "中", 49: "低", 0: "低"}
        for s, expected in cases.items():
            self.assertEqual(score.confidence_level(s), expected, s)


class ConfidenceTest(unittest.TestCase):
    def conf(self, r):
        return r["confidence"]["score"]

    def test_clean_full_run_is_100_and_publishable(self):
        r = compute([claim("C1", "true")])
        self.assertEqual(self.conf(r), 100)
        self.assertEqual(r["confidence"]["level"], "高")
        self.assertTrue(r["publishable"])

    def test_no_cross_model_seat_deducts_20_and_blocks_publishing(self):
        seats = [{"seat": "A", "engine": "claude", "cross_model": False, "can_search": True, "status": "ok"}]
        r = compute([claim("C1", "true")], seats=seats)
        self.assertEqual(self.conf(r), 80)
        self.assertFalse(r["publishable"])

    def test_failed_cross_model_seat_counts_as_missing(self):
        seats = [{"seat": "X1", "engine": "codex", "cross_model": True, "can_search": True, "status": "failed"}]
        r = compute([claim("C1", "true")], seats=seats)
        self.assertEqual(self.conf(r), 80)
        self.assertFalse(r["publishable"])

    def test_cross_model_without_search_deducts_10(self):
        seats = [{"seat": "X1", "engine": "ollama", "cross_model": True, "can_search": False, "status": "ok"}]
        r = compute([claim("C1", "true")], seats=seats)
        self.assertEqual(self.conf(r), 90)

    def test_each_failed_review_deducts_10(self):
        r = compute([claim("C1", "unverified", review="failed"), claim("C2", "true", review="failed"),
                     claim("C3", "true", importance=5)])
        self.assertEqual(self.conf(r), 80)

    def test_failed_review_of_an_unscored_type_does_not_deduct(self):
        r = compute([claim("C1", "true"), {**claim("C2", "false", core=False, importance=2, review="failed"), "type": "O"}])
        self.assertEqual(self.conf(r), 100)

    def test_missing_law_text_on_an_unscored_type_does_not_deduct(self):
        r = compute([claim("C1", "true"), {**claim("C2", "unverified", core=False, importance=1, legal=True, law=False), "type": "P"}])
        self.assertEqual(self.conf(r), 100)

    def test_core_claim_relying_only_on_limited_sources_deducts_10_each_capped_at_30(self):
        ledger = [ev("S1", tier=1, chain="a", access="paywall"), ev("S2", tier=1, chain="b", access="blocked")]
        claims = [claim(f"C{i}", "true", evidence=["S1", "S2"]) for i in range(1, 5)]
        r = compute(claims, ledger=ledger)
        self.assertEqual(self.conf(r), 70)

    def test_supplementary_limited_source_does_not_deduct(self):
        """Regression (first E2E run): extra mirror/snippet evidence must not lower confidence
        when the claim already has full-access direct evidence."""
        ledger = FULL_LEDGER + [ev("S3", tier=1, chain="c", access="not_original"),
                                ev("S4", tier=3, chain="d", access="snippet")]
        r = compute([claim("C1", "true", evidence=["S1", "S2", "S3", "S4"])], ledger=ledger)
        self.assertEqual(self.conf(r), 100)

    def test_access_limits_on_non_core_claims_are_ignored(self):
        ledger = FULL_LEDGER + [ev("S3", access="blocked")]
        r = compute([claim("C1", "true"), claim("C2", "true", core=False, evidence=["S3"])], ledger=ledger)
        self.assertEqual(self.conf(r), 100)

    def test_missing_law_text_deducts_15_once(self):
        r = compute([claim("C1", "unverified", legal=True, law=False, importance=1),
                     claim("C2", "true", legal=True, law=None, importance=5)])
        self.assertEqual(self.conf(r), 85)

    def test_quick_mode_caps_at_60_and_is_never_publishable(self):
        r = compute([claim("C1", "true")], run={"mode": "quick", "host": "claude"})
        self.assertEqual(self.conf(r), 60)
        self.assertEqual(r["confidence"]["level"], "中")
        self.assertFalse(r["publishable"])

    def test_confidence_floors_at_zero(self):
        ledger = [ev(f"S{i}", access="blocked", tier=6) for i in range(1, 5)]
        claims = [claim(f"C{i}", "true", review="failed", legal=True, law=False,
                        evidence=["S1", "S2", "S3", "S4"]) for i in range(1, 8)]
        r = compute(claims, ledger=ledger, seats=[])
        self.assertEqual(self.conf(r), 0)

    def test_evidence_quality_needs_primary_tier_for_first_half(self):
        ledger = [ev("S1", tier=3, chain="a"), ev("S2", tier=3, chain="b")]
        r = compute([claim("C1", "true")], ledger=ledger)
        self.assertAlmostEqual(r["confidence"]["evidence_quality"], 0.5)
        self.assertEqual(self.conf(r), 90)

    def test_evidence_quality_needs_two_chains_for_second_half(self):
        ledger = [ev("S1", tier=1, chain="a"), ev("S2", tier=2, chain="a")]
        r = compute([claim("C1", "true")], ledger=ledger)
        self.assertAlmostEqual(r["confidence"]["evidence_quality"], 0.5)
        self.assertEqual(self.conf(r), 90)

    def test_context_only_evidence_does_not_count(self):
        ledger = [ev("S1", tier=1, chain="a", stance="context"), ev("S2", tier=1, chain="b", stance="context")]
        r = compute([claim("C1", "true")], ledger=ledger)
        self.assertEqual(r["confidence"]["evidence_quality"], 0)
        self.assertEqual(self.conf(r), 80)

    def test_evidence_quality_uses_core_claims_only(self):
        ledger = [ev("S1", tier=1, chain="a"), ev("S2", tier=1, chain="b"), ev("S3", tier=6, chain="c")]
        r = compute([claim("C1", "true", core=True, evidence=["S1", "S2"]),
                     claim("C2", "true", core=False, evidence=["S3"])], ledger=ledger)
        self.assertEqual(r["confidence"]["evidence_quality"], 1)
        self.assertEqual(self.conf(r), 100)

    def test_unscored_types_are_ignored_for_evidence_quality_and_access_limits(self):
        ledger = FULL_LEDGER + [ev("S3", tier=6, chain="c", access="blocked")]
        r = compute([claim("C1", "true"), {**claim("C2", "misleading", evidence=["S3"]), "type": "U"}], ledger=ledger)
        self.assertEqual(r["confidence"]["evidence_quality"], 1)
        self.assertEqual(self.conf(r), 100)

    def test_deductions_are_itemised(self):
        r = compute([claim("C1", "true")], seats=[])
        reasons = [d["reason"] for d in r["confidence"]["deductions"]]
        self.assertTrue(any("跨模型" in x for x in reasons))
        self.assertEqual(sum(d["points"] for d in r["confidence"]["deductions"]), 20)


def verdicts_with(claims, unverified):
    return {"claims": claims, "ledger": FULL_LEDGER, "unverified_rulings": unverified}


class PublishBlockTest(unittest.TestCase):
    """Conditions that keep a report from being publishable without changing its scores."""

    def test_unverified_ruling_blocks_publishing_without_lowering_confidence(self):
        u = [{"attack_id": "B-1", "seat": "B", "claim_id": "C1", "target": "label"}]
        r = score.compute(verdicts_with([claim("C1", "false")], u), FULL_RUN, OK_SEAT)
        self.assertEqual(r["confidence"]["score"], 100)
        self.assertFalse(r["publishable"])
        self.assertTrue(any("核對過的網址" in b for b in r["publish_blocks"]))

    def test_unverified_trace_ruling_blocks_publishing_too(self):
        u = [{"attack_id": "C-1", "seat": "C", "claim_id": None, "target": "trace"}]
        self.assertFalse(score.compute(verdicts_with([claim("C1", "false")], u), FULL_RUN, OK_SEAT)["publishable"])

    def test_unscored_claim_that_would_change_the_result_blocks_publishing(self):
        """Red-team: typing a damaging fact as vague hides it from the score. If counting the opinion,
        prediction or vague claims the judge still labelled would change the result, do not publish."""
        hidden = {**claim("C2", "false", importance=5, core=True), "type": "U"}
        r = compute([claim("C1", "true", core=False), hidden])
        self.assertEqual(r["result"], "符合")
        self.assertFalse(r["publishable"])
        self.assertTrue(any("C2" in b and "不符" in b for b in r["publish_blocks"]))

    def test_classification_block_names_the_final_label_without_crediting_the_judge(self):
        """Skeptic re-review: a review that did not confirm a change turns the label into `unverified`, which the
        judge never gave, so the block must not say the judge judged it as a fact."""
        hidden = {**claim("C2", "unverified", importance=5, core=True), "type": "U"}
        b = next(b for b in compute([claim("C1", "true", core=False), hidden])["publish_blocks"] if "C2" in b)
        self.assertNotIn("裁判", b)
        self.assertIn("C2（無法證實）", b)

    def test_lowering_importance_or_core_does_not_get_around_the_check(self):
        """Red-team re-review: the first guard only looked at core or importance >= 4."""
        r = compute([claim("C1", "true"), {**claim("C2", "false", core=False), "type": "U"},
                     {**claim("C3", "false", core=False), "type": "O"}])
        self.assertFalse(r["publishable"])

    def test_key_unscored_claim_judged_unverified_blocks_when_it_would_make_the_result_undetermined(self):
        """Simplifier re-review: excluding unverified left a hole (符合 instead of 無法判定)."""
        r = compute([claim("C1", "true"), {**claim("C2", "unverified", importance=5), "type": "O"}])
        self.assertFalse(r["publishable"])

    def test_unscored_claim_that_would_not_change_the_result_does_not_block(self):
        r = compute([claim("C1", "false", importance=5), {**claim("C2", "false", importance=2, core=False), "type": "O"}])
        self.assertTrue(r["publishable"])

    def test_unscored_claim_judged_not_factual_never_blocks(self):
        r = compute([claim("C1", "true"), {**claim("C2", "not_factual", importance=5), "type": "O"}])
        self.assertTrue(r["publishable"])

    def test_importance_challenge_cannot_lift_a_publish_block(self):
        """Skeptic re-review: lowering a weight in the debate must not make a report publishable."""
        lowered = {**claim("C2", "false", importance=1, core=False), "type": "O", "importance_from": 2}
        r = compute([claim("C1", "true", importance=5), lowered])
        self.assertEqual(r["result"], "符合")
        self.assertFalse(r["publishable"])
        self.assertTrue(any("重要性" in b for b in r["publish_blocks"]))

    def test_failed_or_missing_internal_seat_blocks_publishing_in_full_mode(self):
        for status in ("failed", "missing"):
            seats = OK_SEAT + [{"seat": "B", "engine": "claude", "cross_model": False, "can_search": True, "status": status}]
            r = compute([claim("C1", "true")], seats=seats)
            self.assertFalse(r["publishable"], status)
            self.assertTrue(any("反方 B" in b for b in r["publish_blocks"]), status)

    def test_unconfirmed_judge_only_change_blocks_publishing(self):
        """Red-team: fewer completed reviews must never make a report easier to publish."""
        v = {"claims": [claim("C1", "true"), claim("C2", "unverified", review="failed")], "ledger": FULL_LEDGER,
             "disputes": [{"claim_id": "C2", "judge_label": "false", "label_kept": False, "proponent_label": "true",
                           "objections": [], "review_reasons": ["席位 X1：覆核未完成"]}]}
        r = score.compute(v, FULL_RUN, OK_SEAT)
        self.assertFalse(r["publishable"])
        self.assertTrue(any("C2" in b and "裁判" in b for b in r["publish_blocks"]))

    def test_judge_only_change_with_the_label_accepted_does_not_block(self):
        v = {"claims": [claim("C1", "true"), claim("C2", "false", review="failed")], "ledger": FULL_LEDGER,
             "disputes": [{"claim_id": "C2", "judge_label": "false", "label_kept": True, "proponent_label": "true",
                           "objections": [], "review_reasons": ["席位 X1：理由少引一半"]}]}
        self.assertFalse(any("裁判" in b for b in score.compute(v, FULL_RUN, OK_SEAT)["publish_blocks"]))

    def test_clean_run_has_no_blocks(self):
        self.assertEqual(compute([claim("C1", "true")])["publish_blocks"], [])


class DeterminismTest(unittest.TestCase):
    def test_same_input_same_output(self):
        claims = [claim("C1", "misleading", flags=["out_of_context"]), claim("C2", "true", importance=2)]
        self.assertEqual(compute(claims), compute(claims))


if __name__ == "__main__":
    unittest.main()
