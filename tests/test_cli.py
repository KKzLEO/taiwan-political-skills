import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests import fixtures as fx
from tests.helpers import SKILL, make_run

FC = SKILL / "scripts" / "fc.py"


def fc(*args, cwd=None):
    return subprocess.run([sys.executable, str(FC), *map(str, args)], capture_output=True, text=True, cwd=cwd)


class PipelineCliTest(unittest.TestCase):
    def test_finalize_score_render_on_fixture_run(self):
        run = make_run(fx.run_files())
        for step in ("finalize", "score", "render"):
            p = fc(step, "--run", run)
            self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads((run / "score.json").read_text())["result"], "不符")
        self.assertIn("結果：不符", (run / "report.md").read_text())

    def test_finalize_refuses_an_invalid_proponent_file(self):
        """Skeptic re-review: finalize compares the judge with the proponent (judge-only changes), so it checks both."""
        files = fx.run_files()
        files["proponent.json"]["verdicts"].append(dict(files["proponent.json"]["verdicts"][0]))
        run = make_run(files)
        p = fc("finalize", "--run", run)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("proponent.json", p.stderr)
        self.assertFalse((run / "verdicts.json").exists())

    def test_finalize_refuses_a_run_with_a_step_missing_or_out_of_date(self):
        """Audit: with no rebuttal.json, or an attack the rebuttal never answered, finalize, score and render all
        passed and the report was publishable."""
        o = fx.tactic_attack_overrides()
        o["rebuttal_json"] = copy.deepcopy(fx.REBUTTAL)
        broken_review = {"seat": "B", "reviews": ["C1"]}
        for what, files, named in (("no rebuttal", fx.run_files(rebuttal_json=None), "rebuttal.json"),
                                   ("late attack", fx.run_files(**o), "rebuttal.json"),
                                   ("broken review", fx.run_files(review__B_json=broken_review), "review-B.json")):
            with self.subTest(what):
                run = make_run(files)
                p = fc("finalize", "--run", run)
                self.assertNotEqual(p.returncode, 0)
                self.assertIn(named, p.stderr)
                self.assertNotIn("Traceback", p.stderr)
                self.assertFalse((run / "verdicts.json").exists())

    def test_validate_reports_errors_with_exit_1(self):
        files = fx.run_files()
        files["proponent.json"]["ledger"][0]["excerpt"] = ""
        run = make_run(files)
        p = fc("validate", "--run", run, "proponent.json")
        self.assertEqual(p.returncode, 1)
        self.assertIn("摘錄", p.stdout)

    def test_validate_ok(self):
        run = make_run(fx.run_files())
        p = fc("validate", "--run", run, "claims.json", "proponent.json")
        self.assertEqual(p.returncode, 0, p.stdout)

    def test_set_aside_moves_only_bad_tags_out(self):
        files = fx.run_files()
        files["trace.json"]["tactics"].append({"tactic_id": "TW-T01", "features": ["a"], "quote": "快轉傳！"})
        run = make_run(files)
        p = fc("set-aside-tactics", "--run", run, "trace.json")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        trace = json.loads((run / "trace.json").read_text())
        self.assertEqual([t["tactic_id"] for t in trace["tactics"]], ["TW-T16"])
        self.assertEqual(trace["set_aside_tactics"][0]["entry"]["tactic_id"], "TW-T01")

    def test_set_aside_says_what_is_kept_for_each_file(self):
        """The trace keeps the tags it moves out; the judge's rejected checks are dropped, only the errors stay."""
        files = fx.run_files()
        files["trace.json"]["tactics"].append({"tactic_id": "TW-T01", "features": ["a"], "quote": "快轉傳！"})
        files["judgment.json"]["tactic_checks"][0]["features"] = {"z": True}  # not a feature of TW-T16
        run = make_run(files)
        self.assertIn("原內容保留在檔案裡", fc("set-aside-tactics", "--run", run, "trace.json").stdout)
        p = fc("set-aside-tactics", "--run", run, "judgment.json")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("裁判的逐項檢查不保留", p.stdout)
        self.assertNotIn("原內容保留在檔案裡", p.stdout)

    def test_set_aside_refuses_when_more_than_tags_is_wrong(self):
        files = fx.run_files()
        files["trace.json"]["publisher"]["kind"] = "網軍"
        run = make_run(files)
        p = fc("set-aside-tactics", "--run", run, "trace.json")
        self.assertEqual(p.returncode, 1)
        self.assertEqual(json.loads((run / "trace.json").read_text())["publisher"]["kind"], "網軍")

    def test_score_refuses_invalid_verdicts(self):
        run = make_run(fx.run_files())
        fc("finalize", "--run", run)
        v = json.loads((run / "verdicts.json").read_text())
        v["claims"][0]["label"] = "probably"
        (run / "verdicts.json").write_text(json.dumps(v))
        p = fc("score", "--run", run)
        self.assertEqual(p.returncode, 2)

    def test_finalize_says_which_seats_left_no_review(self):
        """Audit: with review-B.json missing, finalize turned the judge's 誤導 into 無法證實 and printed nothing."""
        run = make_run(fx.run_files(review__B_json=None))
        p = fc("finalize", "--run", run)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout.strip(), str(run.resolve() / "verdicts.json"))  # stdout stays the path alone
        self.assertIn("席位 B 沒有覆核檔", p.stderr)
        self.assertIn("C1", p.stderr)
        self.assertIn("無法證實", p.stderr)

    def test_finalize_names_every_seat_that_left_no_review(self):
        run = make_run(fx.run_files(**fx.judge_only_overrides(),  # every seat that ran must review C1
                                    review__A_json={"seat": "A", "reviews": [{"claim_id": "C1", "pass": True, "reason": "合理"}]}))
        p = fc("finalize", "--run", run)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("席位 B、C、X1 沒有覆核檔", p.stderr)

    def test_finalize_is_quiet_when_every_review_is_there(self):
        p = fc("finalize", "--run", make_run(fx.run_files()))
        self.assertEqual((p.returncode, p.stderr), (0, ""))

    def test_score_prints_no_credibility_when_the_report_shows_none(self):
        """Audit: for 無法判定 the report says 可信度 —, but this line said 35, and the host reads this line."""
        run = make_run(fx.run_files(review__B_json=None))  # C1 becomes 無法證實, so the result is 無法判定
        fc("finalize", "--run", run)
        p = fc("score", "--run", run)
        self.assertEqual(p.returncode, 0, p.stderr)
        printed = json.loads(p.stdout)
        self.assertEqual((printed["result"], printed["credibility"]), ("無法判定", None))
        self.assertEqual(json.loads((run / "score.json").read_text())["credibility"]["score"], 35)  # the file is unchanged

    def test_score_prints_the_credibility_the_report_shows(self):
        run = make_run(fx.run_files())
        fc("finalize", "--run", run)
        self.assertEqual(json.loads(fc("score", "--run", run).stdout)["credibility"], 25)


FAKE_CLAUDE = """import json, os, sys
sys.stdin.read()
with open(os.environ["FAKE_LOG"], "a", encoding="utf-8") as fh:
    fh.write("call\\n")
print(json.dumps({"result": os.environ.get("FAKE_REPLY", ""), "is_error": False}))
"""


def with_fake_claude(files, seats=("A", "B", "C", "X1")):
    """A run folder whose host engine is a fake claude CLI that logs each call (no model is called)."""
    run = make_run(files)
    (run / "fake_claude.py").write_text(FAKE_CLAUDE, encoding="utf-8")
    lenses = {"A": "evidence", "B": "counter", "C": "stance"}
    models = dict(fx.MODELS, engines=fx.MODELS["engines"] + [
        {"engine": "claude", "vendor": "anthropic", "available": True, "cross_model": False, "can_search": True,
         "same_tier": True, "model": None, "probe": "skipped", "isolation": "unknown",
         "cmd": [sys.executable, str(run / "fake_claude.py")]}],
        seats=[{"seat": s, "engine": "codex" if s.startswith("X") else "claude", "kind": "external" if s.startswith("X")
                else "internal", "lens": lenses.get(s, "external"), "model": None} for s in seats])
    (run / "models.json").write_text(json.dumps(models), encoding="utf-8")
    return run


def fc_env(run, *args, reply=""):
    env = {**os.environ, "FAKE_LOG": str(run / "calls.log"), "FAKE_REPLY": reply}
    (run / "calls.log").unlink(missing_ok=True)
    p = subprocess.run([sys.executable, str(FC), *map(str, args)], capture_output=True, text=True, env=env)
    calls = (run / "calls.log").read_text().count("call") if (run / "calls.log").exists() else 0
    return p, calls


class RunModelCliTest(unittest.TestCase):
    def test_a_finished_step_is_not_run_again(self):
        """Audit: rerunning a finished judge called the model, and a worse answer deleted the valid judgment."""
        run = with_fake_claude(fx.run_files())
        before = (run / "judgment.json").read_text()
        p, calls = fc_env(run, "run-model", "--run", run, "--role", "judge")
        self.assertEqual((p.returncode, calls), (0, 0), p.stderr)
        self.assertEqual(p.stdout.strip(), str(run.resolve() / "judgment.json"))
        self.assertIn("已經完成", p.stderr)
        self.assertIn("--force", p.stderr)
        self.assertEqual((run / "judgment.json").read_text(), before)

    def test_force_runs_a_finished_step_again(self):
        run = with_fake_claude(fx.run_files())
        p, calls = fc_env(run, "run-model", "--run", run, "--role", "judge", "--force",
                          reply=json.dumps(fx.JUDGMENT, ensure_ascii=False))
        self.assertEqual((p.returncode, calls), (0, 1), p.stderr)

    def test_a_redone_judge_leaves_no_review_of_the_old_judgment(self):
        """Final review: after the judge was redone the old review file still validated, status called it done,
        and the report said the new verdict had passed review and could be published."""
        run = with_fake_claude(fx.run_files())
        for step in ("finalize", "score", "render"):
            self.assertEqual(fc(step, "--run", run).returncode, 0)
        redone = copy.deepcopy(fx.JUDGMENT)
        redone["verdicts"][0]["label"] = "false"  # was: misleading, reviewed by seat B
        p, calls = fc_env(run, "run-model", "--run", run, "--role", "judge", "--force",
                          reply=json.dumps(redone, ensure_ascii=False))
        self.assertEqual((p.returncode, calls), (0, 1), p.stderr)
        for gone in ("review-B.json", "verdicts.json", "score.json", "report.md"):
            self.assertFalse((run / gone).exists(), gone)
        for kept in ("opponent-B.json", "rebuttal.json", "proponent.json"):
            self.assertTrue((run / kept).exists(), kept)
        self.assertIn("缺少（要覆核 C1）", fc("status", "--run", run).stdout)
        p = fc("finalize", "--run", run)
        self.assertIn("席位 B 沒有覆核檔", p.stderr)
        self.assertIn('"publishable": false', fc("score", "--run", run).stdout)

    def test_a_rerun_seat_leaves_nothing_built_on_the_old_seat(self):
        run = with_fake_claude(fx.run_files())
        failed = {**fx.OPP_C, "status": "failed", "error": "額度用完", "attacks": []}
        (run / "opponent-C.json").write_text(json.dumps(failed, ensure_ascii=False))
        p, calls = fc_env(run, "run-model", "--run", run, "--role", "opponent", "--seat", "C",
                          reply=json.dumps({"searches_run": 2, "attacks": []}, ensure_ascii=False))
        self.assertEqual((p.returncode, calls), (0, 1), p.stderr)
        for gone in ("rebuttal.json", "judgment.json", "review-B.json"):
            self.assertFalse((run / gone).exists(), gone)
        for kept in ("opponent-A.json", "opponent-B.json", "opponent-X1.json", "proponent.json", "trace.json"):
            self.assertTrue((run / kept).exists(), kept)

    def test_a_seat_that_fails_again_leaves_the_finished_report_alone(self):
        """Delta review: the seat had failed, the report was made without it, the rerun failed too (quota still
        out), and everything after the seat was deleted although nothing later steps read had changed."""
        files = fx.run_files()
        files["opponent-C.json"] = {**fx.OPP_C, "status": "failed", "error": "額度用完", "attacks": []}
        run = with_fake_claude(files)
        for step in ("finalize", "score", "render"):
            self.assertEqual(fc(step, "--run", run).returncode, 0)
        p, calls = fc_env(run, "run-model", "--run", run, "--role", "opponent", "--seat", "C", reply="不是 JSON")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads((run / "opponent-C.json").read_text())["status"], "failed")
        for kept in ("rebuttal.json", "judgment.json", "review-B.json", "verdicts.json", "score.json", "report.md"):
            self.assertTrue((run / kept).exists(), kept)
        status = fc("status", "--run", run).stdout
        self.assertNotIn("rebuttal.json 缺少", status)
        # and the later steps still count as done: the seat's file must not look newer than what was built on it
        p, calls = fc_env(run, "run-model", "--run", run, "--role", "rebuttal")
        self.assertEqual(calls, 0, p.stderr)

    def test_a_seat_that_worked_and_now_fails_drops_what_was_built_on_it(self):
        run = with_fake_claude(fx.run_files())
        p, calls = fc_env(run, "run-model", "--run", run, "--role", "opponent", "--seat", "C", "--force", reply="不是 JSON")
        self.assertEqual(json.loads((run / "opponent-C.json").read_text())["status"], "failed")
        for gone in ("rebuttal.json", "judgment.json", "review-B.json"):
            self.assertFalse((run / gone).exists(), gone)

    def test_a_redone_split_leaves_nothing_built_on_the_old_claims(self):
        files = fx.run_files()
        files["input.json"] = {"input_type": "text", "content": fx.SOURCE["original_text"], "prompt": "幫我查核", "url": None}
        run = with_fake_claude(files)
        reply = json.dumps({"source": fx.SOURCE, "claims": fx.CLAIMS}, ensure_ascii=False)
        p, calls = fc_env(run, "run-model", "--run", run, "--role", "prep", "--force", reply=reply)
        self.assertEqual((p.returncode, calls), (0, 1), p.stderr)
        for gone in ("trace.json", "proponent.json", "opponent-A.json", "rebuttal.json", "judgment.json", "review-B.json"):
            self.assertFalse((run / gone).exists(), gone)
        self.assertTrue((run / "claims.json").exists())

    def test_settling_again_leaves_no_score_or_report_of_the_old_verdicts(self):
        run = make_run(fx.run_files())
        for step in ("finalize", "score", "render"):
            self.assertEqual(fc(step, "--run", run).returncode, 0)
        fc("finalize", "--run", run)
        self.assertFalse((run / "score.json").exists())
        self.assertFalse((run / "report.md").exists())
        fc("score", "--run", run)
        fc("render", "--run", run)
        fc("score", "--run", run)
        self.assertFalse((run / "report.md").exists())

    def test_a_missing_review_is_still_run(self):
        run = with_fake_claude(fx.run_files(review__B_json=None))
        p, calls = fc_env(run, "run-model", "--run", run, "--role", "review", "--seat", "B",
                          reply=json.dumps(fx.REVIEW_B, ensure_ascii=False))
        self.assertEqual((p.returncode, calls), (0, 1), p.stderr)
        self.assertTrue((run / "review-B.json").exists())


def no_review_needed():
    """The judge rejects B-1 and keeps the proponent's labels, so no seat has anything to review."""
    judgment = copy.deepcopy(fx.JUDGMENT)
    judgment["rulings"][1]["upheld"] = False
    judgment["verdicts"][0]["label"] = "false"
    return {"judgment_json": judgment, "review__B_json": None}


class StatusCliTest(unittest.TestCase):
    """Audit: status listed failed seats as 完成 and left out seats with no file, so resuming from it skipped them."""

    def status(self, run):
        p = subprocess.run([sys.executable, str(FC), "status", "--run", str(run)], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout

    def test_every_seat_is_listed_done_failed_or_missing(self):
        failed = {"seat": "A", "engine": "claude", "lens": "evidence", "status": "failed", "error": "額度用完", "attacks": []}
        out = self.status(with_fake_claude(fx.run_files(opponent__A_json=failed, opponent__C_json=None)))
        self.assertRegex(out, r"opponent-A\.json\s+失敗（可以重跑這一席）")
        self.assertRegex(out, r"opponent-B\.json\s+完成")
        self.assertRegex(out, r"opponent-C\.json\s+缺少")
        self.assertRegex(out, r"opponent-X1\.json\s+完成")

    def test_reviews_are_listed_by_the_seats_that_must_review(self):
        out = self.status(with_fake_claude(fx.run_files(review__B_json=None)))
        self.assertRegex(out, r"review-B\.json\s+缺少（要覆核 C1）")
        self.assertRegex(self.status(with_fake_claude(fx.run_files())), r"review-B\.json\s+完成")

    def test_no_review_needed_is_not_shown_as_missing(self):
        out = self.status(with_fake_claude(fx.run_files(**no_review_needed())))
        self.assertRegex(out, r"review-\*\.json\s+不需要")
        self.assertNotIn("缺少（要覆核", out)


class SeatCliTest(unittest.TestCase):
    def test_a_failed_seat_says_so_on_stderr(self):
        """Audit: a seat that failed exited 0 with only the file path, so nobody saw it fail."""
        run = with_fake_claude(fx.run_files(opponent__A_json=None, rebuttal_json=None, judgment_json=None,
                                            review__B_json=None))
        p, calls = fc_env(run, "run-model", "--run", run, "--role", "opponent", "--seat", "A", reply="not json")
        self.assertEqual((p.returncode, calls), (0, 2), p.stderr)
        self.assertIn("反方 A 失敗", p.stderr)
        self.assertEqual(json.loads((run / "opponent-A.json").read_text())["status"], "failed")

    def test_a_seat_that_is_not_in_models_json_is_refused(self):
        """Audit: --seat D was a KeyError traceback, and --seat X9 ran as an extra seat on the host model."""
        run = with_fake_claude(fx.run_files(opponent__X1_json=None))
        for args in (("run-model", "--run", run, "--role", "opponent", "--seat", "X9"),
                     ("run-model", "--run", run, "--role", "review", "--seat", "不需要派覆核"),
                     ("prompt", "--run", run, "--role", "opponent", "--seat", "D")):
            with self.subTest(args[0] + " " + args[-1]):
                p, calls = fc_env(run, *args)
                self.assertNotEqual(p.returncode, 0)
                self.assertEqual(calls, 0)
                self.assertNotIn("Traceback", p.stderr)
                self.assertIn("A、B、C、X1", p.stderr)
        self.assertFalse((run / "opponent-X9.json").exists())

    def test_fc_timeout_that_is_not_a_number_is_one_clear_line(self):
        run = with_fake_claude(fx.run_files(trace_json=None, proponent_json=None))
        p = subprocess.run([sys.executable, str(FC), "run-model", "--run", str(run), "--role", "tracer"],
                           capture_output=True, text=True, env={**os.environ, "FC_TIMEOUT": "60m",
                                                                "FAKE_LOG": str(run / "calls.log")})
        self.assertNotEqual(p.returncode, 0)
        self.assertNotIn("Traceback", p.stderr)
        self.assertIn("FC_TIMEOUT", p.stderr)
        self.assertFalse((run / "calls.log").exists())

    def test_reviewers_prints_nothing_on_stdout_when_no_seat_reviews(self):
        """Audit: the loop over `fc.py reviewers | cut -f1` ran once with the seat 不需要派覆核."""
        p = fc("reviewers", "--run", make_run(fx.run_files(**no_review_needed())))
        self.assertEqual((p.returncode, p.stdout), (0, ""))
        self.assertIn("不需要派覆核", p.stderr)
        self.assertEqual(fc("reviewers", "--run", make_run(fx.run_files())).stdout, "B\tC1\n")


class MissingFileCliTest(unittest.TestCase):
    """Audit: a missing or broken file gave a 28-line traceback instead of one line saying which file."""

    def one_line_error(self, p, name):
        self.assertNotEqual(p.returncode, 0)
        self.assertNotIn("Traceback", p.stderr)
        self.assertEqual(len(p.stderr.strip().splitlines()), 1, p.stderr)
        self.assertTrue(p.stderr.startswith("錯誤："), p.stderr)
        self.assertIn(name, p.stderr)

    def test_reviewers_without_a_judgment(self):
        run = make_run(fx.run_files(judgment_json=None, review__B_json=None))
        self.one_line_error(fc("reviewers", "--run", run), "judgment.json")

    def test_render_without_a_score(self):
        run = make_run(fx.run_files())
        fc("finalize", "--run", run)
        self.one_line_error(fc("render", "--run", run), "score.json")
        self.assertFalse((run / "report.md").exists())

    def test_finalize_with_a_review_file_that_is_not_json(self):
        run = make_run(fx.run_files())
        (run / "review-B.json").write_text("{not json", encoding="utf-8")
        self.one_line_error(fc("finalize", "--run", run), "review-B.json")

    def test_prompt_without_the_input_it_needs(self):
        run = make_run(fx.run_files(judgment_json=None, review__B_json=None))
        self.one_line_error(fc("prompt", "--run", run, "--role", "review", "--seat", "B"), "judgment.json")


class InputCliTest(unittest.TestCase):
    """User text reaches fc.py only through files (reviews: the shell ate $ and backticks and ran $(...), and a
    URL could close single quotes)."""

    def run_dir(self):
        return make_run(fx.run_files(source_json=None, claims_json=None))

    def write(self, run, name, text):
        (run / name).write_text(text, encoding="utf-8")
        return run / name

    def input(self, run, *args, prompt="查核"):
        return fc("input", "--run", run, *args, "--prompt-file", self.write(run, "prompt.txt", prompt))

    def test_text_and_prompt_are_copied_verbatim_including_shell_characters(self):
        run = self.run_dir()
        text = "第一行  有兩個空格\n第二行：明年油價一定漲三成！\n"
        question = "油價真的會從 $100 漲到 $130 嗎？`剛剛` 是什麼時候？$(touch x)"
        p = self.input(run, "--type", "text", "--file", self.write(run, "msg.txt", text), prompt=question)
        self.assertEqual(p.returncode, 0, p.stderr)
        data = json.loads((run / "input.json").read_text())
        self.assertEqual((data["content"], data["prompt"], data["input_type"]), (text, question, "text"))

    def test_url_from_a_file_keeps_quotes_and_dollar_signs(self):
        run = self.run_dir()
        url = "https://news.example.tw/a'$(id)'b"
        p = self.input(run, "--type", "url", "--url-file", self.write(run, "url.txt", url + "\n"))
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads((run / "input.json").read_text())["content"], url)

    def test_video_keeps_its_url_and_there_is_no_free_text_field(self):
        run = self.run_dir()
        p = self.input(run, "--type", "video", "--file", self.write(run, "t.txt", "逐字稿內容"),
                       "--url-file", self.write(run, "url.txt", "https://youtu.be/x"))
        self.assertEqual(p.returncode, 0, p.stderr)
        data = json.loads((run / "input.json").read_text())
        self.assertEqual(data["url"], "https://youtu.be/x")
        self.assertNotIn("notes", data)

    def test_a_folder_that_was_already_read_refuses_a_new_message(self):
        """Second review: after a new message, the old debate files still looked finished and mixed into the report."""
        run = make_run(fx.run_files())
        p = self.input(run, "--type", "text", "--file", self.write(run, "msg.txt", "另一則訊息"))
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("fc.py init", p.stderr)
        self.assertFalse((run / "input.json").exists())

    def test_failed_rerun_keeps_the_previous_input(self):
        run = self.run_dir()
        self.input(run, "--type", "text", "--file", self.write(run, "msg.txt", "訊息"))
        before = (run / "input.json").read_text()
        p = self.input(run, "--type", "text", "--file", self.write(run, "empty.txt", " "))
        self.assertNotEqual(p.returncode, 0)
        self.assertEqual((run / "input.json").read_text(), before)

    def test_text_and_a_link_together_are_refused_instead_of_dropping_one(self):
        """Audit: --type url ignored --file (the user's sentence was lost) and --type text dropped the link."""
        for kind, other in (("url", ("--file", "msg.txt")), ("text", ("--url-file", "url.txt"))):
            with self.subTest(kind):
                run = self.run_dir()
                self.write(run, "msg.txt", "朋友說這篇新聞證明健保費要漲三成")
                self.write(run, "url.txt", "https://news.example.tw/a")
                main = ("--url-file", run / "url.txt") if kind == "url" else ("--file", run / "msg.txt")
                p = self.input(run, "--type", kind, *main, other[0], run / other[1])
                self.assertNotEqual(p.returncode, 0)
                self.assertIn("分兩次", p.stderr)
                self.assertFalse((run / "input.json").exists())

    def test_file_that_is_not_utf8_is_a_clear_error(self):
        run = self.run_dir()
        (run / "big5.txt").write_bytes("油價".encode("big5"))
        p = self.input(run, "--type", "text", "--file", run / "big5.txt")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("UTF-8", p.stderr)
        self.assertNotIn("Traceback", p.stderr)


class SetupCliTest(unittest.TestCase):
    def test_init_creates_run_dir_with_run_json(self):
        base = Path(tempfile.mkdtemp())
        p = fc("init", "--mode", "quick", "--host", "codex", "--slug", "油價 謠言/測試", "--base", base)
        self.assertEqual(p.returncode, 0, p.stderr)
        run = Path(p.stdout.strip())
        self.assertTrue(run.is_dir())
        self.assertTrue(run.parent == base / "factcheck-runs")
        self.assertNotIn("/", run.name.split("-", 2)[-1])
        data = json.loads((run / "run.json").read_text())
        self.assertEqual((data["mode"], data["host"]), ("quick", "codex"))

    def test_init_rejects_bad_mode(self):
        p = fc("init", "--mode", "turbo", "--host", "claude", "--slug", "x")
        self.assertNotEqual(p.returncode, 0)

    def test_status_lists_missing_and_done(self):
        run = make_run(fx.run_files(trace_json=None))
        p = fc("status", "--run", run)
        self.assertEqual(p.returncode, 0)
        self.assertIn("claims.json", p.stdout)
        self.assertRegex(p.stdout, r"trace\.json\s+缺少")
        self.assertRegex(p.stdout, r"claims\.json\s+完成")

    def test_prompt_prints_role_and_inputs(self):
        run = make_run(fx.run_files())
        p = fc("prompt", "--run", run, "--role", "opponent", "--seat", "A")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("反方 A", p.stdout)
        self.assertIn("proponent.json", p.stdout)

    def test_media_lookup(self):
        p = fc("media", "https://www.cna.com.tw/news/aipl/1.aspx")
        self.assertIn(p.returncode, (0, 1))  # 1 = not in table yet
        if p.returncode == 0:
            self.assertEqual(json.loads(p.stdout)["id"], "cna")

    def test_media_lookup_takes_a_domain_without_https(self):
        """Audit: cna.com.tw and udn.com/news/story/1 were 'not in the table'; only https:// links matched."""
        for query, outlet in (("cna.com.tw", "cna"), ("www.cna.com.tw/news/aipl/1.aspx", "cna"),
                              ("udn.com/news/story/1", "udn"), ("中央社", "cna")):
            with self.subTest(query):
                p = fc("media", query)
                self.assertEqual(p.returncode, 0, p.stdout)
                self.assertEqual(json.loads(p.stdout)["id"], outlet)

    def test_video_needs_a_real_link(self):
        """Audit: url.txt holding `--version` or `-U` went to yt-dlp as an option."""
        d = Path(tempfile.mkdtemp())
        (d / "yt-dlp").write_text(f"#!{sys.executable}\nopen({str(d / 'called')!r}, 'w').close()\n", encoding="utf-8")
        (d / "yt-dlp").chmod(0o755)  # a fake on a PATH of its own: the real yt-dlp must never get these
        for bad in ("--version", "-U", "not a url", "file:///etc/passwd"):
            with self.subTest(bad):
                (d / "url.txt").write_text(bad, encoding="utf-8")
                p = subprocess.run([sys.executable, str(FC), "video", "--url-file", str(d / "url.txt")],
                                   capture_output=True, text=True, env={"PATH": str(d)})
                self.assertNotEqual(p.returncode, 0)
                self.assertIn("http(s)", p.stderr)
                self.assertFalse((d / "called").exists())

    def test_output_is_utf8_whatever_the_terminal_encoding(self):
        """Audit: with an English-Windows encoding, `score` crashed printing Chinese after writing score.json."""
        run = make_run(fx.run_files(trace_json=None))
        p = subprocess.run([sys.executable, str(FC), "status", "--run", str(run)], capture_output=True,
                           env={**os.environ, "PYTHONIOENCODING": "cp1252"})
        self.assertEqual(p.returncode, 0, p.stderr.decode("utf-8", "replace"))
        self.assertIn("缺少", p.stdout.decode("utf-8"))

    def test_old_python_gets_one_line_naming_the_version(self):
        """Audit: macOS's own python3 is 3.9, and the first command was an 8-line traceback about tomllib."""
        old = next((p for p in ("/usr/bin/python3", "/usr/bin/python3.9", "/usr/bin/python3.10") if os.path.exists(p)), None)
        version = subprocess.run([old, "-c", "import sys;print(sys.version_info[:2] < (3, 11))"], capture_output=True,
                                 text=True).stdout.strip() if old else ""
        if version != "True":
            self.skipTest("no Python older than 3.11 on this machine")
        p = subprocess.run([old, str(FC), "init", "--mode", "full", "--host", "claude", "--slug", "x",
                            "--base", tempfile.mkdtemp()], capture_output=True, text=True)
        self.assertNotEqual(p.returncode, 0)
        self.assertNotIn("Traceback", p.stderr)
        self.assertIn("需要 Python 3.11 以上", p.stderr)

    def test_detect_without_probe_writes_models_and_seats(self):
        base = Path(tempfile.mkdtemp())
        run = Path(fc("init", "--mode", "full", "--host", "claude", "--slug", "d", "--base", base).stdout.strip())
        p = fc("detect", "--run", run)
        self.assertEqual(p.returncode, 0, p.stderr)
        models = json.loads((run / "models.json").read_text())
        self.assertEqual([s["seat"] for s in models["seats"]][:3], ["A", "B", "C"])

    def test_detect_records_the_host_model_and_effort(self):
        base = Path(tempfile.mkdtemp())
        run = Path(fc("init", "--mode", "full", "--host", "claude", "--slug", "d", "--base", base).stdout.strip())
        p = fc("detect", "--run", run, "--host-model", "claude-opus-5-5", "--host-effort", "xhigh")
        self.assertEqual(p.returncode, 0, p.stderr)
        host = next(e for e in json.loads((run / "models.json").read_text())["engines"] if e["engine"] == "claude")
        self.assertEqual((host["model"], host["effort"]), ("claude-opus-5-5", "xhigh"))

    def test_host_effort_applies_to_codex_when_codex_is_the_host(self):
        """Host decision: --host-effort used to be recorded for a Codex host but never passed to codex."""
        base = Path(tempfile.mkdtemp())
        for host, effort, expected in (("codex", "xhigh", "xhigh"), ("claude", "xhigh", "high")):
            with self.subTest(host):
                run = Path(fc("init", "--mode", "full", "--host", host, "--slug", "d", "--base", base).stdout.strip())
                p = subprocess.run([sys.executable, str(FC), "detect", "--run", str(run), "--host-effort", effort],
                                   capture_output=True, text=True,
                                   env={"PATH": "/usr/bin:/bin", "FC_CODEX_CMD": "codex", "FC_CLAUDE_CMD": "claude"})
                self.assertEqual(p.returncode, 0, p.stderr)
                codex = next(e for e in json.loads((run / "models.json").read_text())["engines"] if e["engine"] == "codex")
                self.assertEqual(codex["effort"], expected)

    def test_detect_rejects_an_unknown_effort(self):
        base = Path(tempfile.mkdtemp())
        run = Path(fc("init", "--mode", "full", "--host", "claude", "--slug", "d", "--base", base).stdout.strip())
        self.assertNotEqual(fc("detect", "--run", run, "--host-effort", "turbo").returncode, 0)

    def test_detect_reports_the_host_model_and_a_missing_host_cli(self):
        """Red-team re-review: a forgotten --host-model or a missing claude command only surfaced at step 3."""
        base = Path(tempfile.mkdtemp())
        run = Path(fc("init", "--mode", "full", "--host", "claude", "--slug", "d", "--base", base).stdout.strip())
        p = subprocess.run([sys.executable, str(FC), "detect", "--run", str(run)], capture_output=True, text=True,
                           env={"PATH": "/usr/bin:/bin"})
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("沒有指定模型", p.stderr)
        self.assertIn("找不到主體的 CLI", p.stderr)

    def test_detect_mentions_an_api_key_without_printing_it(self):
        base = Path(tempfile.mkdtemp())
        run = Path(fc("init", "--mode", "full", "--host", "claude", "--slug", "d", "--base", base).stdout.strip())
        p = subprocess.run([sys.executable, str(FC), "detect", "--run", str(run)], capture_output=True, text=True,
                           env={"PATH": "/usr/bin:/bin", "FC_CLAUDE_CMD": "false", "ANTHROPIC_API_KEY": "sk-test-SECRET"})
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("ANTHROPIC_API_KEY", p.stderr)
        self.assertNotIn("sk-test-SECRET", p.stderr + p.stdout + (run / "models.json").read_text())

    def test_detect_probe_failure_prints_the_reason(self):
        base = Path(tempfile.mkdtemp())
        run = Path(fc("init", "--mode", "full", "--host", "claude", "--slug", "d", "--base", base).stdout.strip())
        # PATH without the user's folders: a gemini CLI installed there would otherwise be probed for real.
        p = subprocess.run([sys.executable, str(FC), "detect", "--run", str(run), "--probe"], capture_output=True,
                           text=True, env={"PATH": "/usr/bin:/bin", "FC_CODEX_CMD": "false"})
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("codex: probe=failed", p.stderr)
        self.assertIn("結束碼 1", p.stderr)


if __name__ == "__main__":
    unittest.main()
