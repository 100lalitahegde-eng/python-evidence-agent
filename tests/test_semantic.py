import asyncio
from dataclasses import replace
import unittest
from evidence_agent.domain import Citation
from evidence_agent.semantic import AssessedClaim, Judgment, SemanticAssessment, decide
from evidence_agent.service import EvidenceService
from test_service import Fake, REQUEST, SOURCE


class FixtureSemantic:
    def assess_claim(self, claim, sources):
        citations = [Citation(s.id, s.digest, 0, len(s.text), s.text) for s in sources]
        return AssessedClaim(citations, [Judgment(s.id, 'contradiction', .98, 'test_fixture', c) for s,c in zip(sources,citations)], model='test-fixture', revision='test')


class BadSemantic(FixtureSemantic):
    def assess_claim(self, claim, sources):
        row = super().assess_claim(claim, sources)
        row.judgments[0] = replace(row.judgments[0], citation=replace(row.citations[0], quote='fabricated'))
        return row


class SemanticTests(unittest.TestCase):
    def test_scores_abstention_and_neutral(self):
        self.assertEqual(decide({'entailment':.97,'contradiction':.01,'neutral':.02}, 'holds consume capacity','holds consume capacity')[0], 'support')
        self.assertEqual(decide({'entailment':.01,'contradiction':.97,'neutral':.02}, 'holds consume capacity','holds do not consume capacity')[0], 'contradiction')
        self.assertEqual(decide({'entailment':.01,'contradiction':.02,'neutral':.97}, 'holds consume capacity','a question about holds')[0], 'uncertain')
        self.assertEqual(decide({'entailment':.01,'contradiction':.02,'neutral':.97}, 'holds consume capacity','bananas are yellow')[0], 'irrelevant')
        self.assertEqual(decide({'entailment':.6,'contradiction':.3,'neutral':.1}, 'a','b')[0], 'uncertain')
        with self.assertRaises(ValueError):
            decide({'entailment':float('nan'),'contradiction':.1,'neutral':.1}, 'a','b')
        for kwargs in ({'threshold':float('nan')},{'max_tokens':True},{'margin':-1}):
            with self.assertRaises(ValueError):
                SemanticAssessment(**kwargs)

    def test_nondecisive_without_citation_and_bad_scores(self):
        Judgment(SOURCE.id, 'uncertain', None, 'too_long').validate(SOURCE)
        with self.assertRaises(ValueError):
            Judgment(SOURCE.id, 'support', .95, 'prediction').validate(SOURCE)
        with self.assertRaises(ValueError):
            Judgment(SOURCE.id, 'uncertain', float('nan'), 'prediction').validate(SOURCE)


class SemanticServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_semantic_output_remains_predictions(self):
        result = await EvidenceService(Fake(), FixtureSemantic()).run(REQUEST)
        claim = result['claims'][0]
        self.assertEqual(claim['semantic']['judgments'][0]['label'], 'contradiction')
        self.assertEqual(claim['status'], 'needs human verification')
        Citation(**claim['citations'][0]).validate(SOURCE)

    async def test_semantic_fabrication_rejected(self):
        with self.assertRaises(ValueError):
            await EvidenceService(Fake(), BadSemantic()).run(REQUEST)
