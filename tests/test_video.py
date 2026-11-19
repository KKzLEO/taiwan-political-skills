import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests import helpers  # noqa: F401
from fclib import video

VTT = """WEBVTT
Kind: captions
Language: zh-TW

00:00:01.000 --> 00:00:03.000 align:start position:0%
大家好<00:00:01.500><c> 今天</c>

00:00:03.000 --> 00:00:05.000
大家好 今天

00:00:05.000 --> 00:00:07.000
我們來談油價

NOTE 這是註解

00:00:07.000 --> 00:00:09.000
我們來談油價
"""


class VttTest(unittest.TestCase):
    def test_strips_headers_timestamps_tags_and_rolling_duplicates(self):
        self.assertEqual(video.vtt_to_text(VTT), "大家好 今天\n我們來談油價")

    def test_keeps_timestamps_when_asked(self):
        out = video.vtt_to_text(VTT, keep_times=True)
        self.assertIn("[00:00:05] 我們來談油價", out)


    def test_cue_numbers_are_dropped_but_a_number_that_is_the_caption_stays(self):
        """Audit: numbered cues put '2' between two halves of a quote, so the quote check could not find it."""
        vtt = ("WEBVTT\n\n1\n00:00:01.000 --> 00:00:03.000\n明年油價\n\n2\n00:00:03.000 --> 00:00:05.000\n一定漲三成\n\n"
               "3\n00:00:05.000 --> 00:00:06.000\n2026\n")
        self.assertEqual(video.vtt_to_text(vtt), "明年油價\n一定漲三成\n2026")
        self.assertIn("[00:00:03] 一定漲三成", video.vtt_to_text(vtt, keep_times=True))

    def test_short_and_srt_timestamps_and_entities(self):
        self.assertEqual(video.vtt_to_text("WEBVTT\n\n00:01.000 --> 00:03.000\n明年油價一定漲三成\n"), "明年油價一定漲三成")
        srt = "1\n00:00:01,000 --> 00:00:03,000\n明年油價一定漲三成\n"
        self.assertEqual(video.vtt_to_text(srt, keep_times=True), "[00:00:01] 明年油價一定漲三成")
        ent = "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\nA&amp;B&nbsp;公司 &lt;油價&gt; 漲 3 成\n"
        self.assertEqual(video.vtt_to_text(ent), "A&B 公司 <油價> 漲 3 成")


FAKE_YTDLP = """import os, sys
from pathlib import Path
args = sys.argv[1:]
out = Path(args[args.index("-o") + 1]).parent
mode = os.environ["FAKE_YTDLP"]
VTT = "WEBVTT\\n\\n00:00:01.000 --> 00:00:03.000\\n{}\\n"
if mode == "429":
    sys.stderr.write("WARNING: [youtube] Some formats may be missing\\n"
                     "ERROR: Unable to download video subtitles for 'zh-Hant': HTTP Error 429: Too Many Requests\\n")
    sys.exit(1)
if mode == "both":
    (out / "vid.zh-Hant.vtt").write_text(VTT.format("機器翻譯的字幕"), encoding="utf-8")
    (out / "vid.zh-TW.vtt").write_text(VTT.format("上傳者的字幕"), encoding="utf-8")
if mode == "srt":
    (out / "vid.zh-TW.srt").write_text("1\\n00:00:01,000 --> 00:00:03,000\\n明年油價一定漲三成\\n", encoding="utf-8")
# Under --ignore-errors yt-dlp 2026.10.26 prints a failed language as a WARNING (YoutubeDL._write_subtitles).
WARN = "WARNING: Unable to download video subtitles for '{}': HTTP Error 429: Too Many Requests\\n"
if mode == "warn429":
    sys.stderr.write(WARN.format("zh-TW"))
if mode == "zh_failed_en_ok":
    (out / "vid.en.vtt").write_text(VTT.format("Fuel prices will rise 30% next year"), encoding="utf-8")
    sys.stderr.write(WARN.format("zh-TW"))
if mode == "en_failed_zh_ok":
    (out / "vid.zh-TW.vtt").write_text(VTT.format("上傳者的字幕"), encoding="utf-8")
    sys.stderr.write(WARN.format("en"))
"""


class FetchTest(unittest.TestCase):
    """A fake yt-dlp on a PATH of its own; no network."""

    def fetch(self, mode):
        d = Path(tempfile.mkdtemp())
        (d / "yt-dlp").write_text(f"#!{sys.executable}\n" + FAKE_YTDLP, encoding="utf-8")
        (d / "yt-dlp").chmod(0o755)
        with mock.patch.dict(os.environ, {"PATH": str(d), "FAKE_YTDLP": mode}):
            return video.fetch_transcript("https://www.youtube.com/watch?v=vid")

    def test_a_yt_dlp_error_is_reported_as_it_is(self):
        """Audit: an HTTP 429 on one language was reported as 'this video has no subtitles'."""
        text, note = self.fetch("429")
        self.assertIsNone(text)
        self.assertIn("抓字幕失敗", note)
        self.assertIn("HTTP Error 429", note)
        self.assertIn("逐字稿", note)
        self.assertNotIn("whisper", note)

    def test_the_uploaders_own_subtitles_are_used(self):
        """Audit: the zh-Hant track YouTube offered was English speech recognition machine-translated to Chinese."""
        text, note = self.fetch("both")
        self.assertEqual(text, "[00:00:01] 上傳者的字幕")
        self.assertEqual(note, "人工字幕：vid.zh-TW.vtt")

    def test_no_subtitles_asks_for_a_transcript(self):
        text, note = self.fetch("none")
        self.assertIsNone(text)
        self.assertIn("沒有上傳者自己放的字幕", note)
        self.assertIn("逐字稿", note)
        self.assertNotIn("whisper", note)

    def test_a_failed_language_is_reported_in_the_form_ignore_errors_prints(self):
        """Review: with --ignore-errors the 429 is a WARNING line, and it was reported as 'no subtitles'."""
        text, note = self.fetch("warn429")
        self.assertIsNone(text)
        self.assertIn("抓字幕失敗", note)
        self.assertIn("HTTP Error 429", note)

    def test_english_is_not_used_when_the_chinese_track_failed(self):
        """Review: zh-TW hit a 429, en came through, and the English translation became the speaker's words."""
        text, note = self.fetch("zh_failed_en_ok")
        self.assertIsNone(text)
        self.assertIn("抓字幕失敗", note)
        self.assertIn("'zh-TW': HTTP Error 429", note)
        self.assertIn("vid.en.vtt", note)
        self.assertIn("逐字稿", note)

    def test_a_lower_language_that_failed_is_still_mentioned(self):
        text, note = self.fetch("en_failed_zh_ok")
        self.assertEqual(text, "[00:00:01] 上傳者的字幕")
        self.assertTrue(note.startswith("人工字幕：vid.zh-TW.vtt"), note)
        self.assertIn("'en': HTTP Error 429", note)

    def test_srt_subtitles_are_read_too(self):
        self.assertEqual(self.fetch("srt")[0], "[00:00:01] 明年油價一定漲三成")

    def test_yt_dlp_output_is_read_as_utf8(self):
        with mock.patch.object(video.shutil, "which", return_value="/x/yt-dlp"), \
                mock.patch.object(video.subprocess, "run") as run:
            run.return_value = subprocess.CompletedProcess([], 0, "", "")
            video.fetch_transcript("https://youtu.be/x")
        self.assertEqual(run.call_args.kwargs.get("encoding"), "utf-8")


class CommandTest(unittest.TestCase):
    def test_subtitle_command_takes_only_uploaded_subtitles_and_prefers_taiwan(self):
        """Audit: --write-auto-subs let a machine-translated track win, and one failed language stopped the rest."""
        argv = video.subtitle_command("https://youtu.be/x", "/tmp/out")
        self.assertIn("--skip-download", argv)
        self.assertIn("--write-subs", argv)
        self.assertNotIn("--write-auto-subs", argv)
        self.assertIn("--ignore-errors", argv)
        self.assertTrue(argv[argv.index("--sub-langs") + 1].startswith("zh-TW,"))

    def test_the_link_cannot_be_read_as_an_option(self):
        self.assertEqual(video.subtitle_command("https://youtu.be/x", "/tmp/out")[-2:], ["--", "https://youtu.be/x"])
