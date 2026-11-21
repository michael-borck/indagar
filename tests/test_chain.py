from __future__ import annotations

import asyncio

from indagar.models import Source
from indagar.search.base import SearchError
from indagar.search.chain import SearchChain, normalize_url


class FakeProvider:
    name: str

    def __init__(
        self,
        name: str,
        results: list[Source] | None = None,
        error: Exception | None = None,
    ):
        self.name = name
        self.results = results or []
        self.error = error
        self.calls: list[int] = []

    async def search(self, query: str, limit: int) -> list[Source]:
        self.calls.append(limit)
        if self.error:
            raise self.error
        return self.results


def run(coro):
    return asyncio.run(coro)


def test_falls_through_an_error_and_records_attempts():
    first = FakeProvider("first", error=SearchError("first", "boom"))
    second = FakeProvider("second", results=[Source("A", "https://example.com/a")])
    chain = SearchChain([first, second])

    outcome = run(chain.search("query", 5))

    assert [attempt.status for attempt in outcome.attempts] == ["error", "ok"]
    assert outcome.sources[0].provider == "second"
    assert first.calls == [10]


def test_overfetches_deduplicates_and_filters_invalid_urls():
    provider = FakeProvider(
        "p",
        results=[
            Source("A", "https://www.example.com/a/?utm_source=newsletter"),
            Source("A again", "https://example.com/a"),
            Source("B", "https://example.com/b"),
            Source("Broken", "not-a-url"),
        ],
    )
    chain = SearchChain([provider])

    outcome = run(chain.search("query", 4))

    assert provider.calls == [8]
    assert len(outcome.sources) == 2
    assert [source.domain for source in outcome.sources] == [
        "www.example.com",
        "example.com",
    ]


def test_caches_identical_queries():
    provider = FakeProvider("p", results=[Source("A", "https://example.com/a")])
    chain = SearchChain([provider])

    run(chain.search("same query", 5))
    run(chain.search("same query", 5))

    assert len(provider.calls) == 1


def test_empty_results_are_not_cached():
    provider = FakeProvider("p", results=[])
    chain = SearchChain([provider])

    run(chain.search("query", 5))
    run(chain.search("query", 5))

    assert len(provider.calls) == 2


def test_classifies_source_type_and_confidence():
    provider = FakeProvider(
        "p",
        results=[
            Source("Paper", "https://www.nature.com/articles/example"),
            Source("Report", "https://www.cdc.gov/report"),
            Source("Video", "https://www.youtube.com/watch?v=1"),
        ],
    )
    chain = SearchChain([provider])

    outcome = run(chain.search("query", 5))

    assert [(source.source_type, source.confidence) for source in outcome.sources] == [
        ("academic", "high"),
        ("institution", "high"),
        ("media", "low"),
    ]


def test_normalize_url_strips_tracking_and_www():
    assert (
        normalize_url("https://www.Example.com/a/?utm_source=x&b=2") == "https://example.com/a?b=2"
    )
