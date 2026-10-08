"""Validated, immutable values shared by application and adapters."""
from dataclasses import dataclass
from hashlib import sha256
import math
from urllib.parse import urlsplit


def text(value: str, name: str, limit: int) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{name} must be nonblank text of at most {limit} characters")


def integer(value: int, name: str, low: int, high: int) -> None:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be an integer in [{low}, {high}]")


@dataclass(frozen=True)
class Source:
    id: str
    title: str
    url: str
    text: str

    def __post_init__(self):
        text(self.id, "source id", 128)
        text(self.title, "title", 512)
        text(self.text, "source text", 100_000)
        text(self.url, "url", 2048)
        parsed = urlsplit(self.url)
        if parsed.scheme not in {"local", "https"} or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError("source URL must be local:// or https:// without credentials")

    @property
    def digest(self) -> str:
        return sha256(self.text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Request:
    question: str
    claims: tuple[str, ...]

    def __post_init__(self):
        text(self.question, "question", 4000)
        if not isinstance(self.claims, tuple) or not 1 <= len(self.claims) <= 20:
            raise ValueError("claims must be a tuple of 1–20 strings")
        for claim in self.claims:
            text(claim, "claim", 2000)


@dataclass(frozen=True)
class Policy:
    max_reads: int = 3
    max_calls: int = 8
    max_attempts: int = 2
    max_concurrent: int = 8
    deadline_seconds: float = 10.0
    call_timeout_seconds: float = 2.0
    retry_delay_seconds: float = 0.05

    def __post_init__(self):
        for name, low, high in (("max_reads", 1, 20), ("max_calls", 1, 100),
                                ("max_attempts", 1, 5), ("max_concurrent", 1, 100)):
            integer(getattr(self, name), name, low, high)
        for name in ("deadline_seconds", "call_timeout_seconds", "retry_delay_seconds"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 300:
                raise ValueError(f"{name} must be finite and in (0, 300]")


@dataclass(frozen=True)
class Citation:
    source_id: str
    source_sha256: str
    start: int
    end: int
    quote: str

    def validate(self, source: Source) -> None:
        if (self.source_id != source.id or self.source_sha256 != source.digest
                or type(self.start) is not int or type(self.end) is not int
                or not 0 <= self.start < self.end <= len(source.text)
                or self.quote != source.text[self.start:self.end]):
            raise ValueError("citation does not match source snapshot")
