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
    def test_its_twelve_rows_say_what_the_results_page_says(self):
        theirs = {name: (kind, expected, got) for name, kind, expected, got in re.findall(
            r'<tr id="(case-\d+)" class="(\w+)"><th.*?</th><td>([^<]*)</td><td>([^<]*)</td>', read(RESULTS))}
        ours = {name: (kind, expected, got) for kind, name, expected, got in re.findall(
            r'<li class="(\w+)"><a href="results/#(case-\d+)"><span>[^<]*</span><span>([^<]*)</span><span>([^<]*)</span>', read(FRONT))}
        self.assertEqual(len(ours), 12)
        self.assertEqual(ours, theirs)


class Run(unittest.TestCase):
    """The run the front page plays is the worked example, and what the page says about it is counted from it."""

    def setUp(self):
        spec = importlib.util.spec_from_file_location("build_run", SITE / "tools/build_run.py")
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.steps = {s["id"]: s for s in self.module.build()["steps"]}

    def test_committed_data_is_what_the_example_produces(self):
        self.assertEqual(read(SITE / "assets/run-data.js"), self.module.TEXT)

    def test_the_window_lists_the_steps_the_data_has(self):
        self.assertEqual(re.findall(r'data-step="(\w+)"', read(FRONT)), list(self.steps))

    def test_the_finished_state_written_into_the_page_matches_the_score(self):
        front, score = read(FRONT), self.steps["score"]
        self.assertIn(f'<p class="verdict-word">{score["result"]}</p>', front)
        self.assertIn(f'<dt>可信度</dt><dd>{score["credibility"]}</dd>', front)
        self.assertIn(f'<dt>信心度</dt><dd>{score["confidence"]}<small>{score["level"]}</small></dd>', front)
        self.assertIn('<dd class="word">可公開</dd>' if score["publishable"] else '<dd class="word">不可公開</dd>', front)
        rows = re.findall(r'<li class="r-claim(?: off)?"><code>(C\d+)</code><p>([^<]*)(<small>[^<]*</small>)?</p>'
                          r'<span class="mark \w+">([^<]*)</span><span class="num">([^<]*)</span>', front)
        self.assertEqual(rows, [(r["id"], r["text"], "<small>問法在辯論中修正過</small>" if r["revised"] else "", r["label"], r["reviewed"])
                                for r in score["rows"]])

    def test_what_the_page_says_about_the_seats_is_counted_from_the_run(self):
        front, seats = read(FRONT), self.steps["opponents"]["seats"]
        total = sum(s["attacks"] for s in seats)
        outside = sum(s["attacks"] for s in seats if s["engine"] != seats[0]["engine"])
        self.assertIn(f"{total} 條質疑，有 {outside} 條是它提的", front)
        drawn = re.findall(r'<p><b>(\w+)</b><span>(\w+)</span><i style="--n:(\d+)"></i><em>(\d+)</em></p>', front)
        self.assertEqual(drawn, [(s["seat"], s["engine"], str(s["attacks"]), str(s["attacks"])) for s in seats])


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
