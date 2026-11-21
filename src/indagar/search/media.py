from __future__ import annotations

import asyncio
import importlib.util
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime

import httpx

from ..config import Settings
from ..models import Source
from .base import SearchError
from .chain import SearchChain
from .providers import USER_AGENT


def _youtube_url(entry: dict) -> str:
    url = str(entry.get("webpage_url") or entry.get("url") or "")
    if url.startswith("http"):
        return url
    video_id = entry.get("id")
    return f"https://www.youtube.com/watch?v={video_id}" if video_id else ""


def _date(value: object) -> str:
    text = str(value or "")
    if not text:
        return ""
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return text[:10]


def _media_source(
    *,
    title: object,
    url: object,
    snippet: object,
    provider: str,
    published: object = "",
    authors: object = "",
) -> Source | None:
    clean_title = " ".join(str(title or "").split())
    clean_url = str(url or "").strip()
    if not clean_title or not clean_url.startswith(("http://", "https://")):
        return None
    return Source(
        title=clean_title,
        url=clean_url,
        snippet=" ".join(str(snippet or "").split())[:600],
        provider=provider,
        source_type="media",
        confidence="low",
        published=_date(published),
        authors=" ".join(str(authors or "").split()),
    )


class YouTubeProvider:
    name = "youtube"

    def __init__(
        self,
        extractor: Callable[[str, int], list[dict]] | None = None,
    ):
        self._extractor = extractor or _youtube_extract

    async def search(self, query: str, limit: int) -> list[Source]:
        if self._extractor is _youtube_extract and (importlib.util.find_spec("yt_dlp") is None):
            raise SearchError(self.name, "Install yt-dlp for YouTube search.")
        try:
            entries = await asyncio.to_thread(
                self._extractor,
                query,
                min(max(limit, 1), 20),
            )
        except Exception as exc:
            raise SearchError(self.name, f"youtube search failed: {exc}") from exc
        results: list[Source] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            source = _media_source(
                title=entry.get("title"),
                url=_youtube_url(entry),
                snippet=entry.get("description"),
                provider=self.name,
                published=entry.get("upload_date"),
                authors=entry.get("uploader") or entry.get("channel"),
            )
            if source:
                results.append(source)
        return results


def _youtube_extract(query: str, limit: int) -> list[dict]:
    from yt_dlp import YoutubeDL

    options = {
        "quiet": True,
        "skip_download": True,
        "extract_flat": True,
        "noplaylist": True,
    }
    with YoutubeDL(options) as youtube:
        data = youtube.extract_info(f"ytsearch{limit}:{query}", download=False)
    entries = data.get("entries") if isinstance(data, dict) else None
    return [entry for entry in entries or [] if isinstance(entry, dict)]


class PodcastProvider:
    name = "podcast"

    def __init__(self, client: httpx.AsyncClient | None = None):
        self._client = client

    @asynccontextmanager
    async def _client_ctx(self) -> AsyncIterator[httpx.AsyncClient]:
        if self._client is not None:
            yield self._client
        else:
            async with httpx.AsyncClient(timeout=30.0) as client:
                yield client

    async def search(self, query: str, limit: int) -> list[Source]:
        try:
            async with self._client_ctx() as client:
                response = await client.get(
                    "https://itunes.apple.com/search",
                    params={
                        "term": query,
                        "media": "podcast",
                        "entity": "podcastEpisode",
                        "limit": min(max(limit, 1), 20),
                    },
                    headers={
                        "accept": "application/json",
                        "user-agent": USER_AGENT,
                    },
                )
        except httpx.HTTPError as exc:
            raise SearchError(self.name, f"podcast request failed: {exc}") from exc
        if response.status_code >= 400:
            raise SearchError(
                self.name,
                f"podcast returned HTTP {response.status_code}",
                status=response.status_code,
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise SearchError(self.name, "podcast returned invalid JSON") from exc
        results: list[Source] = []
        for item in (data.get("results") or []) if isinstance(data, dict) else []:
            if not isinstance(item, dict):
                continue
            source = _media_source(
                title=item.get("trackName") or item.get("collectionName"),
                url=item.get("trackViewUrl") or item.get("collectionViewUrl"),
                snippet=item.get("description"),
                provider=self.name,
                published=item.get("releaseDate"),
                authors=item.get("artistName"),
            )
            if source:
                results.append(source)
        return results


def create_media_provider(name: str, settings: Settings):
    if name == "youtube":
        if importlib.util.find_spec("yt_dlp") is None:
            return None
        return YouTubeProvider()
    if name == "podcast":
        return PodcastProvider()
    return None


def build_media_chain(settings: Settings) -> SearchChain:
    providers = [
        provider
        for name in settings.configured_media_providers()
        if (provider := create_media_provider(name, settings)) is not None
    ]
    return SearchChain(providers)


__all__ = [
    "PodcastProvider",
    "YouTubeProvider",
    "build_media_chain",
    "create_media_provider",
]
