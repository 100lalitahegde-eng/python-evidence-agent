import unittest
from evaluations.semantic_score import metrics


class MetricTests(unittest.TestCase):
    def test_abstention_not_hidden_and_contradictions_counted(self):
        result=metrics([{'gold':'support','predicted':'uncertain'},
                        {'gold':'contradiction','predicted':'support'},
                        {'gold':'contradiction','predicted':'contradiction'}])
        self.assertEqual(result['per_label']['support']['recall'],0)
        self.assertEqual(result['per_label']['support']['precision'],0)
        self.assertEqual(result['per_label']['contradiction']['recall'],.5)
        self.assertEqual(result['contradiction_as_support'],1)
        self.assertAlmostEqual(result['abstention_rate'],1/3)
