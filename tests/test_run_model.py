import json
import subprocess
import unittest
from pathlib import Path

from tests import fixtures as fx
from tests.helpers import make_run
from fclib import run_model

CODEX = {"engine": "codex", "vendor": "openai", "cmd": ["/bin/codex"], "model": None, "can_search": True}
CLAUDE = {"engine": "claude", "vendor": "anthropic", "cmd": ["/bin/claude"], "model": None, "can_search": True}


class ExtractJsonTest(unittest.TestCase):
    def test_plain_object(self):
        self.assertEqual(run_model.extract_json_object('{"a": 1}'), {"a": 1})

    def test_fenced_block_with_chatter(self):
        text = 'Here you go:\n```json\n{"a": 2}\n```\nThanks'
        self.assertEqual(run_model.extract_json_object(text), {"a": 2})

    def test_last_object_wins(self):
        self.assertEqual(run_model.extract_json_object('{"a": 1} then {"b": 2}'), {"b": 2})

    def test_nested_braces_in_strings(self):
        self.assertEqual(run_model.extract_json_object('x {"s": "a}b{c"} y'), {"s": "a}b{c"})

    def test_none_when_absent(self):
        self.assertIsNone(run_model.extract_json_object("no json here"))


class CommandTest(unittest.TestCase):
    def test_codex_runs_isolated_in_workdir(self):
        argv, mode = run_model.build_command(CODEX, "/tmp/w", "/tmp/w/out.txt", env={})
        for flag in ["exec", "--ignore-user-config", "--ephemeral", "--skip-git-repo-check", "read-only"]:
            self.assertIn(flag, argv)
        self.assertEqual(argv[argv.index("-C") + 1], "/tmp/w")
        self.assertEqual(argv[argv.index("-o") + 1], "/tmp/w/out.txt")
        self.assertEqual(mode, "file")

    def test_claude_uses_bare_only_with_api_key(self):
        argv, _ = run_model.build_command(CLAUDE, "/tmp/w", None, env={})
        self.assertNotIn("--bare", argv)
        argv, _ = run_model.build_command(CLAUDE, "/tmp/w", None, env={"ANTHROPIC_API_KEY": "k"})
        self.assertIn("--bare", argv)

    def test_claude_gets_isolation_note_and_search_tools(self):
        argv, mode = run_model.build_command(CLAUDE, "/tmp/w", None, env={})
        self.assertIn("--append-system-prompt", argv)
        self.assertIn("WebSearch", argv)
        self.assertEqual(mode, "claude-json")

    def test_model_override_from_env(self):
        argv, _ = run_model.build_command(CODEX, "/tmp/w", "/tmp/o", env={"FC_CODEX_MODEL": "m1"})
        self.assertEqual(argv[argv.index("-m") + 1], "m1")


class FakeRunner:
    """Replays scripted replies. Each reply: str (final text), 'TIMEOUT', or (code, text)."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, argv, stdin, cwd, timeout, env):
        self.calls.append({"argv": argv, "stdin": stdin, "cwd": cwd})
        reply = self.replies.pop(0)
        if reply == "TIMEOUT":
            raise subprocess.TimeoutExpired(argv, timeout)
        code, text = reply if isinstance(reply, tuple) else (0, reply)
        if "-o" in argv:
            Path(argv[argv.index("-o") + 1]).write_text(text, encoding="utf-8")
            return code, "", ""
        if "--output-format" in argv:
            return code, json.dumps({"result": text, "is_error": code != 0}), ""
        return code, text, ""


class CallTest(unittest.TestCase):
    def test_retries_once_after_timeout(self):
        r = FakeRunner(["TIMEOUT", '{"ok": true}'])
        ok, text, err = run_model.call(CODEX, "p", runner=r, env={})
        self.assertTrue(ok)
        self.assertEqual(len(r.calls), 2)

    def test_two_timeouts_fail(self):
        r = FakeRunner(["TIMEOUT", "TIMEOUT"])
        ok, _, err = run_model.call(CODEX, "p", runner=r, env={})
        self.assertFalse(ok)
        self.assertIn("逾時", err)

    def test_nonzero_exit_is_retried(self):
        r = FakeRunner([(1, "boom"), '{"ok": true}'])
        ok, _, _ = run_model.call(CLAUDE, "p", runner=r, env={})
        self.assertTrue(ok)

    def test_prompt_goes_through_stdin_and_runs_in_clean_temp_dir(self):
        r = FakeRunner(['{"ok": true}'])
        run_model.call(CODEX, "PROMPT-TEXT", runner=r, env={})
        call = r.calls[0]
        self.assertEqual(call["stdin"], "PROMPT-TEXT")
        self.assertTrue(Path(call["argv"][call["argv"].index("-C") + 1]) == Path(call["cwd"]))
        self.assertFalse(Path(call["cwd"]).exists(), "temp dir should be removed afterwards")


GOOD_ATTACKS = json.dumps({"seat": "WRONG", "engine": "fake", "lens": "x", "searches_run": 2, "attacks": [
    {"id": "X1-1", "claim_id": "C1", "target": "label", "argument": "另有逐字稿",
     "proposed_label": "misleading", "evidence": [{"url": "https://example.org/t", "excerpt": "可能上漲"}]}]})


class RunRoleTest(unittest.TestCase):
    def run_dir(self):
        return make_run(fx.run_files(**{"opponent__X1_json": None, "rebuttal_json": None,
                                        "judgment_json": None, "review__B_json": None}))

    def test_external_opponent_output_is_written_with_script_owned_fields(self):
        run = self.run_dir()
        r = FakeRunner([GOOD_ATTACKS])
        run_model.run_role(run, "opponent", "X1", CODEX, runner=r, env={})
        data = json.loads((run / "opponent-X1.json").read_text())
        self.assertEqual((data["seat"], data["engine"], data["lens"], data["status"]),
                         ("X1", "codex", "external", "ok"))

    def test_invalid_output_is_retried_with_errors_in_prompt(self):
        run = self.run_dir()
        bad = json.dumps({"attacks": [{"id": "X1-1", "claim_id": "C1", "target": "label",
                                        "argument": "沒附證據", "evidence": []}]})
        r = FakeRunner([bad, GOOD_ATTACKS])
        run_model.run_role(run, "opponent", "X1", CODEX, runner=r, env={})
        self.assertEqual(len(r.calls), 2)
        self.assertIn("必須附證據", r.calls[1]["stdin"])
        self.assertEqual(json.loads((run / "opponent-X1.json").read_text())["status"], "ok")

    def test_opponent_that_keeps_failing_becomes_failed_seat(self):
        run = self.run_dir()
        r = FakeRunner(["not json", "still not json"])
        run_model.run_role(run, "opponent", "X1", CODEX, runner=r, env={})
        data = json.loads((run / "opponent-X1.json").read_text())
        self.assertEqual(data["status"], "failed")
        self.assertEqual(data["attacks"], [])

    def test_non_opponent_role_failure_raises(self):
        run = make_run(fx.run_files(proponent_json=None))
        r = FakeRunner(["nope", "nope"])
        with self.assertRaises(run_model.RunModelError):
            run_model.run_role(run, "proponent", None, CODEX, runner=r, env={})
        self.assertFalse((run / "proponent.json").exists())


class PromptTest(unittest.TestCase):
    def test_opponent_prompt_has_only_its_inputs(self):
        run = make_run(fx.run_files())
        p = run_model.build_prompt(run, "opponent", "X1", lens="external")
        self.assertIn("proponent.json", p)
        self.assertIn("claims.json", p)
        self.assertNotIn("rebuttal.json", p)
        self.assertNotIn("judgment.json", p)

    def test_judge_prompt_hides_opponent_engines(self):
        run = make_run(fx.run_files())
        p = run_model.build_prompt(run, "judge", None)
        self.assertIn("opponent-X1.json", p)
        self.assertNotIn('"engine"', p)

    def test_review_prompt_only_includes_own_seat(self):
        run = make_run(fx.run_files())
        p = run_model.build_prompt(run, "review", "B")
        self.assertIn("opponent-B.json", p)
        self.assertNotIn("opponent-A.json", p)

    def test_internal_seat_prompt_states_host_engine(self):
        run = make_run(fx.run_files())
        p = run_model.build_prompt(run, "opponent", "A", lens="evidence")
        self.assertIn('"engine": "claude"', p)

    def test_external_seat_prompt_states_its_engine(self):
        run = make_run(fx.run_files(models_json=dict(fx.MODELS, seats=[
            {"seat": "X1", "engine": "codex", "kind": "external", "lens": "external"}])))
        p = run_model.build_prompt(run, "opponent", "X1", lens="external")
        self.assertIn('"engine": "codex"', p)

    def test_prompt_states_output_file_and_seat(self):
        run = make_run(fx.run_files())
        p = run_model.build_prompt(run, "opponent", "A", lens="evidence")
        self.assertIn("opponent-A.json", p)
        self.assertIn('"seat": "A"', p)


class ProbeTest(unittest.TestCase):
    def test_probe_reports_partial_isolation_when_user_context_seen(self):
        r = FakeRunner(['{"user_context": true, "can_web_search": true}'])
        res = run_model.probe(CODEX, runner=r, env={})
        self.assertEqual((res["probe"], res["isolation"]), ("ok", "partial"))

    def test_probe_clean(self):
        r = FakeRunner(['{"user_context": false, "can_web_search": true}'])
        self.assertEqual(run_model.probe(CODEX, runner=r, env={})["isolation"], "full")

    def test_probe_failure(self):
        r = FakeRunner(["TIMEOUT", "TIMEOUT"])
        self.assertEqual(run_model.probe(CODEX, runner=r, env={})["probe"], "failed")

    def test_probe_downgrades_search_when_model_says_no(self):
        r = FakeRunner(['{"user_context": false, "can_web_search": false}'])
        self.assertFalse(run_model.probe(CODEX, runner=r, env={})["can_search"])

    def test_probe_does_not_store_user_instructions(self):
        r = FakeRunner(['{"user_context": true, "first_words": "SECRET PREFS", "can_web_search": true}'])
        self.assertNotIn("SECRET", json.dumps(run_model.probe(CODEX, runner=r, env={})))


if __name__ == "__main__":
    unittest.main()


class PromptDataTest(unittest.TestCase):
    def data_dir(self):
        import tempfile
        d = Path(tempfile.mkdtemp(prefix="fc-data-"))
        (d / "tactics.toml").write_text(
            'schema_version = 1\n[[tactic]]\nid = "TW-T07"\nname = "急迫轉傳"\nlayer = "content"\n'
            'observable = ["快轉傳"]\ncannot_infer = "不能推論散布者身分"\n', encoding="utf-8")
        (d / "media.toml").write_text(
            'schema_version = 1\n[[outlet]]\nid = "cna"\nname = "中央社"\ndomains = ["cna.com.tw"]\n', encoding="utf-8")
        (d / "sources.toml").write_text(
            'schema_version = 1\n[[source]]\nid = "ly-ivod"\nname = "立法院 IVOD"\nurl = "https://ivod.ly.gov.tw/"\n'
            'tier = 1\ncovers = ["質詢"]\n', encoding="utf-8")
        return d

    def test_tracer_prompt_includes_tactics_and_media_ids(self):
        run = make_run(fx.run_files())
        p = run_model.build_prompt(run, "tracer", None, data_dir=self.data_dir())
        self.assertIn("TW-T07", p)
        self.assertIn("不能推論散布者身分", p)
        self.assertIn("cna", p)

    def test_proponent_prompt_includes_first_hand_sources(self):
        run = make_run(fx.run_files())
        p = run_model.build_prompt(run, "proponent", None, data_dir=self.data_dir())
        self.assertIn("https://ivod.ly.gov.tw/", p)
        self.assertNotIn("TW-T07", p)

    def test_stance_opponent_gets_tactics(self):
        run = make_run(fx.run_files())
        p = run_model.build_prompt(run, "opponent", "C", lens="stance", data_dir=self.data_dir())
        self.assertIn("TW-T07", p)

    def test_missing_data_files_are_skipped(self):
        import tempfile
        run = make_run(fx.run_files())
        p = run_model.build_prompt(run, "tracer", None, data_dir=Path(tempfile.mkdtemp()))
        self.assertIn("trace.json", p)
