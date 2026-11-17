import json
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


if __name__ == "__main__":
    unittest.main()
