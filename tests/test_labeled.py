import unittest
from evaluations.score import evaluate


class LabeledTests(unittest.TestCase):
    def test_balanced_challenge_set_and_metrics(self):
        result = evaluate()
        self.assertEqual({v['total'] for v in result['by_label'].values()}, {12})
        self.assertIsNone(result['stance_accuracy'])
        self.assertGreater(result['by_label']['contradiction']['selected'], 0)
        self.assertGreater(result['by_label']['irrelevant']['selected'], 0)
        self.assertEqual(len({r['id'] for r in result['cases']}), 36)
