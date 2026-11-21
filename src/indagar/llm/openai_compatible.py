from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx

from ..config import DEFAULT_OPENAI_BASE_URL
from .base import LLMError, LLMResponse, status_error


def _content_text(content: object) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts).strip()
    return ""


def _int_or_none(value: object) -> int | None:
    return value if isinstance(value, int) else None


class OpenAICompatibleProvider:
    """OpenAI Chat Completions adapter for OpenAI and compatible servers."""

    name = "openai-compatible"

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_OPENAI_BASE_URL,
        api_key: str | None = None,
        model: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
        timeout: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout
        self._client = client

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

        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"

        payload: dict[str, object] = {
            "model": selected_model,
            "messages": ([{"role": "system", "content": system}] if system else [])
            + [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": self.temperature if temperature is None else temperature,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            async with self._client_ctx() as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
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

        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LLMError(self.name, f"{self.name} returned no choices")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        text = _content_text(content)
        if not text:
            raise LLMError(self.name, f"{self.name} returned empty content")

        usage = data.get("usage")
        if not isinstance(usage, dict):
            usage = {}

        return LLMResponse(
            text=text,
            provider=self.name,
            model=str(data.get("model") or selected_model),
            input_tokens=_int_or_none(usage.get("prompt_tokens")),
            output_tokens=_int_or_none(usage.get("completion_tokens")),
        )


__all__ = ["OpenAICompatibleProvider"]
