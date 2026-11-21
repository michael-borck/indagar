from __future__ import annotations

import asyncio

import httpx

from indagar.config import Settings
from indagar.search.academic import (
    ArxivProvider,
    CrossrefProvider,
    OpenAlexProvider,
    SemanticScholarProvider,
    build_academic_chain,
)


def _run(provider, query: str = "photosynthesis") -> list:
    async def run():
        transport = httpx.MockTransport(provider.handler)
        async with httpx.AsyncClient(transport=transport) as client:
            provider._client = client
            return await provider.search(query, 3)

    return asyncio.run(run())


def test_openalex_provider_shapes_sources():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["search"] == "photosynthesis"
        assert request.url.params["per-page"] == "3"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "A photosynthesis paper",
                        "doi": "https://doi.org/10.1000/example",
                        "primary_location": {"landing_page_url": "https://example.org/paper"},
                        "abstract_inverted_index": {
                            "Photosynthesis": [0],
                            "converts": [1],
                            "light.": [2],
                        },
                        "publication_year": 2024,
                        "authorships": [
                            {"author": {"display_name": "Ada Lovelace"}},
                            {"author": {"display_name": "Alan Turing"}},
                        ],
                    }
                ]
            },
        )

    provider = OpenAlexProvider()
    provider.handler = handler
    results = _run(provider)

    assert len(results) == 1
    source = results[0]
    assert source.title == "A photosynthesis paper"
    assert source.url == "https://doi.org/10.1000/example"
    assert source.snippet == "Photosynthesis converts light."
    assert source.published == "2024"
    assert source.authors == "Ada Lovelace, Alan Turing"
    assert source.source_type == "academic"
    assert source.confidence == "high"


def test_crossref_provider_shapes_sources():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "message": {
                    "items": [
                        {
                            "title": ["A Crossref paper"],
                            "DOI": "10.2000/example",
                            "abstract": "<jats:p>An abstract.</jats:p>",
                            "published-print": {"date-parts": [[2023, 1]]},
                            "author": [{"given": "Grace", "family": "Hopper"}],
                        }
                    ]
                }
            },
        )

    provider = CrossrefProvider()
    provider.handler = handler
    results = _run(provider)

    assert len(results) == 1
    assert results[0].url == "https://doi.org/10.2000/example"
    assert results[0].snippet == "An abstract."
    assert results[0].published == "2023"
    assert results[0].authors == "Grace Hopper"


def test_arxiv_provider_shapes_sources():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text="""<?xml version="1.0" encoding="UTF-8"?>
            <feed xmlns="http://www.w3.org/2005/Atom">
              <entry>
                <title>An arXiv paper</title>
                <id>https://arxiv.org/abs/2501.00001v1</id>
                <summary>A useful abstract.</summary>
                <published>2025-01-01T00:00:00Z</published>
                <author><name>Katherine Johnson</name></author>
              </entry>
            </feed>""",
        )

    provider = ArxivProvider()
    provider.handler = handler
    results = _run(provider)

    assert len(results) == 1
    assert results[0].url == "https://arxiv.org/abs/2501.00001v1"
    assert results[0].published == "2025-01-01"
    assert results[0].authors == "Katherine Johnson"


def test_semantic_scholar_provider_shapes_sources():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-api-key"] == "key"
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "title": "A Semantic Scholar paper",
                        "abstract": "An abstract.",
                        "url": "https://semanticscholar.org/paper/1",
                        "year": 2022,
                        "authors": [{"name": "Marie Curie"}],
                        "externalIds": {"DOI": "10.3000/example"},
                    }
                ]
            },
        )

    provider = SemanticScholarProvider("key")
    provider.handler = handler
    results = _run(provider)

    assert len(results) == 1
    assert results[0].url == "https://doi.org/10.3000/example"
    assert results[0].published == "2022"
    assert results[0].authors == "Marie Curie"


def test_academic_chain_uses_configured_providers():
    settings = Settings(
        openalex_mailto="test@example.com",
        semantic_scholar_api_key="key",
    )

    chain = build_academic_chain(settings)

    assert chain.provider_names == (
        "openalex",
        "crossref",
        "arxiv",
        "semantic-scholar",
    )


def test_academic_can_be_disabled():
    settings = Settings(academic_enabled=False)

    assert settings.configured_academic_providers() == ()
    assert build_academic_chain(settings).provider_names == ()


def test_openalex_mailto_is_sent():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["mailto"] == "test@example.com"
        return httpx.Response(200, json={"results": []})

    provider = OpenAlexProvider("test@example.com")
    provider.handler = handler

    assert _run(provider) == []
