import copy
import json
import unittest

from tests import fixtures as fx
from tests.helpers import make_run
from fclib import validate


def errors_for(name, mutate=None, **overrides):
    files = fx.run_files(**overrides)
    if mutate:
        mutate(files[name])
    run = make_run(files)
    return validate.validate_file(run, name, known_tactics=fx.TACTIC_LIB)


class ValidRunTest(unittest.TestCase):
    def test_every_fixture_file_is_valid(self):
        run = make_run(fx.run_files())
        for name in fx.run_files():
            with self.subTest(name=name):
                self.assertEqual(validate.validate_file(run, name, known_tactics=fx.TACTIC_LIB), [])

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


class DeadlineEvidenceTest(unittest.TestCase):
    """Whether a deadline has passed is a comparison of two dates; there may be no page to quote for it."""

    def verdicts(self, kind, label, evidence):
        o = fx.time_claim_overrides(kind, label)
        for doc in (o["proponent_json"], o["judgment_json"]):
            doc["verdicts"][-1]["evidence_ids"] = evidence
        return o

    def test_a_deadline_premise_needs_no_evidence(self):
        for label in ("false", "true"):
            o = self.verdicts("deadline", label, [])
            for name in ("proponent.json", "judgment.json"):
                self.assertEqual(errors_for(name, **o), [], (label, name))

    def test_an_implied_time_and_every_other_claim_still_need_evidence(self):
        o = self.verdicts("relative", "false", [])
        self.assertTrue(any("C3" in e or "沒有引用任何證據" in e for e in errors_for("judgment.json", **o)))


class PublishedAtTest(unittest.TestCase):
    """The publication time now decides whether the time rules apply, so it has to be a date or nothing."""

    def test_published_at_is_a_date_or_empty(self):
        for ok in (None, "", "2026-10-20", "2026-10-20T14:15:00+08:00", "2026-10-20 14:15"):
            self.assertEqual(errors_for("source.json", lambda d: d.update(published_at=ok)), [], ok)
        for bad in ("14:15", "不明", "下午 2:15", "10/20", 20261020, "2026-10", "2026-13-45", "２０２６-１０-２０"):
            errs = errors_for("source.json", lambda d: d.update(published_at=bad))
            self.assertTrue(any("published_at" in e and "不要自己補" in e for e in errs), bad)


class TimeClaimsTest(unittest.TestCase):
    """claims.json must say which implied claim, if any, is the deadline premise and which the implied time."""

    def errs(self, time_claims, source=None, extra=("C3",)):
        def m(c):
            for cid in extra:
                c["claims"].append(_claim(cid, "快轉傳！" if cid == "C3" else "某部長說：明年油價一定漲三成", "I"))
            if time_claims is None:
                del c["time_claims"]
            else:
                c["time_claims"] = time_claims
        return errors_for("claims.json", m, **({"source_json": source} if source else {}))

    def test_both_keys_are_required_so_that_none_is_an_explicit_answer(self):
        for bad in (None, {}, {"deadline": None}, "none", {"deadline": None, "relative": None, "other": "C3"}):
            self.assertTrue(any("time_claims" in e for e in self.errs(bad)), bad)
        self.assertEqual(self.errs({"deadline": None, "relative": None}), [])

    def test_a_marked_claim_must_be_an_implied_claim_that_exists(self):
        self.assertEqual(self.errs({"deadline": "C3", "relative": None}), [])
        for bad in ("C1", "C9", 3):  # C1 is a stated fact
            self.assertTrue(any("time_claims.deadline" in e for e in self.errs({"deadline": bad, "relative": None})), bad)

    def test_a_mark_that_is_not_a_claim_id_gets_the_plain_message(self):
        errs = self.errs({"deadline": ["C3"], "relative": None})
        self.assertTrue(any("time_claims.deadline 必須是 null" in e for e in errs), errs)
        self.assertFalse(any("TypeError" in e for e in errs), errs)

    def test_one_claim_cannot_be_both(self):
        self.assertTrue(any("同一條" in e for e in self.errs({"deadline": "C3", "relative": "C3"})))
        self.assertEqual(self.errs({"deadline": "C3", "relative": "C4"}, extra=("C3", "C4")), [])

    def test_a_time_claim_that_overlaps_another_implied_claim_is_told_to_quote_less(self):
        """Final review: the message said "merge them", which puts "when" and "is it in force" in one claim."""
        def m(c):
            c["claims"].append(_claim("C3", "某部長說：明年油價一定漲三成", "I"))  # what the sentence implies
            c["claims"].append(_claim("C4", "明年", "I"))                            # when
            c["time_claims"] = {"deadline": None, "relative": "C4"}
        errs = errors_for("claims.json", m)
        self.assertTrue(any("C4" in e and "時間命題" in e and "只抄" in e for e in errs), errs)
        self.assertFalse(any("請合併成一條" in e for e in errs), errs)

    def test_content_with_a_publication_time_has_no_time_claims(self):
        dated = {**fx.SOURCE, "published_at": "2026-10-20"}
        for marks in ({"deadline": "C3", "relative": None}, {"deadline": None, "relative": "C3"}):
            self.assertTrue(any("發布時間" in e and "一起刪掉" in e for e in self.errs(marks, source=dated)), marks)
        self.assertEqual(self.errs({"deadline": None, "relative": None}, source=dated), [])
        self.assertEqual(self.errs({"deadline": None, "relative": "C3"}, source={**fx.SOURCE, "published_at": ""}), [])


def _claim(cid, original, type_="F"):
    return {"id": cid, "original": original, "neutral": original, "type": type_, "importance": 3,
            "core": False, "legal": False, "time_place": "", "entities": [], "search_seeds": {"pro": [], "con": []}}


class ClaimSpanTest(unittest.TestCase):
    """Each claim quotes the message; stated claims never double-count the same words (2026-11-18 eval)."""

    def test_original_must_come_from_the_message(self):
        def m(c):
            c["claims"][0]["original"] = "某部長說明年油價會漲三成"
        self.assertTrue(any("C1" in e and "找不到" in e for e in errors_for("claims.json", m)))

    def test_punctuation_differences_are_ignored(self):
        # fixture C1 drops the colon that the message has
        self.assertEqual(errors_for("claims.json"), [])

    def test_fragment_of_a_stated_claim_is_rejected(self):
        def m(c):
            c["claims"].append(_claim("C3", "明年油價一定漲三成"))
        errs = errors_for("claims.json", m)
        self.assertTrue(any("C1" in e and "C3" in e and "重疊" in e for e in errs), errs)

    def test_implied_claim_may_share_a_stated_claims_words(self):
        def m(c):
            c["claims"].append(_claim("C3", "某部長說：明年油價一定漲三成", "I"))
        self.assertEqual(errors_for("claims.json", m), [])

    def test_two_implied_claims_on_the_same_words_are_rejected(self):
        def m(c):
            c["claims"].append(_claim("C3", "明年油價一定漲三成", "I"))
            c["claims"].append(_claim("C4", "油價一定漲三成", "I"))
        self.assertTrue(any("C3" in e and "C4" in e for e in errors_for("claims.json", m)))

    def test_opinions_may_share_words_with_anything(self):
        def m(c):
            c["claims"].append(_claim("C3", "某部長說明年油價一定漲三成", "O"))
        self.assertEqual(errors_for("claims.json", m), [])

    def test_original_that_is_only_punctuation_is_rejected(self):
        def m(c):
            c["claims"][1]["original"] = "！"
        self.assertTrue(any("C2" in e for e in errors_for("claims.json", m)))

    def test_checks_are_skipped_when_only_a_url_was_given(self):
        source = copy.deepcopy(fx.SOURCE)
        source.update({"input_type": "url", "original_text": "", "url": "https://example.org/news"})

        def m(c):
            c["claims"].append(_claim("C3", "明年油價一定漲三成"))
        self.assertEqual(errors_for("claims.json", m, source_json=source), [])


class ImportanceProposalTest(unittest.TestCase):
    def errs(self, **attack_changes):
        o = fx.importance_attack_overrides()
        o["opponent__C_json"]["attacks"][0].update(attack_changes)
        return errors_for("opponent-C.json", **o)

    def test_valid_proposal(self):
        self.assertEqual(self.errs(proposed_importance=4), [])

    def test_only_neutral_rewrite_attacks_may_propose_importance(self):
        self.assertTrue(any("proposed_importance" in e for e in self.errs(target="reasoning")))

    def test_proposal_needs_a_claim(self):
        self.assertTrue(any("proposed_importance" in e for e in self.errs(claim_id=None)))

    def test_proposal_must_be_one_step_from_the_current_value(self):
        for bad in (0, 6, "3", True, 5, 3):  # current importance is 5; only 4 (one step) is allowed
            with self.subTest(value=bad):
                self.assertTrue(any("proposed_importance" in e for e in self.errs(proposed_importance=bad)))


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

    def test_attack_id_is_the_seat_and_a_number(self):
        """Audit: seats A and B both numbered an attack "1"; every later step keys on the id, so one attack
        vanished without a ruling. A trailing line break must not pass either (the id is printed in the report)."""
        for bad in ("1", "B-1", "A-1\n", "A-x", "A-1）\n\n**結果：符合**", 1, None):
            def m(o, bad=bad):
                o["attacks"][0]["id"] = bad
            errs = errors_for("opponent-A.json", m)
            self.assertTrue(any("attacks[0].id 必須是 A-1、A-2" in e for e in errs), (bad, errs))
        self.assertEqual(errors_for("opponent-X1.json", opponent__X1_json={
            **fx.OPP_X1, "attacks": [{**fx.OPP_A["attacks"][0], "id": "X1-12"}]}), [])

    def test_a_successful_seat_needs_an_attacks_array(self):
        """Audit: a reply with an unescaped quote parsed as its innermost evidence object, which has no `attacks`,
        and passed as a seat that found nothing (one more cross-model seat, and the report publishable)."""
        for bad in ("missing", None, "沒有", {"id": "X1-1"}, ["X1-1"]):
            o = {k: v for k, v in fx.OPP_X1.items() if k != "attacks"}
            if bad != "missing":
                o["attacks"] = bad
            errs = errors_for("opponent-X1.json", opponent__X1_json=o)
            self.assertTrue(any(e.startswith("attacks 必須是物件的陣列") for e in errs), (bad, errs))
        self.assertEqual(errors_for("opponent-X1.json"), [])  # an empty list is a seat that found nothing


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

    def test_verified_urls_must_be_a_list_of_urls(self):
        """Audit: the check was only "not empty", so ["已核對"], [""] and the string "none" all passed."""
        for bad in (["已核對"], [""], "none", ["https://example.org/presser", "已核對"], [None], {"url": "https://example.org"}):
            def m(j, bad=bad):
                j["rulings"][1]["verified_urls"] = bad
            errs = errors_for("judgment.json", m)
            self.assertTrue(any(e.startswith("rulings[1] ") and "verified_urls" in e for e in errs), (bad, errs))

    def test_judgment_verdict_evidence_must_be_in_its_ledger(self):
        def m(j):
            j["verdicts"][0]["evidence_ids"] = ["S1", "S4"]
        self.assertTrue(any("S4" in e for e in errors_for("judgment.json", m)))


class NullListTest(unittest.TestCase):
    """Audit: a list field written as null gave "結構不對（TypeError…）" without naming the field. That line was all
    the judge's retry prompt carried, and a second null stopped the whole check."""

    def test_a_null_list_in_a_verdict_is_an_error_that_names_the_field(self):
        for name in ("proponent.json", "judgment.json"):
            for key in ("evidence_ids", "context_flags"):
                def m(d, key=key):
                    d["verdicts"][1][key] = None
                errs = errors_for(name, m)
                self.assertTrue(any(f"verdicts[1].{key} 必須是陣列" in e for e in errs), (name, key, errs))
                self.assertFalse(any("結構不對" in e for e in errs), (name, key, errs))

    def test_a_list_left_out_of_a_verdict_still_counts_as_empty(self):
        def m(d):
            del d["verdicts"][1]["evidence_ids"], d["verdicts"][1]["context_flags"]
        self.assertEqual(errors_for("judgment.json", m), [])

    def test_null_attack_evidence_counts_as_no_evidence(self):
        def m(o):
            o["attacks"][0]["evidence"] = None
        self.assertEqual(errors_for("opponent-A.json", m), [])  # a reasoning attack needs none
        errs = errors_for("opponent-B.json", m)  # a label attack does
        self.assertTrue(any("必須附證據" in e for e in errs), errs)
        self.assertFalse(any("結構不對" in e for e in errs), errs)

    def test_null_responses_are_reported_as_the_answers_that_are_missing(self):
        def m(r):
            r["responses"] = None
        errs = errors_for("rebuttal.json", m)
        self.assertTrue(any("A-1 需要剛好一則答辯" in e for e in errs), errs)
        self.assertFalse(any("結構不對" in e for e in errs), errs)


def judgment_missing_url():
    """B-1 carries evidence and is upheld, but the judge listed no URL it checked."""
    j = copy.deepcopy(fx.JUDGMENT)
    j["rulings"][1]["verified_urls"] = []
    return j


class UnverifiedRulingFallbackTest(unittest.TestCase):
    """Regression (round 2, case-011): the judge twice left out the URLs it had checked for one upheld
    attack, and the whole check stopped at its most expensive step."""

    def fallback(self, judgment):
        run = make_run(fx.run_files(judgment_json=judgment))
        errors = validate.validate_file(run, "judgment.json", known_tactics=fx.TACTIC_LIB)
        fixed = validate.fallback(judgment, run, "judgment.json", fx.TACTIC_LIB, errors)
        if fixed is not None:
            (run / "judgment.json").write_text(json.dumps(fixed, ensure_ascii=False), encoding="utf-8")
        return fixed, validate.validate_file(run, "judgment.json", known_tactics=fx.TACTIC_LIB)

    def test_only_missing_urls_are_accepted_as_unverified_rulings(self):
        fixed, left = self.fallback(judgment_missing_url())
        self.assertEqual(fixed["rulings_unverified"], ["B-1"])
        self.assertTrue(fixed["rulings"][1]["upheld"])
        self.assertEqual(left, [])

    def test_a_list_that_holds_no_urls_takes_the_same_way_out(self):
        j = copy.deepcopy(fx.JUDGMENT)
        j["rulings"][1]["verified_urls"] = ["已核對"]
        fixed, left = self.fallback(j)
        self.assertEqual(fixed["rulings_unverified"], ["B-1"])
        self.assertEqual(left, [])

    def test_no_fallback_when_anything_else_is_wrong(self):
        j = judgment_missing_url()
        j["rulings"].pop(0)
        fixed, _ = self.fallback(j)
        self.assertIsNone(fixed)

    def test_missing_urls_and_bad_tag_checks_are_both_handled(self):
        j = judgment_missing_url()
        j["tactic_checks"] = []
        fixed, left = self.fallback(j)
        self.assertEqual(fixed["rulings_unverified"], ["B-1"])
        self.assertTrue(fixed["tactic_checks_set_aside"])
        self.assertEqual(left, [])

    def test_the_list_must_name_upheld_attacks_that_carry_evidence(self):
        """Skeptic/red-team: a malformed list passed validation and crashed finalize."""
        for bad in ([{"attack_id": "B-1"}], ["A-1"], "B-1", [3]):
            j = copy.deepcopy(fx.JUDGMENT)
            j["rulings_unverified"] = bad
            self.assertTrue(any("rulings_unverified" in e for e in errors_for("judgment.json", judgment_json=j)), bad)

    def test_the_list_only_excuses_the_rulings_it_names(self):
        j = judgment_missing_url()
        j["rulings_unverified"] = ["A-1"]
        self.assertTrue(any("verified_urls" in e for e in errors_for("judgment.json", judgment_json=j)))


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


RECHECKED = fx.PROPONENT["prior_factchecks_rechecked"][0]


class FieldsTheReportReadsTest(unittest.TestCase):
    """Audit: render indexes these fields directly. Each shape below passed validation and then stopped the last
    step with a KeyError, TypeError or AttributeError, after every model call had been paid for."""

    def trace(self, where=None, **change):
        def m(t):
            (t["publisher"] if where == "publisher" else t).update(change)
        return errors_for("trace.json", m)

    def proponent(self, rechecked):
        def m(p):
            p["prior_factchecks_rechecked"] = rechecked
        return errors_for("proponent.json", m)

    def named(self, errs, field):
        self.assertTrue(any(e.startswith(field) for e in errs), (field, errs))
        self.assertFalse(any("結構不對" in e for e in errs), errs)

    def test_a_spread_signal_needs_its_signal(self):
        self.named(self.trace(spread_signals=[{"evidence_url": "https://example.org/a", "excerpt": "同文案 30 則"}]),
                   "spread_signals[0]")

    def test_an_attribution_needs_its_statement(self):
        self.named(self.trace(attribution=[{"report_url": "https://example.org/r", "report_org": "某研究機構"}]),
                   "attribution[0]")

    def test_a_wording_issue_needs_the_quote_and_the_issue(self):
        self.named(self.trace("publisher", wording_issues=[{"quote": "無恥"}]), "publisher.wording_issues[0]")
        self.named(self.trace("publisher", wording_issues=[{"issue": "情緒字眼"}]), "publisher.wording_issues[0]")

    def test_lists_of_objects_must_be_lists_of_objects(self):
        for where, key in ((None, "variants"), (None, "spread_signals"), (None, "attribution"),
                           (None, "prior_factchecks"), ("publisher", "wording_issues"), ("publisher", "flagged")):
            field = f"{where}.{key}" if where else key
            for bad in ("沒有", ["一個字串"], {"url": "https://example.org/x"}):
                self.named(self.trace(where, **{key: bad}), field + " 必須是物件的陣列")

    def test_first_seen_is_an_object_or_null(self):
        for bad in ("2026-11-10 LINE", ["2026-11-10"]):
            self.named(self.trace(first_seen=bad), "first_seen")
        self.assertEqual(self.trace(first_seen=None), [])

    def test_limits_is_a_list(self):
        self.named(self.trace(limits="查不到最早出處"), "limits 必須是陣列")

    def test_byline_is_text(self):
        self.named(self.trace("publisher", byline=["王小明"]), "publisher.byline")
        self.assertEqual(self.trace("publisher", byline=None), [])

    def test_null_in_place_of_a_list_reads_as_empty(self):
        """Nothing is missing, so the tracer is not sent back for it; render reads these the same way."""
        self.assertEqual(self.trace(variants=None, spread_signals=None, attribution=None, prior_factchecks=None,
                                    limits=None), [])
        self.assertEqual(self.trace("publisher", wording_issues=None, flagged=None), [])
        self.assertEqual(self.proponent(None), [])
        self.assertEqual(self.proponent([{**RECHECKED, "claim_ids": None}]), [])

    def test_a_rechecked_fact_check_needs_its_org_and_url(self):
        for key in ("org", "url"):
            self.named(self.proponent([{k: v for k, v in RECHECKED.items() if k != key}]),
                       "prior_factchecks_rechecked[0]")
        self.named(self.proponent([{**RECHECKED, "url": "事實查核中心的報告"}]), "prior_factchecks_rechecked[0]")

    def test_rechecked_fact_checks_are_a_list_of_objects(self):
        for bad in (["台灣事實查核中心"], dict(RECHECKED), "沒有"):
            self.named(self.proponent(bad), "prior_factchecks_rechecked 必須是物件的陣列")

    def test_a_rechecked_fact_check_lists_claim_ids_as_text(self):
        for bad in ("C1", [["C1"]], [1]):
            self.named(self.proponent([{**RECHECKED, "claim_ids": bad}]), "prior_factchecks_rechecked[0].claim_ids")


def _tag(tid="TW-T16", features=("a",), quote="快轉傳！", **extra):
    return {"tactic_id": tid, "features": list(features), "quote": quote, "explanation": "說明", **extra}


EVIDENCE = [{"url": "https://example.org/factcheck", "excerpt": "這段話在 2019 年就流傳過"}]


class TagStandardTest(unittest.TestCase):
    """2026-11-18 symmetry probe: the same message got different tags per party. Every tag must rest on
    at least one visible or verified feature from the shared library; clues alone never count."""

    def errs(self, *tags, mutate=None):
        def m(t):
            t["tactics"] = list(tags)
            if mutate:
                mutate(t)
        return errors_for("trace.json", m)

    def test_fixture_tag_is_valid(self):
        self.assertEqual(errors_for("trace.json"), [])

    def test_tag_needs_features(self):
        self.assertTrue(any("features" in e for e in self.errs(_tag(features=()))))

    def test_unknown_feature_id(self):
        self.assertTrue(any("z" in e for e in self.errs(_tag(features=("z",)))))

    def test_clue_alone_cannot_support_a_tag(self):
        self.assertTrue(any("線索" in e for e in self.errs(_tag("TW-T01", features=("a",)))))

    def test_visible_feature_needs_a_quote_from_the_message(self):
        self.assertTrue(any("原文" in e for e in self.errs(_tag(quote="這句不在訊息裡"))))
        self.assertTrue(any("quote" in e for e in self.errs(_tag(quote=""))))

    def test_quote_keeps_the_messages_punctuation(self):
        # red-team: with letters-only matching, an invented "！！！" could prop up 大量驚嘆號
        self.assertTrue(any("原文" in e for e in self.errs(_tag(quote="快轉傳！！！"))))

    def test_quote_may_join_passages_with_an_ellipsis(self):
        self.assertEqual(self.errs(_tag(quote="某部長說：……快轉傳！")), [])
        self.assertEqual(self.errs(_tag(quote="某部長說：⋯⋯快轉傳！")), [])

    def test_quote_of_nothing_but_an_ellipsis_is_rejected(self):
        self.assertTrue(any("quote" in e for e in self.errs(_tag(quote="……"))))

    def test_verified_feature_needs_evidence_and_no_quote(self):
        self.assertTrue(any("evidence" in e for e in self.errs(_tag("TW-T01", features=("c",), quote=None))))
        self.assertEqual(self.errs(_tag("TW-T01", features=("c",), quote=None, evidence=EVIDENCE)), [])

    def test_same_tactic_twice_is_rejected(self):
        errs = self.errs(_tag(), _tag(quote="某部長說："))
        self.assertTrue(any("TW-T16" in e and "兩次" in e for e in errs))

    def test_attribution_tactic_needs_a_formal_report(self):
        tag = _tag("TW-T29", features=("a",), quote=None, evidence=EVIDENCE)
        self.assertTrue(any("attribution" in e for e in self.errs(tag)))

        def with_report(t):
            t["attribution"] = [{"statement": "報告點名此案", "report_url": "https://example.org/r", "report_org": "某研究院"}]
        self.assertEqual(self.errs(tag, mutate=with_report), [])

    def test_tactic_errors_name_the_entry(self):
        # the set-aside fallback recognises tactic errors by this prefix
        self.assertTrue(all(e.startswith("tactics") for e in self.errs(_tag("TW-T01", features=("a",)))))


class TacticAttackTest(unittest.TestCase):
    def test_tactic_attack_must_name_a_tagged_tactic(self):
        for bad in (None, "TW-T25"):
            with self.subTest(tactic_id=bad):
                o = fx.tactic_attack_overrides()
                o["opponent__C_json"]["attacks"][0]["tactic_id"] = bad
                self.assertTrue(any("tactic_id" in e for e in errors_for("opponent-C.json", **o)))

    def test_valid_tactic_attack(self):
        self.assertEqual(errors_for("opponent-C.json", **fx.tactic_attack_overrides()), [])


class TacticCheckTest(unittest.TestCase):
    """The judge checks every tag, attacked or not (round 1: who happened to be attacked decided the tags)."""

    def errs(self, mutate=None, trace=None, **kw):
        o = fx.tactic_attack_overrides(**kw)
        if trace is not None:
            o["trace_json"] = trace
        return errors_for("judgment.json", mutate, **o)

    def test_valid_checks(self):
        self.assertEqual(errors_for("judgment.json"), [])
        self.assertEqual(self.errs(), [])

    def test_every_tag_needs_exactly_one_check(self):
        def missing(j):
            j["tactic_checks"] = []

        def twice(j):
            j["tactic_checks"].append(copy.deepcopy(j["tactic_checks"][0]))

        def extra(j):
            j["tactic_checks"].append({"tactic_id": "TW-T25", "features": {"a": False}, "keep": False, "reason": "x"})
        for m in (missing, twice, extra):
            with self.subTest(case=m.__name__):
                self.assertTrue(any("tactic_checks" in e for e in errors_for("judgment.json", m)))

    def test_check_covers_exactly_the_tags_non_clue_features(self):
        for features in ({}, {"b": True}, {"a": True, "c": True}, {"a": "yes"}):
            with self.subTest(features=features):
                def m(j, f=features):
                    j["tactic_checks"][0]["features"] = f
                self.assertTrue(any("features" in e for e in errors_for("judgment.json", m)))

    def test_keep_follows_the_features(self):
        def contradict(j):
            j["tactic_checks"][0]["keep"] = False
        self.assertTrue(any("keep" in e for e in errors_for("judgment.json", contradict)))

    def test_upheld_attack_on_a_tag_means_the_tag_goes(self):
        # red-team: an upheld "T15 does not match" next to a kept T15 contradicted the report
        self.assertTrue(any("C-1" in e for e in self.errs(upheld=True, keep=True)))

    def test_rejected_attack_leaves_the_tag_to_the_check(self):
        self.assertEqual(self.errs(upheld=False, keep=True), [])

    def test_kept_tag_resting_on_verified_features_needs_opened_urls(self):
        trace = copy.deepcopy(fx.TRACE)
        trace["tactics"] = [_tag("TW-T01", features=("c",), quote=None, evidence=EVIDENCE)]

        def check(urls):
            def m(j):
                j["tactic_checks"] = [{"tactic_id": "TW-T01", "features": {"c": True}, "keep": True,
                                       "reason": "查到 2019 年的版本", **({"verified_urls": urls} if urls is not None else {})}]
            return m
        self.assertTrue(any("verified_urls" in e for e in errors_for("judgment.json", check(None), trace_json=trace)))
        self.assertTrue(any("verified_urls" in e for e in errors_for("judgment.json", check(["https://other.org"]), trace_json=trace)))
        self.assertEqual(errors_for("judgment.json", check(["https://example.org/factcheck"]), trace_json=trace), [])

    def test_set_aside_checks_are_not_validated(self):
        def m(j):
            j.pop("tactic_checks")
            j["tactic_checks_set_aside"] = ["tactic_checks：缺少 TW-T16"]
        self.assertEqual(errors_for("judgment.json", m), [])

    def test_no_tags_needs_no_checks(self):
        trace = copy.deepcopy(fx.TRACE)
        trace["tactics"] = []

        def m(j):
            j.pop("tactic_checks")
        self.assertEqual(errors_for("judgment.json", m, trace_json=trace), [])


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

    def test_every_claim_the_seat_must_review_needs_exactly_one_review(self):
        """Audit: {"seat": "B", "reviews": []} passed, was never retried, and finalize then read the missing review
        as a failed one: the judge's 誤導 became 無法證實 and the result 無法判定."""
        def none(r):
            r["reviews"] = []

        def null(r):
            r["reviews"] = None

        def twice(r):
            r["reviews"].append(dict(r["reviews"][0], **{"pass": False, "label_ok": False}))
        for m in (none, null, twice):
            errs = errors_for("review-B.json", m)
            self.assertTrue(any("C1 需要剛好一筆覆核" in e for e in errs), (m.__name__, errs))

    def test_null_reviews_are_an_error_even_for_a_seat_with_nothing_to_review(self):
        """finalize iterates `reviews` of every review file, so null must never get past this check."""
        for bad in (None, ["C1"], {"claim_id": "C1"}):
            errs = errors_for("review-A.json", review__A_json={"seat": "A", "reviews": bad})
            self.assertTrue(any(e.startswith("reviews 必須是物件的陣列") for e in errs), (bad, errs))

    def test_the_list_covers_judge_only_changes_for_every_seat(self):
        o = fx.judge_only_overrides()
        o["review__A_json"] = {"seat": "A", "reviews": []}
        self.assertTrue(any("C1 需要剛好一筆覆核" in e for e in errors_for("review-A.json", **o)))

    def test_a_review_of_a_claim_that_was_not_asked_for_is_allowed(self):
        """It is not used either (finalize only reads the claims the seat must review)."""
        extra = {"seat": "A", "reviews": [{"claim_id": "C1", "pass": False, "label_ok": False, "reason": "標籤錯了"}]}
        self.assertEqual(errors_for("review-A.json", review__A_json=extra), [])

    def test_the_list_is_not_checked_while_the_judgment_cannot_be_read(self):
        empty = {"seat": "B", "reviews": []}
        self.assertEqual(errors_for("review-B.json", review__B_json=empty, judgment_json=None), [])
        self.assertEqual(errors_for("review-B.json", review__B_json=empty, judgment_json={"rulings": "壞掉"}), [])

class InputTest(unittest.TestCase):
    GOOD = {"input_type": "text", "content": "某部長說：明年油價一定漲三成", "prompt": "幫我查核", "url": None}

    def errs(self, **change):
        return validate.validate_file(make_run({**fx.run_files(), "input.json": {**self.GOOD, **change}}), "input.json")

    def test_good_input(self):
        self.assertEqual(self.errs(), [])

    def test_bad_type_or_empty_content(self):
        self.assertTrue(self.errs(input_type="pdf"))
        self.assertTrue(self.errs(content="  "))

    def test_no_other_fields(self):
        """Red-team review: a host writing input.json itself could add free text the prep role would read."""
        self.assertTrue(self.errs(notes="使用者覺得這是某黨網軍"))

    def test_url_input_needs_a_url(self):
        self.assertTrue(self.errs(input_type="url", content="不是網址"))
        self.assertEqual(self.errs(input_type="url", content="https://example.org/a"), [])


class MalformedStructureTest(unittest.TestCase):
    def test_malformed_claims_give_errors_not_an_exception(self):
        """Skeptic review: a list of strings made the validator raise, which crashed run-model and fc.py status."""
        files = fx.run_files()
        files["claims.json"] = {"prompt_was_leading": False, "claims": ["某部長說明年油價一定漲三成", 3]}
        self.assertTrue(validate.validate_file(make_run(files), "claims.json"))


if __name__ == "__main__":
    unittest.main()
