from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from html import unescape
from urllib.parse import urlparse

import httpx

from ..config import Settings
from ..models import Source
from .base import SearchError
from .chain import SearchChain
from .providers import USER_AGENT

ATOM = {"atom": "http://www.w3.org/2005/Atom"}


def _is_http_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.hostname)


def _clean(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", value)).split())


def _authors(names: list[str]) -> str:
    cleaned = [" ".join(name.split()) for name in names if name and name.strip()]
    if not cleaned:
        return ""
    if len(cleaned) > 3:
        return ", ".join(cleaned[:3]) + " et al."
    return ", ".join(cleaned)


def _source(
    *,
    title: str | None,
    url: str | None,
    abstract: str | None,
    provider: str,
    published: str = "",
    authors: str = "",
) -> Source | None:
    clean_title = " ".join((title or "").split())
    clean_url = (url or "").strip()
    if not clean_title or not _is_http_url(clean_url):
        return None
    return Source(
        title=clean_title,
        url=clean_url,
        snippet=_clean(abstract)[:600],
        provider=provider,
        source_type="academic",
        confidence="high",
        published=published,
        authors=authors,
    )


def _openalex_abstract(index: object) -> str:
    if not isinstance(index, dict):
        return ""
    positions: list[tuple[int, str]] = []
    for word, indexes in index.items():
        if not isinstance(indexes, list):
            continue
        for position in indexes:
            if isinstance(position, int):
                positions.append((position, str(word)))
    positions.sort()
    return " ".join(word for _, word in positions)


def _crossref_year(item: dict) -> str:
    for key in ("published-print", "published-online", "issued"):
        value = item.get(key)
        if not isinstance(value, dict):
            continue
        parts = value.get("date-parts")
        if isinstance(parts, list) and parts and isinstance(parts[0], list) and parts[0]:
            return str(parts[0][0])
    return ""


class _BaseAcademicProvider:
    name = "academic"
    base_url = ""
    timeout = 30.0

    def __init__(self, *, client: httpx.AsyncClient | None = None):
        self._client = client

    @asynccontextmanager
    async def _client_ctx(self) -> AsyncIterator[httpx.AsyncClient]:
        if self._client is not None:
            yield self._client
        else:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                yield client

    def _headers(self) -> dict[str, str]:
        return {
            "accept": "application/json",
            "user-agent": USER_AGENT,
        }

    async def _get(
        self,
        url: str,
        *,
        params: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        try:
            async with self._client_ctx() as client:
                response = await client.get(
                    url,
                    params=params,
                    headers=headers or self._headers(),
                )
        except httpx.HTTPError as exc:
            raise SearchError(self.name, f"{self.name} request failed: {exc}") from exc
        if response.status_code >= 400:
            raise SearchError(
                self.name,
                f"{self.name} returned HTTP {response.status_code}",
                status=response.status_code,
            )
        return response


class OpenAlexProvider(_BaseAcademicProvider):
    name = "openalex"
    base_url = "https://api.openalex.org/works"

    def __init__(self, mailto: str | None = None, *, client=None):
        super().__init__(client=client)
        self.mailto = mailto

    async def search(self, query: str, limit: int) -> list[Source]:
        params: dict[str, object] = {
            "search": query,
            "per-page": min(max(limit, 1), 50),
        }
        if self.mailto:
            params["mailto"] = self.mailto
        response = await self._get(self.base_url, params=params)
        try:
            data = response.json()
        except ValueError as exc:
            raise SearchError(self.name, "openalex returned invalid JSON") from exc
        results: list[Source] = []
        for item in (data.get("results") or []) if isinstance(data, dict) else []:
            if not isinstance(item, dict):
                continue
            location = item.get("primary_location")
            location = location if isinstance(location, dict) else {}
            names = []
            for authorship in item.get("authorships") or []:
                if not isinstance(authorship, dict):
                    continue
                author = authorship.get("author")
                if isinstance(author, dict) and author.get("display_name"):
                    names.append(str(author["display_name"]))
            source = _source(
                title=item.get("title"),
                url=item.get("doi") or location.get("landing_page_url") or location.get("pdf_url"),
                abstract=_openalex_abstract(item.get("abstract_inverted_index")),
                provider=self.name,
                published=str(item.get("publication_year") or ""),
                authors=_authors(names),
            )
            if source:
                results.append(source)
        return results


class CrossrefProvider(_BaseAcademicProvider):
    name = "crossref"
    base_url = "https://api.crossref.org/works"

    async def search(self, query: str, limit: int) -> list[Source]:
        response = await self._get(
            self.base_url,
            params={"query": query, "rows": min(max(limit, 1), 20)},
        )
        try:
            data = response.json()
        except ValueError as exc:
            raise SearchError(self.name, "crossref returned invalid JSON") from exc
        message = data.get("message") if isinstance(data, dict) else {}
        items = message.get("items") if isinstance(message, dict) else []
        results: list[Source] = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            titles = item.get("title")
            title = titles[0] if isinstance(titles, list) and titles else ""
            item_type = str(item.get("type") or "").lower()
            if item_type in {"component", "dataset"}:
                continue
            if title.casefold().startswith(("table ", "figure ", "supplementary")):
                continue
            names = []
            for author in item.get("author") or []:
                if not isinstance(author, dict):
                    continue
                value = " ".join(
                    part
                    for part in (author.get("given"), author.get("family"))
                    if isinstance(part, str) and part
                )
                if value:
                    names.append(value)
            doi = item.get("DOI")
            url = f"https://doi.org/{doi}" if doi else item.get("URL")
            source = _source(
                title=title,
                url=url,
                abstract=item.get("abstract"),
                provider=self.name,
                published=_crossref_year(item),
                authors=_authors(names),
            )
            if source:
                results.append(source)
        return results


class ArxivProvider(_BaseAcademicProvider):
    name = "arxiv"
    base_url = "https://export.arxiv.org/api/query"

    def _headers(self) -> dict[str, str]:
        return {"accept": "application/atom+xml", "user-agent": USER_AGENT}

    async def search(self, query: str, limit: int) -> list[Source]:
        response = await self._get(
            self.base_url,
            params={
                "search_query": f"all:{query}",
                "start": 0,
                "max_results": min(max(limit, 1), 20),
                "sortBy": "relevance",
            },
        )
        try:
            root = ET.fromstring(response.text)
        except ET.ParseError as exc:
            raise SearchError(self.name, "arxiv returned invalid XML") from exc
        results: list[Source] = []
        for entry in root.findall("atom:entry", ATOM):
            title = entry.findtext("atom:title", default="", namespaces=ATOM)
            url = entry.findtext("atom:id", default="", namespaces=ATOM)
            if url.startswith("http://arxiv.org/"):
                url = "https://" + url[len("http://") :]
            summary = entry.findtext("atom:summary", default="", namespaces=ATOM)
            published = entry.findtext("atom:published", default="", namespaces=ATOM)[:10]
            names = []
            for author in entry.findall("atom:author", ATOM):
                name = author.findtext("atom:name", default="", namespaces=ATOM)
                if name:
                    names.append(name)
            source = _source(
                title=title,
                url=url,
                abstract=summary,
                provider=self.name,
                published=published,
                authors=_authors(names),
            )
            if source:
                results.append(source)
        return results


class SemanticScholarProvider(_BaseAcademicProvider):
    name = "semantic-scholar"
    base_url = "https://api.semanticscholar.org/graph/v1/paper/search"

    def __init__(self, api_key: str, *, client=None):
        super().__init__(client=client)
        self.api_key = api_key

    def _headers(self) -> dict[str, str]:
        headers = super()._headers()
        headers["x-api-key"] = self.api_key
        return headers

    async def search(self, query: str, limit: int) -> list[Source]:
        response = await self._get(
            self.base_url,
            params={
                "query": query,
                "limit": min(max(limit, 1), 20),
                "fields": "title,abstract,url,year,authors,externalIds",
            },
        )
        try:
            data = response.json()
        except ValueError as exc:
            raise SearchError(
                self.name,
                "semantic scholar returned invalid JSON",
            ) from exc
        results: list[Source] = []
        for item in (data.get("data") or []) if isinstance(data, dict) else []:
            if not isinstance(item, dict):
                continue
            external = item.get("externalIds")
            external = external if isinstance(external, dict) else {}
            doi = external.get("DOI")
            url = f"https://doi.org/{doi}" if doi else item.get("url")
            names = [
                str(author.get("name"))
                for author in item.get("authors") or []
                if isinstance(author, dict) and author.get("name")
            ]
            source = _source(
                title=item.get("title"),
                url=url,
                abstract=item.get("abstract"),
                provider=self.name,
                published=str(item.get("year") or ""),
                authors=_authors(names),
            )
            if source:
                results.append(source)
        return results


def create_academic_provider(name: str, settings: Settings):
    if name == "openalex":
        return OpenAlexProvider(settings.openalex_mailto)
    if name == "crossref":
        return CrossrefProvider()
    if name == "arxiv":
        return ArxivProvider()
    if name == "semantic-scholar" and settings.semantic_scholar_api_key:
        return SemanticScholarProvider(settings.semantic_scholar_api_key)
    return None


def build_academic_chain(settings: Settings) -> SearchChain:
    providers = [
        provider
        for name in settings.configured_academic_providers()
        if (provider := create_academic_provider(name, settings)) is not None
    ]
    return SearchChain(providers)


__all__ = [
    "ArxivProvider",
    "CrossrefProvider",
    "OpenAlexProvider",
    "SemanticScholarProvider",
    "build_academic_chain",
    "create_academic_provider",
]
