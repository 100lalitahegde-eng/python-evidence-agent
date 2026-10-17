import asyncio
import multiprocessing
import time
import unittest
from evidence_agent.assessment import LexicalAssessment
from evidence_agent.domain import Policy
from evidence_agent.service import EvidenceService
from test_service import Fake, REQUEST


class SlowAssessment:
    def candidates(self, claim, sources):
        time.sleep(30)
        return []


class ExplodingAssessment:
    def candidates(self, claim, sources):
        raise RuntimeError("private detail")


class BoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_slow_assessment_deadline_reaps_worker(self):
        before = {p.pid for p in multiprocessing.active_children()}
        service = EvidenceService(Fake(), SlowAssessment(), Policy(deadline_seconds=.15))
        start = time.monotonic()
        result = await service.run(REQUEST)
        self.assertLess(time.monotonic() - start, 1)
        self.assertIn({"code": "deadline_exceeded", "operation": "assessment"}, result["errors"])
        self.assertEqual(result["claims"][0]["status"], "assessment incomplete")
        self.assertEqual({p.pid for p in multiprocessing.active_children()}, before)
        service.assessment = LexicalAssessment()
        service.policy = Policy()
        self.assertEqual((await service.run(REQUEST))["status"], "complete")

    async def test_cancel_during_assessment_and_event_loop_responsive(self):
        before = {p.pid for p in multiprocessing.active_children()}
        service = EvidenceService(Fake(), SlowAssessment())
        task = asyncio.create_task(service.run(REQUEST))
        await asyncio.sleep(.1)
        self.assertFalse(task.done())
        start = time.monotonic()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertLess(time.monotonic() - start, .5)
        self.assertEqual(service._active, 0)
        self.assertEqual({p.pid for p in multiprocessing.active_children()}, before)

    async def test_worker_failure_is_sanitized(self):
        with self.assertRaisesRegex(ValueError, "invalid assessment output"):
            await EvidenceService(Fake(), ExplodingAssessment()).run(REQUEST)
