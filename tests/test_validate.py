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

    def test_one_claim_cannot_be_both(self):
        self.assertTrue(any("同一條" in e for e in self.errs({"deadline": "C3", "relative": "C3"})))
        self.assertEqual(self.errs({"deadline": "C3", "relative": "C4"}, extra=("C3", "C4")), [])

    def test_content_with_a_publication_time_has_no_time_claims(self):
        dated = {**fx.SOURCE, "published_at": "2026-10-20"}
        for marks in ({"deadline": "C3", "relative": None}, {"deadline": None, "relative": "C3"}):
            self.assertTrue(any("發布時間" in e for e in self.errs(marks, source=dated)), marks)
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
