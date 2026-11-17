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

    def test_cross_model_is_computed_not_trusted(self):
        lying = dict(fx.OPP_A, cross_model=True)
        self.assertFalse(self.seats(opponent__A_json=lying)["A"]["cross_model"])

    def test_external_seat_without_search(self):
        models = {"host": "claude", "host_vendor": "anthropic", "engines": [
            {"engine": "codex", "vendor": "openai", "available": True, "cross_model": True,
             "can_search": False, "same_tier": True, "isolation": "unknown", "probe": "ok"}]}
        self.assertFalse(self.seats(models_json=models)["X1"]["can_search"])
