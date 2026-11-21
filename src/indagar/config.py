from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

DEFAULT_SEARCH_ORDER = ("firecrawl", "brave", "serper", "searxng")
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def _search_order() -> tuple[str, ...]:
    raw = os.getenv("INDAGAR_SEARCH_ORDER", "")
    if not raw.strip():
        return DEFAULT_SEARCH_ORDER
    names = tuple(part.strip().lower() for part in raw.split(",") if part.strip())
    return names or DEFAULT_SEARCH_ORDER


@dataclass(frozen=True)
class Settings:
    firecrawl_url: str | None = None
    firecrawl_api_key: str | None = None
    brave_api_key: str | None = None
    serper_api_key: str | None = None
    searxng_url: str | None = None
    search_order: tuple[str, ...] = DEFAULT_SEARCH_ORDER
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    openai_base_url: str = DEFAULT_OPENAI_BASE_URL
    max_sources: int = 12
    max_seconds: int = 300
    search_limit: int = 8

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv(override=False)
        return cls(
            firecrawl_url=os.getenv("FIRECRAWL_URL", "").strip() or None,
            firecrawl_api_key=os.getenv("FIRECRAWL_API_KEY", "").strip() or None,
            brave_api_key=os.getenv("BRAVE_API_KEY", "").strip() or None,
            serper_api_key=os.getenv("SERPER_API_KEY", "").strip() or None,
            searxng_url=os.getenv("SEARXNG_URL", "").strip() or None,
            search_order=_search_order(),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", "").strip() or None,
            openai_api_key=os.getenv("OPENAI_API_KEY", "").strip() or None,
            openai_base_url=(os.getenv("OPENAI_BASE_URL", "").strip() or DEFAULT_OPENAI_BASE_URL),
            max_sources=_env_int("INDAGAR_MAX_SOURCES", 12),
            max_seconds=_env_int("INDAGAR_MAX_SECONDS", 300),
            search_limit=_env_int("INDAGAR_SEARCH_LIMIT", 8),
        )

    def configured_search_providers(self) -> tuple[str, ...]:
        configured: list[str] = []
        for name in self.search_order:
            if name == "firecrawl" and self.firecrawl_url:
                configured.append(name)
            elif name == "brave" and self.brave_api_key:
                configured.append(name)
            elif name == "serper" and self.serper_api_key:
                configured.append(name)
            elif name == "searxng" and self.searxng_url:
                configured.append(name)
        return tuple(configured)

    def llm_providers(self) -> tuple[str, ...]:
        providers: list[str] = []
        if self.anthropic_api_key:
            providers.append("anthropic")
        if self.openai_api_key or self.openai_base_url != DEFAULT_OPENAI_BASE_URL:
            providers.append("openai-compatible")
        return tuple(providers)
