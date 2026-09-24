import unittest
from pathlib import Path
from evidence_agent.agent import Agent, Corpus

CORPUS = Path(__file__).resolve().parents[1] / "corpus.json"


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.agent = Agent(Corpus(CORPUS), max_reads=2)

    def test_budget_and_trace(self):
        result = self.agent.run("How does a reservation hold consume capacity?", ["A hold consumes available capacity while active."])
        self.assertLessEqual(len(result["sources"]), 2)
        self.assertEqual(len(result["trace"]), len(result["sources"]) + 1)
        self.assertTrue(all(s["url"].startswith("local://") for s in result["sources"]))

    def test_unrelated_claim_flagged(self):
        result = self.agent.run("reservation hold", ["The moon is made of cheese."])
        self.assertEqual(result["claims"][0]["status"], "unsupported by retrieved text")

    def test_rejects_empty_input(self):
        with self.assertRaises(ValueError):
            self.agent.run("", ["a claim"])


if __name__ == "__main__":
    unittest.main()
