#!/usr/bin/env python3
"""Write the Taipei-election block of the front page from the four runs in examples/.

    python3 site/tools/build_cases.py          # rewrites the block between the two markers in site/index.html

Which four statements, and why these, is in evals/results/2026-11-20-taipei-preregistration.md, written before
any of them was run. Everything shown comes from each run's own files; nothing is rounded or reworded except
that long sentences are cut at a sentence end.
"""
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "skills/factcheck/scripts"))
FRONT = ROOT / "site/index.html"
BEGIN, END = "<!-- taipei:begin (written by site/tools/build_cases.py) -->", "<!-- taipei:end -->"
GH = "https://github.com/KKzLEO/taiwan-political-skills"
e = html.escape

# In ballot order. Each candidate: one circulating claim about them, one statement of their own from the debate.
# "text" is what was sent to the tool, word for word; "run" is the folder under examples/ once that run has
# finished (None while it has not), "minutes" how long the host took.
PEOPLE = [
    {"no": 3, "name": "沈伯洋", "party": "民進黨",
     "about": {"text": "網路流傳一段錄音，字幕寫「疑似沈姓候選人私下錄音」，內容是沈伯洋自己承認利用黑熊學院在美國軍購案收回扣。",
               "run": None, "minutes": None},
     "said": {"text": "沈伯洋在 10 月 31 日台北市長辯論會上說：「都更7599專案，現在動工的數量是零，沒有辦法動工。」",
              "run": None, "minutes": None,
              "tfc": ("資料雖符合，但僅提供部分資訊，無法瞭解全貌", "https://tfc-taiwan.org.tw/taipei-urban-renewal-7599-zero-construction-claim/")}},
    {"no": 5, "name": "蔣萬安", "party": "國民黨",
     "about": {"text": "在大稻埕聽到垃圾車廣播「市長選舉請支持蔣萬安」，這是公器私用。",
               "run": None, "minutes": None},
     "said": {"text": "蔣萬安在 10 月 31 日台北市長辯論會上說：「這四年當中，非常重視的施政原則，四年下來，臺北市總共減債超過了400億，是六都第一。」",
              "run": None, "minutes": None,
              "tfc": ("與蔣萬安所述資料相符", "https://tfc-taiwan.org.tw/chiang-taipei-debt-reduction-40-billion-facts/")}},
]
KINDS = [("about", "針對他、在流傳的說法"), ("said", "他在辯論會上說的")]


def cut(text, limit):
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    head = text[:limit]
    for mark in "。；，":
        at = head.rfind(mark)
        if at >= limit // 2:
            return head[:at] + "…"
    return head + "…"


def points(run, most=2):
    """How the heaviest claims were judged: the label, and the first sentence of the judge's reason."""
    from fclib.labels import UNSCORED_TYPES, ZH_LABELS
    claims = json.loads((run / "verdicts.json").read_text(encoding="utf-8"))["claims"]
    scored = [c for c in claims if c["type"] not in UNSCORED_TYPES and c["label"] != "not_factual" and not c.get("time")]
    scored.sort(key=lambda c: (not c.get("core"), -c["importance"]))
    out = []
    for c in scored[:most]:
        first = re.split(r"(?<=。)", " ".join(c["reasoning"].split()), maxsplit=1)[0]
        out.append((ZH_LABELS[c["label"]], cut(first, 84)))
    return out


def case(person, item):
    run = ROOT / "examples" / item["run"]
    score = json.loads((run / "score.json").read_text(encoding="utf-8"))
    sent = json.loads((run / "input.json").read_text(encoding="utf-8"))["content"].strip()
    if sent != item["text"]:
        raise SystemExit(f'{item["run"]}: the run was given a different text from the one shown')
    shown = bool(score["credibility"].get("show_on_spectrum")) and score["result"] != "無法判定"
    at = score["credibility"]["score"] if shown else 0
    blocks = score.get("publish_blocks") or []
    out = ['<article class="case">',
           f'  <p class="case-who"><b>{person["no"]}</b>{e(person["name"])}<small>{e(person["party"])}</small></p>',
           f'  <blockquote>{e(item["text"])}</blockquote>',
           f'  <p class="case-result"><strong>{e(score["result"])}</strong>'
           f'<span class="scale{"" if shown else " none"}" style="--at:{at}"><span>錯誤</span><i></i><span>正確</span></span></p>',
           '  <dl>'
           f'<div><dt>可信度</dt><dd>{at if shown else "不顯示"}</dd></div>'
           f'<div><dt>信心度</dt><dd>{score["confidence"]["score"]}<small>{e(score["confidence"]["level"])}</small></dd></div>'
           f'<div><dt>公開引用</dt><dd class="word">{"可公開" if score["publishable"] else "工具標了不可公開"}</dd></div></dl>']
    if blocks:
        out.append(f'  <p class="case-why">不可公開的原因：{e("；".join(blocks))}</p>')
    found = points(run)
    if found:
        out.append('  <ul class="case-points">' + "".join(f'<li><b>{e(label)}</b>{e(text)}</li>' for label, text in found) + '</ul>')
    if item.get("tfc"):
        out.append(f'  <p class="case-tfc">台灣事實查核中心的結論：<a href="{e(item["tfc"][1])}">{e(item["tfc"][0])}</a></p>')
    out.append(f'  <p class="case-links"><a class="link" href="{GH}/blob/main/examples/{e(item["run"])}/report.md">完整報告<svg width="16" height="16"><use href="#i-out"/></svg></a>'
               f'<a class="link" href="{GH}/tree/main/examples/{e(item["run"])}">全部檔案<svg width="16" height="16"><use href="#i-out"/></svg></a><span>{item["minutes"]} 分鐘</span></p>')
    out.append('</article>')
    return "\n".join("        " + line for line in out)


SECTION = """<section class="sec" id="taipei">
  <div class="wrap">
    <div class="sec-head">
      <h2>台北市長選舉，選前查了四則</h2>
      <p class="wide">兩位主要候選人各兩則：一則是針對他、正在流傳的說法，一則是他自己在 10 月 31 日辯論會上講的話。選哪四則、怎麼跑，都在開跑前寫好提交；結果不管好不好看，都原樣放在這裡。<a class="link" href="{gh}/blob/main/evals/results/2026-11-20-taipei-preregistration.md">開跑前的登記<svg width="16" height="16"><use href="#i-out"/></svg></a></p>
    </div>
    <div class="duo">
{rows}
    </div>
    <p class="duo-note">候選人照號次排。這四則沒有我們自己寫的答案卷，所以不算評測，是工具實際跑出來的結果；工具標「不可公開」的，代表它自己認為還不能拿去引用。</p>
  </div>
</section>"""


def ready():
    return all(p[key]["run"] for p in PEOPLE for key, _ in KINDS)


def block():
    """The whole section once all four runs are in; nothing at all before that, so that a claim about a
    candidate never stands on the page without its result beside it."""
    if not ready():
        return f"{BEGIN}\n{END}"
    rows = []
    for key, label in KINDS:
        cells = "\n".join(case(p, p[key]) for p in PEOPLE)
        rows.append(f'      <h3 class="duo-kind">{label}</h3>\n      <div class="duo-row">\n{cells}\n      </div>')
    return BEGIN + "\n" + SECTION.format(gh=GH, rows="\n".join(rows)) + "\n" + END


def rewritten(text):
    a, b = text.index(BEGIN), text.index(END) + len(END)
    return text[:a] + block() + text[b:]


if __name__ == "__main__":
    FRONT.write_text(rewritten(FRONT.read_text(encoding="utf-8")), encoding="utf-8")
    print("site/index.html: Taipei block rewritten")
