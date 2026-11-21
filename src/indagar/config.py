from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass

from dotenv import load_dotenv

DEFAULT_SEARCH_ORDER = ("firecrawl", "brave", "serper", "searxng", "tavily", "exa")
DEFAULT_ACADEMIC_ORDER = ("openalex", "crossref", "arxiv", "semantic-scholar")
DEFAULT_MEDIA_ORDER = ("youtube", "podcast")
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_ANTHROPIC_BASE_URL = "https://api.anthropic.com"


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        return default


def _env_float(
    name: str,
    default: float,
    *,
    minimum: float = 0.0,
    maximum: float = 2.0,
) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return max(minimum, min(maximum, float(raw)))
    except ValueError:
        return default


def _env_optional_float(name: str) -> float | None:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off", ""}


def _academic_order() -> tuple[str, ...]:
    raw = os.getenv("INDAGAR_ACADEMIC_ORDER", "")
    if not raw.strip():
        return DEFAULT_ACADEMIC_ORDER
    names = tuple(part.strip().lower().replace("_", "-") for part in raw.split(",") if part.strip())
    return names or DEFAULT_ACADEMIC_ORDER


def _media_order() -> tuple[str, ...]:
    raw = os.getenv("INDAGAR_MEDIA_ORDER", "")
    if not raw.strip():
        return DEFAULT_MEDIA_ORDER
    names = tuple(part.strip().lower().replace("_", "-") for part in raw.split(",") if part.strip())
    return names or DEFAULT_MEDIA_ORDER


def _normalize_llm_provider(raw: str | None) -> str | None:
    value = (raw or "").strip().lower().replace("_", "-")
    if not value:
        return None
    if value == "openai":
        return "openai-compatible"
    return value


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
    tavily_api_key: str | None = None
    exa_api_key: str | None = None
    search_order: tuple[str, ...] = DEFAULT_SEARCH_ORDER
    academic_enabled: bool = True
    academic_order: tuple[str, ...] = DEFAULT_ACADEMIC_ORDER
    openalex_mailto: str | None = None
    semantic_scholar_api_key: str | None = None
    media_enabled: bool = False
    media_order: tuple[str, ...] = DEFAULT_MEDIA_ORDER
    anthropic_api_key: str | None = None
    anthropic_base_url: str = DEFAULT_ANTHROPIC_BASE_URL
    openai_api_key: str | None = None
    openai_base_url: str = DEFAULT_OPENAI_BASE_URL
    llm_provider: str | None = None
    llm_model: str | None = None
    planner_model: str | None = None
    reader_model: str | None = None
    writer_model: str | None = None
    llm_max_tokens: int = 1024
    llm_temperature: float = 0.2
    llm_timeout: float = 60.0
    llm_max_retries: int = 2
    retry_base_seconds: float = 0.5
    llm_min_interval: float = 0.0
    input_cost_per_mtok: float | None = None
    output_cost_per_mtok: float | None = None
    max_sources: int = 12
    max_seconds: int = 300
    search_limit: int = 8
    concurrency: int = 2
    max_depth: int = 1
    max_follow_ups: int = 3
    max_content_chars: int = 12000
    max_claims: int = 5
    synthesis_max_tokens: int = 2048
    reader_timeout: float = 45.0

    @classmethod
    def from_env(cls) -> Settings:
        load_dotenv(override=False)
        return cls(
            firecrawl_url=os.getenv("FIRECRAWL_URL", "").strip() or None,
            firecrawl_api_key=os.getenv("FIRECRAWL_API_KEY", "").strip() or None,
            brave_api_key=os.getenv("BRAVE_API_KEY", "").strip() or None,
            serper_api_key=os.getenv("SERPER_API_KEY", "").strip() or None,
            searxng_url=os.getenv("SEARXNG_URL", "").strip() or None,
            tavily_api_key=os.getenv("TAVILY_API_KEY", "").strip() or None,
            exa_api_key=os.getenv("EXA_API_KEY", "").strip() or None,
            search_order=_search_order(),
            academic_enabled=_env_bool("INDAGAR_ACADEMIC", True),
            academic_order=_academic_order(),
            openalex_mailto=os.getenv("OPENALEX_MAILTO", "").strip() or None,
            semantic_scholar_api_key=(os.getenv("SEMANTIC_SCHOLAR_API_KEY", "").strip() or None),
            media_enabled=_env_bool("INDAGAR_MEDIA", False),
            media_order=_media_order(),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", "").strip() or None,
            anthropic_base_url=(
                os.getenv("ANTHROPIC_BASE_URL", "").strip() or DEFAULT_ANTHROPIC_BASE_URL
            ),
            openai_api_key=os.getenv("OPENAI_API_KEY", "").strip() or None,
            openai_base_url=(os.getenv("OPENAI_BASE_URL", "").strip() or DEFAULT_OPENAI_BASE_URL),
            llm_provider=_normalize_llm_provider(os.getenv("INDAGAR_LLM_PROVIDER")),
            llm_model=os.getenv("INDAGAR_LLM_MODEL", "").strip() or None,
            planner_model=os.getenv("INDAGAR_PLANNER_MODEL", "").strip() or None,
            reader_model=os.getenv("INDAGAR_READER_MODEL", "").strip() or None,
            writer_model=os.getenv("INDAGAR_WRITER_MODEL", "").strip() or None,
            llm_max_tokens=_env_int("INDAGAR_LLM_MAX_TOKENS", 1024),
            llm_temperature=_env_float("INDAGAR_LLM_TEMPERATURE", 0.2),
            llm_timeout=_env_float(
                "INDAGAR_LLM_TIMEOUT",
                60.0,
                minimum=1.0,
                maximum=3600.0,
            ),
            llm_max_retries=_env_int("INDAGAR_LLM_MAX_RETRIES", 2, minimum=0),
            retry_base_seconds=_env_float(
                "INDAGAR_RETRY_BASE_SECONDS",
                0.5,
                minimum=0.0,
                maximum=60.0,
            ),
            llm_min_interval=_env_float(
                "INDAGAR_LLM_MIN_INTERVAL",
                0.0,
                minimum=0.0,
                maximum=60.0,
            ),
            input_cost_per_mtok=_env_optional_float("INDAGAR_INPUT_COST_PER_MTOK"),
            output_cost_per_mtok=_env_optional_float("INDAGAR_OUTPUT_COST_PER_MTOK"),
            max_sources=_env_int("INDAGAR_MAX_SOURCES", 12),
            max_seconds=_env_int("INDAGAR_MAX_SECONDS", 300),
            search_limit=_env_int("INDAGAR_SEARCH_LIMIT", 8),
            concurrency=_env_int("INDAGAR_CONCURRENCY", 2, minimum=1),
            max_depth=_env_int("INDAGAR_MAX_DEPTH", 1, minimum=0),
            max_follow_ups=_env_int("INDAGAR_MAX_FOLLOW_UPS", 3),
            max_content_chars=_env_int("INDAGAR_MAX_CONTENT_CHARS", 12000, minimum=1000),
            max_claims=_env_int("INDAGAR_MAX_CLAIMS", 5),
            synthesis_max_tokens=_env_int("INDAGAR_SYNTHESIS_MAX_TOKENS", 2048, minimum=256),
            reader_timeout=_env_float(
                "INDAGAR_READER_TIMEOUT",
                45.0,
                minimum=1.0,
                maximum=300.0,
            ),
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
            elif name == "tavily" and self.tavily_api_key:
                configured.append(name)
            elif name == "exa" and self.exa_api_key:
                configured.append(name)
        return tuple(configured)

    def configured_academic_providers(self) -> tuple[str, ...]:
        if not self.academic_enabled:
            return ()
        configured: list[str] = []
        for name in self.academic_order:
            if name in {"openalex", "crossref", "arxiv"}:
                configured.append(name)
            elif name == "semantic-scholar" and self.semantic_scholar_api_key:
                configured.append(name)
        return tuple(configured)

    def configured_media_providers(self) -> tuple[str, ...]:
        if not self.media_enabled:
            return ()
        configured: list[str] = []
        for name in self.media_order:
            if name == "youtube":
                if importlib.util.find_spec("yt_dlp") is not None:
                    configured.append(name)
            elif name == "podcast":
                configured.append(name)
        return tuple(configured)

    def llm_providers(self) -> tuple[str, ...]:
        providers: list[str] = []
        if self.anthropic_api_key:
            providers.append("anthropic")
        if self.openai_api_key or self.openai_base_url != DEFAULT_OPENAI_BASE_URL:
            providers.append("openai-compatible")
        return tuple(providers)

    def selected_llm_provider(self) -> str | None:
        if self.llm_provider:
            return self.llm_provider
        providers = self.llm_providers()
        return providers[0] if providers else None

    def llm_model_for(self, role: str) -> str | None:
        models = {
            "planner": self.planner_model,
            "reader": self.reader_model,
            "writer": self.writer_model,
        }
        return models.get(role.lower()) or self.llm_model
