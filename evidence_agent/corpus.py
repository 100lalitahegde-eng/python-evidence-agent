"""Bounded local retrieval adapter. URLs are metadata, never fetched."""
import json
from pathlib import Path
import re
from types import MappingProxyType
from .domain import Source, integer
from .ports import ProviderError


def terms(value: str) -> set[str]:
    return set(re.findall(r"[a-z]{4,}", value.lower()))


class Corpus:
    def __init__(self, path: Path):
        with Path(path).open("rb") as stream:
            raw = stream.read(4_000_001)
        if len(raw) > 4_000_000:
            raise ValueError("corpus exceeds 4 MB")
        records = json.loads(raw)
        if not isinstance(records, list) or not 1 <= len(records) <= 1000:
            raise ValueError("corpus must contain 1–1000 sources")
        sources = []
        for record in records:
            if not isinstance(record, dict) or set(record) != {"id", "title", "url", "text"}:
                raise ValueError("invalid corpus record schema")
            sources.append(Source(**record))
        if len({s.id for s in sources}) != len(sources):
            raise ValueError("duplicate source IDs")
        self.sources = tuple(sources)
        self._by_id = MappingProxyType({s.id: s for s in sources})
        self._index = tuple((terms(s.title + " " + s.text), s) for s in sources)

    def search(self, question: str, limit: int = 3) -> list[Source]:
        integer(limit, "limit", 1, 20)
        query = terms(question)
        scored = [(len(query & tokens), source) for tokens, source in self._index]
        return [source for score, source in sorted(scored, key=lambda item: (-item[0], item[1].id))
                if score > 0][:limit]

    def read(self, source_id: str) -> Source:
        try:
            return self._by_id[source_id]
        except KeyError:
            raise ProviderError("source not found") from None


class LocalRetrieval:
    def __init__(self, corpus: Corpus):
        self.corpus = corpus

    async def search(self, question: str, limit: int) -> list[str]:
        return [s.id for s in self.corpus.search(question, limit)]

    async def read(self, source_id: str) -> Source:
        return self.corpus.read(source_id)
