from __future__ import annotations

from urllib.parse import urlparse

import httpx

from ..config import Settings
from ..models import Source
from .base import SearchError

USER_AGENT = "Indagar/0.1 (+https://github.com/michael-borck/indagar)"


def _is_http_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.hostname)


def _source(
    title: str | None,
    url: str | None,
    snippet: str | None,
    provider: str,
) -> Source | None:
    if not title or not url or not _is_http_url(url):
        return None
    return Source(
        title=" ".join(title.split()),
        url=url,
        snippet=" ".join((snippet or "").split())[:600],
        provider=provider,
    )


def _status_error(provider: str, response: httpx.Response) -> SearchError:
    return SearchError(
        provider,
        f"{provider} returned HTTP {response.status_code}",
        status=response.status_code,
    )


class FirecrawlProvider:
    name = "firecrawl"

    def __init__(self, base_url: str, api_key: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    async def search(self, query: str, limit: int) -> list[Source]:
        headers = {"content-type": "application/json", "user-agent": USER_AGENT}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/v2/search",
                    json={"query": query, "limit": max(1, limit), "sources": ["web"]},
                    headers=headers,
                )
        except httpx.HTTPError as exc:
            raise SearchError(self.name, f"firecrawl request failed: {exc}") from exc
        if response.status_code >= 400:
            raise _status_error(self.name, response)
        data = response.json()
        web = ((data.get("data") or {}).get("web")) or []
        results: list[Source] = []
        for item in web:
            source = _source(
                item.get("title"),
                item.get("url"),
                item.get("description"),
                self.name,
            )
            if source:
                results.append(source)
        return results


class BraveProvider:
    name = "brave"

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def search(self, query: str, limit: int) -> list[Source]:
        params = {
            "q": query,
            "count": min(max(limit, 1), 20),
            "search_lang": "en",
            "country": "US",
            "safesearch": "moderate",
        }
        headers = {
            "X-Subscription-Token": self.api_key,
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    params=params,
                    headers=headers,
                )
        except httpx.HTTPError as exc:
            raise SearchError(self.name, f"brave request failed: {exc}") from exc
        if response.status_code >= 400:
            raise _status_error(self.name, response)
        data = response.json()
        results: list[Source] = []
        for item in (data.get("web") or {}).get("results") or []:
            source = _source(
                item.get("title"),
                item.get("url"),
                item.get("description"),
                self.name,
            )
            if source:
                results.append(source)
        return results


class SerperProvider:
    name = "serper"

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def search(self, query: str, limit: int) -> list[Source]:
        headers = {
            "X-API-KEY": self.api_key,
            "content-type": "application/json",
            "user-agent": USER_AGENT,
        }
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(
                    "https://google.serper.dev/search",
                    json={"q": query, "num": min(max(limit, 1), 100)},
                    headers=headers,
                )
        except httpx.HTTPError as exc:
            raise SearchError(self.name, f"serper request failed: {exc}") from exc
        if response.status_code >= 400:
            raise _status_error(self.name, response)
        data = response.json()
        results: list[Source] = []
        for item in data.get("organic") or []:
            source = _source(
                item.get("title"),
                item.get("link"),
                item.get("snippet"),
                self.name,
            )
            if source:
                results.append(source)
        return results


class SearxngProvider:
    name = "searxng"

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    async def search(self, query: str, limit: int) -> list[Source]:
        params = {"q": query, "format": "json", "safesearch": "1"}
        headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.get(
                    f"{self.base_url}/search",
                    params=params,
                    headers=headers,
                )
        except httpx.HTTPError as exc:
            raise SearchError(self.name, f"searxng request failed: {exc}") from exc
        if response.status_code >= 400:
            raise _status_error(self.name, response)
        data = response.json()
        results: list[Source] = []
        for item in data.get("results") or []:
            source = _source(
                item.get("title"),
                item.get("url"),
                item.get("content"),
                self.name,
            )
            if source:
                results.append(source)
        return results


def create_provider(name: str, settings: Settings):
    if name == "firecrawl" and settings.firecrawl_url:
        return FirecrawlProvider(settings.firecrawl_url, settings.firecrawl_api_key)
    if name == "brave" and settings.brave_api_key:
        return BraveProvider(settings.brave_api_key)
    if name == "serper" and settings.serper_api_key:
        return SerperProvider(settings.serper_api_key)
    if name == "searxng" and settings.searxng_url:
        return SearxngProvider(settings.searxng_url)
    return None


__all__ = [
    "BraveProvider",
    "FirecrawlProvider",
    "SearxngProvider",
    "SerperProvider",
    "create_provider",
]
