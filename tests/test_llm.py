from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from indagar.config import Settings
from indagar.llm.anthropic import AnthropicProvider
from indagar.llm.base import LLMError
from indagar.llm.factory import build_llm, build_llms
from indagar.llm.openai_compatible import OpenAICompatibleProvider
from indagar.rate_limit import RetryPolicy


def test_openai_compatible_request_and_response():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://llm.example/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer test-key"
        payload = json.loads(request.content)
        assert payload["model"] == "test-model"
        assert payload["messages"] == [
            {"role": "system", "content": "Be concise."},
            {"role": "user", "content": "Hello"},
        ]
        assert payload["max_tokens"] == 64
        assert payload["temperature"] == 0.1
        assert payload["response_format"] == {"type": "json_object"}
        return httpx.Response(
            200,
            json={
                "model": "test-model-2026",
                "choices": [{"message": {"content": "Hi there."}}],
                "usage": {"prompt_tokens": 9, "completion_tokens": 4},
            },
        )

    async def run() -> object:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            provider = OpenAICompatibleProvider(
                base_url="https://llm.example/v1",
                api_key="test-key",
                model="test-model",
                max_tokens=64,
                temperature=0.1,
                client=client,
            )
            return await provider.complete("Hello", system="Be concise.", json_mode=True)

    response = asyncio.run(run())

    assert response.text == "Hi there."
    assert response.provider == "openai-compatible"
    assert response.model == "test-model-2026"
    assert response.input_tokens == 9
    assert response.output_tokens == 4


def test_anthropic_request_and_response():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://api.anthropic.com/v1/messages"
        assert request.headers["x-api-key"] == "test-key"
        assert request.headers["anthropic-version"] == "2023-06-01"
        payload = json.loads(request.content)
        assert payload["model"] == "claude-test"
        assert payload["system"] == "Be concise."
        assert payload["messages"] == [{"role": "user", "content": "Hello"}]
        assert payload["max_tokens"] == 64
        return httpx.Response(
            200,
            json={
                "model": "claude-test",
                "content": [{"type": "text", "text": "Hi there."}],
                "usage": {"input_tokens": 9, "output_tokens": 4},
            },
        )

    async def run() -> object:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            provider = AnthropicProvider(
                api_key="test-key",
                model="claude-test",
                max_tokens=64,
                client=client,
            )
            return await provider.complete("Hello", system="Be concise.")

    response = asyncio.run(run())

    assert response.text == "Hi there."
    assert response.provider == "anthropic"
    assert response.model == "claude-test"
    assert response.input_tokens == 9
    assert response.output_tokens == 4


def test_provider_error_includes_status_and_detail():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "rate limited"}})

    async def run() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            provider = OpenAICompatibleProvider(
                base_url="https://llm.example/v1",
                model="test-model",
                client=client,
                retry=RetryPolicy(max_retries=0),
            )
            await provider.complete("Hello")

    with pytest.raises(LLMError) as excinfo:
        asyncio.run(run())

    assert excinfo.value.status == 429
    assert "429" in str(excinfo.value)
    assert "rate limited" in str(excinfo.value)


def test_openai_provider_retries_a_transient_error():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(429, json={"error": {"message": "rate limited"}})
        return httpx.Response(
            200,
            json={
                "model": "test-model",
                "choices": [{"message": {"content": "Recovered."}}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 1},
            },
        )

    async def run() -> object:
        sleeps: list[float] = []

        async def sleep(delay: float) -> None:
            sleeps.append(delay)

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            provider = OpenAICompatibleProvider(
                base_url="https://llm.example/v1",
                model="test-model",
                client=client,
                retry=RetryPolicy(
                    max_retries=1,
                    base_seconds=0.1,
                    sleep=sleep,
                    rng=lambda: 0.5,
                ),
            )
            response = await provider.complete("Hello")
        return response, sleeps

    response, sleeps = asyncio.run(run())

    assert response.text == "Recovered."
    assert calls["count"] == 2
    assert len(sleeps) == 1


def test_build_anthropic_from_settings():
    settings = Settings(
        anthropic_api_key="key",
        llm_provider="anthropic",
        llm_model="claude-test",
    )

    provider = build_llm(settings, role="writer")

    assert isinstance(provider, AnthropicProvider)
    assert provider.model == "claude-test"


def test_factory_wires_retry_and_shared_limiter():
    settings = Settings(
        anthropic_api_key="key",
        llm_provider="anthropic",
        llm_model="claude-test",
        llm_max_retries=3,
        llm_min_interval=1.0,
    )

    llms = build_llms(settings)

    assert llms.planner.retry.max_retries == 3
    assert llms.planner.limiter is not None
    assert llms.planner.limiter is llms.reader.limiter
    assert llms.reader.limiter is llms.writer.limiter


def test_build_openai_compatible_local_without_key():
    settings = Settings(
        openai_base_url="http://localhost:11434/v1",
        llm_provider="openai-compatible",
        writer_model="local-model",
    )

    provider = build_llm(settings, role="writer")

    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.model == "local-model"
    assert provider.api_key is None


def test_build_llm_requires_a_provider():
    with pytest.raises(LLMError, match="No LLM provider"):
        build_llm(Settings())


def test_build_llm_requires_a_model():
    settings = Settings(anthropic_api_key="key", llm_provider="anthropic")

    with pytest.raises(LLMError, match="INDAGAR_LLM_MODEL"):
        build_llm(settings)


def test_build_llm_rejects_unknown_role():
    with pytest.raises(LLMError, match="Unknown LLM role"):
        build_llm(Settings(anthropic_api_key="key"), role="critic")
