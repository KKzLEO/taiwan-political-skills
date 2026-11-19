import unittest

from tests import helpers  # noqa: F401
from fclib import detect

TIERS = {
    "hosts": {"claude": "anthropic", "codex": "openai"},
    "engine": [
        {"id": "claude", "vendor": "anthropic", "cli": "claude", "can_search": True, "same_tier": True},
        {"id": "codex", "vendor": "openai", "cli": "codex", "can_search": True, "same_tier": True},
        {"id": "gemini", "vendor": "google", "cli": "gemini", "can_search": True, "same_tier": True},
        {"id": "ollama", "vendor": "local", "cli": "ollama", "can_search": False, "same_tier": False},
    ],
    "local": {"same_tier_patterns": ["bigmodel:*"]},
}


def which_from(found):
    return lambda name: f"/usr/bin/{name}" if name in found else None


def run(host="claude", found=(), env=None, ollama_models=(), probe=None):
    return detect.detect(host, TIERS, which=which_from(found), env=env or {},
                         list_ollama=lambda cmd: list(ollama_models), probe=probe)


def engine(models, eid, model=None):
    return next(e for e in models["engines"] if e["engine"] == eid and e.get("model") == model)


class DetectTest(unittest.TestCase):
    def test_other_vendor_is_cross_model(self):
        m = run(found=("claude", "codex"))
        self.assertTrue(engine(m, "codex")["cross_model"])
        self.assertFalse(engine(m, "claude")["cross_model"])
        self.assertEqual(m["host_vendor"], "anthropic")

    def test_codex_host_treats_claude_as_external(self):
        m = run(host="codex", found=("claude", "codex"))
        self.assertTrue(engine(m, "claude")["cross_model"])
        self.assertFalse(engine(m, "codex")["cross_model"])

    def test_missing_cli_is_unavailable(self):
        m = run(found=())
        self.assertFalse(engine(m, "codex")["available"])

    def test_stored_command_has_no_absolute_path(self):
        """Run folders are meant to be shared; they must not leak the user's home directory."""
        e = engine(run(found=("codex",)), "codex")
        self.assertEqual(e["cmd"], ["codex"])

    def test_env_override_command(self):
        m = run(found=(), env={"FC_CODEX_CMD": "zsh -ic codex"})
        e = engine(m, "codex")
        self.assertTrue(e["available"])
        self.assertEqual(e["cmd"], ["zsh", "-ic", "codex"])

    def test_ollama_models_need_whitelist(self):
        m = run(found=("ollama",), ollama_models=("bigmodel:120b", "tiny:7b"))
        self.assertTrue(engine(m, "ollama", "bigmodel:120b")["same_tier"])
        self.assertFalse(engine(m, "ollama", "tiny:7b")["same_tier"])
        self.assertFalse(engine(m, "ollama", "bigmodel:120b")["can_search"])

    def test_codex_records_the_effort_and_model_its_roles_will_use(self):
        """Host decision: the report's seat table shows the model and effort, so models.json has to hold them."""
        e = engine(run(found=("codex",)), "codex")
        self.assertEqual((e["model"], e["effort"]), (None, "high"))
        m = run(found=("codex",), env={"FC_CODEX_EFFORT": "medium", "FC_CODEX_MODEL": "m1"})
        e = engine(m, "codex", "m1")
        self.assertEqual((e["model"], e["effort"]), ("m1", "medium"))
        self.assertEqual([s["model"] for s in detect.assign_seats(m, "full") if s["seat"] == "X1"], ["m1"])

    def test_claude_records_its_env_overrides(self):
        e = engine(run(found=("claude", "codex"), env={"FC_CLAUDE_MODEL": "c1", "FC_CLAUDE_EFFORT": "max"}), "claude", "c1")
        self.assertEqual(e["effort"], "max")
        self.assertIsNone(engine(run(found=("claude",)), "claude").get("effort"))
        self.assertNotIn("effort", engine(run(found=("gemini",), env={"FC_GEMINI_EFFORT": "max"}), "gemini"))

    def test_ollama_list_is_read_as_utf8(self):
        from unittest import mock
        import subprocess
        with mock.patch.object(detect.subprocess, "run") as run:
            run.return_value = subprocess.CompletedProcess([], 0, "NAME\nbigmodel:120b x\n", "")
            self.assertEqual(detect._list_ollama(["ollama"]), ["bigmodel:120b"])
        self.assertEqual(run.call_args.kwargs.get("encoding"), "utf-8")

    def test_probe_result_is_recorded(self):
        m = run(found=("codex",), probe=lambda e: {"probe": "failed", "isolation": "unknown", "detail": "not logged in"})
        self.assertEqual(engine(m, "codex")["probe"], "failed")

    def test_unprobed_engines_are_marked(self):
        m = run(found=("codex",))
        self.assertEqual(engine(m, "codex")["probe"], "skipped")


class SeatsTest(unittest.TestCase):
    def seats(self, models, mode):
        return [(s["seat"], s["engine"], s["kind"]) for s in detect.assign_seats(models, mode)]

    def test_full_mode_has_three_internal_plus_each_external(self):
        m = run(found=("claude", "codex", "gemini"))
        self.assertEqual(self.seats(m, "full"), [
            ("A", "claude", "internal"), ("B", "claude", "internal"), ("C", "claude", "internal"),
            ("X1", "codex", "external"), ("X2", "gemini", "external")])

    def test_quick_mode_prefers_one_external_seat(self):
        m = run(found=("claude", "codex", "gemini"))
        self.assertEqual(self.seats(m, "quick"), [("X1", "codex", "external")])

    def test_quick_mode_without_external_uses_counter_lens(self):
        m = run(found=("claude",))
        self.assertEqual(self.seats(m, "quick"), [("B", "claude", "internal")])

    def test_failed_probe_is_not_seated(self):
        m = run(found=("codex",), probe=lambda e: {"probe": "failed", "isolation": "unknown", "detail": "x"})
        self.assertEqual([s for s in self.seats(m, "full") if s[2] == "external"], [])

    def test_non_whitelisted_local_model_is_not_seated(self):
        m = run(found=("ollama",), ollama_models=("tiny:7b",))
        self.assertEqual([s for s in self.seats(m, "full") if s[2] == "external"], [])

    def test_whitelisted_local_model_is_seated(self):
        m = run(found=("ollama",), ollama_models=("bigmodel:120b",))
        ext = [s for s in detect.assign_seats(m, "full") if s["kind"] == "external"]
        self.assertEqual((ext[0]["engine"], ext[0]["model"]), ("ollama", "bigmodel:120b"))

    def test_internal_seat_lenses(self):
        m = run(found=())
        lenses = {s["seat"]: s["lens"] for s in detect.assign_seats(m, "full")}
        self.assertEqual(lenses, {"A": "evidence", "B": "counter", "C": "stance"})


if __name__ == "__main__":
    unittest.main()
