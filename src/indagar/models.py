from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlparse


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class Source:
    title: str
    url: str
    snippet: str = ""
    provider: str = ""
    source_type: str = "web"
    sub_question: str | None = None

    @property
    def domain(self) -> str:
        try:
            return urlparse(self.url).hostname or ""
        except ValueError:
            return ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class Citation:
    id: str
    source_url: str
    title: str
    quote: str
    locator: str | None = None
    sub_question: str | None = None
    note: str = ""
    source_type: str = "web"

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("citation id is required")
        if not self.source_url.strip():
            raise ValueError("citation source_url is required")
        if not self.quote.strip():
            raise ValueError("citation quote is required")
        object.__setattr__(self, "title", " ".join(self.title.split()))
        object.__setattr__(self, "quote", " ".join(self.quote.split()))

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SubQuestion:
    question: str
    rationale: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ResearchPlan:
    question: str
    sub_questions: tuple[SubQuestion, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "question": self.question,
            "sub_questions": [item.to_dict() for item in self.sub_questions],
        }


@dataclass(frozen=True)
class SearchAttempt:
    provider: str
    status: str
    count: int
    latency_ms: int
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SearchOutcome:
    sources: tuple[Source, ...]
    attempts: tuple[SearchAttempt, ...]


@dataclass
class Run:
    id: str
    question: str
    plan: ResearchPlan
    sources: tuple[Source, ...]
    attempts: tuple[SearchAttempt, ...]
    report: str
    citations: tuple[Citation, ...] = ()
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "question": self.question,
            "created_at": self.created_at,
            "plan": self.plan.to_dict(),
            "sources": [source.to_dict() for source in self.sources],
            "attempts": [attempt.to_dict() for attempt in self.attempts],
            "citations": [citation.to_dict() for citation in self.citations],
            "report": self.report,
        }
