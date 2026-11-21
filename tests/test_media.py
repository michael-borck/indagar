from __future__ import annotations

import asyncio

import httpx

from indagar.config import Settings
from indagar.search.media import (
    PodcastProvider,
    YouTubeProvider,
    build_media_chain,
)


def test_youtube_provider_uses_extractor():
    def extractor(query: str, limit: int) -> list[dict]:
        assert query == "photosynthesis"
        assert limit == 2
        return [
            {
                "id": "abc123",
                "title": "Photosynthesis explained",
                "description": "A video about photosynthesis.",
                "uploader": "Science Channel",
                "upload_date": "20240102",
            }
        ]

    provider = YouTubeProvider(extractor)
    results = asyncio.run(provider.search("photosynthesis", 2))

    assert len(results) == 1
    assert results[0].url == "https://www.youtube.com/watch?v=abc123"
    assert results[0].published == "2024-01-02"
    assert results[0].authors == "Science Channel"
    assert results[0].source_type == "media"
    assert results[0].confidence == "low"


def test_podcast_provider_shapes_episodes():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["media"] == "podcast"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "trackName": "Episode 1",
                        "trackViewUrl": "https://podcasts.apple.com/episode/1",
                        "description": "An episode.",
                        "releaseDate": "2025-01-02T10:00:00Z",
                        "artistName": "A Host",
                    }
                ]
            },
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = PodcastProvider(client=client)
            return await provider.search("photosynthesis", 2)

    results = asyncio.run(run())

    assert len(results) == 1
    assert results[0].title == "Episode 1"
    assert results[0].published == "2025-01-02"
    assert results[0].authors == "A Host"


def test_media_chain_is_optional_and_configurable():
    assert build_media_chain(Settings()).provider_names == ()
    chain = build_media_chain(Settings(media_enabled=True, media_order=("podcast",)))
    assert chain.provider_names == ("podcast",)
