#!/usr/bin/env python3
"""Write the Taipei-election pages from the runs in examples/.

    python3 site/tools/build_cases.py     # site/taipei/index.html, and the block between the two markers in site/index.html

Which statements, and why these, is in the two registrations under evals/results/, each pushed before any of its
statements was run; site/tools/taipei.py reads them. Everything shown comes from each run's own files; nothing is
rounded or reworded except that long sentences are cut at a sentence end. An issue is shown only when both of its
statements have been run, so one candidate's statement never stands on a page without the other's beside it.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "skills/factcheck/scripts"))
import taipei  # noqa: E402
from pages import BLOB, GH, NEXT, OUT, TREE, credibility, e, frame, load, scale, who  # noqa: E402

FRONT = ROOT / "site/index.html"
PAGE = ROOT / "site/taipei/index.html"
BEGIN, END = "<!-- taipei:begin (written by site/tools/build_cases.py) -->", "<!-- taipei:end -->"
ABOUT_NAME = "針對候選人、在流傳的說法"


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


def first(text, count=1):
    return "".join(re.split(r"(?<=。)", " ".join(text.split()))[:count])


def points(run, most=2):
    """How the heaviest claims came out: the claim, its label and the first sentence of the reason. A claim whose
    review did not pass also shows the reviewing seat's side. That is one of two things: the seat would not confirm
    the label, so the claim was relisted as unverified; or it agreed with the label and found the reasons incomplete."""
    from fclib.labels import UNSCORED_TYPES, ZH_LABELS
    from fclib.render import LENS
    judged = {v["claim_id"]: v for v in load(run, "judgment.json")["verdicts"]}
    seats = {s["seat"]: s for s in load(run, "models.json")["seats"]}
    refused = {}  # for each claim, the reviews that did not pass: (seat, reason, whether the seat agreed with the label)
    for path in sorted(run.glob("review-*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        for r in doc["reviews"]:
            if not r["pass"]:
                refused.setdefault(r["claim_id"], []).append((doc["seat"], r["reason"], r.get("label_ok") is True))
    verdicts = load(run, "verdicts.json")
    kept = {d["claim_id"]: d["label_kept"] for d in verdicts.get("disputes", [])}
    claims = [c for c in verdicts["claims"]
              if c["type"] not in UNSCORED_TYPES and c["label"] != "not_factual" and not c.get("time")]
    claims.sort(key=lambda c: (not c.get("core"), -c["importance"]))

    def seat_name(seat):
        return "另一家公司的模型" if seats[seat]["kind"] == "external" else LENS[seats[seat]["lens"]]

    out = []
    for c in claims[:most]:
        cid = c["claim_id"]
        lines = [cut(first(c["reasoning"]), 170)]
        if c["review_status"] == "failed" and kept.get(cid):
            # the label stood; the seat quoted is one that agreed with it and found the reasons wanting
            agreeing = [(seat, reason) for seat, reason, agreed in refused.get(cid, []) if agreed]
            if agreeing:
                seat, reason = agreeing[0]
                lines.append(f'{seat_name(seat)}覆核時同意這個判定，但認為理由或證據還有缺漏：{cut(first(reason, 2), 130)}')
            else:
                lines.append("覆核同意這個判定，但認為理由或證據還有缺漏。")
        elif c["review_status"] == "failed" and cid in kept:
            # the label fell; the seat quoted is one that would not confirm it, never one that agreed
            was = judged[cid]
            lines = [f'裁判判「{ZH_LABELS[was["label"]]}」：{cut(first(was["reasoning"]), 170)}']
            against = [(seat, reason) for seat, reason, agreed in refused.get(cid, []) if not agreed]
            if against:
                seat, reason = against[0]
                lines.append(f'{seat_name(seat)}覆核時不同意：{cut(first(reason), 130)}')
            lines.append(f'覆核沒有通過或沒有完成，所以這一條改列「{ZH_LABELS[c["label"]]}」。')
        out.append((cid, ZH_LABELS[c["label"]], lines))
    return out


def registered(at):
    """The address of a registration as it stood in the commit that registered it."""
    return f"{GH}/blob/{at[1]}/{at[0]}"


def compared(run):
    """Whether the run's report has its section that sets the result beside other fact-checkers' conclusions."""
    return any(line.startswith("## 和既有查核的比對") for line in (run / "report.md").read_text(encoding="utf-8").splitlines())


def case(statement, about=False):
    """One statement as a card: whose it is (or whom it is about), what was said, how it came out, the way to the
    whole report."""
    run, person = statement["run"], taipei.PEOPLE[statement["who"]]
    score = load(run, "score.json")
    at, public = credibility(score), score["publishable"] is True
    beside = scale(at) if at is not None else f'<span class="case-reason">{e(score.get("result_reason") or "")}</span>'
    out = ['<article class="case">',
           "  " + who(person, about),
           f'  <blockquote>{e(statement["text"])}</blockquote>',
           f'  <p class="case-result"><strong>{e(score["result"])}</strong>{beside}</p>',
           '  <dl>'
           f'<div><dt>可信度</dt><dd>{"不顯示" if at is None else at}</dd></div>'
           f'<div><dt>信心度</dt><dd>{int(score["confidence"]["score"])}<small>{e(score["confidence"]["level"])}</small></dd></div>'
           f'<div><dt>公開引用</dt><dd class="word">{"可公開" if public else "不可公開"}</dd></div></dl>']
    found = points(run)
    if found:
        out.append('  <ul class="case-points">' + "".join(
            f'<li><b>{e(label)}</b>' + "".join(f'<span>{e(line)}</span>' for line in lines) + '</li>' for _, label, lines in found) + '</ul>')
    if not public:
        reasons = score.get("publish_blocks") or ["這一份的分數檔沒有寫原因，請看完整報告。"]
        out.append('  <div class="case-why"><p>工具自己標了不可公開，原因：</p><ul>' + "".join(f'<li>{e(b)}</li>' for b in reasons) + '</ul></div>')
    if statement["id"] in taipei.CAVEATS:
        out.append(f'  <p class="case-note">{e(taipei.CAVEATS[statement["id"]])}</p>')
    if compared(run):
        out.append(f'  <p class="case-tfc"><a href="../reports/{e(run.name)}/#others">這份報告有一段和既有查核機構的結論比對</a></p>')
    out.append(f'  <p class="case-links"><a class="link" href="../reports/{e(run.name)}/">完整報告{NEXT}</a>'
               f'<a class="link" href="{TREE}examples/{e(run.name)}">全部檔案{OUT}</a><span>{int(taipei.TIMES[run.name]["minutes"])} 分鐘</span>'
               f'<span>{e(taipei.model(run))}</span></p>')
    out.append('</article>')
    return "\n".join("      " + line for line in out)


def pair(statements, about=False):
    return '    <div class="duo-row">\n' + "\n".join(case(s, about) for s in statements) + "\n    </div>"


def issue_section(issue):
    """An issue with both statements, or nothing at all while either run is missing."""
    if not issue["ready"]:
        return ""
    return (f'<section id="{issue["id"]}" class="tp-issue">\n  <h2>{e(issue["name"])}</h2>\n  <p>{e(issue["about"])}</p>\n'
            f'{pair(issue["statements"])}\n</section>')


def page():
    issues, about = taipei.issues(), taipei.about()
    ready, waiting = [i for i in issues if i["ready"]], [i for i in issues if not i["ready"]]
    jump = "".join(f'<a href="#{i["id"]}">{e(i["name"])}</a>' if i["ready"] else f'<span>{e(i["name"])}</span>' for i in issues)
    other = sorted({taipei.model(s["run"]) for i in ready for s in i["statements"]} - {taipei.MODELS[taipei.REGISTERED_MODEL]})
    switched = ""
    if other:
        switched = (f'\n    <li><strong>不是每一則都用登記寫的模型。</strong>登記寫明用 {taipei.MODELS[taipei.REGISTERED_MODEL]}；它的額度在清單跑完之前用完了，'
                    f'後面幾則改用 {"、".join(other)}，主體和查核流程裡的角色都是。同一個議題的兩句一定是同一個模型跑的，每張卡片寫著自己用的模型；'
                    f'什麼時候換的、為什麼，寫在<a href="{BLOB}evals/results/2026-11-22-taipei-issues-results.md">結果紀錄</a>的「和登記不一樣的地方」。</li>')
    later = ""
    if waiting:
        later = (f'<section id="later">\n  <h2>還沒上線的 {len(waiting)} 個議題</h2>\n'
                 f'  <p>{"、".join(e(i["name"]) for i in waiting)}。照登記的順序一則一則跑，一個議題的兩則都跑完才會出現在這一頁和「全部報告」；'
                 '只跑完一邊的不放。額度用完就停在那裡，停在哪裡會寫在紀錄裡。</p>\n</section>')
    main = f'''<main class="wrap doc tp">
<header class="top">
  <h1>台北市長選舉：<br>一個議題，兩個人各查一句</h1>
  <p>10 月 31 日的電視辯論會上，兩位與會的候選人各講了很多數字和事實。我們照議題把它們排成對：每個議題各取一句可以查證的話，用同一套流程各查一次。這樣兩個人被查的則數永遠一樣。</p>
  <ul>
    <li><strong>清單在開跑之前就公開登記</strong>，連結指向登記當時的版本：<a href="{registered(taipei.SECOND)}">照議題成對的二十則</a>、<a href="{registered(taipei.FIRST)}">最早的四則</a>。登記之後發現的幾處出入另外寫在<a href="{BLOB}evals/results/2026-11-22-taipei-issues-notes.md">補充說明</a>，登記本身不改。</li>
    <li><strong>結果好不好看都放。</strong>工具自己標「不可公開」的，照樣列出來並寫明原因。</li>
    <li><strong>報告是工具自動產生的，上線前沒有人逐篇審過。</strong>它不是查核機構的報告；要引用之前，請點進完整報告看證據。</li>
    <li><strong>不放民調數字</strong>，11 月 28 日投票日當天不新增內容。</li>{switched}
  </ul>
  <p class="tp-jump" aria-label="議題">{jump}<a href="#about">流傳的說法</a></p>
</header>
{chr(10).join(filter(None, (issue_section(i) for i in issues)))}
<section id="about" class="tp-issue">
  <h2>{ABOUT_NAME}</h2>
  <p>這兩則不是候選人說的話，是網路上針對他們的說法，一人一則，在 11 月 20 日登記。這裡的結果講的是那個說法站不站得住：「不符」代表說法不成立，對被針對的人是有利的；「無法判定」代表這次查核沒有辦法確定，原因寫在那一則的卡片和報告裡。</p>
{pair(about, about=True)}
</section>
{later}
<section id="notes">
  <h2>讀這些結果的時候要注意</h2>
  <ul>
    <li><strong>每一則查的是那一句話，不是那個人。</strong>把一個人的幾則結果加起來，得不到「誰比較誠實」：每個議題挑的是哪一句、那一句好不好查，都會影響結果。</li>
    <li><strong>候選人照號次排</strong>，3 號在前、5 號在後，每一個議題都一樣。今年台北市長候選人有六位，這場辯論會只邀了兩位，所以這裡也只有這兩位。</li>
    <li><strong>每一則只有一次完整的結果。</strong>同一句話再跑一次，結果可能不同。跑到一半中斷、整則重跑的，寫在那一則的報告頁和紀錄裡。這些也沒有我們自己寫的答案卷，所以不算評測，不能拿來算準確率。</li>
    <li><strong>查核中心查過的句子，兩個人不一樣多。</strong>辯論發言的 22 句裡，台灣事實查核中心也查過的，蔣萬安有 6 句、沈伯洋有 2 句。所以蔣萬安的句子有比較多是查核機構先挑出來的，沈伯洋的句子大多是我們照規則從逐字稿挑的。</li>
    <li><strong>辯論會的話沒有核對影片原音。</strong>送進工具的文字照查核中心的標題或一份民間逐字稿，每一句的出處寫在登記裡；它和媒體記下的原話差在哪裡，看那一則報告的「溯源」。</li>
    <li><strong>「可公開」不保證結論正確</strong>，只代表流程跑完整了、信心度夠高。</li>
  </ul>
  <p class="note">跑完之後的紀錄：<a href="{BLOB}evals/results/2026-11-21-taipei.md">最早的四則</a>、<a href="{BLOB}evals/results/2026-11-22-taipei-issues-results.md">照議題成對的二十則</a>。產生這一頁的程式是 <a href="{BLOB}site/tools/build_cases.py"><code>site/tools/build_cases.py</code></a>；每張卡片的結果、分數和能不能公開，測試會拿去和 <code>examples/</code> 裡那一次的分數檔核對。</p>
</section>
</main>'''
    return frame("../", "taipei/", "台北市長選舉：一個議題，兩個人各查一句",
                 f"2026 台北市長選舉辯論會上的說法，照議題成對查核：已經上線 {len(ready)} 個議題，每一則都有完整報告和全部檔案。", main)


def flag(score):
    return "" if score["publishable"] is True else "<em>不可公開</em>"


def cell(statement):
    """One result in the front page's table: the word, where it stands on the scale, and whether the tool itself
    held it back from being quoted."""
    score = load(statement["run"], "score.json")
    at = credibility(score)
    if at is None:
        return f'<span class="tp-r"><strong>{e(score["result"])}</strong><small>不給可信度分數</small>{flag(score)}</span>'
    return f'<span class="tp-r"><strong>{e(score["result"])}</strong><i class="bar" style="--at:{at}"></i><code>{at}</code>{flag(score)}</span>'


def block():
    """The front page's part: a line for each issue that is in, the two candidates' results side by side; and,
    set apart from that table, the two circulating claims, which are about the candidates and not by them."""
    issues, about = taipei.issues(), taipei.about()
    ready = [i for i in issues if i["ready"]]
    heads = "".join(f'<span><b>{int(p["no"])}</b>{e(p["name"])}</span>' for p in taipei.PEOPLE.values())
    rows = [f'        <li><a href="taipei/#{i["id"]}"><span>{e(i["name"])}</span>{"".join(cell(s) for s in i["statements"])}</a></li>' for i in ready]
    left = len(issues) - len(ready)
    foot = (f'登記了 {len(issues)} 個議題，已經上線 {len(ready)} 個' + (f'，另外 {left} 個還沒上線' if left else '')
            + '。每一格是他在辯論會上講的那一句查出來的結果；查的是那一句話，不是那個人，分數不能加起來比。')
    for name in sorted({taipei.model(s["run"]) for i in ready for s in i["statements"]} - {taipei.MODELS[taipei.REGISTERED_MODEL]}):
        count = sum(1 for i in ready if taipei.model(i["statements"][0]["run"]) == name)
        foot += f'其中 {count} 個議題改用 {name} 跑（登記寫的模型額度用完了），原因見選舉頁。'

    claims = []
    for s in about:
        person, score = taipei.PEOPLE[s["who"]], load(s["run"], "score.json")
        claims.append(f'        <li><a href="taipei/#about"><span class="tp-whom">針對<b>{int(person["no"])}</b>{e(person["name"])}</span>'
                      f'<span class="tp-claim">{e(s["text"])}</span><strong>{e(score["result"])}</strong>{flag(score)}</a></li>')
    return f'''{BEGIN}
<section class="sec" id="taipei">
  <div class="wrap split">
    <div class="split-text">
      <h2>台北市長選舉：<br>一個議題，兩個人各查一句</h2>
      <p>10 月 31 日辯論會上兩位與會候選人講的事實說法，照議題排成對，各查一次，兩個人被查的則數永遠一樣。清單在開跑前公開登記，結果好不好看都放。</p>
      <p>報告是工具自動產生的，上線前沒有人逐篇審過；工具自己標「不可公開」的，照樣列出來。</p>
      <p><a class="btn ghost" href="taipei/">每一則的結果和完整報告{NEXT}</a></p>
    </div>
    <div class="split-main">
      <div class="sheet tp-sheet">
        <p class="sheet-head"><span>議題</span>{heads}</p>
        <ol class="tp-rows">
{chr(10).join(rows)}
        </ol>
        <p class="sheet-foot">{foot}</p>
      </div>
      <div class="sheet tp-about">
        <p class="sheet-bar"><b>{ABOUT_NAME}</b></p>
        <ol>
{chr(10).join(claims)}
        </ol>
        <p class="sheet-foot">這兩則不是候選人說的話。「不符」代表那個說法不成立，對被針對的人是有利的；「無法判定」代表這次查核沒有辦法確定，原因在那一則的報告裡。</p>
      </div>
    </div>
  </div>
</section>
{END}'''


def rewritten(text):
    """The front page with its Taipei part as it should be now."""
    a, b = text.index(BEGIN), text.index(END) + len(END)
    return text[:a] + block() + text[b:]


if __name__ == "__main__":
    front, whole = rewritten(FRONT.read_text(encoding="utf-8")), page()  # both worked out before either is written
    FRONT.write_text(front, encoding="utf-8")
    PAGE.parent.mkdir(parents=True, exist_ok=True)
    PAGE.write_text(whole, encoding="utf-8")
    print("site/index.html: Taipei block rewritten; site/taipei/index.html written")
