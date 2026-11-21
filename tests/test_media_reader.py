from __future__ import annotations

import asyncio

import pytest

from indagar.models import Source
from indagar.research.media_reader import YouTubeTranscriptReader
from indagar.research.reader import ReadError


def _source(url: str = "https://www.youtube.com/watch?v=abc") -> Source:
    return Source(title="Video", url=url, provider="youtube", source_type="media")


def test_youtube_reader_extracts_vtt_captions():
    def extractor(url: str) -> dict:
        return {"subtitles": {"en": [{"url": "https://example.com/captions.vtt", "ext": "vtt"}]}}

    async def fetcher(url: str) -> str:
        return """WEBVTT

00:00:00.000 --> 00:00:02.000
Photosynthesis converts light energy.

00:00:02.000 --> 00:00:04.000
It releases oxygen.
"""

    reader = YouTubeTranscriptReader(extractor=extractor, fetcher=fetcher)
    content = asyncio.run(reader.read(_source()))

    assert "Photosynthesis converts light energy." in content.text
    assert "It releases oxygen." in content.text
    assert content.provider == "youtube"


def test_youtube_reader_requires_captions():
    reader = YouTubeTranscriptReader(
        extractor=lambda url: {"subtitles": {}},
        fetcher=lambda url: "",
    )

    with pytest.raises(ReadError, match="no captions"):
        asyncio.run(reader.read(_source()))


def test_youtube_reader_rejects_other_hosts():
    reader = YouTubeTranscriptReader(extractor=lambda url: {})

    with pytest.raises(ReadError, match="not a YouTube"):
        asyncio.run(reader.read(Source("Page", "https://example.com")))
