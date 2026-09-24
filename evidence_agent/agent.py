"""Offline research agent: retrieve, inspect, cite, and flag unsupported claims.

The deterministic policy is deliberate. No model or live web access is claimed.
It provides a reproducible baseline for later LLM-assisted planning.
"""
from dataclasses import dataclass
import json
from pathlib import Path
import re


@dataclass(frozen=True)
class Source:
    id: str
    title: str
    url: str
    text: str


class Corpus:
    def __init__(self, path: Path):
        records = json.loads(path.read_text(encoding="utf-8"))
        self.sources = [Source(**record) for record in records]
        if len({s.id for s in self.sources}) != len(self.sources):
            raise ValueError("duplicate source IDs")

    def search(self, question: str, limit: int = 3) -> list[Source]:
        terms = set(re.findall(r"[a-z]{4,}", question.lower()))
        scored = [(len(terms & set(re.findall(r"[a-z]{4,}", (s.title + " " + s.text).lower()))), s)
                  for s in self.sources]
        return [source for score, source in sorted(scored, key=lambda pair: (-pair[0], pair[1].id))
                if score > 0][:limit]

    def read(self, source_id: str) -> Source:
        return next(s for s in self.sources if s.id == source_id)


class Agent:
    def __init__(self, corpus: Corpus, max_reads: int = 3):
        self.corpus = corpus
        self.max_reads = max_reads

    def run(self, question: str, claims: list[str]) -> dict:
        if not question.strip() or not claims or len(claims) > 20:
            raise ValueError("question and 1–20 claims required")
        trace = []
        found = self.corpus.search(question, self.max_reads)
        trace.append({"tool": "search", "query": question, "results": [s.id for s in found]})
        sources = []
        for source in found:
            sources.append(self.corpus.read(source.id))
            trace.append({"tool": "read", "source_id": source.id})
        assessment = []
        for claim in claims:
            # Conservative lexical support signal, never treated as entailment.
            terms = set(re.findall(r"[a-z]{5,}", claim.lower()))
            matches = [s.id for s in sources if terms and
                       len(terms & set(re.findall(r"[a-z]{5,}", s.text.lower()))) / len(terms) >= .75]
            assessment.append({"claim": claim, "candidate_sources": matches,
                               "status": "needs human verification" if matches else "unsupported by retrieved text"})
        return {"question": question, "sources": [{"id": s.id, "title": s.title, "url": s.url} for s in sources],
                "claims": assessment, "trace": trace, "read_budget": self.max_reads}
