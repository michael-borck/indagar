from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

import httpx

LLMRole = Literal["planner", "reader", "writer"]
LLM_ROLES: tuple[LLMRole, ...] = ("planner", "reader", "writer")


class LLMError(Exception):
    """A provider could not complete a request."""

    def __init__(self, provider: str, message: str, status: int | None = None):
        super().__init__(message)
        self.provider = provider
        self.status = status


@dataclass(frozen=True)
class LLMResponse:
    text: str
    provider: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "text": self.text,
            "provider": self.provider,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
        }


class LLMProvider(Protocol):
    name: str
    model: str | None

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
        """Return one completion. Raise LLMError on failure."""
        ...


def clean_text(value: str, limit: int = 300) -> str:
    return " ".join(value.split())[:limit]


def error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        text = response.text
    else:
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                text = str(error.get("message") or error)
            elif error:
                text = str(error)
            else:
                text = str(payload)
        else:
            text = str(payload)
    return clean_text(text) or f"HTTP {response.status_code}"


def status_error(provider: str, response: httpx.Response) -> LLMError:
    return LLMError(
        provider,
        f"{provider} returned HTTP {response.status_code}: {error_detail(response)}",
        status=response.status_code,
    )


__all__ = [
    "LLM_ROLES",
    "LLMError",
    "LLMProvider",
    "LLMResponse",
    "LLMRole",
    "clean_text",
    "error_detail",
    "status_error",
]
