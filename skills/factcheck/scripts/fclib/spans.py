"""Find quoted passages inside the message text, ignoring differences that are not wording.

Claims must quote the message (`content`: letters and digits only, so a dropped colon or a
zero-width space does not matter). Tactic quotes keep punctuation (`literal`), because some
features are about punctuation itself (e.g. a run of exclamation marks).
"""

from __future__ import annotations

import re
import unicodedata

_STAMP = re.compile(r"\[\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d+)?\]")
_ELLIPSIS = re.compile(r"…+|⋯+|\.{3,}")
SEARCH_LIMIT = 20000


def _base(text) -> str:
    return _STAMP.sub("", unicodedata.normalize("NFKC", text or ""))


def content(text) -> str:
    """Letters and digits only, after NFKC and with transcript timestamps removed. Marks that change
    a number are kept: "." and "/" between digits, "-" before a digit, "%" after one (1.5 ≠ 15)."""
    t = _base(text)
    out = []
    for i, ch in enumerate(t):
        prev_digit = i > 0 and t[i - 1].isdigit()
        next_digit = i + 1 < len(t) and t[i + 1].isdigit()
        if (unicodedata.category(ch)[0] in "LN" or (ch in "./" and prev_digit and next_digit)
                or (ch == "-" and next_digit) or (ch == "%" and prev_digit)):
            out.append(ch)
    return "".join(out)


def literal(text) -> str:
    """NFKC with timestamps, whitespace and invisible format characters removed; punctuation kept."""
    return "".join(ch for ch in _base(text) if not ch.isspace() and unicodedata.category(ch) != "Cf")


def pieces(quote) -> list:
    """A quote may join several passages of the message with an ellipsis."""
    return [p for p in _ELLIPSIS.split(quote or "")]


def occurrences(needle: str, hay: str) -> list:
    """Every (start, end) where needle occurs in hay, overlapping matches included."""
    out = []
    if not needle:
        return out
    i = hay.find(needle)
    while i >= 0:
        out.append((i, i + len(needle)))
        i = hay.find(needle, i + 1)
    return out


def _overlap(a, b) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def disjoint(items: dict):
    """items: key -> candidate (start, end) spans. Can every key get one span with no two overlapping?

    Returns (True, []) or (False, keys involved in a clash). Stops after SEARCH_LIMIT steps and
    reports a clash, so a pathological message cannot hang validation or slip through it.
    """
    keys = sorted(items, key=lambda k: (len(items[k]), k))
    chosen, steps = {}, 0

    def place(i):
        nonlocal steps
        if i == len(keys):
            return True
        for span in items[keys[i]]:
            steps += 1
            if steps > SEARCH_LIMIT:
                raise TimeoutError
            if all(not _overlap(span, other) for other in chosen.values()):
                chosen[keys[i]] = span
                if place(i + 1):
                    return True
                del chosen[keys[i]]
        return False

    try:
        if place(0):
            return True, []
    except TimeoutError:
        pass
    return False, sorted({k for g in _groups(items) for k in g}, key=_order)


def clash_groups(items: dict):
    """Like disjoint(), but the clashing keys come back as separate groups the author can fix one by one."""
    ok, _ = disjoint(items)
    return (True, []) if ok else (False, _groups(items))


def _order(key):
    digits = "".join(ch for ch in str(key) if ch.isdigit())
    return (int(digits) if digits else 0, str(key))


def _groups(items):
    names = sorted(items, key=_order)
    pairs = [(a, b) for i, a in enumerate(names) for b in names[i + 1:]]
    edges = [(a, b) for a, b in pairs if all(_overlap(x, y) for x in items[a] for y in items[b])]
    if not edges:  # only clash in combination: report everything that touches
        edges = [(a, b) for a, b in pairs if any(_overlap(x, y) for x in items[a] for y in items[b])]
    parent = {k: k for k in names}

    def root(k):
        while parent[k] != k:
            k = parent[k]
        return k

    for a, b in edges:
        parent[root(a)] = root(b)
    groups = {}
    for a, b in edges:
        for k in (a, b):
            groups.setdefault(root(k), set()).add(k)
    return sorted((sorted(g, key=_order) for g in groups.values()), key=lambda g: _order(g[0]))
