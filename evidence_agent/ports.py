"""Provider contracts: implementations must cooperate with asyncio cancellation."""
from typing import Protocol
from .domain import Citation, Source


class ProviderError(Exception):
    """Permanent retrieval failure. Message is never copied to output/telemetry."""


class TransientProviderError(ProviderError):
    """Only this provider failure is retried (along with call timeouts)."""


class Retrieval(Protocol):
    async def search(self, question: str, limit: int) -> list[str]: ...
    async def read(self, source_id: str) -> Source: ...


class Assessment(Protocol):
    """Picklable module-level implementation; runs in a disposable spawned process."""
    def candidates(self, claim: str, sources: tuple[Source, ...]) -> list[Citation]: ...

