import asyncio
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from evidence_agent.assessment import LexicalAssessment
from evidence_agent.corpus import Corpus, LocalRetrieval
from evidence_agent.domain import Citation, Policy, Request, Source
from evidence_agent.ports import ProviderError, TransientProviderError
from evidence_agent.service import BusyError, EvidenceService
from evidence_agent.store import RunStore

SOURCE = Source("one", "Capacity", "local://one", "An active reservation consumes inventory capacity.")
REQUEST = Request("reservation capacity", ("An active reservation consumes inventory capacity.",))


class Fake:
    def __init__(self):
        self.searches = 0
        self.reads = 0

    async def search(self, question, limit):
        self.searches += 1
        return ["one"]

    async def read(self, source_id):
        self.reads += 1
        return SOURCE


class Fabricator:
    def candidates(self, claim, sources):
        return [Citation("one", SOURCE.digest, 0, 2, "fabricated")]


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_citation_and_safe_telemetry(self):
        service = EvidenceService(Fake(), LexicalAssessment())
        with self.assertLogs("evidence_agent.service", level="INFO") as logs:
            result = await service.run(REQUEST)
        self.assertEqual(result["status"], "complete")
        citation = Citation(**result["claims"][0]["citations"][0])
        citation.validate(SOURCE)
        self.assertEqual(result["metrics"]["tool_calls"], 2)
        self.assertNotIn(REQUEST.question, str(result["trace"]))
        self.assertNotIn(REQUEST.question, str(logs.output))
        with self.assertRaises(ValueError):
            replace(citation, quote="invented evidence").validate(SOURCE)

    async def test_transient_retry_and_budget(self):
        class Flaky(Fake):
            async def search(self, question, limit):
                self.searches += 1
                if self.searches == 1:
                    raise TransientProviderError("private provider details")
                return ["one"]
        fake = Flaky()
        service = EvidenceService(fake, LexicalAssessment(), Policy(retry_delay_seconds=.001))
        result = await service.run(REQUEST)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(fake.searches, 2)
        self.assertEqual(result["metrics"]["tool_calls"], 3)
        self.assertNotIn("private provider details", json.dumps(result))
        limited = EvidenceService(Fake(), LexicalAssessment(), Policy(max_calls=1))
        result = await limited.run(REQUEST)
        self.assertEqual(result["errors"][0]["code"], "call_budget_exhausted")
        self.assertEqual(result["claims"][0]["status"], "retrieval incomplete")

    async def test_retry_exhaustion_is_bounded(self):
        class Failing(Fake):
            async def search(self, question, limit):
                self.searches += 1
                raise TransientProviderError("sensitive adapter message")
        fake = Failing()
        result = await EvidenceService(fake, LexicalAssessment(),
                                       Policy(max_attempts=3, retry_delay_seconds=.001)).run(REQUEST)
        self.assertEqual(fake.searches, 3)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["errors"][0]["code"], "provider_transient")
        self.assertEqual(len(result["trace"]), 3)

    async def test_permanent_failure_never_retried(self):
        class Broken(Fake):
            async def search(self, question, limit):
                self.searches += 1
                raise ProviderError("secret")
        fake = Broken()
        result = await EvidenceService(fake, LexicalAssessment()).run(REQUEST)
        self.assertEqual(fake.searches, 1)
        self.assertEqual(result["status"], "failed")
        self.assertNotIn("secret", json.dumps(result))

    async def test_timeout_and_deadline(self):
        class Slow(Fake):
            async def search(self, question, limit):
                await asyncio.Event().wait()
        policy = Policy(call_timeout_seconds=.01, max_attempts=1)
        result = await EvidenceService(Slow(), LexicalAssessment(), policy).run(REQUEST)
        self.assertEqual(result["errors"][0]["code"], "provider_timeout")
        result = await EvidenceService(Slow(), LexicalAssessment(), replace(policy, deadline_seconds=.005, max_attempts=2)).run(REQUEST)
        self.assertEqual(result["errors"][0]["code"], "deadline_exceeded")

    async def test_admission_cancellation_releases_capacity(self):
        entered, release = asyncio.Event(), asyncio.Event()
        class Gated(Fake):
            async def search(self, question, limit):
                entered.set()
                await release.wait()
                return ["one"]
        service = EvidenceService(Gated(), LexicalAssessment(), Policy(max_concurrent=1))
        first = asyncio.create_task(service.run(REQUEST))
        await entered.wait()
        with self.assertRaises(BusyError):
            await service.run(REQUEST)
        first.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await first
        release.set()
        self.assertEqual((await service.run(REQUEST))["status"], "complete")

    async def test_partial_read_failure_and_invalid_provider(self):
        class Partial(Fake):
            async def search(self, question, limit):
                return ["one", "missing"]
            async def read(self, source_id):
                if source_id == "missing":
                    raise ProviderError("unavailable")
                return SOURCE
        result = await EvidenceService(Partial(), LexicalAssessment()).run(REQUEST)
        self.assertEqual(result["status"], "partial")
        self.assertTrue(result["claims"][0]["citations"])
        class Wrong(Fake):
            async def read(self, source_id):
                return replace(SOURCE, id="different")
        result = await EvidenceService(Wrong(), LexicalAssessment()).run(REQUEST)
        self.assertEqual(result["errors"][0]["code"], "invalid_provider_response")
        self.assertEqual(result["sources"], [])
        class Duplicates(Fake):
            async def search(self, question, limit):
                return ["one", "one"]
        result = await EvidenceService(Duplicates(), LexicalAssessment()).run(REQUEST)
        self.assertEqual(result["errors"][0]["code"], "invalid_provider_response")

    async def test_bad_assessor_fails_closed(self):
        with self.assertRaises(ValueError):
            await EvidenceService(Fake(), Fabricator()).run(REQUEST)

    async def test_store_survives_reopen_and_rejects_overwrite(self):
        result = await EvidenceService(Fake(), LexicalAssessment()).run(REQUEST)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "runs.db"
            RunStore(path).save(result)
            reopened = RunStore(path)
            self.assertEqual(reopened.get(result["run_id"]), result)
            with self.assertRaises(sqlite3.IntegrityError):
                reopened.save(result)
            self.assertEqual(reopened.get(result["run_id"]), result)


class ValidationTests(unittest.TestCase):
    def test_policy_and_inputs(self):
        for value in (-1, 0, True, 1.5, 21):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Policy(max_reads=value)
        for value in (float("nan"), float("inf"), -1, True):
            with self.assertRaises(ValueError):
                Policy(deadline_seconds=value)
        for claims in ((), ("",), (42,), ("x" * 2001,)):
            with self.assertRaises(ValueError):
                Request("question", claims)
        with self.assertRaises(ValueError):
            replace(SOURCE, url="https://user:password@example.com")

    def test_corpus_validation(self):
        from dataclasses import asdict
        for records in ({}, [], [asdict(SOURCE), asdict(SOURCE)], [{"id": "missing fields"}]):
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "corpus.json"
                path.write_text(json.dumps(records))
                with self.assertRaises(ValueError):
                    Corpus(path)

    def test_cli_success_error_and_persistence(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "audit.db"
            cmd = [sys.executable, "-m", "evidence_agent.cli", "reservation capacity", "--claim", "active holds consume capacity"]
            result = subprocess.run(cmd + ["--audit-db", str(path)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(RunStore(path).get(data["run_id"]), data)
            failed_store = subprocess.run(cmd + ["--audit-db", str(Path(folder) / "missing" / "db")], capture_output=True, text=True, timeout=10)
            self.assertEqual(failed_store.returncode, 4)
            self.assertEqual(json.loads(failed_store.stdout)["error"]["code"], "persistence_failed")
            result = subprocess.run(cmd + ["--max-reads", "-1"], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)["error"]["code"], "invalid_input_or_corpus")

