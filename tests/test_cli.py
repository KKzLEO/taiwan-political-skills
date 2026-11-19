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
