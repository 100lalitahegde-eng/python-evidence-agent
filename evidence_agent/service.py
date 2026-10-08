"""Async application orchestration; no filesystem, model SDK or network dependency."""
import asyncio
from dataclasses import asdict
import logging
import time
from uuid import uuid4
from .domain import Policy, Request, Source
from .ports import Assessment, ProviderError, Retrieval, TransientProviderError

logger = logging.getLogger(__name__)


class BusyError(Exception):
    """Admission rejected immediately; caller owns retry/backpressure policy."""


class _Failure(Exception):
    def __init__(self, code):
        self.code = code


class EvidenceService:
    """One event-loop lifetime per instance. No unbounded waiting admission queue."""
    def __init__(self, retrieval: Retrieval, assessment: Assessment, policy: Policy = Policy()):
        self.retrieval, self.assessment, self.policy = retrieval, assessment, policy
        self._active = 0
        self._loop = None

    async def run(self, request: Request) -> dict:
        if not isinstance(request, Request):
            raise ValueError("a validated Request is required")
        loop = asyncio.get_running_loop()
        if self._loop is not None and self._loop is not loop:
            raise RuntimeError("service must remain on one event loop")
        self._loop = loop
        if self._active >= self.policy.max_concurrent:
            raise BusyError("service capacity exhausted")
        self._active += 1  # No await between admission check and increment.
        started = time.monotonic()
        deadline = started + self.policy.deadline_seconds
        run_id = str(uuid4())
        trace, errors, sources = [], [], []
        calls = 0

        async def call(operation, factory):
            nonlocal calls
            for attempt in range(1, self.policy.max_attempts + 1):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise _Failure("deadline_exceeded")
                if calls >= self.policy.max_calls:
                    raise _Failure("call_budget_exhausted")
                calls += 1
                began = time.monotonic()
                code = "ok"
                try:
                    value = await asyncio.wait_for(factory(), min(remaining, self.policy.call_timeout_seconds))
                    if time.monotonic() > deadline:
                        raise _Failure("deadline_exceeded")
                    return value
                except asyncio.TimeoutError:
                    code = "provider_timeout"
                except TransientProviderError:
                    code = "provider_transient"
                except ProviderError:
                    code = "provider_failure"
                    raise _Failure(code) from None
                except asyncio.CancelledError:
                    code = "cancelled"
                    raise
                except _Failure as exc:
                    code = exc.code
                    raise
                except Exception:
                    code = "provider_internal_error"
                    raise _Failure(code) from None
                finally:
                    trace.append({"tool": operation, "attempt": attempt, "outcome": code,
                                  "duration_ms": round((time.monotonic() - began) * 1000, 3)})
                if attempt == self.policy.max_attempts:
                    raise _Failure(code)
                delay = self.policy.retry_delay_seconds * 2 ** (attempt - 1)
                if time.monotonic() + delay >= deadline:
                    raise _Failure("deadline_exceeded")
                await asyncio.sleep(delay)

        try:
            try:
                ids = await call("search", lambda: self.retrieval.search(request.question, self.policy.max_reads))
                if (not isinstance(ids, list) or len(ids) > self.policy.max_reads
                        or any(not isinstance(i, str) or not i.strip() or len(i) > 128 for i in ids)
                        or len(set(ids)) != len(ids)):
                    raise _Failure("invalid_provider_response")
                for source_id in ids:
                    try:
                        source = await call("read", lambda: self.retrieval.read(source_id))
                        if not isinstance(source, Source) or source.id != source_id:
                            raise _Failure("invalid_provider_response")
                        sources.append(source)
                    except _Failure as exc:
                        errors.append({"code": exc.code, "operation": "read"})
                        if exc.code in {"deadline_exceeded", "call_budget_exhausted"}:
                            break
            except _Failure as exc:
                errors.append({"code": exc.code, "operation": "search"})
            assessments = []
            for claim in request.claims:
                citations = self.assessment.candidates(claim, tuple(sources))
                if not isinstance(citations, list) or len(citations) > len(sources):
                    raise ValueError("invalid assessment output")
                by_id = {s.id: s for s in sources}
                for citation in citations:
                    citation.validate(by_id[citation.source_id])
                assessments.append({"claim": claim,
                                    "status": "needs human verification" if citations else
                                    "retrieval incomplete" if errors else "unsupported by retrieved text",
                                    "candidate_sources": list(dict.fromkeys(c.source_id for c in citations)),
                                    "citations": [asdict(c) for c in citations]})
            status = "partial" if errors and sources else "failed" if errors else "complete"
            result = {"schema_version": "1.0", "run_id": run_id, "status": status,
                      "question": request.question, "claims": assessments,
                      "sources": [{"id": s.id, "title": s.title, "url": s.url, "sha256": s.digest} for s in sources],
                      "trace": trace, "errors": errors, "read_budget": self.policy.max_reads,
                      "metrics": {"tool_calls": calls, "sources_read": len(sources),
                                  "duration_ms": round((time.monotonic() - started) * 1000, 3)}}
            logger.info("evidence_run", extra={"run_id": run_id, "status": status, "tool_calls": calls})
            return result
        finally:
            self._active -= 1
