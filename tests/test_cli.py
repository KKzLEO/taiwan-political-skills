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
        p = subprocess.run([sys.executable, str(FC), "detect", "--run", str(run), "--probe"], capture_output=True,
                           text=True, env={**os.environ, "FC_CODEX_CMD": "false"})
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("codex: probe=failed", p.stderr)
        self.assertIn("結束碼 1", p.stderr)


if __name__ == "__main__":
    unittest.main()
