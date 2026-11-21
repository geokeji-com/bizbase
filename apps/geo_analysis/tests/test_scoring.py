import unittest

from geo_analysis.scoring import evaluate, format_rate


class SampleRules(unittest.TestCase):
    def test_mention_in_negative_context_is_not_rank(self):
        value = evaluate('不推荐甲。', ['甲', '甲'], 'Unranked', 0, '不推荐甲', 'Exclude')
        self.assertEqual((value['hit'], value['included'], value['mentioned_as']), (0, 1, '甲'))

    def test_refusal_strategies(self):
        for policy, denominator in [('Exclude', 0), ('Include as miss', 1)]:
            with self.subTest(policy=policy):
                value = evaluate('无法推荐', ['甲'], 'Refusal', None, '无法推荐', policy)
                self.assertEqual((value['hit'], value['included']), (0, denominator))

    def test_ranked_needs_positive_rank_and_evidence_from_answer(self):
        for position, quote in [(0, '推荐甲'), (2, '推荐乙')]:
            with self.assertRaises(ValueError):
                evaluate('推荐甲', ['甲'], 'Ranked', position, quote, 'Exclude')
        for rank, expected in [(1, 1), (3, 1), (4, 0)]:
            value = evaluate('推荐甲', ['甲'], 'Ranked', rank, '推荐甲', 'Exclude')
            self.assertEqual(value['hit'], expected)

    def test_empty_denominator(self):
        self.assertEqual(format_rate(0, 0), '无有效样本')
        self.assertEqual(format_rate(1, 3), '33.33%')
