from __future__ import annotations

import asyncio
import json

import httpx

from indagar.config import Settings
from indagar.models import Source
from indagar.research.reader import (
    FallbackReader,
    FirecrawlReader,
    ReadError,
    SimpleHttpReader,
    SourceContent,
    build_reader,
)


def _source(url: str = "https://example.com/page") -> Source:
    return Source(title="Example", url=url, provider="test")


def test_firecrawl_reader_uses_markdown_and_metadata():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://firecrawl:3002/v2/scrape"
        payload = json.loads(request.content)
        assert payload["url"] == "https://example.com/page"
        assert payload["formats"] == ["markdown"]
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "markdown": "# Heading\n\nBody text.",
                    "metadata": {"title": "Page title"},
                },
            },
        )

    async def run() -> SourceContent:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            reader = FirecrawlReader("http://firecrawl:3002", client=client)
            return await reader.read(_source())

    content = asyncio.run(run())

    assert content.provider == "firecrawl"
    assert content.title == "Page title"
    assert "Body text." in content.text


def test_simple_reader_strips_html_and_scripts():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=utf-8"},
            text=(
                "<html><head><style>.x{}</style></head><body>"
                "<h1>Heading</h1><p>Hello <b>world</b>.</p>"
                "<script>bad()</script></body></html>"
            ),
        )

    async def run() -> SourceContent:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            reader = SimpleHttpReader(client=client)
            return await reader.read(_source())

    content = asyncio.run(run())

    assert "Heading" in content.text
    assert "Hello world." in content.text
    assert "bad()" not in content.text


def test_simple_reader_reports_http_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="missing")

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            reader = SimpleHttpReader(client=client)
            await reader.read(_source())

    try:
        asyncio.run(run())
    except ReadError as exc:
        assert exc.status == 404
    else:
        raise AssertionError("expected ReadError")


class FailingReader:
    async def read(self, source: Source) -> SourceContent:
        raise ReadError(source.url, "primary failed")


class StaticReader:
    async def read(self, source: Source) -> SourceContent:
        return SourceContent(source.url, source.title, "fallback text", "static")


def test_fallback_reader_uses_fallback():
    reader = FallbackReader(FailingReader(), StaticReader())

    content = asyncio.run(reader.read(_source()))

    assert content.text == "fallback text"
    assert content.provider == "static"


def test_build_reader_uses_firecrawl_when_configured():
    with_firecrawl = build_reader(Settings(firecrawl_url="http://firecrawl:3002"))
    without = build_reader(Settings())

    assert isinstance(with_firecrawl, FallbackReader)
    assert isinstance(without, SimpleHttpReader)
