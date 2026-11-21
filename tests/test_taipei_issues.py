"""The second Taipei registration: the list the runner and the pages read is the list that was registered."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIST = ROOT / "evals/results/2026-11-22-taipei-issues.json"
REGISTERED = ROOT / "evals/results/2026-11-22-taipei-issues-preregistration.md"


class Registration(unittest.TestCase):
    def setUp(self):
        self.doc = json.loads(LIST.read_text(encoding="utf-8"))
        self.statements = [s for issue in self.doc["issues"] for s in issue["statements"]]

    def test_every_text_stands_in_the_registration_word_for_word(self):
        registered = REGISTERED.read_text(encoding="utf-8")
        for s in self.statements:
            self.assertIn("「" + s["text"] + "」", registered, s["id"])
        self.assertIn("「" + self.doc["request"] + "」", registered)

    def test_each_issue_has_one_statement_from_each_candidate(self):
        people = [p["key"] for p in self.doc["people"]]
        for issue in self.doc["issues"]:
            self.assertEqual(sorted(s["who"] for s in issue["statements"]), sorted(people), issue["id"])

    def test_candidates_are_listed_in_ballot_order(self):
        numbers = [p["no"] for p in self.doc["people"]]
        self.assertEqual(numbers, sorted(numbers))

    def test_a_statement_is_either_run_before_or_has_its_place_in_the_order(self):
        new = sorted(s["order"] for s in self.statements if "earlier" not in s)
        self.assertEqual(new, list(range(1, len(new) + 1)))
        for s in self.statements:
            self.assertNotEqual("earlier" in s, "order" in s, s["id"])

    def test_the_ones_run_before_were_given_the_same_text(self):
        for s in self.statements:
            if "earlier" in s:
                given = json.loads((ROOT / "examples" / s["earlier"] / "input.json").read_text(encoding="utf-8"))
                self.assertEqual(given["content"].strip(), s["text"], s["id"])
                self.assertEqual(given["prompt"], self.doc["request"], s["id"])

    def test_who_goes_first_changes_from_one_issue_to_the_next(self):
        first = [min(issue["statements"], key=lambda s: s["order"])["who"]
                 for issue in self.doc["issues"] if all("order" in s for s in issue["statements"])]
        self.assertTrue(all(a != b for a, b in zip(first, first[1:])), first)

    def test_statement_ids_are_unique_and_name_the_speaker(self):
        ids = [s["id"] for s in self.statements]
        self.assertEqual(len(ids), len(set(ids)))
        for s in self.statements:
            self.assertTrue(s["id"].startswith(s["who"] + "-"), s["id"])
            name = next(p["name"] for p in self.doc["people"] if p["key"] == s["who"])
            self.assertTrue(s["text"].startswith(name + "在 10 月 31 日台北市長辯論會上"), s["id"])


if __name__ == "__main__":
    unittest.main()
