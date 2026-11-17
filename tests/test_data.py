"""Data integrity rules. These enforce the neutrality promises mechanically."""

import glob
import re
import tomllib
import unittest

from tests.helpers import ROOT, SKILL
from fclib.labels import CONTEXT_FLAGS, FACTORS, TACTIC_LAYERS, TARGET_CAMPS

DATA = SKILL / "data"
URL = re.compile(r"^https?://\S+$")
DATE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")


def load(path):
    with open(path, "rb") as fh:
        return tomllib.load(fh)


class ModelTiersTest(unittest.TestCase):
    def test_engines(self):
        d = load(DATA / "model-tiers.toml")
        self.assertEqual(set(d["hosts"]), {"claude", "codex"})
        ids = [e["id"] for e in d["engine"]]
        self.assertEqual(len(ids), len(set(ids)))
        for e in d["engine"]:
            for k in ("vendor", "cli", "can_search", "same_tier"):
                self.assertIn(k, e, e["id"])
        self.assertIsInstance(d["local"]["same_tier_patterns"], list)


class MediaTest(unittest.TestCase):
    def setUp(self):
        self.outlets = load(DATA / "tw" / "media.toml")["outlet"]

    def test_ids_unique_and_basic_fields(self):
        ids = [o["id"] for o in self.outlets]
        self.assertEqual(len(ids), len(set(ids)))
        for o in self.outlets:
            self.assertTrue(o.get("name"), o["id"])
            self.assertIsInstance(o.get("domains", []), list)

    def test_every_claim_about_an_outlet_has_a_source(self):
        for o in self.outlets:
            with self.subTest(outlet=o["id"]):
                if o.get("ownership"):
                    self.assertRegex(o.get("ownership_source", ""), URL)
                if "trust" in o:
                    t = o["trust"]
                    self.assertTrue(0 <= t["score"] <= 100)
                    self.assertIsInstance(t["year"], int)
                    self.assertRegex(t["url"], URL)
                for ln in o.get("lean", []):
                    self.assertIsInstance(ln["year"], int)
                    self.assertTrue(ln["source"].strip())
                    self.assertRegex(ln["url"], URL)
                for r in o.get("record", []):
                    self.assertIn(r["kind"], {"ncc_sanction", "correction", "research_finding"})
                    self.assertRegex(r["url"], URL)
                    self.assertRegex(str(r["date"]), DATE)

    def test_domains_do_not_collide(self):
        seen = {}
        for o in self.outlets:
            for d in o.get("domains", []):
                self.assertNotIn(d, seen, f"{d} 同時屬於 {seen.get(d)} 和 {o['id']}")
                seen[d] = o["id"]


class SourcesTest(unittest.TestCase):
    def test_sources(self):
        for s in load(DATA / "tw" / "sources.toml")["source"]:
            with self.subTest(source=s["id"]):
                self.assertRegex(s["url"], URL)
                self.assertIn(s["tier"], range(1, 7))


class TacticsTest(unittest.TestCase):
    def setUp(self):
        self.tactics = load(DATA / "tw" / "tactics.toml")["tactic"]

    def test_ids_unique(self):
        ids = [t["id"] for t in self.tactics]
        self.assertEqual(len(ids), len(set(ids)))

    def test_required_fields(self):
        for t in self.tactics:
            with self.subTest(tactic=t["id"]):
                for k in ("name", "category", "definition", "cannot_infer", "how_to_spot"):
                    self.assertTrue(str(t.get(k, "")).strip(), k)
                self.assertTrue(t.get("observable"))
                self.assertIn(t["layer"], TACTIC_LAYERS)
                if "context_flag" in t:
                    self.assertIn(t["context_flag"], CONTEXT_FLAGS)

    def test_examples_cover_at_least_two_camps(self):
        """中立性規則：每種手法至少兩個案例，被攻擊方至少涵蓋兩個不同陣營。"""
        for t in self.tactics:
            with self.subTest(tactic=t["id"]):
                ex = t.get("example", [])
                self.assertGreaterEqual(len(ex), 2)
                self.assertGreaterEqual(len({e["target"] for e in ex}), 2)
                for e in ex:
                    self.assertIn(e["target"], TARGET_CAMPS)
                    self.assertRegex(e["url"], URL)
                    self.assertRegex(str(e["date"]), DATE)
                    self.assertTrue(e["summary"].strip())

    def test_attribution_tactics_say_content_cannot_prove_the_actor(self):
        for t in self.tactics:
            if t["layer"] == "attribution":
                with self.subTest(tactic=t["id"]):
                    self.assertIn("報告", t["cannot_infer"])

    def test_no_camp_dominates_examples(self):
        counts = {}
        for t in self.tactics:
            for e in t.get("example", []):
                counts[e["target"]] = counts.get(e["target"], 0) + 1
        total = sum(counts.values())
        self.assertLess(max(counts.values()) / total, 0.5, counts)


class EvalCasesTest(unittest.TestCase):
    def setUp(self):
        self.cases = [load(p) for p in sorted(glob.glob(str(ROOT / "evals" / "cases" / "*.toml")))]

    def test_cases_exist(self):
        self.assertGreaterEqual(len(self.cases), 8)

    def test_case_shape(self):
        for c in self.cases:
            with self.subTest(case=c["id"]):
                self.assertIn(c["input_type"], {"text", "url"})
                self.assertIn(c["target"], TARGET_CAMPS)
                self.assertIn(c["expected_result"], {"符合", "大致符合", "部分符合", "不符", "無法判定"})
                for cl in c["claim"]:
                    self.assertIn(cl["expected_label"], FACTORS)
                    if cl["expected_label"] != "not_factual":
                        gt = cl.get("ground_truth", [])
                        self.assertTrue(gt, cl["original"])
                        for g in gt:
                            self.assertRegex(g["url"], URL)
                            self.assertTrue(g["excerpt"].strip())

    def test_label_coverage(self):
        labels = {cl["expected_label"] for c in self.cases for cl in c["claim"]}
        for needed in ("true", "false", "misleading", "unverified", "not_factual"):
            self.assertIn(needed, labels)


if __name__ == "__main__":
    unittest.main()
