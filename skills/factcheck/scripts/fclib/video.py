"""Fetch video subtitles with yt-dlp (optional dependency) and flatten WebVTT (or SRT) to text."""

from __future__ import annotations

import html
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

# Uploaders' own subtitles only, Taiwan first: YouTube's automatic zh-Hant track was English speech recognition
# machine-translated to Chinese, and the report cannot say a transcript was machine-made.
LANGS = "zh-TW,zh-Hant,zh-Hant-TW,zh-HK,zh,zh-Hans,en"
# Hours are optional (00:01.000) and SRT writes the decimal point as a comma.
TIME = re.compile(r"^(?:(\d+):)?(\d{2}):(\d{2})[.,]\d{3}\s+-->")
# yt-dlp's message for one language it could not download (YoutubeDL._write_subtitles).
SUB_FAILED = re.compile(r"Unable to download video subtitles for '([^']+)'")


def vtt_to_text(vtt: str, keep_times: bool = False) -> str:
    lines, last, stamp, skip_block = [], None, None, False
    raw = [r.strip() for r in vtt.splitlines()]
    for i, line in enumerate(raw):
        if not line:
            skip_block = False
            continue
        if line.startswith("WEBVTT") or re.match(r"^(Kind|Language):", line):
            continue
        if line.startswith("NOTE") or line.startswith("STYLE"):
            skip_block = True
            continue
        if skip_block:
            continue
        m = TIME.match(line)
        if m:
            stamp = f"{int(m.group(1) or 0):02d}:{m.group(2)}:{m.group(3)}"
            continue
        if (i == 0 or not raw[i - 1]) and i + 1 < len(raw) and TIME.match(raw[i + 1]):
            continue  # a cue number or id: left in, it split a quote across two lines with a digit between them
        text = html.unescape(re.sub(r"<[^>]+>", "", line))
        text = re.sub(r"\s+", " ", text).strip()
        if not text or text == last:
            continue
        last = text
        lines.append(f"[{stamp}] {text}" if keep_times and stamp else text)
    return "\n".join(lines)


def subtitle_command(url: str, out_dir: str):
    # --ignore-errors: one language that fails (HTTP 429) no longer stops the others. "--": the link is never an option.
    return ["yt-dlp", "--skip-download", "--write-subs", "--ignore-errors", "--sub-langs", LANGS,
            "--sub-format", "vtt", "-o", str(Path(out_dir) / "%(id)s.%(ext)s"), "--", url]


def fetch_transcript(url: str, keep_times: bool = True):
    """Return (text, note). text is None when no subtitles could be fetched."""
    if shutil.which("yt-dlp") is None:
        return None, "沒有安裝 yt-dlp，請使用者提供逐字稿"
    with tempfile.TemporaryDirectory(prefix="fc-video-") as d:
        try:
            p = subprocess.run(subtitle_command(url, d), capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=300, check=False)
        except subprocess.TimeoutExpired:
            return None, "抓字幕逾時（超過 5 分鐘）；請使用者提供逐字稿"
        # yt-dlp falls back to SRT when a site has no VTT.
        files = sorted(f for f in Path(d).iterdir() if f.suffix in (".vtt", ".srt"))
        # Under --ignore-errors a language that failed (HTTP 429) is printed as a WARNING, not an ERROR.
        errors = [line.strip() for line in (p.stderr or "").splitlines()
                  if line.startswith("ERROR") or SUB_FAILED.search(line)]
        if not files:  # yt-dlp's own error, not "no subtitles": a 429 or a bad link used to be reported as that
            if errors:
                return None, f"抓字幕失敗（yt-dlp：{errors[-1]}）；請使用者提供逐字稿"
            return None, "這支影片沒有上傳者自己放的字幕（自動產生和機器翻譯的字幕不採用）；請使用者提供逐字稿"
        order = LANGS.split(",")

        def rank(f):
            return next((i for i, lang in enumerate(order) if f.name.endswith((f".{lang}.vtt", f".{lang}.srt"))),
                        len(order))

        chosen = min(files, key=rank)
        # A better language that failed left a lower one, often a translation, to stand in for the speaker's words.
        for line in errors:
            m = SUB_FAILED.search(line)
            if m and m.group(1) in order and order.index(m.group(1)) < rank(chosen):
                return None, (f"抓字幕失敗（yt-dlp：{line}）；只抓到排在後面的 {chosen.name}，"
                              "那可能是翻譯，不採用；請使用者提供逐字稿")
        note = f"人工字幕：{chosen.name}" + (f"；yt-dlp 另外回報：{errors[-1]}" if errors else "")
        return vtt_to_text(chosen.read_text(encoding="utf-8"), keep_times), note
