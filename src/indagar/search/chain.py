from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import replace
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from ..classify import classify_url
from ..config import Settings
from ..models import SearchAttempt, SearchOutcome, Source
from .base import SearchProvider
from .providers import create_provider

TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
}


def normalize_url(raw: str) -> str:
    parsed = urlparse(raw.strip())
    hostname = (parsed.hostname or "").lower()
    if hostname.startswith("www."):
        hostname = hostname[4:]
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in TRACKING_PARAMS
    ]
    path = parsed.path.rstrip("/") or "/"
    return urlunparse(
        (
            parsed.scheme.lower(),
            hostname,
            path,
            "",
            urlencode(query),
            "",
        )
    )


def _is_http_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.hostname)


class SearchChain:
    """Ordered providers with over-fetch, dedupe, and a short cache."""

    def __init__(
        self,
        providers: list[SearchProvider],
        ttl_seconds: int = 600,
        max_entries: int = 100,
    ):
        self.providers = providers
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._cache: OrderedDict[str, tuple[float, SearchOutcome]] = OrderedDict()

    @property
    def provider_names(self) -> tuple[str, ...]:
        return tuple(provider.name for provider in self.providers)

    async def search(self, query: str, limit: int = 8) -> SearchOutcome:
        key = self._cache_key(query, limit)
        cached = self._cache_get(key)
        if cached is not None:
            return cached

        attempts: list[SearchAttempt] = []
        seen: set[str] = set()

        for provider in self.providers:
            started = time.perf_counter()
            try:
                raw = await provider.search(query, limit * 2)
                results: list[Source] = []
                for source in raw:
                    if not _is_http_url(source.url):
                        continue
                    normalized = normalize_url(source.url)
                    if normalized in seen:
                        continue
                    seen.add(normalized)
                    source = replace(
                        source,
                        provider=source.provider or provider.name,
                    )
                    if source.source_type == "web":
                        source_type, confidence = classify_url(source.url)
                        source = replace(
                            source,
                            source_type=source_type,
                            confidence=confidence,
                        )
                    results.append(source)
                    if len(results) >= limit:
                        break
                latency = int((time.perf_counter() - started) * 1000)
                attempts.append(
                    SearchAttempt(
                        provider=provider.name,
                        status="ok" if results else "empty",
                        count=len(results),
                        latency_ms=latency,
                    )
                )
                if results:
                    outcome = SearchOutcome(tuple(results), tuple(attempts))
                    self._cache_set(key, outcome)
                    return outcome
            except Exception as exc:  # noqa: BLE001 - one provider must not stop the chain
                latency = int((time.perf_counter() - started) * 1000)
                attempts.append(
                    SearchAttempt(
                        provider=provider.name,
                        status="error",
                        count=0,
                        latency_ms=latency,
                        error=str(exc),
                    )
                )

        return SearchOutcome((), tuple(attempts))

    def _cache_key(self, query: str, limit: int) -> str:
        normalized_query = " ".join(query.lower().split())
        providers = ",".join(self.provider_names)
        return f"{normalized_query}|{limit}|{providers}"

    def _cache_get(self, key: str) -> SearchOutcome | None:
        entry = self._cache.get(key)
        if entry is None:
            return None
        stored_at, outcome = entry
        if time.monotonic() - stored_at >= self.ttl_seconds:
            self._cache.pop(key, None)
            return None
        self._cache.move_to_end(key)
        return outcome

    def _cache_set(self, key: str, outcome: SearchOutcome) -> None:
        if not outcome.sources:
            return
        if len(self._cache) >= self.max_entries:
            self._cache.popitem(last=False)
        self._cache[key] = (time.monotonic(), outcome)


def build_chain(settings: Settings) -> SearchChain:
    providers = [
        provider
        for name in settings.configured_search_providers()
        if (provider := create_provider(name, settings)) is not None
    ]
    return SearchChain(providers)


__all__ = ["SearchChain", "build_chain", "normalize_url"]
