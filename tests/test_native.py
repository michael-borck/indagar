from __future__ import annotations

import asyncio
import json

import httpx

from indagar.config import Settings
from indagar.search.providers import ExaProvider, TavilyProvider, create_provider


def test_tavily_provider_shapes_results():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer tvly-key"
        payload = json.loads(request.content)
        assert payload["query"] == "photosynthesis"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Tavily result",
                        "url": "https://example.com/a",
                        "content": "A snippet.",
                    }
                ]
            },
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = TavilyProvider("tvly-key", client=client)
            return await provider.search("photosynthesis", 3)

    results = asyncio.run(run())

    assert len(results) == 1
    assert results[0].title == "Tavily result"
    assert results[0].provider == "tavily"


def test_exa_provider_shapes_results():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-api-key"] == "exa-key"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Exa result",
                        "url": "https://example.com/b",
                        "text": "Exa content.",
                    }
                ]
            },
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = ExaProvider("exa-key", client=client)
            return await provider.search("photosynthesis", 3)

    results = asyncio.run(run())

    assert len(results) == 1
    assert results[0].title == "Exa result"
    assert results[0].snippet == "Exa content."


def test_native_provider_selection():
    settings = Settings(tavily_api_key="t", exa_api_key="e")

    assert create_provider("tavily", settings).name == "tavily"
    assert create_provider("exa", settings).name == "exa"
    assert settings.configured_search_providers()[-2:] == ("tavily", "exa")
