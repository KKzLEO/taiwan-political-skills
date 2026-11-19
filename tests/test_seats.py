import copy
import unittest

from tests import fixtures as fx
from tests.helpers import make_run
from fclib import detect


class SeatStatusTest(unittest.TestCase):
    def seats(self, **overrides):
        run = make_run(fx.run_files(**overrides))
        return {s["seat"]: s for s in detect.seat_status(run)}

    def test_internal_seats_are_not_cross_model(self):
        s = self.seats()
        self.assertFalse(s["A"]["cross_model"])
        self.assertEqual(s["A"]["status"], "ok")

    def test_external_seat_is_cross_model_and_uses_probed_search(self):
        s = self.seats()
        self.assertTrue(s["X1"]["cross_model"])
        self.assertTrue(s["X1"]["can_search"])
        self.assertEqual(s["X1"]["isolation"], "partial")

    def test_failed_seat(self):
        failed = {"seat": "X1", "engine": "codex", "lens": "external", "status": "failed", "error": "t", "attacks": []}
        self.assertEqual(self.seats(opponent__X1_json=failed)["X1"]["status"], "failed")

    def test_seat_assigned_in_models_without_a_file_is_missing(self):
        """Red-team: a seat that never ran must not silently disappear from the seat table."""
        models = dict(fx.MODELS, seats=[{"seat": s, "engine": "claude", "kind": "internal", "lens": lens}
                                         for s, lens in (("A", "evidence"), ("B", "counter"), ("C", "stance"))]
                      + [{"seat": "X1", "engine": "codex", "kind": "external", "lens": "external"}])
        s = self.seats(models_json=models, opponent__C_json=None)
        self.assertEqual(s["C"]["status"], "missing")
        self.assertFalse(s["C"]["cross_model"])
        self.assertEqual(s["A"]["status"], "ok")

    def test_missing_external_seat_is_described_like_a_failed_one(self):
        """Skeptic re-review: a missing X1 showed 'not cross-model, cannot search' in the seat table."""
        models = dict(fx.MODELS, seats=[{"seat": "X1", "engine": "codex", "kind": "external", "lens": "external"}])
        s = self.seats(models_json=models, opponent__X1_json=None)["X1"]
        self.assertEqual((s["status"], s["cross_model"], s["can_search"], s["isolation"]), ("missing", True, True, "partial"))

    def test_cross_model_is_computed_not_trusted(self):
        lying = dict(fx.OPP_A, cross_model=True)
        self.assertFalse(self.seats(opponent__A_json=lying)["A"]["cross_model"])

    def test_seat_table_shows_the_model_and_effort_each_seat_ran_with(self):
        """Host decision: the 模型 column showed only `codex` or `claude`, not which model or how much reasoning."""
        from fclib import finalize, io, render, score
        models = copy.deepcopy(fx.MODELS)
        models["engines"][0].update(model=None, effort="high")
        models["engines"].append({"engine": "claude", "vendor": "anthropic", "available": True, "cross_model": False,
                                  "can_search": True, "same_tier": True, "model": "claude-opus-5-5", "effort": "xhigh",
                                  "probe": "skipped", "isolation": "unknown"})
        models["seats"] = ([{"seat": s, "engine": "claude", "kind": "internal", "lens": lens, "model": None}
                            for s, lens in (("A", "evidence"), ("B", "counter"), ("C", "stance"))]
                           + [{"seat": "X1", "engine": "codex", "kind": "external", "lens": "external", "model": None}])
        run = make_run(fx.run_files(models_json=models))
        v = finalize.finalize(run)
        io.write_json(run / "verdicts.json", v)
        io.write_json(run / "score.json", score.compute(v, io.read_json(run / "run.json"), detect.seat_status(run)))
        out = render.render(run, outlets=[], tactics=[])
        self.assertIn("| A | 反方 A：證據 | claude（claude-opus-5-5，推理強度 xhigh） | 成功 |", out)
        self.assertIn("| X1 | 外部反方 | codex（預設模型，推理強度 high） | 成功 |", out)
        models["engines"][1].update(model=None, effort=None)
        run = make_run(fx.run_files(models_json=models))
        io.write_json(run / "verdicts.json", v)
        io.write_json(run / "score.json", score.compute(v, io.read_json(run / "run.json"), detect.seat_status(run)))
        self.assertIn("| B | 反方 B：反證 | claude（預設模型，推理強度 預設） |", render.render(run, outlets=[], tactics=[]))

    def test_external_seat_without_search(self):
        models = {"host": "claude", "host_vendor": "anthropic", "engines": [
            {"engine": "codex", "vendor": "openai", "available": True, "cross_model": True,
             "can_search": False, "same_tier": True, "isolation": "unknown", "probe": "ok"}]}
        self.assertFalse(self.seats(models_json=models)["X1"]["can_search"])
