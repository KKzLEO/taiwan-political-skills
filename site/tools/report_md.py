"""The Markdown a report is written in, read back into blocks and set as HTML.

A report is written by skills/factcheck/scripts/fclib/render.py and uses a small part of Markdown: one title,
"##" sections, quoted lines, one fenced block (the scale), lists two levels deep, tables and paragraphs; inside a
line, bold, code, the links the report made itself and bare web addresses. Only that part is read here.

Much of a report's text was written by a model from what it found on the web, so nothing in it is trusted: every
character is escaped, and the only thing that becomes a link is an address that starts with http:// or https://.
"""
import html
import re
from urllib.parse import urlsplit

e = html.escape
# Where a bare address ends: at a space, a bracket or a mark that closes the sentence it stands in. A pair of
# brackets inside it (the name of a Wikipedia page) belongs to it; a lone closing bracket after it does not.
BARE = r"https?://(?:[^\s<>\"'()）」』】》，。；、]|\([^\s<>\"'()]*\))+"
TOKEN = re.compile(r"\*\*(?P<bold>.+?)\*\*|`(?P<code>[^`]+)`|\[(?P<label>[^\[\]]{1,300})\]\((?P<target>[^)\s]+)\)|(?P<bare>" + BARE + ")")
SEPARATOR = re.compile(r"\|[-| :]+\|")


def host(url):
    """The host an address leads to, as a browser would name it, or None when the address is not followed. Not
    followed: anything but http(s); a name and an "@" before the host, which can be dressed up as another site;
    a backslash or a "%" in the host, which browsers read their own way. A host written in other letters than
    Latin ones is shown in its encoded form, so a look-alike does not pass for the site it imitates."""
    if not re.match(r"https?://", url):
        return None
    try:
        parts = urlsplit(url)
        name = parts.hostname
        if not name or "@" in parts.netloc or "\\" in url or "%" in parts.netloc:
            return None
        return name.encode("idna").decode("ascii")
    except (ValueError, UnicodeError):
        return None


def link(target, label):
    return f'<a href="{e(target)}" rel="noopener nofollow">{label}</a>'


def inline(text, links=True):
    """One line of a report as HTML. A link the report made shows where it leads beside its label, because the
    label was written by a model and may read like another address; the label itself never becomes a link."""
    out, at = [], 0
    for m in TOKEN.finditer(text):
        out.append(e(text[at:m.start()]))
        at = m.end()
        if m["bold"] is not None:
            out.append(f"<strong>{inline(m['bold'], links)}</strong>")
        elif m["code"] is not None:
            out.append(f"<code>{e(m['code'])}</code>")
        elif m["label"] is not None:
            where = host(m["target"]) if links else None
            if where:
                out.append(link(m["target"], inline(m["label"], links=False)) + f'<small class="host">{e(where)}</small>')
            else:  # not an address to follow: shown as the text it is
                out.append(e(m.group(0)))
        else:
            bare = m["bare"].rstrip(".,;:!?")  # marks that end the sentence, not the address
            at -= len(m["bare"]) - len(bare)
            out.append(link(bare, e(bare)) if links and host(bare) else e(bare))
    out.append(e(text[at:]))
    return "".join(out)


def plain(text):
    """The words of a line as a reader sees them: the marks of bold, code and links taken away."""
    def shown(m):
        if m["bold"] is not None:
            return plain(m["bold"])
        if m["code"] is not None:
            return m["code"]
        if m["label"] is not None:
            return plain(m["label"]) if re.match(r"https?://", m["target"]) else m.group(0)
        return m.group(0)
    return TOKEN.sub(shown, text)


def cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse(text):
    """A report as a list of blocks: ("h1", text), ("h2", text), ("quote", text), ("fence", lines), ("p", text),
    ("list", [(item, [sub-items])]) and ("table", header, rows)."""
    blocks, lines, i = [], text.splitlines(), 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
        elif line.startswith("```"):
            j = i + 1
            while j < len(lines) and not lines[j].startswith("```"):
                j += 1
            blocks.append(("fence", lines[i + 1:j]))
            i = j + 1
        elif line.startswith("## "):
            blocks.append(("h2", line[3:].strip()))
            i += 1
        elif line.startswith("# "):
            blocks.append(("h1", line[2:].strip()))
            i += 1
        elif line.startswith(">"):
            blocks.append(("quote", line[1:].strip()))
            i += 1
        elif line.startswith("|"):
            j = i
            while j < len(lines) and lines[j].startswith("|"):
                j += 1
            rows = [cells(ln) for ln in lines[i:j] if not SEPARATOR.fullmatch(ln.strip())]
            blocks.append(("table", rows[0], rows[1:]))
            i = j
        elif line.startswith("- "):
            items = []
            while i < len(lines) and (lines[i].startswith("- ") or lines[i].startswith("  - ")):
                if lines[i].startswith("- "):
                    items.append((lines[i][2:].strip(), []))
                else:
                    items[-1][1].append(lines[i][4:].strip())
                i += 1
            blocks.append(("list", items))
        else:
            blocks.append(("p", line.strip()))
            i += 1
    return blocks

