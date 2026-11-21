from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Protocol

import httpx

from .. import __version__
from ..config import Settings
from ..models import Source

USER_AGENT = f"Indagar/{__version__} (+https://github.com/michael-borck/indagar)"
BLOCK_TAGS = {
    "article",
    "br",
    "div",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "li",
    "p",
    "section",
    "tr",
}
SKIP_TAGS = {"script", "style", "noscript", "svg"}


class ReadError(Exception):
    """A source could not be read."""

    def __init__(self, url: str, message: str, status: int | None = None):
        super().__init__(message)
        self.url = url
        self.status = status


@dataclass(frozen=True)
class SourceContent:
    url: str
    title: str
    text: str
    provider: str
    truncated: bool = False


class Reader(Protocol):
    async def read(self, source: Source) -> SourceContent:
        """Return readable text for a source. Raise ReadError on failure."""
        ...


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in SKIP_TAGS:
            self._skip += 1
        elif tag in BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIP_TAGS and self._skip:
            self._skip -= 1
        elif tag in BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._parts.append(data)

    def text(self) -> str:
        raw = "".join(self._parts)
        lines = [" ".join(line.split()) for line in raw.splitlines()]
        return "\n".join(line for line in lines if line)


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit].rstrip(), True


def _html_to_text(value: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(value)
    return parser.text()


class SimpleHttpReader:
    name = "simple"

    def __init__(
        self,
        *,
        max_chars: int = 12000,
        timeout: float = 20.0,
        client: httpx.AsyncClient | None = None,
    ):
        self.max_chars = max_chars
        self.timeout = timeout
        self._client = client

    @asynccontextmanager
    async def _client_ctx(self) -> AsyncIterator[httpx.AsyncClient]:
        if self._client is not None:
            yield self._client
        else:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                yield client

    async def read(self, source: Source) -> SourceContent:
        headers = {
            "user-agent": USER_AGENT,
            "accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.8",
        }
        try:
            async with self._client_ctx() as client:
                response = await client.get(
                    source.url,
                    headers=headers,
                    follow_redirects=True,
                )
        except httpx.HTTPError as exc:
            raise ReadError(source.url, f"request failed: {exc}") from exc
        if response.status_code >= 400:
            raise ReadError(
                source.url,
                f"HTTP {response.status_code}",
                status=response.status_code,
            )

        text = response.text
        content_type = response.headers.get("content-type", "").lower()
        if "html" in content_type or "<html" in text[:500].lower():
            text = _html_to_text(text)
        text, truncated = _truncate(text, self.max_chars)
        if not text.strip():
            raise ReadError(source.url, "empty content")
        return SourceContent(
            url=source.url,
            title=source.title,
            text=text,
            provider=self.name,
            truncated=truncated,
        )


class FirecrawlReader:
    name = "firecrawl"

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        *,
        max_chars: int = 12000,
        timeout: float = 45.0,
        client: httpx.AsyncClient | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.max_chars = max_chars
        self.timeout = timeout
        self._client = client

    @asynccontextmanager
    async def _client_ctx(self) -> AsyncIterator[httpx.AsyncClient]:
        if self._client is not None:
            yield self._client
        else:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                yield client

    async def read(self, source: Source) -> SourceContent:
        headers = {"content-type": "application/json", "user-agent": USER_AGENT}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"
        try:
            async with self._client_ctx() as client:
                response = await client.post(
                    f"{self.base_url}/v2/scrape",
                    json={
                        "url": source.url,
                        "formats": ["markdown"],
                        "onlyMainContent": True,
                    },
                    headers=headers,
                )
        except httpx.HTTPError as exc:
            raise ReadError(source.url, f"firecrawl request failed: {exc}") from exc
        if response.status_code >= 400:
            raise ReadError(
                source.url,
                f"firecrawl returned HTTP {response.status_code}",
                status=response.status_code,
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise ReadError(source.url, "firecrawl returned invalid JSON") from exc
        payload = data.get("data") if isinstance(data, dict) else None
        if not isinstance(payload, dict):
            raise ReadError(source.url, "firecrawl returned no data")

        text = payload.get("markdown") or payload.get("content") or payload.get("text")
        if not isinstance(text, str) or not text.strip():
            html = payload.get("html")
            if isinstance(html, str) and html.strip():
                text = _html_to_text(html)
            else:
                raise ReadError(source.url, "firecrawl returned no readable text")

        metadata = payload.get("metadata")
        title = source.title
        if isinstance(metadata, dict) and isinstance(metadata.get("title"), str):
            title = metadata["title"] or source.title

        text, truncated = _truncate(text.strip(), self.max_chars)
        return SourceContent(
            url=source.url,
            title=title,
            text=text,
            provider=self.name,
            truncated=truncated,
        )


class FallbackReader:
    def __init__(self, primary: Reader, fallback: Reader):
        self.primary = primary
        self.fallback = fallback

    async def read(self, source: Source) -> SourceContent:
        try:
            return await self.primary.read(source)
        except Exception as primary_exc:
            try:
                return await self.fallback.read(source)
            except Exception as fallback_exc:
                raise ReadError(
                    source.url,
                    f"primary failed ({primary_exc}); fallback failed ({fallback_exc})",
                ) from fallback_exc


def build_reader(settings: Settings) -> Reader:
    simple = SimpleHttpReader(
        max_chars=settings.max_content_chars,
        timeout=settings.reader_timeout,
    )
    if settings.firecrawl_url:
        firecrawl = FirecrawlReader(
            settings.firecrawl_url,
            settings.firecrawl_api_key,
            max_chars=settings.max_content_chars,
            timeout=settings.reader_timeout,
        )
        return FallbackReader(firecrawl, simple)
    return simple


__all__ = [
    "FallbackReader",
    "FirecrawlReader",
    "ReadError",
    "Reader",
    "SimpleHttpReader",
    "SourceContent",
    "build_reader",
]
