"""The report pages: each report in examples/ shown on the site as it was written, with nothing in it turned
into markup that the report did not mean, and nothing left out."""
import fnmatch
import html
import importlib.util
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SITE / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def seen(page):
    """What a reader sees of a page: its text, without the tags."""
    body = re.sub(r"<(script|style|svg)\b.*?</\1>", " ", page, flags=re.S)
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", body)).split())


def squeezed(text):
    return "".join(text.split())


class Inline(unittest.TestCase):
    def setUp(self):
        self.md = load("report_md")

    def test_text_a_model_wrote_cannot_become_markup(self):
        self.assertEqual(self.md.inline('<img src=x onerror=a()> & "q"'), "&lt;img src=x onerror=a()&gt; &amp; &quot;q&quot;")

    def test_bold_and_code_are_kept(self):
        self.assertEqual(self.md.inline("**C1：正確**。見 `fc.py render`"), "<strong>C1：正確</strong>。見 <code>fc.py render</code>")

    def test_a_link_the_report_made_is_a_link_that_shows_where_it_leads(self):
        self.assertEqual(self.md.inline("[查核中心](https://tfc-taiwan.org.tw/a-b/)"),
                         '<a href="https://tfc-taiwan.org.tw/a-b/" rel="noopener nofollow">查核中心</a><small class="host">tfc-taiwan.org.tw</small>')

    def test_a_label_that_reads_like_an_address_cannot_hide_where_the_link_goes(self):
        # a headline with a bracket of its own, as news agencies write them: still one link, to where it really goes
        out = self.md.inline("[蔣萬安反指講錯三章一Q[影]](https://www.cna.com.tw/news/aloc/1.aspx)")
        self.assertEqual(out.count("<a "), 1)
        self.assertIn('href="https://www.cna.com.tw/news/aloc/1.aspx"', out)
        self.assertIn('<small class="host">www.cna.com.tw</small>', out)
        out = self.md.inline("[a [b](https://evil.example/x) c](https://real.example/y)")  # and a link dressed up inside a label is not one
        self.assertEqual((out.count("<a "), "real.example" in out, 'href="https://evil.example' in out), (1, True, False))
        out = self.md.inline("[https://tfc-taiwan.org.tw/x](https://evil.example/tfc)")
        self.assertEqual(out.count("<a "), 1)  # the label is text, not a second link inside the first
        self.assertIn('href="https://evil.example/tfc"', out)
        self.assertIn('<small class="host">evil.example</small>', out)

    def test_an_address_with_a_name_before_the_host_is_not_followed(self):
        for text in ("[www.cec.gov.tw/news](https://www.cec.gov.tw@evil.example/news)", "見 https://www.cec.gov.tw@evil.example/news 。"):
            self.assertNotIn("<a", self.md.inline(text), text)

    def test_brackets_that_belong_to_an_address_stay_in_it(self):
        out = self.md.inline("見 https://zh.wikipedia.org/wiki/某人_(律師) 這一頁")
        self.assertIn('href="https://zh.wikipedia.org/wiki/某人_(律師)"', out)

    def test_marks_that_end_a_sentence_do_not_end_up_in_the_address(self):
        self.assertIn('<a href="https://a.tw/x" rel="noopener nofollow">https://a.tw/x</a>.', self.md.inline("see https://a.tw/x."))

    def test_a_long_run_of_brackets_or_of_full_stops_does_not_stall_it(self):
        self.assertEqual(self.md.inline("[" * 5000), "[" * 5000)
        self.assertTrue(self.md.inline("https://a.tw/x" + "." * 40000 + "x").startswith('<a href="https://a.tw/x'))

    def test_a_host_in_look_alike_letters_is_shown_as_what_it_really_is(self):
        out = self.md.inline("[查核中心](https://tfс-taiwan.org.tw/a)")  # a Cyrillic letter in place of the c
        self.assertIn('<small class="host">xn--', out)
        self.assertNotIn('<small class="host">tfc-taiwan.org.tw', out)

    def test_an_address_a_browser_would_read_another_way_is_not_followed(self):
        for text in ("https://evil.example\\.tfc-taiwan.org.tw/", "[x](https://a.tw%2f@evil.example/)"):
            self.assertNotIn("<a", self.md.inline(text), text)

    def test_an_at_sign_after_the_host_is_an_ordinary_address(self):
        self.assertIn('href="https://www.threads.net/@someone/post/1"', self.md.inline("https://www.threads.net/@someone/post/1"))

    def test_only_a_web_address_can_be_followed(self):
        for target in ("javascript:alert(1)", "data:text/html,x", "//evil.example/x", "file:///etc/passwd"):
            self.assertNotIn("<a", self.md.inline(f"[點我]({target})"), target)

    def test_a_bare_address_is_a_link_that_ends_where_the_address_ends(self):
        out = self.md.inline("中央社 https://cna.com.tw/news/a.aspx ；另見（https://x.tw/b）。")
        self.assertIn('<a href="https://cna.com.tw/news/a.aspx" rel="noopener nofollow">https://cna.com.tw/news/a.aspx</a> ；', out)
        self.assertIn('（<a href="https://x.tw/b" rel="noopener nofollow">https://x.tw/b</a>）。', out)

    def test_an_address_with_a_quote_in_it_cannot_leave_its_attribute(self):
        out = self.md.inline('https://x.tw/a"onmouseover="b')
        self.assertNotIn('"onmouseover', out.replace('&quot;', ''))
        self.assertEqual(out.count("<a "), 1)

    def test_a_label_the_report_kept_apart_from_its_address_stays_apart(self):
        out = self.md.inline("[臺中市政府業務報告] (https://a.tw/x.pdf)")
        self.assertTrue(out.startswith("[臺中市政府業務報告] ("))
        self.assertIn('<a href="https://a.tw/x.pdf"', out)

    def test_plain_gives_the_words_a_reader_sees(self):
        self.assertEqual(self.md.plain("**C1** 見 [查核中心](https://a.tw/) 和 `x`"), "C1 見 查核中心 和 x")


class Blocks(unittest.TestCase):
    def setUp(self):
        self.md = load("report_md")

    def test_the_kinds_of_block_a_report_has(self):
        text = "\n".join([
            "# 查核報告", "", "> 第一行", "", "> 第二行", "", "```text", "錯誤 ━▲━ 正確", "   50", "```", "",
            "**結果：符合**", "", "## 結論", "", "- 甲", "  - 甲之一", "  - 甲之二", "- 乙", "",
            "| 命題 | 判定 |", "|---|---|", "| C1 | 正確 |", "| C2 | 錯誤 |", "", "限制：", "- 丙"])
        blocks = self.md.parse(text)
        self.assertEqual([b[0] for b in blocks], ["h1", "quote", "quote", "fence", "p", "h2", "list", "table", "p", "list"])
        self.assertEqual(blocks[1][1:], ("第一行",))
        self.assertEqual(blocks[3][1], ["錯誤 ━▲━ 正確", "   50"])
        self.assertEqual(blocks[6][1], [("甲", ["甲之一", "甲之二"]), ("乙", [])])
        self.assertEqual(blocks[7][1:], (["命題", "判定"], [["C1", "正確"], ["C2", "錯誤"]]))


class Pages(unittest.TestCase):
    def setUp(self):
        self.build = load("build_reports")
        self.md = self.build.report_md
        self.data = self.build.taipei
        self.runs = self.data.published()

    def page(self, run):
        return (SITE / "reports" / run.name / "index.html").read_text(encoding="utf-8")

    def test_committed_pages_are_what_the_script_writes(self):
        pages = self.build.pages()
        for path, text in pages.items():
            self.assertTrue(path.exists(), path)
            self.assertEqual(path.read_text(encoding="utf-8"), text, path)
        on_disk = {p for p in (SITE / "reports").rglob("index.html")}
        self.assertEqual(on_disk, set(pages))

    def test_every_run_shown_has_its_page_and_its_row(self):
        index = (SITE / "reports/index.html").read_text(encoding="utf-8")
        self.assertEqual(sorted(re.findall(r'<li><a href="([^"/]+)/">', index)), sorted(r.name for r in self.runs))

    def test_a_statement_is_shown_only_when_the_other_candidate_s_is_in(self):
        """Of an issue's two statements, either both have a page or neither; a run alone in examples/ is one of the
        two that were public before the issues were paired."""
        shown = {r.name for r in self.runs}
        for issue in self.data.issues():
            names = [s["run"].name for s in issue["statements"] if s["run"]]
            self.assertIn(len([n for n in names if n in shown]), (0, 2), issue["id"])
            if len(names) == 1:
                self.assertIn(names[0], [s.get("earlier") for s in issue["statements"]], issue["id"])

    def test_two_runs_of_one_text_or_a_run_that_belongs_to_nothing_stop_the_build(self):
        real = self.data.EXAMPLES
        for content in (json.loads((self.runs[0] / "input.json").read_text(encoding="utf-8"))["content"], "沒有登記過的一句話。"):
            with tempfile.TemporaryDirectory() as tmp:
                copy = Path(tmp) / "examples"
                shutil.copytree(real, copy)
                stray = copy / "20991231-0000-stray"
                stray.mkdir()
                (stray / "input.json").write_text(json.dumps({"content": content}, ensure_ascii=False), encoding="utf-8")
                (stray / "report.md").write_text("x", encoding="utf-8")
                self.data.EXAMPLES = copy
                try:
                    with self.assertRaises(ValueError):
                        self.data.published()
                finally:
                    self.data.EXAMPLES = real

    def test_nothing_the_report_says_is_missing_from_its_page(self):
        for run in self.runs:
            page = self.page(run)
            shown = squeezed(seen(page))
            lines = (run / "report.md").read_text(encoding="utf-8").splitlines()
            fenced = False
            for line in lines:
                if line.startswith("```"):
                    fenced = not fenced
                    continue
                if fenced or not line.strip() or re.fullmatch(r"\|[-| :]+\|", line.strip()) or line == "# 查核報告":
                    continue  # the scale is drawn from the score, checked below
                if line.startswith("> 被查核的訊息（開頭）"):
                    continue  # the page gives the whole message instead, checked below
                cells = line.strip().strip("|").split("|") if line.startswith("|") else [re.sub(r"^(#+ |> ?| *- )", "", line)]
                for cell in cells:
                    for part in (self.md.plain(cell).split("｜") if line.startswith("**結果：") else [self.md.plain(cell)]):
                        self.assertIn(squeezed(part), shown, f"{run.name}: {part[:50]}")

    def test_the_scale_is_drawn_where_the_score_file_puts_it(self):
        for run in self.runs:
            page = self.page(run)
            score = json.loads((run / "score.json").read_text(encoding="utf-8"))
            top = page[:page.index('class="rep-body"')]
            if score["credibility"].get("show_on_spectrum") and score["result"] != "無法判定":
                self.assertIn(f'style="--at:{score["credibility"]["score"]}"', top, run.name)
            else:
                self.assertNotIn("--at:", top, run.name)
            self.assertIn(f'<strong class="verdict-word">{score["result"]}</strong>', top, run.name)

    def test_every_link_in_the_report_can_be_followed_from_the_page(self):
        for run in self.runs:
            page = self.page(run)
            report = (run / "report.md").read_text(encoding="utf-8")
            for target in re.findall(r"\]\((https?://[^)\s]+)\)", report):
                self.assertIn(f'href="{html.escape(target)}"', page, f"{run.name}: {target}")

    def test_evidence_numbers_point_at_a_source_on_the_same_page(self):
        for run in self.runs:
            page = self.page(run)
            ids = set(re.findall(r'id="(S\d+)"', page))
            pointed = set(re.findall(r'href="#(S\d+)"', page))
            self.assertTrue(pointed, run.name)
            self.assertEqual(pointed - ids, set(), run.name)

    def test_the_sections_come_in_the_report_s_order(self):
        for run in self.runs:
            report = (run / "report.md").read_text(encoding="utf-8")
            wanted = [self.md.plain(ln[3:].strip()) for ln in report.splitlines() if ln.startswith("## ")] + ["每一步的檔案"]
            self.assertEqual([html.unescape(re.sub(r"<[^>]+>", "", h)) for h in re.findall(r"<h2>(.*?)</h2>", self.page(run))], wanted, run.name)

    def test_each_claim_carries_its_own_label_reason_and_evidence(self):
        """Read from the report's table row by row: a page that shifted a column or a row would still hold every
        word somewhere."""
        for run in self.runs:
            page, checked = self.page(run), 0
            for line in (run / "report.md").read_text(encoding="utf-8").splitlines():
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                if not line.startswith("| C") or len(cells) != 6:
                    continue
                claim, said, weight, label, reason, sources = cells
                item = re.search(rf'<li id="{claim}">(.*?)</li>', page, flags=re.S).group(1)
                parts = {name: squeezed(seen(body)) for name, body in (
                    ("head", re.search(r'<p class="claim-head">(.*?)</p>', item, flags=re.S).group(1)),
                    ("said", re.search(r"<blockquote>(.*?)</blockquote>", item, flags=re.S).group(1)),
                    ("why", re.search(r'<p class="claim-why">(.*?)</p>', item, flags=re.S).group(1)),
                    ("ev", re.search(r'<p class="claim-ev">(.*?)</p>', item, flags=re.S).group(1)))}
                self.assertEqual(parts["head"], squeezed(f"命題{claim}判定{self.md.plain(label)}重要性{weight}"), (run.name, claim))
                self.assertEqual(parts["said"], squeezed(self.md.plain(said)), (run.name, claim))
                self.assertEqual(parts["why"], squeezed(self.md.plain(reason)), (run.name, claim))
                self.assertEqual(parts["ev"], squeezed("證據" + sources), (run.name, claim))
                checked += 1
            self.assertGreater(checked, 0, run.name)

    def test_the_top_of_a_page_says_what_the_files_say_and_nothing_more(self):
        """Word for word: who, the message, the result line taken apart, the notes, and the site's own fixed
        sentences. A verdict slipped in up here would be read before anything else."""
        for run in self.runs:
            page = self.page(run)
            top = seen(page[page.index('<header class="rep-top">'):page.index('<div class="rep-body">')])
            score = json.loads((run / "score.json").read_text(encoding="utf-8"))
            lines = (run / "report.md").read_text(encoding="utf-8").splitlines()
            at = next(i for i, ln in enumerate(lines) if ln.startswith("**結果："))
            first, cred, conf, mode, public = lines[at].strip("*").split("｜")
            notes = [self.md.plain(ln[1:].strip()) for ln in lines[at + 1:lines.index("## 結論")] if ln.startswith(">")]
            where = self.data.place(run)
            want = ["全部報告"]
            if where:
                person = self.data.PEOPLE[where["statement"]["who"]]
                want += ["/", "台北市長選舉・" + (where["issue"]["name"] if where["issue"] else "流傳的說法"),
                         ("" if where["issue"] else "針對") + f'{person["no"]}{person["name"]}{person["party"]}']
            want += [json.loads((run / "input.json").read_text(encoding="utf-8"))["content"], first]
            if score["credibility"] and score["credibility"].get("show_on_spectrum") and score["result"] != "無法判定":
                want.append("錯誤正確")
            want += ["可信度", cred.removeprefix("可信度 "), "信心度", conf.removeprefix("信心度 "), "模式", mode, "公開引用", public] + notes
            want += [self.build.NOTES.get(run.name, ""), self.data.CAVEATS.get(where["statement"]["id"], "") if where else "",
                     "這一頁是工具自動產生的報告，照原始檔排版，沒有人改寫過，上線前也沒有人逐篇審過。它不是查核機構的報告；要引用之前，請先看下面的證據。"
                     f'這次查核花了 {self.data.TIMES[run.name]["minutes"]} 分鐘。', "這次查核的全部檔案", "報告的原始檔"]
            self.assertEqual(squeezed(top), squeezed("".join(want)), run.name)
            self.assertTrue(first.startswith("結果：" + score["result"]), run.name)

    def test_each_row_of_the_list_gives_what_that_run_s_score_file_says(self):
        index = (SITE / "reports/index.html").read_text(encoding="utf-8")
        for run in self.runs:
            row = re.search(rf'<li><a href="{re.escape(run.name)}/">(.*?)</a></li>', index, flags=re.S).group(1)
            score = json.loads((run / "score.json").read_text(encoding="utf-8"))
            cred = score["credibility"] or {}
            shown = cred.get("show_on_spectrum") and score["result"] != "無法判定"
            self.assertIn(f'<strong>{score["result"]}</strong>', row, run.name)
            self.assertIn(f'<small>可信度</small>{cred["score"] if shown else "—"}</span>', row, run.name)
            self.assertIn(f'<small>信心度</small>{score["confidence"]["score"]}</span>', row, run.name)
            self.assertIn(f'<span class="rl-pub">{"可公開" if score["publishable"] else "不可公開"}</span>', row, run.name)
            self.assertIn(html.escape(json.loads((run / "input.json").read_text(encoding="utf-8"))["content"].strip()), row, run.name)
            where = self.data.place(run)
            if where and not where["issue"]:
                self.assertIn(f'・針對{self.data.PEOPLE[where["statement"]["who"]]["name"]}</small>', row, run.name)
            else:
                self.assertNotIn("針對", row.split("</small>")[0], run.name)

    def test_a_score_that_is_not_a_number_never_reaches_a_page(self):
        with self.assertRaises((ValueError, TypeError)):
            self.build.credibility({"result": "符合", "credibility": {"score": '50" onmouseover="x', "show_on_spectrum": True}})
        self.assertIsNone(self.build.credibility({"result": "符合", "credibility": None}))

    def test_a_report_of_another_shape_stops_the_build(self):
        with self.assertRaises(ValueError):
            self.build.table(["命題", "判定"], [["C1", "正確", "多一格"]])
        with self.assertRaises(ValueError):
            self.build.body([("fence", ["x"])])
        with self.assertRaises(ValueError):
            self.build.result_line([("p", "**結果：符合｜可信度 90**")])

    def test_only_the_files_a_run_is_known_to_leave_are_listed(self):
        patterns = [name for name, _ in self.build.FILES]
        for run in self.runs:
            page = self.page(run)
            listed = re.findall(r"<li><a href=\"[^\"]+\"><code>([^<]+)</code></a>", page[page.index('id="files"'):])
            self.assertEqual(sorted(listed), sorted(p.name for p in run.iterdir() if any(fnmatch.fnmatchcase(p.name, pat) for pat in patterns)), run.name)
            self.assertNotIn("report-with-tactics.md", listed)

    def cells(self, line):
        return [c.strip() for c in line.strip().strip("|").split("|")]

    def shown(self, cell):
        """A cell of the report as its page shows it: the words, and beside a link the host it leads to."""
        text = self.md.plain(cell)
        for target in re.findall(r"\]\((https?://[^)\s]+)\)", cell):
            text += self.md.host(target) or ""
        return squeezed(text)

    def test_each_source_stands_on_its_own_line_with_its_own_details(self):
        for run in self.runs:
            page, lines = self.page(run), (run / "report.md").read_text(encoding="utf-8").splitlines()
            head = self.cells(next(ln for ln in lines if ln.startswith("| 編號 | 來源 |")))
            rows = [self.cells(ln) for ln in lines if re.match(r"\| S\d+ \|", ln)]
            self.assertTrue(rows, run.name)
            for row in rows:
                item = re.search(rf'<li id="{row[0]}">(.*?)</li>', page, flags=re.S).group(1)
                want = head[0] + row[0] + "".join(f"{name}：{self.shown(cell)}" for name, cell in zip(head[1:], row[1:]))
                self.assertEqual(squeezed(seen(item)), squeezed(want), (run.name, row[0]))
                target = re.search(r"\]\((https?://[^)\s]+)\)", row[1])
                if target:
                    self.assertIn(f'href="{html.escape(target.group(1))}"', item, (run.name, row[0]))

    def test_every_other_table_keeps_each_cell_under_its_own_heading(self):
        for run in self.runs:
            page, lines = self.page(run), (run / "report.md").read_text(encoding="utf-8").splitlines()
            tables, at = [], 0
            while at < len(lines):
                if lines[at].startswith("|"):
                    end = at
                    while end < len(lines) and lines[end].startswith("|"):
                        end += 1
                    tables.append([self.cells(ln) for ln in lines[at:end] if not re.fullmatch(r"\|[-| :]+\|", ln.strip())])
                    at = end
                else:
                    at += 1
            seats = [tb for tb in tables if tb[0][0] == "席位"]
            others = [tb for tb in tables if tb[0][0] not in ("席位", "命題", "編號")]
            got = [[[squeezed(seen(c)) for c in re.findall(r"<t[hd]>(.*?)</t[hd]>", tr, flags=re.S)] for tr in re.findall(r"<tr>(.*?)</tr>", tb, flags=re.S)]
                   for tb in re.findall(r"<table>(.*?)</table>", page, flags=re.S)]
            self.assertEqual(got, [[[self.shown(c) for c in row] for row in tb] for tb in seats], run.name)
            entries = [[(squeezed(seen(dt)), squeezed(seen(dd))) for dt, dd in re.findall(r"<dt>(.*?)</dt><dd>(.*?)</dd>", dl, flags=re.S)]
                       for dl in re.findall(r'<div class="records">(.*?)</div>\n', page, flags=re.S) for dl in re.findall(r"<dl>(.*?)</dl>", dl, flags=re.S)]
            want = [[(squeezed(h), self.shown(c)) for h, c in zip(tb[0], row)] for tb in others for row in tb[1:]]
            self.assertEqual(entries, want, run.name)

    def test_an_evidence_number_leads_to_the_source_of_that_number(self):
        for run in self.runs:
            links = re.findall(r'<a href="#(S\d+)">(S\d+)</a>', self.page(run))
            self.assertTrue(links, run.name)
            for target, text in links:
                self.assertEqual(target, text, run.name)

    def test_the_way_to_the_other_statement_leads_to_it_and_names_whose_it_is(self):
        for run in self.runs:
            where, page = self.data.place(run), self.page(run)
            found = re.search(r'<p class="rep-next">(.*?)</p>', page, flags=re.S)
            if not where:
                self.assertIsNone(found, run.name)
                continue
            other = self.data.PEOPLE[where["other"]["who"]]
            self.assertIn(f'href="../{where["other"]["run"].name}/"', found.group(1), run.name)
            self.assertIn(f'{other["no"]} 號 {other["name"]}', seen(found.group(1)), run.name)
            self.assertEqual("針對" in seen(found.group(1)), not where["issue"], run.name)
            self.assertNotEqual(where["other"]["run"], run)

    def test_the_title_of_a_page_gives_the_result_and_says_when_a_claim_is_about_someone(self):
        for run in self.runs:
            title = html.unescape(re.search(r"<title>(.*?)</title>", self.page(run)).group(1))
            score, where = json.loads((run / "score.json").read_text(encoding="utf-8")), self.data.place(run)
            self.assertTrue(title.startswith(f'查核結果「{score["result"]}」：'), run.name)
            about = bool(where and not where["issue"])
            self.assertEqual("的流傳說法，" in title, about, run.name)
            if about:
                self.assertIn(f'針對{self.data.PEOPLE[where["statement"]["who"]]["name"]}的流傳說法，', title, run.name)

    def test_the_list_in_examples_is_what_the_script_writes(self):
        readme = (ROOT / "examples/README.md").read_text(encoding="utf-8")
        self.assertEqual(self.build.listed(readme), readme)
        for run in sorted(p.parent for p in (ROOT / "examples").glob("*/report.md")):
            line = next(ln for ln in readme.splitlines() if ln.startswith(f"| `{run.name}` |"))
            where, score = self.data.place(run), json.loads((run / "score.json").read_text(encoding="utf-8"))
            if where:
                name = self.data.PEOPLE[where["statement"]["who"]]["name"]
                self.assertIn(f'| {name}的辯論會發言（{where["issue"]["name"]}） |' if where["issue"] else f"| 針對{name}的流傳說法 |", line, run.name)
            self.assertIn(f'| {score["result"]}｜', line, run.name)
            self.assertIn(f'| {self.data.TIMES[run.name]["minutes"]} 分鐘 |', line, run.name)

    def test_no_page_names_the_machine_it_was_made_on(self):
        for path in SITE.rglob("*.html"):
            self.assertIsNone(re.search(r"/Users/|/private/tmp|/var/folders|\.work/", path.read_text(encoding="utf-8")), path)

    def test_nothing_on_a_generated_page_can_run(self):
        """Every page a script writes from the runs: no script, no handler, and no link that is not a plain one."""
        for path in [*(SITE / "reports").rglob("index.html"), SITE / "taipei/index.html"]:
            page = path.read_text(encoding="utf-8")
            body = page[page.index("<main"):page.index("</main>")]
            self.assertNotIn("<script", body, path)
            self.assertIsNone(re.search(r"<[^>]*\son\w+\s*=", body), path)
            self.assertIsNone(re.search(r'style="(?!--at:\d{1,3}")', body), path)
            for target in re.findall(r'href="([^"]*)"', body):
                self.assertRegex(target, r"^(https?://[^/?#@\\]+([/?#].*)?$|#[\w-]+$|(\.\./)+[\w%./-]*(#[\w-]+)?$|[\w%.-]+/$)", f"{path}: {target}")


if __name__ == "__main__":
    unittest.main()
