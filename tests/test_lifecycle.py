"""Event-gated lifecycle tests avoid relying on provider timing."""
import asyncio
import unittest

from evidence_agent.assessment import LexicalAssessment
from evidence_agent.domain import Citation, Request, Source
from evidence_agent.service import AssessmentError, ClosedError, EvidenceService

SOURCE = Source('one', 'Capacity', 'local://one', 'Active holds consume capacity.')
REQUEST = Request('capacity', ('Active holds consume capacity.',))


class GatedRetrieval:
    def __init__(self):
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def search(self, question, limit):
        self.entered.set()
        await self.release.wait()
        return ['one']

    async def read(self, source_id):
        return SOURCE


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_shutdown_rejects_new_work_and_drains_existing_work(self):
        provider = GatedRetrieval()
        service = EvidenceService(provider, LexicalAssessment())
        request = asyncio.create_task(service.run(REQUEST))
        await provider.entered.wait()
        closing = asyncio.create_task(service.aclose())
        await asyncio.sleep(0)
        self.assertFalse(service.accepting)
        self.assertEqual(service.active_runs, 1)
        self.assertFalse(closing.done())
        with self.assertRaises(ClosedError):
            await service.run(REQUEST)
        provider.release.set()
        self.assertEqual((await request)['status'], 'complete')
        await closing
        await service.aclose()
        self.assertEqual(service.active_runs, 0)
        with self.assertRaises(ClosedError):
            async with service:
                self.fail('closed instance reopened')

    async def test_cancelled_shutdown_wait_does_not_cancel_work_or_reopen(self):
        provider = GatedRetrieval()
        service = EvidenceService(provider, LexicalAssessment())
        request = asyncio.create_task(service.run(REQUEST))
        await provider.entered.wait()
        closing = asyncio.create_task(service.aclose())
        await asyncio.sleep(0)
        closing.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await closing
        self.assertFalse(request.done())
        self.assertFalse(service.accepting)
        request.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await request
        await service.aclose()
        self.assertEqual(service.active_runs, 0)

    async def test_multiple_shutdown_waiters_and_context_manager(self):
        provider = GatedRetrieval()
        service = EvidenceService(provider, LexicalAssessment())
        async with service:
            request = asyncio.create_task(service.run(REQUEST))
            await provider.entered.wait()
            waiters = [asyncio.create_task(service.aclose()) for _ in range(2)]
            await asyncio.sleep(0)
            self.assertTrue(all(not waiter.done() for waiter in waiters))
            provider.release.set()
            await request
            await asyncio.gather(*waiters)
        self.assertFalse(service.accepting)

    async def test_assessment_contract_failures_release_capacity(self):
        class BrokenAssessment:
            value = None
            def candidates(self, claim, sources):
                if isinstance(self.value, Exception):
                    raise self.value
                return self.value
        provider = GatedRetrieval()
        provider.release.set()
        assessor = BrokenAssessment()
        service = EvidenceService(provider, assessor)
        for value in (None, [object()], [Citation('missing', SOURCE.digest, 0, 1, 'A')],
                      RuntimeError('sensitive source content')):
            assessor.value = value
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(AssessmentError) as caught:
                    await service.run(REQUEST)
                self.assertEqual(str(caught.exception), 'assessment failed validation')
                self.assertEqual(service.active_runs, 0)
        service.assessment = LexicalAssessment()
        self.assertEqual((await service.run(REQUEST))['status'], 'complete')
        await service.aclose()


class LoopOwnershipTests(unittest.TestCase):
    def test_close_cannot_move_service_to_another_loop(self):
        service = EvidenceService(GatedRetrieval(), LexicalAssessment())
        asyncio.run(service.aclose())
        with self.assertRaises(RuntimeError):
            asyncio.run(service.aclose())
