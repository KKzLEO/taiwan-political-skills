"""Fetch video subtitles with yt-dlp (optional dependency) and flatten WebVTT to text."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

LANGS = "zh-Hant,zh-TW,zh-Hant-TW,zh,zh-Hans,en"
TIME = re.compile(r"^(\d{2}:\d{2}:\d{2})\.\d{3}\s+-->")


def vtt_to_text(vtt: str, keep_times: bool = False) -> str:
    lines, last, stamp, skip_block = [], None, None, False
    for raw in vtt.splitlines():
        line = raw.strip()
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
            stamp = m.group(1)
            continue
        text = re.sub(r"<[^>]+>", "", line)
        text = re.sub(r"\s+", " ", text).strip()
        if not text or text == last:
            continue
        last = text
        lines.append(f"[{stamp}] {text}" if keep_times and stamp else text)
    return "\n".join(lines)


def subtitle_command(url: str, out_dir: str):
    return ["yt-dlp", "--skip-download", "--write-subs", "--write-auto-subs", "--sub-langs", LANGS,
            "--sub-format", "vtt", "-o", str(Path(out_dir) / "%(id)s.%(ext)s"), url]


def fetch_transcript(url: str, keep_times: bool = True):
    """Return (text, note). text is None when no subtitles could be fetched."""
    if shutil.which("yt-dlp") is None:
        return None, "沒有安裝 yt-dlp，請使用者提供逐字稿"
    with tempfile.TemporaryDirectory(prefix="fc-video-") as d:
        try:
            subprocess.run(subtitle_command(url, d), capture_output=True, text=True, timeout=300, check=False)
        except subprocess.TimeoutExpired:
            return None, "抓字幕逾時"
        files = sorted(Path(d).glob("*.vtt"))
        if not files:
            return None, "這支影片沒有字幕；可以用 whisper 轉文字，或請使用者提供逐字稿"
        for lang in LANGS.split(","):
            for f in files:
                if f.name.endswith(f".{lang}.vtt"):
                    return vtt_to_text(f.read_text(encoding="utf-8"), keep_times), f"字幕語言：{lang}"
        return vtt_to_text(files[0].read_text(encoding="utf-8"), keep_times), f"字幕檔：{files[0].name}"
