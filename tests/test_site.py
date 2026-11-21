"""The public pages. The results page is whatever the records produce, the front page agrees with it, and
nothing on either page points at something that is not there."""
import html
import importlib.util
from datetime import datetime
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
FRONT = SITE / "index.html"
RESULTS = SITE / "results/index.html"
REPO = "https://github.com/KKzLEO/taiwan-political-skills"
sys.path.insert(0, str(ROOT / "skills/factcheck/scripts"))  # the labels, read from the skill itself


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

    def test_the_window_in_the_page_is_what_the_script_writes(self):
        self.assertEqual(self.module.rewritten(read(FRONT)), read(FRONT))

    def test_the_window_lists_the_steps_the_data_has(self):
        self.assertEqual(re.findall(r'data-step="(\w+)"', read(FRONT)), list(self.steps))
        for step in self.steps.values():
            self.assertIn(f'<b>{step["name"]}</b><span>{step["summary"]}</span>', read(FRONT))

    def test_the_reply_shown_is_the_opening_of_the_report_word_for_word(self):
        """The window ends on what the host says back. The skill has it copy these lines from report.md
        unchanged, so the page shows them from the report and nothing else stands in the reply."""
        report = read(self.module.RUN / "report.md").splitlines()
        reply, front = self.module.reply(), read(FRONT)
        self.assertIn("**" + reply["result"] + "**", report)
        self.assertTrue(reply["result"].startswith("結果：" + self.steps["score"]["result"] + "｜"))
        low, bar, high, value = reply["scale"]
        self.assertIn(f"{low} {bar} {high}", report)
        self.assertEqual(report[report.index(f"{low} {bar} {high}") + 1].strip(), value)
        self.assertEqual(value, str(self.steps["score"]["credibility"]))
        self.assertEqual(["> " + note for note in reply["notes"]],
                         [ln for ln in report[:report.index("## 結論")] if ln.startswith("> ") and "被查核的" not in ln])
        for line in [reply["result"], bar, *reply["notes"]]:
            self.assertIn(line, front)

    def test_the_time_on_the_window_is_the_measured_one(self):
        self.assertIn(f"| 從開始到回報 | {self.module.MINUTES} 分鐘 |", read(ROOT / "evals/results/2026-11-20-hosts.md"))
        self.assertIn(f"{self.module.MINUTES} 分鐘", self.module.block())

    def test_what_the_page_says_about_the_seats_is_counted_from_the_run(self):
        front, seats = read(FRONT), self.steps["opponents"]["seats"]
        total = sum(s["attacks"] for s in seats)
        outside = sum(s["attacks"] for s in seats if s["engine"] != seats[0]["engine"])
        self.assertIn(f"{total} 條質疑，有 {outside} 條是它提的", front)
        drawn = re.findall(r'<p(?: class="out")?><b>(\w+)</b><span>(\w+)</span><i style="--n:(\d+)"></i><em>(\d+)</em></p>', front)
        self.assertEqual(drawn, [(s["seat"], s["engine"], str(s["attacks"]), str(s["attacks"])) for s in seats])


class Taipei(unittest.TestCase):
    """The election pages: what the script produces, both candidates under every issue shown, the registered texts,
    and each number checked against the score file of the run it belongs to."""

    def setUp(self):
        spec = importlib.util.spec_from_file_location("build_cases", SITE / "tools/build_cases.py")
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.data = self.module.taipei
        self.page = read(SITE / "taipei/index.html")
        self.people = list(self.data.PEOPLE.values())
        self.shown = [(i["id"], i["statements"]) for i in self.data.issues() if i["ready"]]

    def sections(self):
        return re.findall(r'<section id="([\w-]+)" class="tp-issue">(.*?)</section>', self.page, flags=re.S)

    def test_committed_block_is_what_the_script_writes(self):
        self.assertEqual(self.module.rewritten(read(FRONT)), read(FRONT))

    def test_committed_page_is_what_the_script_writes(self):
        self.assertEqual(self.page, self.module.page())

    def test_every_issue_shown_has_both_candidates_in_ballot_order(self):
        self.assertEqual([name for name, _ in self.sections()], [name for name, _ in self.shown] + ["about"])
        for name, body in self.sections():
            self.assertEqual([int(n) for n in re.findall(r'<p class="case-who">(?:<span>針對</span>)?<b>(\d+)</b>', body)],
                             [p["no"] for p in self.people], name)

    def test_each_issue_stands_under_its_own_name_with_its_own_statements(self):
        """Read from the registered list itself: the heading and the line under it are that issue's, and the two
        statements under them are the two registered for it."""
        listed = {i["id"]: i for i in json.loads(read(ROOT / "evals/results/2026-11-22-taipei-issues.json"))["issues"]}
        for name, body in self.sections():
            if name == "about":
                continue
            issue = listed[name]
            self.assertIn(f'<h2>{html.escape(issue["name"])}</h2>\n  <p>{html.escape(issue["about"])}</p>', body, name)
            quotes = [html.unescape(q) for q in re.findall(r"<blockquote>(.*?)</blockquote>", body)]
            self.assertEqual(sorted(quotes), sorted(s["text"] for s in issue["statements"]), name)
        front = read(FRONT)
        for target, shown in re.findall(r'<li><a href="taipei/#([\w-]+)"><span>([^<]*)</span>', front):
            self.assertEqual(html.unescape(shown), listed[target]["name"], target)

    def test_how_long_a_run_took_is_what_its_start_and_end_say(self):
        """Straight from examples/times.json, not through the page's own code."""
        times = json.loads(read(ROOT / "examples/times.json"))
        for (name, body), statements in zip(self.sections(), [s for _, s in self.shown] + [self.data.about()]):
            for card, statement in zip(re.findall(r'<article class="case">(.*?)</article>', body, flags=re.S), statements):
                took = times[statement["run"].name]
                start, end = (datetime.fromisoformat(took[k]) for k in ("start", "end"))
                self.assertLessEqual(abs((end - start).total_seconds() / 60 - took["minutes"]), 1.5, statement["id"])
                self.assertIn(f'<span>{took["minutes"]} 分鐘</span>', card, statement["id"])
                page = read(SITE / "reports" / statement["run"].name / "index.html")
                self.assertIn(f'這次查核花了 {took["minutes"]} 分鐘。', page, statement["id"])

    def test_each_card_says_what_its_run_s_files_say(self):
        """Card by card against the score file: the words, the result, both numbers, whether it may be quoted and
        why not. Two cards swapped, or a number put under the wrong name, fails here."""
        for (name, body), statements in zip(self.sections(), [s for _, s in self.shown] + [self.data.about()]):
            cards = re.findall(r'<article class="case">(.*?)</article>', body, flags=re.S)
            self.assertEqual(len(cards), len(statements), name)
            for card, statement in zip(cards, statements):
                score = json.loads(read(statement["run"] / "score.json"))
                person = self.data.PEOPLE[statement["who"]]
                cred = score["credibility"] or {}
                on_scale = cred.get("show_on_spectrum") and score["result"] != "無法判定"
                self.assertIn(f'<b>{person["no"]}</b>{person["name"]}<small>{person["party"]}</small>', card, statement["id"])
                self.assertIn(f'<blockquote>{html.escape(statement["text"])}</blockquote>', card, statement["id"])
                self.assertIn(f'<p class="case-result"><strong>{score["result"]}</strong>', card, statement["id"])
                self.assertIn(f'<dt>可信度</dt><dd>{cred["score"] if on_scale else "不顯示"}</dd>', card, statement["id"])
                self.assertEqual(f'style="--at:{cred.get("score")}"' in card, bool(on_scale), statement["id"])
                self.assertIn(f'<dt>信心度</dt><dd>{score["confidence"]["score"]}<small>{score["confidence"]["level"]}</small></dd>', card, statement["id"])
                self.assertIn(f'<dd class="word">{"可公開" if score["publishable"] else "不可公開"}</dd>', card, statement["id"])
                for reason in score.get("publish_blocks") or []:
                    self.assertIn(html.escape(reason), card, statement["id"])
                self.assertEqual("工具自己標了不可公開" in card, not score["publishable"], statement["id"])
                self.assertIn(f'href="../reports/{statement["run"].name}/">完整報告', card, statement["id"])
                self.assertIn(f'href="{REPO}/tree/main/examples/{statement["run"].name}">全部檔案', card, statement["id"])
                if not on_scale:
                    self.assertIn(f'<span class="case-reason">{html.escape(score.get("result_reason") or "")}</span>', card, statement["id"])
                note = self.data.CAVEATS.get(statement["id"])
                self.assertEqual('<p class="case-note">' in card, bool(note), statement["id"])
                if note:
                    self.assertIn(html.escape(note), card, statement["id"])
                self.assertIn(f'<span>{self.data.TIMES[statement["run"].name]["minutes"]} 分鐘</span>', card, statement["id"])
                self.lines_come_from_the_files(card, statement)

    def lines_come_from_the_files(self, card, statement):
        """Which claims a card lists, under which labels, and every sentence it gives as a reason, worked out here
        from the run's files and not from the page's own code: the two heaviest scored claims in the final
        verdicts; each sentence is the opening of the final reason, of the judge's reason, or of what a reviewing
        seat wrote, and says which."""
        from fclib.labels import UNSCORED_TYPES, ZH_LABELS
        run = statement["run"]
        verdicts, judged = json.loads(read(run / "verdicts.json")), json.loads(read(run / "judgment.json"))
        was = {v["claim_id"]: v for v in judged["verdicts"]}
        kept = {d["claim_id"]: d["label_kept"] for d in verdicts.get("disputes", [])}
        reviews = {}
        for path in sorted(run.glob("review-*.json")):
            for r in json.loads(read(path))["reviews"]:
                reviews.setdefault(r["claim_id"], []).append(r)
        scored = [c for c in verdicts["claims"] if c["type"] not in UNSCORED_TYPES and c["label"] != "not_factual" and not c.get("time")]
        scored.sort(key=lambda c: (not c.get("core"), -c["importance"]))
        items = re.findall(r"<li><b>([^<]+)</b>(.*?)</li>", card, flags=re.S)
        self.assertEqual([label for label, _ in items], [ZH_LABELS[c["label"]] for c in scored[:2]], statement["id"])

        def opens(line, source):
            flat = " ".join(source.split())
            return flat.startswith(html.unescape(line).rstrip("…")) and len(line) > 8

        for (label, body), claim in zip(items, scored[:2]):
            cid = claim["claim_id"]
            for line in re.findall(r"<span>(.*?)</span>", body, flags=re.S):
                if m := re.fullmatch(r"裁判判「([^」]+)」：(.*)", line, flags=re.S):
                    self.assertIs(kept.get(cid), False, (statement["id"], cid))
                    self.assertEqual(m.group(1), ZH_LABELS[was[cid]["label"]], (statement["id"], cid))
                    self.assertTrue(opens(m.group(2), was[cid]["reasoning"]), (statement["id"], cid, line))
                elif m := re.fullmatch(r"(.+?)覆核時不同意：(.*)", line, flags=re.S):
                    self.assertIs(kept.get(cid), False, (statement["id"], cid))
                    against = [r for r in reviews.get(cid, []) if not r["pass"] and r.get("label_ok") is not True]
                    self.assertTrue(any(opens(m.group(2), r["reason"]) for r in against), (statement["id"], cid, line))
                elif m := re.fullmatch(r"(.+?)覆核時同意這個判定，但認為理由或證據還有缺漏：(.*)", line, flags=re.S):
                    self.assertIs(kept.get(cid), True, (statement["id"], cid))
                    agreeing = [r for r in reviews.get(cid, []) if not r["pass"] and r.get("label_ok") is True]
                    self.assertTrue(any(opens(m.group(2), r["reason"]) for r in agreeing), (statement["id"], cid, line))
                elif m := re.fullmatch(r"覆核沒有通過或沒有完成，所以這一條改列「([^」]+)」。", line):
                    self.assertIs(kept.get(cid), False, (statement["id"], cid))
                    self.assertEqual(m.group(1), ZH_LABELS[claim["label"]], (statement["id"], cid))
                else:
                    self.assertTrue(opens(line, claim["reasoning"]), (statement["id"], cid, line))

    def test_the_four_statements_of_the_first_registration_are_all_on_the_site(self):
        """They were promised a place on the front page whatever came out. Two of them now stand under an issue,
        which shows only once the other candidate's statement is in: until then nothing new may go out."""
        shown = {r.name for r in self.data.published()}
        first = [s["run"] for s in self.data.about()] + [s["run"] for i in self.data.issues() for s in i["statements"] if "earlier" in s]
        self.assertEqual(len(first), 4)
        for run in first:
            self.assertIsNotNone(run)
            self.assertIn(run.name, shown)
        front = read(FRONT)
        for issue in self.data.issues():
            if any("earlier" in s for s in issue["statements"]):
                self.assertIn(f'href="taipei/#{issue["id"]}"', front, issue["id"])

    def test_a_seat_that_agreed_with_the_label_is_never_quoted_as_having_refused_it(self):
        """Two seats may both fail a claim's review for different reasons. When the label fell, the one quoted
        against it has to be a seat that would not confirm it."""
        source = ROOT / "examples/20261120-2249-garbage-truck-broadcast"
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / source.name
            shutil.copytree(source, run)
            (run / "review-A.json").write_text(json.dumps({"seat": "A", "reviews": [
                {"claim_id": "C1", "pass": False, "label_ok": True, "reason": "「錯誤」這個判定可以維持，但理由少寫了一份音檔。"}]}, ensure_ascii=False), encoding="utf-8")
            (claim, label, lines), = self.module.points(run, most=1)
            said = next(ln for ln in lines if "覆核時不同意：" in ln)
            self.assertNotIn("可以維持", said)
            self.assertTrue(said.startswith("另一家公司的模型覆核時不同意："))

    def test_a_run_held_back_without_a_reason_on_file_still_says_so(self):
        source = self.data.about()[0]
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / source["run"].name
            shutil.copytree(source["run"], run)
            score = json.loads(read(run / "score.json"))
            score.update(publishable=False, publish_blocks=[])
            (run / "score.json").write_text(json.dumps(score, ensure_ascii=False), encoding="utf-8")
            real = self.data.TIMES
            card = self.module.case(dict(source, run=run), about=True)
            self.assertIn("不可公開", card)
            self.assertIn("這一份的分數檔沒有寫原因，請看完整報告。", card)
            self.assertIs(self.data.TIMES, real)

    def test_a_claim_about_a_candidate_is_never_shown_as_his_own_statement(self):
        about = dict(self.sections())["about"]
        self.assertEqual(about.count("<span>針對</span>"), len(self.people))
        for name, body in self.sections():
            if name != "about":
                self.assertNotIn("<span>針對</span>", body, name)

    def test_an_issue_with_one_run_missing_is_not_shown_at_all(self):
        issue = dict(self.data.issues()[0])
        issue["statements"] = [dict(issue["statements"][0]), dict(issue["statements"][1], run=None)]
        issue["ready"] = False
        self.assertEqual(self.module.issue_section(issue), "")
        front = read(FRONT)
        for waiting in (i for i in self.data.issues() if not i["ready"]):
            for s in waiting["statements"]:
                self.assertNotIn(html.escape(s["text"]), self.page, s["id"])
                self.assertNotIn(html.escape(s["text"]), front, s["id"])
            self.assertNotIn(f'taipei/#{waiting["id"]}"', front)

    def test_the_texts_shown_are_the_ones_registered_before_the_runs(self):
        registered = read(ROOT / self.data.FIRST[0]) + read(ROOT / self.data.SECOND[0])
        quotes = re.findall(r"<blockquote>(.*?)</blockquote>", self.page)
        self.assertEqual(len(quotes), 2 * (len(self.shown) + 1))
        for quote in quotes:
            self.assertIn("「" + html.unescape(quote) + "」", registered)

    def test_the_front_page_table_has_a_line_for_each_issue_that_is_in_with_what_the_score_files_say(self):
        front = read(FRONT)
        head = re.search(r'<p class="sheet-head"><span>議題</span>(.*?)</p>', front).group(1)
        self.assertEqual(re.findall(r"<span><b>(\d+)</b>([^<]+)</span>", head), [(str(p["no"]), p["name"]) for p in self.people])
        rows = re.findall(r'<li><a href="taipei/#([\w-]+)"><span>[^<]*</span>(.*?)</a></li>', front)
        self.assertEqual([name for name, _ in rows], [name for name, _ in self.shown])
        for (_, cells), (_, statements) in zip(rows, self.shown):
            got = re.findall(r'<span class="tp-r"><strong>([^<]+)</strong>(?:<i class="bar" style="--at:(\d+)"></i><code>(\d+)</code>|<small>不給可信度分數</small>)(<em>不可公開</em>)?</span>', cells)
            want = []
            for s in statements:
                score = json.loads(read(s["run"] / "score.json"))
                cred = score["credibility"] or {}
                n = str(cred["score"]) if cred.get("show_on_spectrum") and score["result"] != "無法判定" else ""
                want.append((score["result"], n, n, "" if score["publishable"] else "<em>不可公開</em>"))
            self.assertEqual(got, want)

    def test_the_two_circulating_claims_stand_apart_on_the_front_page_each_named_as_about_someone(self):
        front = read(FRONT)
        block = front[front.index('<div class="sheet tp-about">'):front.index("<!-- taipei:end -->")]
        rows = re.findall(r'<span class="tp-whom">針對<b>(\d+)</b>([^<]+)</span><span class="tp-claim">(.*?)</span><strong>([^<]+)</strong>(<em>不可公開</em>)?</a>', block)
        want = []
        for s in self.data.about():
            score, person = json.loads(read(s["run"] / "score.json")), self.data.PEOPLE[s["who"]]
            want.append((str(person["no"]), person["name"], html.escape(s["text"]), score["result"], "" if score["publishable"] else "<em>不可公開</em>"))
        self.assertEqual(rows, want)
        self.assertNotIn("--at:", block)  # no place on the scale under a name: a low score here is not his

    def test_a_review_that_did_not_pass_is_told_as_what_it_was(self):
        """Two different things end in "review did not pass": the reviewer would not confirm the label (the claim
        becomes unverified), or agreed with the label and found the reasons incomplete (the label stays)."""
        told = set()
        for run in sorted((ROOT / "examples").iterdir()):
            if not (run / "verdicts.json").exists():
                continue
            kept = {d["claim_id"]: d["label_kept"] for d in json.loads(read(run / "verdicts.json")).get("disputes", [])}
            for claim, _label, lines in self.module.points(run, most=99):
                text = " ".join(lines)
                self.assertEqual("改列" in text, kept.get(claim) is False, f"{run.name} {claim}")
                self.assertEqual("同意這個判定" in text, kept.get(claim) is True, f"{run.name} {claim}")
                told.add(kept.get(claim))
        self.assertEqual(told, {None, True, False})  # the examples hold all three, so each wording is exercised

    def test_every_run_has_how_long_it_took(self):
        for run in sorted((ROOT / "examples").glob("*/report.md")):
            self.assertIsInstance(self.data.TIMES[run.parent.name]["minutes"], int, run.parent.name)

    def test_no_file_of_a_run_carries_a_survey_figure(self):
        """No poll may be published in the ten days before the vote, and the pages say none is. Every file of a run
        is public in the repository, so every one of them is read."""
        asked = r"(民調|民意調查|支持度|支持率|滿意度|看好度)"
        figure = r"(\d+(\.\d+)?\s*([%％趴]|個?百分點|成)|百分之[\d零一二三四五六七八九十]+|[一二三四五六七八九]成)"
        near = re.compile(asked + r"[^。；\n]{0,40}?" + figure + "|" + figure + r"[^。；\n]{0,40}?" + asked)
        for path in sorted((ROOT / "examples").glob("*/*")):
            if path.suffix in (".json", ".md", ".txt") and path.parent.is_dir() and path.parent.name != "examples":
                self.assertIsNone(near.search(read(path)), f"{path.parent.name}/{path.name}")


class Links(unittest.TestCase):
    def pages(self):
        return [(path, read(path)) for path in sorted(SITE.rglob("*.html"))]

    def test_local_files_the_pages_ask_for_exist_and_so_do_the_places_in_them(self):
        for page, text in self.pages():
            for target in re.findall(r'(?:href|src)="([^"]+)"', text):
                if re.match(r"(https?:|#|data:|mailto:)", target):
                    continue
                where, _, spot = target.partition("#")
                path = (page.parent / unquote(where.split("?")[0])).resolve()
                self.assertTrue(path.exists(), f"{page.relative_to(SITE)}: {target}")
                if spot:  # a link to a place on another page lands on something there
                    other = path / "index.html" if path.is_dir() else path
                    self.assertIn(f'id="{spot}"', read(other), f"{page.relative_to(SITE)}: {target}")

    def test_links_into_the_repository_point_at_things_that_exist(self):
        for page, text in self.pages():
            for target in re.findall(re.escape(REPO) + r'/(?:blob|tree)/(?:main|[0-9a-f]{40})/([^"#]+)', text):
                self.assertTrue((ROOT / unquote(target)).exists(), f"{page.name}: {target}")

    def test_links_inside_a_page_land_on_something(self):
        for page, text in self.pages():
            ids = set(re.findall(r'id="([^"]+)"', text))
            for anchor in re.findall(r'href="#([^"]+)"', text):
                self.assertIn(anchor, ids, f"{page.name}: #{anchor}")


if __name__ == "__main__":
    unittest.main()
