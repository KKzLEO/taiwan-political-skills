"""What the generated pages share: the frame they stand in (head, top bar, foot) and the few pieces that
show a result the same way on each of them."""
import html
import json

GH = "https://github.com/KKzLEO/taiwan-political-skills"
BLOB = GH + "/blob/main/"
TREE = GH + "/tree/main/"
e = html.escape

OUT = '<svg width="16" height="16"><use href="#i-out"/></svg>'
NEXT = '<svg width="16" height="16"><use href="#i-next"/></svg>'
ICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 20 20'%3E%3Crect width='20' height='20' rx='5' "
        "fill='%236247d6'/%3E%3Cpath d='M12.2 5.4 7.8 14.6' stroke='%23ffffff' stroke-width='2' stroke-linecap='round'/%3E%3C/svg%3E")
SPRITE = '''<svg class="sprite" aria-hidden="true">
  <symbol id="i-mark" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><rect x="2.25" y="2.25" width="15.5" height="15.5" rx="4.25"/><path d="M11.9 6 8.1 14"/></symbol>
  <symbol id="i-out" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M5.5 10.5 10.5 5.5M6 5.5h4.5V10"/></symbol>
  <symbol id="i-next" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3.5 8h9M9 4.5 12.5 8 9 11.5"/></symbol>
</svg>'''
# The places every generated page links to, as seen from the front page.
CURRENT = ' aria-current="page"'
PLACES = [("taipei/", "台北市長選舉"), ("reports/", "全部報告"), ("#how", "怎麼查的"), ("results/", "驗證結果")]


def load(run, name):
    return json.loads((run / name).read_text(encoding="utf-8"))


def credibility(score):
    """A run's credibility as a whole number when it has a place on the scale, else None. The number is made a
    number here, so nothing a file holds in its place can reach a page as markup."""
    cred = score.get("credibility") or {}
    return int(cred["score"]) if cred.get("show_on_spectrum") and score["result"] != "無法判定" else None


def scale(at):
    return f'<span class="scale" style="--at:{int(at)}"><span>錯誤</span><i></i><span>正確</span></span>'


def who(person, about=False):
    """Whose statement it is; or, for a circulating claim, whom it is about."""
    lead = "<span>針對</span>" if about else ""
    return f'<p class="case-who">{lead}<b>{int(person["no"])}</b>{e(person["name"])}<small>{e(person["party"])}</small></p>'


def frame(root, here, title, description, body):
    """A whole page. root is the way from this page to the front page ("../" or "../../"); here is the entry of
    PLACES this page belongs under, if any."""
    links = "".join(f'<a href="{root}{to}"{CURRENT if to == here else ""}>{name}</a>' for to, name in PLACES)
    sheets = "".join(f'\n<link rel="stylesheet" href="{root}assets/{name}">' for name in ("site.css", "results.css", "report.css"))
    return f'''<!doctype html>
<html lang="zh-Hant-TW">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}｜台灣訊息查核</title>
<meta name="description" content="{e(description)}">
<meta name="theme-color" content="#fafafa">
<link rel="icon" href="{ICON}">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600&family=Geist+Mono:wght@400;500&family=Noto+Sans+TC:wght@400;500&display=swap" rel="stylesheet">{sheets}
</head>
<body>
{SPRITE}
<header class="nav">
  <div class="wrap nav-in">
    <a class="brand" href="{root}"><svg width="20" height="20"><use href="#i-mark"/></svg>台灣訊息查核<small>skill</small></a>
    <nav class="nav-links" aria-label="網站導覽">{links}</nav>
    <div class="nav-end"><a class="nav-out" href="{GH}">GitHub{OUT}</a><a class="btn sm" href="{root}#use">安裝</a></div>
  </div>
</header>
{body}
<footer class="foot">
  <div class="wrap foot-in">
    <p class="brand"><svg width="20" height="20"><use href="#i-mark"/></svg>台灣訊息查核<small>skill</small></p>
    <p class="foot-links"><a href="{root}">首頁</a><a href="{root}taipei/">台北市長選舉</a><a href="{root}reports/">全部報告</a><a href="{GH}">GitHub</a><a href="{GH}/issues">回報問題</a></p>
    <p class="fine">程式採 MIT 授權，資料採 CC BY-SA 4.0。這個網站上的報告是工具自動產生的，不是查核機構的報告；引用查核機構的內容時只附連結和簡短摘錄，著作權屬原機構。</p>
  </div>
</footer>
</body>
</html>
'''
