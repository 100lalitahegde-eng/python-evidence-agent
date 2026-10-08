"""Deterministic lexical candidates, never an entailment/factuality decision."""
import re
from .corpus import terms
from .domain import Citation, Source


class LexicalAssessment:
    def candidates(self, claim: str, sources: tuple[Source, ...]) -> list[Citation]:
        wanted = terms(claim)
        if not wanted:
            return []
        citations = []
        for source in sources:
            # Sentence spans preserve exact character offsets in the source snapshot.
            for match in re.finditer(r"[^.!?\n]+[.!?]?", source.text):
                if len(wanted & terms(match.group())) / len(wanted) >= 0.75:
                    # Never silently truncate a matching span into different evidence.
                    if len(match.group()) <= 1000:
                        citations.append(Citation(source.id, source.digest,
                                                  match.start(), match.end(), match.group()))
                    break
        return citations
