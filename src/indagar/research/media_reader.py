from __future__ import annotations

import asyncio
import html
import re
from collections.abc import Awaitable, Callable

import httpx

from ..models import Source
from .reader import ReadError, SourceContent


def _youtube_info(url: str) -> dict:
    from yt_dlp import YoutubeDL

    options = {
        "quiet": True,
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["en", "en-US", "en-GB", "en-orig"],
        "subtitlesformat": "vtt",
    }
    with YoutubeDL(options) as youtube:
        info = youtube.extract_info(url, download=False)
    return info if isinstance(info, dict) else {}


def _vtt_to_text(value: str) -> str:
    lines: list[str] = []
    for raw in value.splitlines():
        line = raw.strip()
        if not line or line == "WEBVTT" or line.startswith(("NOTE", "Kind:", "Language:")):
            continue
        if "-->" in line or line.isdigit():
            continue
        line = html.unescape(re.sub(r"<[^>]+>", "", line))
        if line and (not lines or lines[-1] != line):
            lines.append(line)
    return " ".join(lines)


class YouTubeTranscriptReader:
    name = "youtube"

    def __init__(
        self,
        *,
        max_chars: int = 12000,
        extractor: Callable[[str], dict] | None = None,
        fetcher: Callable[[str], Awaitable[str]] | None = None,
        client: httpx.AsyncClient | None = None,
    ):
        self.max_chars = max_chars
        self._extractor = extractor or _youtube_info
        self._fetcher = fetcher
        self._client = client

    async def _fetch(self, url: str) -> str:
        if self._fetcher is not None:
            return await self._fetcher(url)
        try:
            if self._client is not None:
                response = await self._client.get(url)
            else:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(url)
        except httpx.HTTPError as exc:
            raise ReadError(url, f"caption request failed: {exc}") from exc
        if response.status_code >= 400:
            raise ReadError(
                url,
                f"captions returned HTTP {response.status_code}",
                status=response.status_code,
            )
        return response.text

    async def read(self, source: Source) -> SourceContent:
        host = source.domain.removeprefix("www.")
        if host not in {"youtube.com", "m.youtube.com", "youtu.be"}:
            raise ReadError(source.url, "not a YouTube source")
        try:
            info = await asyncio.to_thread(self._extractor, source.url)
        except Exception as exc:
            raise ReadError(source.url, f"youtube metadata failed: {exc}") from exc

        tracks = info.get("subtitles") or info.get("automatic_captions") or {}
        if not isinstance(tracks, dict):
            raise ReadError(source.url, "youtube returned no caption tracks")
        entries = None
        for language in ("en", "en-US", "en-GB", "en-orig"):
            value = tracks.get(language)
            if isinstance(value, list) and value:
                entries = value
                break
        if entries is None:
            for value in tracks.values():
                if isinstance(value, list) and value:
                    entries = value
                    break
        if not entries:
            raise ReadError(source.url, "youtube has no captions")
        first = entries[0]
        caption_url = first.get("url") if isinstance(first, dict) else None
        if not isinstance(caption_url, str):
            raise ReadError(source.url, "youtube caption URL is missing")

        text = _vtt_to_text(await self._fetch(caption_url))
        if not text:
            raise ReadError(source.url, "youtube captions were empty")
        truncated = len(text) > self.max_chars
        if truncated:
            text = text[: self.max_chars].rstrip()
        return SourceContent(
            url=source.url,
            title=source.title,
            text=text,
            provider=self.name,
            truncated=truncated,
        )


__all__ = ["YouTubeTranscriptReader"]
