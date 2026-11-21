"""What the pages know about the Taipei statements: who said what, under which issue, and which run in
examples/ is its check.

Two registrations stand behind this. The first (2026-11-20) has two circulating claims, one about each candidate,
and two debate statements. The second (2026-11-22) pairs debate statements by issue and is read from its JSON.
A statement's run is found by the text it was given, so nothing here has to be edited when a run comes in; two
folders given the same text, or a folder that belongs to nothing, stop the build instead of being guessed at.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples"
# The registrations as they were pushed, before any of their statements was run.
FIRST = ("evals/results/2026-11-20-taipei-preregistration.md", "c396a809981a736c32f9e366ae75f5a876058f1f")
SECOND = ("evals/results/2026-11-22-taipei-issues-preregistration.md", "086e40f741816713ddf5601600d1bdf8e18c4d6b")
LIST = json.loads((ROOT / "evals/results/2026-11-22-taipei-issues.json").read_text(encoding="utf-8"))
PEOPLE = {p["key"]: p for p in LIST["people"]}  # in ballot order
# The first registration's two circulating claims. Each is about the candidate it is listed under, not said by him.
ABOUT = [
    {"id": "shen-kickback", "who": "shen",
     "text": "網路流傳一段錄音，字幕寫「疑似沈姓候選人私下錄音」，內容是沈伯洋自己承認利用黑熊學院在美國軍購案收回扣。"},
    {"id": "jiang-garbage-truck", "who": "jiang",
     "text": "在大稻埕聽到垃圾車廣播「市長選舉請支持蔣萬安」，這是公器私用。"},
]
# What a reader of one statement's result should know about the words that were checked.
CAVEATS = {
    "shen-kickback": "這一則的文字是我們照媒體對起訴內容的報導寫的，不是那段錄音的字幕原文。",
    "jiang-garbage-truck": "這一則的文字是我們照媒體對原貼文的轉述寫的，不是原貼文的逐字內容；原貼文已經刪除。",
    "jiang-canopy": "這一句照查核中心的標題；逐字稿記的原話後面還有「包括中央轄管的地方，以及大學的校園」，少了這一段可能比原話難成立。",
}
# Runs in examples/ that are not a registered statement, and what each is.
OTHER = {"20261120-1441-機車大燈罰三千": "為了測試寫的訊息"}
TIMES = json.loads((EXAMPLES / "times.json").read_text(encoding="utf-8"))


def given():
    """The folder of the run that was given each text. Two runs of one text are an error: which of them the pages
    showed would be decided by a folder name."""
    out = {}
    for path in sorted(EXAMPLES.glob("*/input.json")):
        if (path.parent / "report.md").exists():
            text = json.loads(path.read_text(encoding="utf-8"))["content"].strip()
            if text in out:
                raise ValueError(f"examples/ 裡有兩個資料夾查的是同一段文字：{out[text].name}、{path.parent.name}")
            out[text] = path.parent
    return out


def in_ballot_order(statements):
    return sorted(statements, key=lambda s: PEOPLE[s["who"]]["no"])


def issues():
    """Every registered issue with its two statements in ballot order; each statement carries the folder of its
    run under "run" once that run is in examples/."""
    runs, out = given(), []
    for issue in LIST["issues"]:
        pair = [dict(s, run=runs.get(s["text"])) for s in in_ballot_order(issue["statements"])]
        out.append(dict(issue, statements=pair, ready=all(s["run"] for s in pair)))
    return out


def about():
    runs = given()
    return [dict(s, run=runs.get(s["text"])) for s in in_ballot_order(ABOUT)]


def place(run):
    """Where a run belongs among the Taipei statements, or None for one listed in OTHER: its statement, the issue
    it is under (None for a circulating claim) and the other candidate's statement beside it. A run that is
    neither is an error."""
    for issue in issues():
        for s in issue["statements"]:
            if s["run"] == run:
                return {"statement": s, "issue": issue, "other": next(o for o in issue["statements"] if o is not s)}
    pair = about()
    for s in pair:
        if s["run"] == run:
            return {"statement": s, "issue": None, "other": next(o for o in pair if o is not s)}
    if run.name in OTHER:
        return None
    raise ValueError(f"examples/{run.name} 不是登記過的說法，也不在 taipei.OTHER 裡；不知道它是什麼就不產生頁面")


def published():
    """The runs the site shows. A statement of an issue is shown only when the other candidate's is in too."""
    out = []
    for run in sorted(p.parent for p in EXAMPLES.glob("*/report.md")):
        where = place(run)
        if not where or not where["issue"] or where["issue"]["ready"]:
            out.append(run)
    return out
