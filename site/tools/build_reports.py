#!/usr/bin/env python3
"""Write a page for every report the site shows, the list of them, and the table in examples/README.md.

    python3 site/tools/build_reports.py     # site/reports/<run>/index.html for each run, and site/reports/index.html

A page is the run's report.md set as a page: every line of it, sections in the same order. Three things are drawn
instead of printed: the scale (from score.json), the first line of the result (taken apart into the word and its
numbers) and the message, which the report only opens and the page gives whole (from input.json). What the site
adds stands apart from the report: on top, what the page is, how long the run took and where its files are; at the
foot, the list of those files. A report whose shape is not the one expected stops the build; nothing is guessed.
"""
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import report_md  # noqa: E402
import taipei  # noqa: E402
from pages import BLOB, NEXT, OUT, TREE, credibility, e, frame, load, scale, who  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples"
SITE = ROOT / "site/reports"
inline, plain = report_md.inline, report_md.plain

# The sections a report can have, by how their heading starts, and the name each goes by in an address.
SECTIONS = [("結論", "conclusion"), ("查核範圍和限制", "scope"), ("逐項判定", "claims"), ("溯源", "trace"), ("報導品質", "quality"),
            ("操弄手法", "tactics"), ("和既有查核的比對", "others"), ("法條", "law"), ("辯論後的修正", "corrections"),
            ("爭議點", "disputes"), ("已檢驗的質疑", "objections"), ("評分拆解", "score"), ("來源", "sources"), ("執行紀錄", "run")]
# How each label of a claim is marked: the colours say how a check came out and nothing else.
MARKS = {"正確": "ok", "大致正確": "ok", "部分錯誤": "warn", "誤導": "warn", "錯誤": "bad", "無法證實": "no", "非事實陳述": "no"}
CLAIM_COLUMNS = ["命題", "原文說法", "重要性", "判定", "理由", "證據"]
SEAT_COLUMN = "席位"
# What each file of a run is, for the list at the foot of a page. Only these are listed.
FILES = [("prompt.txt", "使用者下的那一句請求"), ("message.txt", "被查核的訊息"), ("input.json", "收下來的訊息，一個字都不改"),
         ("source.json", "訊息的來源資料：網址、發布時間、取得時間"), ("claims.json", "拆成一句一句可以查證的說法"),
         ("trace.json", "溯源：最早在哪裡出現、有沒有別的版本、有沒有人查過"), ("proponent.json", "正方逐句查證找到的資料"),
         ("opponent-*.json", "反方這一席提出的質疑"), ("rebuttal.json", "正方對每一條質疑的答辯"), ("judgment.json", "裁判逐條的裁決"),
         ("review-*.json", "這一席回頭覆核裁判的判定"), ("verdicts.json", "覆核之後的最後判定"), ("score.json", "程式算出來的分數"),
         ("models.json", "每一席用的模型"), ("run.json", "這次查核的設定"), ("report.md", "報告的原始檔")]
# What a reader should know about how one run went, beyond its report. What should be known about the words
# that were checked is in taipei.CAVEATS, by statement.
NOTES = {
    "20261120-1441-機車大燈罰三千": "這則訊息是我們為了測試寫的，不是實際流傳的原文。這一次是 0.2.0 發版前的實測：一個全新的 Claude Code 只拿到說明書和一句請求，自己從頭做到尾。",
    "20261121-0238-shen-kickback-recording": "這一則第一次跑到一半因為額度用完中斷，當時只做到正方的初步判定（方向和這裡的結果相同），還沒有裁判的判定；這裡是整則從頭重跑的結果。",
}
LIST_BEGIN, LIST_END = "<!-- runs:begin (written by site/tools/build_reports.py) -->", "<!-- runs:end -->"


def anchor(title, n):
    return next((name for start, name in SECTIONS if title.startswith(start)), f"part-{n}")


def split(blocks):
    """The blocks before the first section, and each section as (title, its blocks)."""
    head, sections = [], []
    for block in blocks:
        if block[0] == "h2":
            sections.append((block[1], []))
        elif sections:
            sections[-1][1].append(block)
        else:
            head.append(block)
    return head, sections


def mark(label):
    """A label as the report wrote it, with what stands in brackets after it kept beside it."""
    word, _, rest = label.partition("（")
    known = MARKS.get(word)
    if known is None:
        return e(label)
    return f'<span class="mark {known}">{e(word)}</span>' + (f"<small>（{inline(rest)}</small>" if rest else "")


def evidence(cell):
    """The source numbers of a claim, each pointing at its row in the list of sources on the same page."""
    parts = [p.strip() for p in cell.split(",")]
    if not all(re.fullmatch(r"S\d+", p) for p in parts):
        return inline(cell)
    return ", ".join(f'<a href="#{p}">{p}</a>' for p in parts)


def claims(header, rows):
    out = ['<ol class="claims">']
    for row in rows:
        c = dict(zip(header, row))
        if not re.fullmatch(r"C\d+", c["命題"]):
            raise ValueError(f"命題編號不是預期的樣子：{c['命題']!r}")
        out.append(f'<li id="{c["命題"]}"><p class="claim-head"><span class="sr">命題</span><code>{c["命題"]}</code>'
                   f'<span class="sr">判定</span>{mark(c["判定"])}<span class="claim-imp">重要性 {e(c["重要性"])}</span></p>'
                   f'<p class="label">原文說法</p><blockquote>{inline(c["原文說法"])}</blockquote>'
                   f'<p class="label">理由</p><p class="claim-why">{inline(c["理由"])}</p>'
                   f'<p class="claim-ev"><span class="label">證據</span>{evidence(c["證據"])}</p></li>')
    return "\n".join(out + ["</ol>"])


def source_list(header, rows):
    labels = "".join(f"<span>{e(h)}</span>" for h in header)
    out = [f'<div class="sources"><p class="sources-head" aria-hidden="true">{labels}</p>', "<ol>"]
    for row in rows:
        c = dict(zip(header, row))
        if not re.fullmatch(r"S\d+", c["編號"]):
            raise ValueError(f"來源編號不是預期的樣子：{c['編號']!r}")
        rest = "".join(f'<span><span class="sr">{e(h)}：</span>{inline(c[h])}</span>' for h in header[2:])
        out.append(f'<li id="{c["編號"]}"><code><span class="sr">{e(header[0])} </span>{c["編號"]}</code>'
                   f'<p><span class="sr">{e(header[1])}：</span>{inline(c[header[1]])}</p>{rest}</li>')
    return "\n".join(out + ["</ol></div>"])


def records(header, rows):
    """A table whose cells are whole paragraphs, set as one entry for each row."""
    out = ['<div class="records">']
    for row in rows:
        fields = "".join(f"<div><dt>{e(h)}</dt><dd>{inline(cell)}</dd></div>" for h, cell in zip(header, row))
        out.append(f"<dl>{fields}</dl>")
    return "\n".join(out + ["</div>"])


def table(header, rows):
    """A table of the report in the form that suits it: the claims, the sources, the seats as a table, and any
    other as one entry for each row, since its cells are sentences."""
    if any(len(row) != len(header) for row in rows):
        raise ValueError(f"表格「{'｜'.join(header)}」有一列的欄數和表頭不同")
    if header == CLAIM_COLUMNS:
        return claims(header, rows)
    if header[:2] == ["編號", "來源"]:
        return source_list(header, rows)
    if header[0] != SEAT_COLUMN:
        return records(header, rows)
    head = "".join(f"<th>{e(h)}</th>" for h in header)
    body = "".join("<tr>" + "".join(f"<td>{inline(cell)}</td>" for cell in row) + "</tr>" for row in rows)
    return f'<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def body(blocks):
    out = []
    for block in blocks:
        kind = block[0]
        if kind == "p":
            out.append(f"<p>{inline(block[1])}</p>")
        elif kind == "quote":
            out.append(f'<p class="aside">{inline(block[1])}</p>')
        elif kind == "list":
            items = "".join("<li>" + inline(item) + ("<ul>" + "".join(f"<li>{inline(s)}</li>" for s in subs) + "</ul>" if subs else "") + "</li>"
                            for item, subs in block[1])
            out.append(f"<ul>{items}</ul>")
        elif kind == "table":
            out.append(table(block[1], block[2]))
        else:  # a kind of block no report has had inside a section: stop rather than leave it out
            raise ValueError(f"報告的段落裡有沒處理過的區塊：{kind}")
    return "\n".join(out)


def files(run):
    rows = []
    for pattern, what in FILES:
        for path in sorted(run.glob(pattern)):
            rows.append(f'<li><a href="{BLOB}examples/{e(run.name)}/{e(path.name)}"><code>{e(path.name)}</code></a><span>{e(what)}</span></li>')
    return "\n".join(rows)


def result_line(head):
    """The five parts of the line a report gives its result in, and the notes under it."""
    at = next(i for i, b in enumerate(head) if b[0] == "p" and b[1].startswith("**結果："))
    parts = plain(head[at][1]).split("｜")
    if len(parts) != 5:
        raise ValueError(f"結果行不是預期的五段：{head[at][1]}")
    return parts, [b[1] for b in head[at + 1:] if b[0] == "quote"]


def tag(where):
    """What a registered statement is, in a few words, for the path on its page and its row in the list."""
    return "台北市長選舉・" + (where["issue"]["name"] if where["issue"] else "流傳的說法")


def page(run):
    head, sections = split(report_md.parse((run / "report.md").read_text(encoding="utf-8")))
    score, message = load(run, "score.json"), load(run, "input.json")["content"].strip()
    where, minutes = taipei.place(run), int(taipei.TIMES[run.name]["minutes"])
    (first, cred, conf, mode, public), notes = result_line(head)
    word = score["result"]
    if not (first.startswith("結果：" + word) and cred.startswith("可信度 ") and conf.startswith("信心度 ") and "公開" in public):
        raise ValueError(f"{run.name}：結果行和 score.json 對不上，或欄位不是預期的順序")
    aside = first.removeprefix("結果：" + word)  # what the report puts in brackets after the word, if anything

    crumbs = ['<a href="../">全部報告</a>']
    if where:
        crumbs.append(f'<a href="../../taipei/#{where["issue"]["id"] if where["issue"] else "about"}">{e(tag(where))}</a>')
    at = credibility(score)
    fields = [("可信度", cred.removeprefix("可信度 "), ""), ("信心度", conf.removeprefix("信心度 "), ' class="word"'),
              ("模式", mode, ' class="word"'), ("公開引用", public, ' class="word"')]
    said = [NOTES.get(run.name), taipei.CAVEATS.get(where["statement"]["id"]) if where else None]
    top = [f'<p class="rep-path">{"<i>/</i>".join(crumbs)}</p>',
           who(taipei.PEOPLE[where["statement"]["who"]], about=not where["issue"]) if where else "",
           f'<h1 class="rep-msg{" long" if len(message) > 70 else ""}">{e(message)}</h1>',
           f'<div class="verdict"><p><span class="sr">結果：</span><strong class="verdict-word">{e(word)}</strong>'
           + (f'<small class="verdict-alt">{e(aside)}</small>' if aside else "") + "</p>" + (scale(at) if at is not None else "")
           + "<dl>" + "".join(f"<div><dt>{name}</dt><dd{cls}>{e(value)}</dd></div>" for name, value, cls in fields) + "</dl></div>",
           '<ul class="rep-notes">' + "".join(f"<li>{inline(n)}</li>" for n in notes) + "</ul>" if notes else "",
           '<div class="rep-what">'
           + "".join(f"<p>{e(s)}</p>" for s in said if s)
           + f"<p>這一頁是工具自動產生的報告，照原始檔排版，沒有人改寫過，上線前也沒有人逐篇審過。它不是查核機構的報告；要引用之前，請先看下面的證據。這次查核花了 {minutes} 分鐘。</p>"
           + f'<p class="rep-links"><a class="link" href="{TREE}examples/{e(run.name)}">這次查核的全部檔案{OUT}</a>'
           + f'<a class="link" href="{BLOB}examples/{e(run.name)}/report.md">報告的原始檔{OUT}</a></p></div>']

    toc, parts_html = [], []
    for n, (title, blocks) in enumerate(sections, 1):
        name = anchor(title, n)
        toc.append(f'<a href="#{name}">{e(title.split("（")[0])}</a>')
        parts_html.append(f'<section id="{name}">\n<h2>{inline(title)}</h2>\n{body(blocks)}\n</section>')
    toc.append('<a href="#files">每一步的檔案</a>')
    beside = ""
    if where:
        other = taipei.PEOPLE[where["other"]["who"]]
        kind, lead = ("同一個議題，另一位候選人的那一句", "") if where["issue"] else ("同一類說法，另一則", "針對 ")
        beside = (f'<p class="rep-next">{kind}：<a class="link" href="../{e(where["other"]["run"].name)}/">'
                  f'{lead}{int(other["no"])} 號 {e(other["name"])}{NEXT}</a></p>')
    main = f'''<main class="wrap rep">
<header class="rep-top">
{chr(10).join(t for t in top if t)}
</header>
<div class="rep-body">
<nav class="rep-toc" aria-label="這份報告的段落">{"".join(toc)}</nav>
<article class="rep-doc">
{chr(10).join(parts_html)}
<section id="files" class="rep-files">
<h2>每一步的檔案</h2>
<p>這次查核的每個角色各交出一個檔案，都放在公開的 repo 裡。這一段是網站加的，不在報告裡。</p>
<ul>
{files(run)}
</ul>
</section>
{beside}
</article>
</div>
</main>'''
    opening = message if len(message) <= 60 else message[:60] + "…"
    about = f'針對{taipei.PEOPLE[where["statement"]["who"]]["name"]}的流傳說法，' if where and not where["issue"] else ""
    return frame("../../", "reports/", f"查核結果「{word}」：{about}{opening}", f"工具自動產生的查核報告，原樣呈現。結果：{word}。被查核的訊息：{opening}", main)


def row(run):
    score, message = load(run, "score.json"), load(run, "input.json")["content"].strip()
    where, created = taipei.place(run), load(run, "run.json")["created_at"]
    if not re.fullmatch(r"\d{4}-\d\d-\d\dT[\d:]+[+-][\d:]+", created):
        raise ValueError(f"{run.name}：run.json 的建立時間不是預期的格式")
    at = credibility(score)
    what = tag(where) + ("" if where["issue"] else "・針對" + taipei.PEOPLE[where["statement"]["who"]]["name"]) if where else taipei.OTHER[run.name]
    return (f'<li><a href="{e(run.name)}/"><time datetime="{created}">{created[5:10].replace("-", "/")}</time>'
            f'<span class="rl-msg"><small>{e(what)}</small>{e(message)}</span>'
            f'<strong>{e(score["result"])}</strong>'
            f'<span class="rl-num"><small>可信度</small>{"—" if at is None else at}</span>'
            f'<span class="rl-num"><small>信心度</small>{int(score["confidence"]["score"])}</span>'
            f'<span class="rl-pub">{"可公開" if score["publishable"] is True else "不可公開"}</span></a></li>')


def index(runs):
    newest = sorted(runs, key=lambda r: load(r, "run.json")["created_at"], reverse=True)
    main = f'''<main class="wrap doc">
<header class="top">
  <h1>全部報告</h1>
  <p>放進公開 repo 的 <code>examples/</code>、可以在網站上直接看的查核報告，一共 {len(newest)} 份，新的在前面。點進去是整份報告：結論、逐項判定、每一筆來源，和每個角色交出來的檔案。發版前盲測的 12 則不在這裡，在<a href="../results/">驗證結果</a>那一頁。</p>
  <p>報告是工具自動產生的，上線前沒有人逐篇審過；它不是查核機構的報告。工具自己標「不可公開」的，代表它認為這次查核還不能拿整則結論去引用，我們照樣放上來。</p>
</header>
<section>
  <ol class="rep-list">
{chr(10).join("    " + row(r) for r in newest)}
  </ol>
  <p class="note">「可信度」是訊息本身有多正確（0 到 100），有些結果不給分數。「信心度」是這次查得多扎實。兩個數字的算法寫在每份報告的「評分拆解」。針對候選人的流傳說法，分數低代表那個說法站不住，不是候選人說了假話。</p>
</section>
</main>'''
    return frame("../", "reports/", "全部報告", f"台灣訊息查核 skill 放在公開 repo 的 {len(newest)} 份查核報告，每一份都可以在網站上直接看完整內容。", main)


def listed(readme):
    """examples/README.md with its table of runs as it should be now, oldest first. Every folder is in it, shown on
    the site or not."""
    rows = ["| 資料夾 | 輸入 | 結果 | 主體 | 時間 |", "|---|---|---|---|---|"]
    for run in sorted((p.parent for p in EXAMPLES.glob("*/report.md")), key=lambda r: load(r, "run.json")["created_at"]):
        where = taipei.place(run)
        if where:
            name = taipei.PEOPLE[where["statement"]["who"]]["name"]
            what = f'{name}的辯論會發言（{where["issue"]["name"]}）' if where["issue"] else f"針對{name}的流傳說法"
        else:
            what = taipei.OTHER[run.name]
        parts, _ = result_line(split(report_md.parse((run / "report.md").read_text(encoding="utf-8")))[0])
        rows.append(f'| `{run.name}` | {what} | {"｜".join(parts).removeprefix("結果：")} | {load(run, "run.json")["host"]} | {int(taipei.TIMES[run.name]["minutes"])} 分鐘 |')
    a, b = readme.index(LIST_BEGIN), readme.index(LIST_END)
    return readme[:a] + LIST_BEGIN + "\n" + "\n".join(rows) + "\n" + readme[b:]


def pages():
    """Every file under site/reports this script is responsible for, by its path."""
    runs = taipei.published()
    if not runs:
        raise ValueError("examples/ 裡沒有任何可以顯示的報告；不產生頁面，也不刪掉現有的")
    out = {SITE / run.name / "index.html": page(run) for run in runs}
    out[SITE / "index.html"] = index(runs)
    return out


if __name__ == "__main__":
    made = pages()
    readme = EXAMPLES / "README.md"
    table_text = listed(readme.read_text(encoding="utf-8"))  # everything is worked out before anything is written
    for folder in SITE.glob("*/"):
        if folder / "index.html" not in made:
            shutil.rmtree(folder)
    for path, text in made.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    readme.write_text(table_text, encoding="utf-8")
    print(f"site/reports: {len(made) - 1} reports and the list; examples/README.md: its table")
