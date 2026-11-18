import unittest

from tests.helpers import SKILL  # noqa: F401  (puts the skill's scripts on sys.path)
from fclib import spans


class ContentTest(unittest.TestCase):
    def test_keeps_only_letters_and_digits(self):
        self.assertEqual(spans.content("某部長說：明年油價「一定」漲三成！"), "某部長說明年油價一定漲三成")

    def test_folds_full_width_and_drops_zero_width_and_emoji(self):
        self.assertEqual(spans.content("快​轉傳！️ ABC１２"), "快轉傳ABC12")

    def test_keeps_the_marks_that_change_a_number(self):
        self.assertNotEqual(spans.content("1.5億"), spans.content("15億"))
        self.assertNotEqual(spans.content("-3%"), spans.content("3%"))
        self.assertNotEqual(spans.content("10/15"), spans.content("1015"))
        self.assertEqual(spans.content("4,984,060 票"), spans.content("4984060票"))

    def test_drops_transcript_timestamps(self):
        self.assertEqual(spans.content("[00:01:02] 大家好\n[00:01:05] 我是"), "大家好我是")


class LiteralTest(unittest.TestCase):
    def test_keeps_punctuation_but_drops_spaces_and_invisible_characters(self):
        self.assertEqual(spans.literal("快​轉 傳！！"), "快轉傳!!")

    def test_pieces_split_on_ellipsis(self):
        self.assertEqual(spans.pieces("法院判了！！……台北地院重判28年半！"), ["法院判了！！", "台北地院重判28年半！"])
        self.assertEqual(spans.pieces("甲...乙"), ["甲", "乙"])


class DisjointTest(unittest.TestCase):
    def test_same_text_at_two_places_can_be_two_claims(self):
        hay = spans.content("民進黨分配到13席；國民黨也分配到13席")
        occ = spans.occurrences(spans.content("分配到13席"), hay)
        self.assertEqual(len(occ), 2)
        self.assertEqual(spans.disjoint({"C1": occ, "C2": occ}), (True, []))

    def test_fragment_inside_a_whole_sentence_clashes(self):
        hay = spans.content("立法院三讀的「藐視國會罪」早就上路了")
        whole = spans.occurrences(spans.content("立法院三讀的「藐視國會罪」早就上路了"), hay)
        part = spans.occurrences(spans.content("立法院三讀的「藐視國會罪」"), hay)
        self.assertEqual(spans.disjoint({"C1": part, "C2": whole}), (False, ["C1", "C2"]))

    def test_partial_overlap_clashes(self):
        hay = spans.content("大甲媽遶境前夕，陸委會的梁文傑竟然公開說：媽祖是統戰工具")
        a = spans.occurrences(spans.content("大甲媽遶境前夕，陸委會的梁文傑竟然公開說"), hay)
        b = spans.occurrences(spans.content("陸委會的梁文傑竟然公開說：媽祖是統戰工具"), hay)
        self.assertEqual(spans.disjoint({"C1": a, "C2": b})[0], False)

    def test_adjacent_pieces_do_not_clash(self):
        hay = spans.content("民進黨獲得 4,984,060 票，占 36.16%")
        a = spans.occurrences(spans.content("民進黨獲得 4,984,060 票"), hay)
        b = spans.occurrences(spans.content("占 36.16%"), hay)
        self.assertEqual(spans.disjoint({"C1": a, "C2": b}), (True, []))

    def test_clashes_are_reported_as_separate_groups(self):
        hay = spans.content("甲乙丙。丁戊己。")
        s1 = spans.occurrences(spans.content("甲乙丙"), hay)
        s2 = spans.occurrences(spans.content("丁戊己"), hay)
        ok, groups = spans.clash_groups({"C1": s1, "C2": s1, "C3": s1, "C4": s2, "C5": s2})
        self.assertFalse(ok)
        self.assertEqual(groups, [["C1", "C2", "C3"], ["C4", "C5"]])

    def test_search_that_runs_too_long_counts_as_a_clash(self):
        hay = spans.content("甲乙" * 12)
        occ = spans.occurrences(spans.content("甲乙"), hay)
        items = {f"C{i}": occ for i in range(1, 14)}  # 13 claims, 12 places: impossible, and expensive to prove
        self.assertFalse(spans.disjoint(items)[0])

    def test_choice_of_position_is_searched_not_greedy(self):
        # C1 fits either place; C2 only fits the first, so C1 must take the second.
        hay = spans.content("甲乙丙。甲乙")
        c1 = spans.occurrences(spans.content("甲乙"), hay)
        c2 = spans.occurrences(spans.content("甲乙丙"), hay)
        self.assertEqual(spans.disjoint({"C1": c1, "C2": c2}), (True, []))


if __name__ == "__main__":
    unittest.main()
