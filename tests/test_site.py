"""The public pages. The results page is whatever the records produce, the front page agrees with it, and
nothing on either page points at something that is not there."""
import importlib.util
import re
import unittest
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
FRONT = SITE / "index.html"
RESULTS = SITE / "results/index.html"
REPO = "https://github.com/KKzLEO/taiwan-political-skills"


def builder():
    spec = importlib.util.spec_from_file_location("build_results", SITE / "tools/build_results.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read(path):
    return path.read_text(encoding="utf-8")


class ResultsPage(unittest.TestCase):
    def test_committed_page_is_what_the_records_produce(self):
        self.assertEqual(read(RESULTS), builder().PAGE)

    def test_every_case_of_the_batch_has_a_row(self):
        rows = re.findall(r'<tr id="(case-\d+)" class="(\w+)">', read(RESULTS))
        scores = sorted(p.name.split(".")[0] for p in (ROOT / "evals/results/artifacts/2026-11-20-final/scores").glob("case-*.score.json"))
        self.assertEqual([name for name, _ in rows], scores)


class FrontPage(unittest.TestCase):
    def test_its_twelve_tiles_say_what_the_results_page_says(self):
        rows = dict(re.findall(r'<tr id="(case-\d+)" class="(\w+)">', read(RESULTS)))
        tiles = re.findall(r'<li class="(\w+)"><a href="results/#(case-\d+)">', read(FRONT))
        self.assertEqual(len(tiles), 12)
        self.assertEqual({case: kind for kind, case in tiles}, rows)

    def test_the_typed_questions_fit_the_line_made_for_them(self):
        # the line is sized for 21 full-width characters; digits and Latin letters take about half of one
        script = read(SITE / "assets/hero.js")
        questions = re.findall(r"^    '(.+)',?$", script, flags=re.M)
        self.assertEqual(len(questions), 13)
        for q in questions:
            width = sum(0.5 if ord(ch) < 0x2000 else 1 for ch in q)
            self.assertLessEqual(width, 21, q)
            self.assertRegex(q, "[，、]", q)       # where a narrow screen turns the line


class Links(unittest.TestCase):
    def pages(self):
        return [(FRONT, read(FRONT)), (RESULTS, read(RESULTS))]

    def test_local_files_the_pages_ask_for_exist(self):
        for page, text in self.pages():
            for target in re.findall(r'(?:href|src)="([^"]+)"', text):
                if re.match(r"(https?:|#|data:|mailto:)", target):
                    continue
                path = (page.parent / target.split("#")[0].split("?")[0]).resolve()
                self.assertTrue(path.exists(), f"{page.name}: {target}")

    def test_links_into_the_repository_point_at_things_that_exist(self):
        for page, text in self.pages():
            for target in re.findall(re.escape(REPO) + r'/(?:blob|tree)/main/([^"#]+)', text):
                self.assertTrue((ROOT / unquote(target)).exists(), f"{page.name}: {target}")

    def test_links_inside_a_page_land_on_something(self):
        for page, text in self.pages():
            ids = set(re.findall(r'id="([^"]+)"', text))
            for anchor in re.findall(r'href="#([^"]+)"', text):
                self.assertIn(anchor, ids, f"{page.name}: #{anchor}")


if __name__ == "__main__":
    unittest.main()
