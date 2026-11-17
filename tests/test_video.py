import unittest

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


class CommandTest(unittest.TestCase):
    def test_subtitle_command_skips_download_and_prefers_traditional_chinese(self):
        argv = video.subtitle_command("https://youtu.be/x", "/tmp/out")
        self.assertIn("--skip-download", argv)
        self.assertIn("--write-auto-subs", argv)
        langs = argv[argv.index("--sub-langs") + 1]
        self.assertTrue(langs.startswith("zh-Hant"))
