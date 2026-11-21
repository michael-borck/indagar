from __future__ import annotations

from ..config import DEFAULT_OPENAI_BASE_URL, Settings
from .anthropic import AnthropicProvider
from .base import LLM_ROLES, LLMError, LLMProvider
from .openai_compatible import OpenAICompatibleProvider


def build_llm(
    settings: Settings,
    role: str = "writer",
    *,
    model: str | None = None,
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
        )

    raise LLMError("config", f"Unknown LLM provider: {provider}")


__all__ = ["build_llm"]
