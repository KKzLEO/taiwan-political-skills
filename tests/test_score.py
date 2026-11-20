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

    def test_overall_accuracy_is_importance_weighted(self):
        r = compute([claim("C1", "false", importance=5), claim("C2", "true", importance=1)])
        self.assertAlmostEqual(r["credibility"]["overall_accuracy"], 1 / 6, places=4)
        self.assertEqual(r["credibility"]["score"], 0)  # the main claim is false
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


class MainClaimsFirstTest(unittest.TestCase):
    """2026-11-19: the result follows the main claims (the highest importance among scored claims); the other
    claims can only pull it down. Holdout and calibration cases where true details diluted a false or misleading
    main point (001, 009, 011, 012, 015) or a wrong detail did not stop 符合 (018)."""

    def test_true_details_cannot_rescue_a_false_main_claim(self):
        r = compute([claim("C1", "false", importance=5)] + [claim(f"C{i}", "true", importance=3) for i in range(2, 6)])
        self.assertEqual(r["credibility"]["score"], 0)
        self.assertEqual(r["result"], "不符")
        self.assertEqual(r["credibility"]["main_claims"], ["C1"])

    def test_misleading_main_claim_with_true_details_does_not_match(self):
        r = compute([claim("C1", "misleading", importance=5), claim("C2", "true", importance=4), claim("C3", "true", importance=3)])
        self.assertEqual(r["result"], "不符")

    def test_highest_importance_present_is_the_main_tier(self):
        """case-015: no scored claim at 5, two misleading claims at 4 and true details at 3."""
        r = compute([claim("C1", "misleading", importance=4), claim("C2", "misleading", importance=4),
                     claim("C3", "true", importance=3), claim("C4", "true", importance=3)])
        self.assertEqual(r["credibility"]["main_claims"], ["C1", "C2"])
        self.assertEqual(r["result"], "不符")

    def test_wrong_details_still_pull_a_true_main_claim_down(self):
        """case-006: the main claim is true but two details are false."""
        r = compute([claim("C1", "true", importance=5), claim("C2", "false", importance=3), claim("C3", "false", importance=3)])
        self.assertEqual(r["credibility"]["score"], 45)
        self.assertEqual(r["result"], "部分符合")

    def test_a_wrong_detail_caps_a_true_main_claim_at_mostly(self):
        """case-018: both main claims true, one detail false among many true ones."""
        claims = [claim("C1", "true", importance=5), claim("C2", "true", importance=5), claim("C3", "false", importance=2)]
        claims += [claim(f"C{i}", "true", importance=2) for i in range(4, 14)]
        r = compute(claims)
        self.assertEqual(r["credibility"]["score"], 79)
        self.assertTrue(r["credibility"]["capped"])
        self.assertEqual(r["result"], "大致符合")

    def test_a_mixed_or_misleading_detail_caps_too(self):
        for label in ("mixed", "misleading"):
            r = compute([claim("C1", "true", importance=5), claim("C2", label, importance=1)] +
                        [claim(f"C{i}", "true", importance=2) for i in range(3, 9)])
            self.assertEqual(r["result"], "大致符合", label)

    def test_an_unverified_detail_does_not_cap(self):
        r = compute([claim("C1", "true", importance=5), claim("C2", "unverified", importance=1)])
        self.assertFalse(r["credibility"]["capped"])
        self.assertEqual(r["result"], "符合")

    def test_a_false_main_claim_is_determined_even_when_details_are_unverified(self):
        """case-009: the details were mostly unverified, which used to make the whole message 無法判定."""
        r = compute([claim("C1", "false", importance=5), claim("C2", "unverified", importance=4),
                     claim("C3", "unverified", importance=3)])
        self.assertEqual(r["result"], "不符")
        self.assertTrue(r["credibility"]["show_on_spectrum"])

    def test_a_wrong_claim_among_many_main_claims_still_caps_at_mostly(self):
        """Skeptic review: round-1 case-005 had six claims at 5; one of them false still scored 83 符合, while the
        same false claim at 4 was capped. Raising a false claim's importance must never improve the result."""
        claims = [claim(f"C{i}", "true", importance=5) for i in range(1, 6)] + [claim("C6", "false", importance=5)]
        r = compute(claims)
        self.assertEqual(r["result"], "大致符合")
        self.assertTrue(r["credibility"]["capped"])

    def test_a_proven_false_key_fact_is_determined_even_if_the_main_claim_is_unverified(self):
        """Skeptic review: the holdout case-020 with its main claim unverified turned 無法判定 although two key facts
        at importance 4 were proven false; at 4 a claim is one the main point cannot stand without."""
        r = compute([claim("C1", "unverified", importance=5), claim("C2", "false", importance=4),
                     claim("C3", "false", importance=4), claim("C4", "true", importance=3)])
        self.assertEqual(r["result"], "不符")

    def test_a_partly_wrong_key_fact_does_not_turn_an_unverified_main_claim_into_a_mismatch(self):
        """Second review: a mixed or misleading claim at 4 made an unverified main point a publishable 不符 at 35.
        Below the main claims only a proven-false key fact settles it."""
        for label in ("mixed", "misleading"):
            r = compute([claim("C1", "unverified", importance=5), claim("C2", label, importance=4),
                         claim("C3", "true", importance=4)])
            self.assertEqual(r["result"], "無法判定", label)

    def test_without_claims_at_4_the_main_tier_alone_decides(self):
        """Simplifier review: nothing tested a top tier below 4."""
        r = compute([claim("C1", "unverified", importance=3), claim("C2", "false", importance=3)])
        self.assertEqual(r["result"], "不符")

    def test_mostly_unverified_main_claims_are_undetermined(self):
        r = compute([claim("C1", "unverified", importance=5), claim("C2", "unverified", importance=5),
                     claim("C3", "true", importance=5), claim("C4", "false", importance=2)])
        self.assertEqual(r["result"], "無法判定")

    def test_a_wrong_main_claim_beside_unverified_ones_is_determined(self):
        r = compute([claim("C1", "unverified", importance=5), claim("C2", "false", importance=5)])
        self.assertEqual(r["result"], "不符")


class ImportanceChangeTest(unittest.TestCase):
    def adjusted(self, c, original):
        return {**c, "importance_from": original}

    def test_result_without_the_change_is_reported_when_it_differs(self):
        # adjusted: main claims {C1 true, C2 false} -> 50 部分符合; original: main claim {C2 false} -> 0 不符
        r = compute([self.adjusted(claim("C1", "true", 5), 4), claim("C2", "false", 5)])
        self.assertEqual(r["result"], "部分符合")
        self.assertEqual(r["without_importance_changes"], {"result": "不符", "credibility": 0, "publishable": True})
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

    def test_an_unverified_ruling_on_a_tactic_tag_does_not_block_publishing(self):
        """Final delta review: tags are not in the report and never score, yet an upheld attack on one, with the
        judge's checked sources missing, printed 「手法標記」 under the result and turned 可公開 off."""
        u = [{"attack_id": "C-1", "seat": "C", "claim_id": None, "target": "tactic"}]
        r = score.compute(verdicts_with([claim("C1", "false")], u), FULL_RUN, OK_SEAT)
        self.assertTrue(r["publishable"])
        self.assertEqual(r["publish_blocks"], [])

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
        # Counting C2 at 4 leaves C1 the only main claim (不符 either way); at its original 5 it joins the main
        # claims (部分符合), so the unadjusted report hangs on the classification and cannot be published.
        lowered = {**claim("C2", "true", importance=4, core=False), "type": "O", "importance_from": 5}
        r = compute([claim("C1", "false", importance=5), lowered])
        self.assertEqual(r["result"], "不符")
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

    def test_quick_mode_names_itself_as_the_reason(self):
        """Audit: a quick run said 不可公開 and nothing else; its confidence is capped at 60, so the cap is the
        reason and a second line about confidence would read as if checking harder could lift it."""
        r = compute([claim("C1", "true")], run={"mode": "quick", "host": "claude"})
        self.assertFalse(r["publishable"])
        self.assertEqual(r["publish_blocks"], ["這次是快速模式，沒有跑完整的「一個正方對三個反方」"])

    def test_confidence_below_high_is_named_as_the_reason(self):
        ledger = [ev("S1", tier=3, chain="a"), ev("S2", tier=3, chain="a")]  # evidence quality 0: −20
        r = compute([claim("C1", "true", legal=True, law=False)], ledger=ledger)  # −15 more: 65
        self.assertEqual((r["confidence"]["score"], r["publishable"]), (65, False))
        self.assertEqual(r["publish_blocks"], ["信心度 65（中），要到 75 以上才是「高」；扣了哪些分，見後面的「評分拆解」"])

    def test_no_cross_model_seat_is_named_as_the_reason(self):
        for seats in ([], [dict(OK_SEAT[0], status="failed")]):
            r = compute([claim("C1", "true")], seats=seats)
            self.assertEqual(r["confidence"]["level"], "高")  # 80: the seat is the only reason
            self.assertEqual(r["publish_blocks"], ["沒有另一家公司的模型當反方跑成功，少了跨模型抗辯"])

    def test_every_report_that_is_not_publishable_says_why(self):
        """Audit: 7 of 8 reports that could not be published gave no reason. The publishing rule is unchanged."""
        ledgers = (FULL_LEDGER, [ev("S1", tier=3, chain="a"), ev("S2", tier=3, chain="a")])
        for mode in ("full", "quick"):
            for seats in (OK_SEAT, []):
                for ledger in ledgers:
                    for label in ("true", "false", "mostly_true", "unverified"):
                        r = compute([claim("C1", label, legal=True, law=False)], ledger=ledger,
                                    run={"mode": mode, "host": "claude"}, seats=seats)
                        base = mode == "full" and r["confidence"]["level"] == "高" and bool(seats)
                        self.assertEqual(r["publishable"], base and r["result"] in ("符合", "不符"))
                        self.assertEqual(r["publishable"], not r["publish_blocks"], (mode, seats, label))

    def test_unverified_ruling_block_has_no_attack_number(self):
        """Audit: 「B-1」 is an internal number the reader cannot look up, one hyphen away from the claim C1."""
        u = [{"attack_id": "B-1", "seat": "B", "claim_id": "C1", "target": "label"}]
        b = score.compute(verdicts_with([claim("C1", "false")], u), FULL_RUN, OK_SEAT)["publish_blocks"]
        self.assertEqual(b, ["反方 B 對 C1 的一項攻擊判成立，但裁判沒有列出實際核對過的網址，判決照用"])


def timed(cid, kind, label, importance=3, core=False, review="none"):
    return {**claim(cid, label, importance=importance, core=core, review=review), "type": "I", "time": kind}


class TimeClaimTest(unittest.TestCase):
    """Time claims only ever pull the result down: a right one adds nothing, a wrong one has a fixed effect."""

    def test_a_deadline_that_has_not_passed_does_not_lift_a_misleading_main_claim(self):
        r = compute([claim("C1", "misleading", importance=5), timed("C2", "deadline", "true", importance=5, core=True)])
        self.assertEqual(r["credibility"]["score"], 25)
        self.assertEqual(r["result"], "不符")
        self.assertEqual(r["credibility"]["main_claims"], ["C1"])
        self.assertIsNone(next(c for c in r["claims"] if c["claim_id"] == "C2")["factor"])

    def test_a_passed_deadline_voids_true_content_and_is_not_publishable(self):
        for importance in (5, 4, 3):  # whatever the content's importance
            r = compute([claim("C1", "true", importance=importance), timed("C2", "deadline", "false")])
            self.assertEqual((r["credibility"]["score"], r["result"]), (0, "不符"), importance)
            self.assertEqual(r["credibility"]["raw"], 100.0)  # the content alone
            self.assertFalse(r["publishable"])
            self.assertTrue(any("不看 C2" in b and "「符合」" in b for b in r["publish_blocks"]), r["publish_blocks"])

    def test_a_passed_deadline_beside_wrong_content_stays_publishable(self):
        r = compute([claim("C1", "false", importance=5), timed("C2", "deadline", "false")])
        self.assertEqual(r["result"], "不符")
        self.assertTrue(r["publishable"], r["publish_blocks"])

    def test_a_deadline_judged_misleading_or_partly_wrong_limits_the_score_to_its_factor(self):
        for label, expected in (("misleading", (25, "不符")), ("mixed", (50, "部分符合"))):
            r = compute([claim("C1", "true", importance=5), timed("C2", "deadline", label)])
            self.assertEqual((r["credibility"]["score"], r["result"]), expected, label)

    def test_a_passed_deadline_settles_content_that_cannot_be_checked(self):
        r = compute([claim("C1", "unverified", importance=5), timed("C2", "deadline", "false")])
        self.assertEqual((r["credibility"]["score"], r["result"]), (0, "不符"))

    def test_a_partly_wrong_deadline_does_not_turn_unverified_content_into_a_finding(self):
        """Skeptic re-review: 35 comes from the unverified content, not from the deadline (50)."""
        r = compute([claim("C1", "unverified", importance=5), timed("C2", "deadline", "mixed")])
        self.assertEqual(r["result"], "無法判定")

    def test_a_passed_deadline_alone_is_the_basis_of_the_score(self):
        r = compute([{**claim("C1", "not_factual", core=False), "type": "O"}, timed("C2", "deadline", "false")])
        self.assertEqual((r["credibility"]["score"], r["result"]), (0, "不符"))
        self.assertEqual(r["credibility"]["main_claims"], ["C2"])
        self.assertEqual((r["credibility"]["main_accuracy"], r["credibility"]["overall_accuracy"]), (0.0, 0.0))
        self.assertTrue(any("不看 C2" in b and "「無法判定」" in b for b in r["publish_blocks"]), r["publish_blocks"])

    def test_a_run_with_only_a_time_claim_does_not_crash(self):
        self.assertEqual(compute([timed("C1", "deadline", "false")])["result"], "不符")
        self.assertEqual(compute([timed("C1", "relative", "false")])["result"], "無法判定")

    def test_an_unresolved_time_claim_blocks_only_when_a_wrong_one_would_change_the_result(self):
        for kind, would_be in (("deadline", "不符"), ("relative", "大致符合")):
            r = compute([claim("C1", "true", importance=5), timed("C2", kind, "unverified")])
            self.assertEqual((r["credibility"]["score"], r["result"]), (100, "符合"), kind)  # the score does not move
            self.assertFalse(r["publishable"])
            self.assertTrue(any("C2" in b and "沒有查清楚" in b and f"「{would_be}」" in b for b in r["publish_blocks"]),
                            r["publish_blocks"])
            r = compute([claim("C1", "false", importance=5), timed("C2", kind, "unverified")])  # 不符 either way
            self.assertTrue(r["publishable"], r["publish_blocks"])

    def test_an_implied_time_that_is_wrong_caps_true_content_at_79(self):
        for label in ("false", "misleading", "mixed"):
            r = compute([claim("C1", "true", importance=5), claim("C2", "true", importance=3),
                         timed("C3", "relative", label, importance=5, core=True)])
            self.assertEqual((r["credibility"]["score"], r["result"], r["credibility"]["capped"]),
                             (79, "大致符合", True), label)
            self.assertEqual(r["credibility"]["main_claims"], ["C1"])

    def test_the_cap_is_only_reported_when_it_lowers_the_score(self):
        r = compute([claim("C1", "true", importance=5), claim("C2", "false", importance=4),
                     timed("C3", "relative", "false")])
        self.assertEqual((r["credibility"]["score"], r["credibility"]["capped"]), (56, False))

    def test_an_implied_time_that_is_right_changes_nothing(self):
        r = compute([claim("C1", "true", importance=4), timed("C2", "relative", "mostly_true", importance=5, core=True)])
        self.assertEqual((r["credibility"]["score"], r["credibility"]["capped"], r["publish_blocks"]), (100, False, []))
        self.assertTrue(r["publishable"])

    def test_a_time_claim_is_not_a_main_claim_when_the_content_cannot_be_checked(self):
        # as an ordinary claim at importance 5, C2 would be the only main claim and the result 大致符合
        r = compute([claim("C1", "unverified", importance=4), timed("C2", "relative", "true", importance=5, core=True)])
        self.assertEqual(r["result"], "無法判定")

    def test_opinions_with_a_wrong_implied_time_have_no_score(self):
        r = compute([{**claim("C1", "not_factual", core=False), "type": "O"}, timed("C2", "relative", "false")])
        self.assertEqual(r["result"], "無法判定")
        self.assertIsNone(r["credibility"])
        self.assertIn("除了時間命題", r["result_reason"])

    def test_a_failed_review_on_a_time_claim_still_costs_confidence(self):
        r = compute([claim("C1", "true"), timed("C2", "relative", "true", review="failed")])
        self.assertEqual(r["confidence"]["score"], 90)

    def test_the_classification_check_looks_at_the_content_without_time_claims(self):
        """Skeptic re-review: a passed deadline pushes both sides to 不符 and hid that the content hangs on a type."""
        content = [claim("C1", "false", importance=5), {**claim("C2", "true", importance=5), "type": "O"}]
        self.assertFalse(compute(content)["publishable"])
        r = compute(content + [timed("C3", "deadline", "false")])
        self.assertFalse(r["publishable"])
        self.assertTrue(any("被分成意見" in b for b in r["publish_blocks"]), r["publish_blocks"])


class PublishableResultTest(unittest.TestCase):
    def test_only_the_two_ends_of_the_scale_can_be_publishable(self):
        middle = {"大致符合": [claim("C1", "true", importance=5), claim("C2", "false", importance=2)],
                  "部分符合": [claim("C1", "true", importance=5), claim("C2", "false", importance=5)],
                  "無法判定": [claim("C1", "unverified", importance=5)]}
        for result, claims in middle.items():
            r = compute(claims)
            self.assertEqual(r["result"], result)
            self.assertFalse(r["publishable"], result)
            self.assertTrue(any(f"結論是「{result}」" in b and "只有「符合」或「不符」才標可公開" in b
                                for b in r["publish_blocks"]), r["publish_blocks"])
        for claims in ([claim("C1", "true")], [claim("C1", "false")]):
            self.assertTrue(compute(claims)["publishable"])

    def dispute(self, claims, **d):
        v = {"claims": claims, "ledger": FULL_LEDGER,
             "disputes": [{"claim_id": "C2", "label_kept": False, "objections": [], "review_reasons": ["席位 B：覆核未完成"], **d}]}
        return score.compute(v, FULL_RUN, OK_SEAT)

    def test_a_label_the_reviews_did_not_confirm_blocks_publishing(self):
        """Audit: with the review file missing, 大致符合 71 became 符合 81 and stayed publishable."""
        r = self.dispute([claim("C1", "true", importance=5), claim("C2", "unverified", importance=2, review="failed")],
                         judge_label="false")
        self.assertEqual(r["result"], "符合")
        self.assertFalse(r["publishable"])
        self.assertTrue(any("C2" in b and "覆核" in b and "「錯誤」" in b and "結果會是「大致符合」" in b
                            for b in r["publish_blocks"]), r["publish_blocks"])

    def test_a_failed_review_of_an_unverified_ruling_does_not_block(self):
        r = self.dispute([claim("C1", "false", importance=5), claim("C2", "unverified", importance=2, review="failed")],
                         judge_label="unverified")
        self.assertTrue(r["publishable"], r["publish_blocks"])

    def test_a_failed_review_of_an_opinion_does_not_block(self):
        r = self.dispute([claim("C1", "false", importance=5),
                          {**claim("C2", "unverified", importance=2, review="failed"), "type": "O"}], judge_label="false")
        self.assertTrue(r["publishable"], r["publish_blocks"])

    def test_an_unconfirmed_review_cannot_lift_the_classification_block(self):
        """Known limitation until 0.2.0: the opinion the judge called true became unverified, and counting it no
        longer changed the result, so the report with the missing review was the publishable one."""
        r = self.dispute([claim("C1", "false", importance=5),
                          {**claim("C2", "unverified", importance=5, review="failed"), "type": "O"}], judge_label="true")
        self.assertFalse(r["publishable"])
        self.assertTrue(any("C2（正確）被分成意見" in b for b in r["publish_blocks"]), r["publish_blocks"])

    def test_a_time_claim_the_reviews_did_not_confirm_is_reported_once(self):
        r = self.dispute([claim("C1", "true", importance=5), timed("C2", "relative", "unverified", review="failed")],
                         judge_label="false")
        self.assertFalse(r["publishable"])
        self.assertEqual(len([b for b in r["publish_blocks"] if "C2" in b]), 1, r["publish_blocks"])


class DeterminismTest(unittest.TestCase):
    def test_same_input_same_output(self):
        claims = [claim("C1", "misleading", flags=["out_of_context"]), claim("C2", "true", importance=2)]
        self.assertEqual(compute(claims), compute(claims))


if __name__ == "__main__":
    unittest.main()
