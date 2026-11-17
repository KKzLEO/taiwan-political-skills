import unittest

from tests import helpers  # noqa: F401
from fclib import media

OUTLETS = [
    {"id": "ltn", "name": "自由時報", "aliases": ["自由電子報", "Liberty Times"], "domains": ["ltn.com.tw"]},
    {"id": "cna", "name": "中央社", "aliases": ["中央通訊社", "CNA"], "domains": ["cna.com.tw", "focustaiwan.tw"]},
]


class LookupTest(unittest.TestCase):
    def test_url_with_subdomain(self):
        self.assertEqual(media.lookup("https://news.ltn.com.tw/news/politics/1", OUTLETS)["id"], "ltn")

    def test_second_domain(self):
        self.assertEqual(media.lookup("https://focustaiwan.tw/politics/1", OUTLETS)["id"], "cna")

    def test_lookalike_domain_does_not_match(self):
        self.assertIsNone(media.lookup("https://ltn.com.tw.evil.example/x", OUTLETS))
        self.assertIsNone(media.lookup("https://fakeltn.com.tw/x", OUTLETS))

    def test_name_alias_and_id(self):
        self.assertEqual(media.lookup("自由電子報", OUTLETS)["id"], "ltn")
        self.assertEqual(media.lookup("liberty times", OUTLETS)["id"], "ltn")
        self.assertEqual(media.lookup("cna", OUTLETS)["id"], "cna")

    def test_unknown(self):
        self.assertIsNone(media.lookup("不存在的媒體", OUTLETS))
