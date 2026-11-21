from __future__ import annotations

import asyncio
import json

from indagar.llm.base import LLMResponse
from indagar.models import Source
from indagar.research.extract import extract_claims

CONTENT = (
    "Photosynthesis converts light energy into chemical energy in chloroplasts. "
    "The process releases oxygen as a by-product."
)
QUOTE = "Photosynthesis converts light energy into chemical energy in chloroplasts."


class FakeLLM:
    name = "fake"
    model = "fake-model"

    def __init__(self, text: str):
        self.text = text

    async def complete(self, prompt: str, **kwargs) -> LLMResponse:
        return LLMResponse(self.text, "fake", "fake-model")


def test_extract_keeps_only_verbatim_quotes():
    payload = {
        "claims": [
            {"quote": QUOTE, "locator": "p. 1", "note": "Defines the process."},
            {"quote": "A sentence that is not in the source.", "locator": None},
            {"quote": "Too short.", "locator": None},
        ]
    }
    llm = FakeLLM(json.dumps(payload))

    claims = asyncio.run(
        extract_claims(
            llm,
            Source("Photosynthesis", "https://example.com"),
            CONTENT,
            "What is photosynthesis?",
        )
    )

    assert len(claims) == 1
    assert claims[0].quote == QUOTE
    assert claims[0].locator == "p. 1"
    assert claims[0].note == "Defines the process."


def test_extract_accepts_fenced_json_and_limits_claims():
    payload = {"claims": [{"quote": QUOTE}, {"quote": QUOTE}]}
    llm = FakeLLM(f"```json\n{json.dumps(payload)}\n```")

    claims = asyncio.run(
        extract_claims(
            llm,
            Source("Photosynthesis", "https://example.com"),
            CONTENT,
            "What is photosynthesis?",
            max_claims=1,
        )
    )

    assert len(claims) == 1


def test_extract_returns_empty_for_no_claims():
    llm = FakeLLM('{"claims": []}')

    claims = asyncio.run(
        extract_claims(
            llm,
            Source("Photosynthesis", "https://example.com"),
            CONTENT,
            "What is photosynthesis?",
        )
    )

    assert claims == ()
