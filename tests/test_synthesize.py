from __future__ import annotations

import asyncio

import pytest

from indagar.citations import CitationLedger
from indagar.llm.base import LLMResponse
from indagar.models import Citation, ResearchPlan, Source, SubQuestion
from indagar.research.synthesize import (
    SynthesisError,
    citation_ids,
    synthesize_report,
)


class FakeLLM:
    name = "fake"
    model = "fake-model"

    def __init__(self, text: str):
        self.text = text

    async def complete(self, prompt: str, **kwargs) -> LLMResponse:
        return LLMResponse(self.text, "fake", "fake-model")


def _plan() -> ResearchPlan:
    return ResearchPlan("What is X?", (SubQuestion("What is X?", "Define it."),))


def _source() -> Source:
    return Source("Example", "https://example.com", provider="test")


def _citations() -> tuple[Citation, ...]:
    ledger = CitationLedger()
    ledger.add(_source(), "X is supported by evidence.", locator="p. 1")
    return ledger.citations


def test_citation_ids_reads_single_and_grouped_ids():
    assert citation_ids("Claim [C1] and [C2, C3].") == {"C1", "C2", "C3"}


def test_synthesize_accepts_known_citations():
    report = asyncio.run(
        synthesize_report(
            FakeLLM("X is supported by evidence [C1]."),
            "What is X?",
            _plan(),
            (_source(),),
            _citations(),
        )
    )

    assert report == "X is supported by evidence [C1]."


def test_synthesize_rejects_unknown_citation_ids():
    with pytest.raises(SynthesisError, match="unknown citation ids"):
        asyncio.run(
            synthesize_report(
                FakeLLM("X is supported [C99]."),
                "What is X?",
                _plan(),
                (_source(),),
                _citations(),
            )
        )


def test_synthesize_requires_evidence_and_citations():
    with pytest.raises(SynthesisError, match="no grounded evidence"):
        asyncio.run(
            synthesize_report(
                FakeLLM("No citations."),
                "What is X?",
                _plan(),
                (_source(),),
                (),
            )
        )

    with pytest.raises(SynthesisError, match="used no citations"):
        asyncio.run(
            synthesize_report(
                FakeLLM("No citations."),
                "What is X?",
                _plan(),
                (_source(),),
                _citations(),
            )
        )
