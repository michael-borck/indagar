from __future__ import annotations

import asyncio

from indagar.llm.base import LLMResponse
from indagar.usage import TrackedLLM, UsageTracker


class FakeProvider:
    name = "fake"
    model = "fake-model"

    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, prompt: str, **kwargs) -> LLMResponse:
        self.calls += 1
        return LLMResponse(
            text="ok",
            provider="fake",
            model="fake-model",
            input_tokens=3,
            output_tokens=2,
        )


def test_tracker_aggregates_calls_and_tokens():
    tracker = UsageTracker()

    tracker.record(LLMResponse("a", "fake", "model-a", 3, 2))
    tracker.record(LLMResponse("b", "fake", "model-a", 4, 1))
    tracker.record(LLMResponse("c", "other", "model-b", 1, 1))

    assert tracker.calls == 3
    assert tracker.input_tokens == 8
    assert tracker.output_tokens == 4
    assert [item.model for item in tracker.to_models()] == ["model-a", "model-b"]
    assert tracker.to_models()[0].calls == 2


def test_tracked_llm_delegates_and_records():
    provider = FakeProvider()
    tracker = UsageTracker()
    llm = TrackedLLM(provider, tracker)

    response = asyncio.run(llm.complete("hello"))

    assert response.text == "ok"
    assert provider.calls == 1
    assert tracker.calls == 1
    assert llm.name == "fake"
    assert llm.model == "fake-model"
