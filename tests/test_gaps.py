from __future__ import annotations

import asyncio
import json

from indagar.llm.base import LLMResponse
from indagar.models import Citation, ResearchPlan, Source, SubQuestion
from indagar.research.gaps import check_gaps


class FakeLLM:
    name = "fake"
    model = "fake-model"

    def __init__(self, text: str):
        self.text = text
        self.calls = 0

    async def complete(self, prompt: str, **kwargs) -> LLMResponse:
        self.calls += 1
        return LLMResponse(self.text, "fake", "fake-model")


def _plan() -> ResearchPlan:
    return ResearchPlan(
        "What is X?",
        (
            SubQuestion("What is X?", "Define it."),
            SubQuestion("What is the evidence for X?", "Find evidence."),
        ),
    )


def _citations() -> tuple[Citation, ...]:
    return (
        Citation(
            id="C1",
            source_url="https://example.com",
            title="Example",
            quote="X is supported by evidence.",
        ),
    )


def test_gap_check_returns_new_follow_ups():
    payload = {
        "done": False,
        "follow_up": [
            {
                "question": "What are the limitations of X?",
                "rationale": "The evidence has no limits.",
            },
            {
                "question": "What is X?",
                "rationale": "Duplicate.",
            },
        ],
    }
    llm = FakeLLM(json.dumps(payload))

    gap = asyncio.run(
        check_gaps(
            llm,
            "What is X?",
            _plan(),
            _citations(),
            (Source("Example", "https://example.com"),),
        )
    )

    assert gap.done is False
    assert len(gap.follow_up) == 1
    assert gap.follow_up[0].question == "What are the limitations of X?"


def test_gap_check_fails_closed_on_bad_json():
    gap = asyncio.run(
        check_gaps(
            FakeLLM("not json"),
            "What is X?",
            _plan(),
            _citations(),
            (),
        )
    )

    assert gap.done is True
    assert gap.follow_up == ()


def test_gap_check_respects_zero_budget_without_calling_llm():
    llm = FakeLLM('{"done": false}')

    gap = asyncio.run(
        check_gaps(
            llm,
            "What is X?",
            _plan(),
            _citations(),
            (),
            max_follow_ups=0,
        )
    )

    assert gap.done is True
    assert llm.calls == 0
