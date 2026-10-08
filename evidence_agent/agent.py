"""Compatibility facade for synchronous callers. Async products use EvidenceService."""
import asyncio
from .assessment import LexicalAssessment
from .corpus import Corpus, LocalRetrieval
from .domain import Policy, Request, Source
from .service import EvidenceService

__all__ = ["Agent", "Corpus", "Source"]


class Agent:
    def __init__(self, corpus: Corpus, max_reads: int = 3):
        self.corpus = corpus
        self.policy = Policy(max_reads=max_reads)

    def run(self, question: str, claims: list[str]) -> dict:
        if not isinstance(claims, list):
            raise ValueError("claims must be a list")
        request = Request(question, tuple(claims))
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(EvidenceService(LocalRetrieval(self.corpus), LexicalAssessment(), self.policy).run(request))
        raise RuntimeError("use EvidenceService.run in async applications")
