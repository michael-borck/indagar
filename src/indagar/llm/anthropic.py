from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx

from ..config import DEFAULT_ANTHROPIC_BASE_URL
from ..rate_limit import RateLimiter, RetryPolicy
from .base import LLMError, LLMResponse, status_error

ANTHROPIC_VERSION = "2023-06-01"


def _int_or_none(value: object) -> int | None:
    return value if isinstance(value, int) else None


class AnthropicProvider:
    """Anthropic Messages API adapter."""

    name = "anthropic"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = DEFAULT_ANTHROPIC_BASE_URL,
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
        timeout: float = 60.0,
        client: httpx.AsyncClient | None = None,
        retry: RetryPolicy | None = None,
        limiter: RateLimiter | None = None,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        if self.base_url.endswith("/v1"):
            self.base_url = self.base_url[:-3]
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout
        self._client = client
        self.retry = retry or RetryPolicy()
        self.limiter = limiter

    @asynccontextmanager
    async def _client_ctx(self) -> AsyncIterator[httpx.AsyncClient]:
        if self._client is not None:
            yield self._client
        else:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                yield client

    async def complete(
        self,
        prompt: str,
        *,
        system: str = "",
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        selected_model = model or self.model
        if not selected_model:
            raise LLMError(
                self.name,
                "No model configured. Set INDAGAR_LLM_MODEL or a role-specific model.",
            )
        if not self.api_key:
            raise LLMError(self.name, "ANTHROPIC_API_KEY is not set")

        system_text = system
        if json_mode:
            hint = "Return only valid JSON. Do not wrap it in markdown fences."
            system_text = f"{system_text}\n\n{hint}" if system_text else hint

        payload: dict[str, object] = {
            "model": selected_model,
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": self.temperature if temperature is None else temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_text:
            payload["system"] = system_text

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

        try:
            if self.limiter is not None:
                await self.limiter.wait()
            async with self._client_ctx() as client:
                response = await self.retry.request(
                    client,
                    "POST",
                    f"{self.base_url}/v1/messages",
                    json=payload,
                    headers=headers,
                )
        except httpx.HTTPError as exc:
            raise LLMError(self.name, f"{self.name} request failed: {exc}") from exc

        if response.status_code >= 400:
            raise status_error(self.name, response)

        try:
            data = response.json()
        except ValueError as exc:
            raise LLMError(self.name, f"{self.name} returned invalid JSON") from exc
        if not isinstance(data, dict):
            raise LLMError(self.name, f"{self.name} returned an unexpected payload")

        content = data.get("content")
        parts: list[str] = []
        if isinstance(content, list):
            for block in content:
                if (
                    isinstance(block, dict)
                    and block.get("type") == "text"
                    and isinstance(block.get("text"), str)
                ):
                    parts.append(block["text"])
        text = "\n".join(parts).strip()
        if not text:
            raise LLMError(self.name, f"{self.name} returned empty content")

        usage = data.get("usage")
        if not isinstance(usage, dict):
            usage = {}

        return LLMResponse(
            text=text,
            provider=self.name,
            model=str(data.get("model") or selected_model),
            input_tokens=_int_or_none(usage.get("input_tokens")),
            output_tokens=_int_or_none(usage.get("output_tokens")),
        )


__all__ = ["ANTHROPIC_VERSION", "AnthropicProvider", "DEFAULT_ANTHROPIC_BASE_URL"]
