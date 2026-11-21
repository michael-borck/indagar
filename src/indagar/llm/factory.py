from __future__ import annotations

from dataclasses import dataclass

from ..config import DEFAULT_OPENAI_BASE_URL, Settings
from ..rate_limit import RateLimiter, RetryPolicy
from .anthropic import AnthropicProvider
from .base import LLM_ROLES, LLMError, LLMProvider
from .openai_compatible import OpenAICompatibleProvider


def build_llm(
    settings: Settings,
    role: str = "writer",
    *,
    model: str | None = None,
    limiter: RateLimiter | None = None,
) -> LLMProvider:
    """Build the configured provider for a model role."""
    role = role.lower()
    if role not in LLM_ROLES:
        raise LLMError("config", f"Unknown LLM role: {role}. Use {', '.join(LLM_ROLES)}.")

    provider = settings.selected_llm_provider()
    if provider is None:
        raise LLMError(
            "config",
            "No LLM provider configured. Set ANTHROPIC_API_KEY, or OPENAI_API_KEY/OPENAI_BASE_URL.",
        )

    selected_model = model or settings.llm_model_for(role)
    if not selected_model:
        raise LLMError(
            "config",
            f"No LLM model configured for role '{role}'. Set INDAGAR_LLM_MODEL "
            f"or INDAGAR_{role.upper()}_MODEL.",
        )

    retry = RetryPolicy(
        max_retries=settings.llm_max_retries,
        base_seconds=settings.retry_base_seconds,
    )
    if limiter is None and settings.llm_min_interval > 0:
        limiter = RateLimiter(settings.llm_min_interval)

    if provider == "anthropic":
        if not settings.anthropic_api_key:
            raise LLMError(
                "config",
                "Anthropic is selected but ANTHROPIC_API_KEY is not set.",
            )
        return AnthropicProvider(
            api_key=settings.anthropic_api_key,
            base_url=settings.anthropic_base_url,
            model=selected_model,
            max_tokens=settings.llm_max_tokens,
            temperature=settings.llm_temperature,
            timeout=settings.llm_timeout,
            retry=retry,
            limiter=limiter,
        )

    if provider == "openai-compatible":
        if not settings.openai_api_key and settings.openai_base_url == DEFAULT_OPENAI_BASE_URL:
            raise LLMError(
                "config",
                "OpenAI-compatible is selected but OPENAI_API_KEY is not set.",
            )
        return OpenAICompatibleProvider(
            base_url=settings.openai_base_url,
            api_key=settings.openai_api_key,
            model=selected_model,
            max_tokens=settings.llm_max_tokens,
            temperature=settings.llm_temperature,
            timeout=settings.llm_timeout,
            retry=retry,
            limiter=limiter,
        )

    raise LLMError("config", f"Unknown LLM provider: {provider}")


@dataclass(frozen=True)
class LLMSet:
    planner: LLMProvider
    reader: LLMProvider
    writer: LLMProvider


def build_llms(settings: Settings) -> LLMSet:
    """Build one provider per role so models can differ by job."""
    limiter = RateLimiter(settings.llm_min_interval) if settings.llm_min_interval > 0 else None
    return LLMSet(
        planner=build_llm(settings, role="planner", limiter=limiter),
        reader=build_llm(settings, role="reader", limiter=limiter),
        writer=build_llm(settings, role="writer", limiter=limiter),
    )


__all__ = ["LLMSet", "build_llm", "build_llms"]
