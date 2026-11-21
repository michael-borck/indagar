from __future__ import annotations

import asyncio
import json

from indagar.config import Settings
from indagar.llm.base import LLMResponse
from indagar.llm.factory import LLMSet
from indagar.models import SearchAttempt, SearchOutcome, Source
from indagar.research.checkpoint import DeepCheckpoint
from indagar.research.deep import run_deep_research
from indagar.research.reader import SourceContent
from indagar.search.chain import SearchChain

QUOTE = "Photosynthesis converts light energy into chemical energy in chloroplasts."
CONTENT = (
    f"{QUOTE} The process releases oxygen as a by-product. "
    "Chlorophyll absorbs light in the visible spectrum. "
) * 8


class FakeChain:
    providers = [object()]

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def search(self, query: str, limit: int = 8) -> SearchOutcome:
        self.calls.append(query)
        index = len(self.calls)
        return SearchOutcome(
            sources=(
                Source(
                    title=f"Source {index}",
                    url=f"https://example.com/{index}",
                    provider="fake",
                ),
            ),
            attempts=(SearchAttempt("fake", "ok", 1, 1),),
        )


class FakeAcademicChain:
    providers = [object()]

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def search(self, query: str, limit: int = 8) -> SearchOutcome:
        self.calls.append(query)
        return SearchOutcome(
            sources=(
                Source(
                    title=f"Academic source {len(self.calls)}",
                    url=f"https://doi.org/10.1000/{len(self.calls)}",
                    provider="openalex",
                    source_type="academic",
                    confidence="high",
                    published="2024",
                    authors="Ada Lovelace",
                ),
            ),
            attempts=(SearchAttempt("openalex", "ok", 1, 1),),
        )


class FakeReader:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def read(self, source: Source) -> SourceContent:
        self.calls.append(source.url)
        return SourceContent(
            url=source.url,
            title=source.title,
            text=CONTENT,
            provider="fake",
        )


class SlowReader(FakeReader):
    def __init__(self) -> None:
        super().__init__()
        self.active = 0
        self.max_active = 0

    async def read(self, source: Source) -> SourceContent:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0.02)
        content = await super().read(source)
        self.active -= 1
        return content


class ScriptedLLM:
    name = "fake"
    model = "fake-model"

    def __init__(
        self,
        *,
        gap: bool = False,
        writer: str | None = None,
        bad_plan: bool = False,
        ungrounded: bool = False,
    ):
        self.gap = gap
        self.writer = writer or ("Photosynthesis converts light energy into chemical energy [C1].")
        self.bad_plan = bad_plan
        self.ungrounded = ungrounded
        self.prompts: list[str] = []

    async def complete(self, prompt: str, **kwargs) -> LLMResponse:
        self.prompts.append(prompt)
        if "Plan research for the question" in prompt:
            if self.bad_plan:
                text = "not json"
            else:
                text = json.dumps(
                    {
                        "sub_questions": [
                            {
                                "question": "What is photosynthesis?",
                                "rationale": "Define it.",
                            },
                            {
                                "question": "What evidence supports photosynthesis?",
                                "rationale": "Find evidence.",
                            },
                        ]
                    }
                )
        elif "Extract evidence for the sub-question" in prompt:
            quote = (
                "This quote does not appear anywhere in the supplied source."
                if self.ungrounded
                else QUOTE
            )
            text = json.dumps(
                {
                    "claims": [
                        {
                            "quote": quote,
                            "locator": "p. 1",
                            "note": "Definition of photosynthesis.",
                        }
                    ]
                }
            )
        elif "Audit whether the evidence" in prompt:
            if self.gap:
                text = json.dumps(
                    {
                        "done": False,
                        "follow_up": [
                            {
                                "question": "What are the limitations of photosynthesis?",
                                "rationale": "Check limitations.",
                            }
                        ],
                    }
                )
            else:
                text = '{"done": true}'
        elif "Write a research report" in prompt:
            text = self.writer
        else:
            text = "{}"
        return LLMResponse(
            text=text,
            provider="fake",
            model="fake-model",
            input_tokens=10,
            output_tokens=5,
        )


def _llms(llm: ScriptedLLM) -> LLMSet:
    return LLMSet(planner=llm, reader=llm, writer=llm)


def test_deep_research_produces_citations_and_usage():
    chain = FakeChain()
    reader = FakeReader()
    llm = ScriptedLLM()

    run = asyncio.run(
        run_deep_research(
            "What is photosynthesis?",
            Settings(academic_enabled=False, max_sources=2, max_seconds=60, max_depth=0),
            llms=_llms(llm),
            reader=reader,
            chain=chain,
        )
    )

    assert run.plan.planner == "llm"
    assert len(chain.calls) == 2
    assert len(run.sources) == 2
    assert len(run.reads) == 2
    assert all(read.status == "ok" for read in run.reads)
    assert len(run.citations) == 2
    assert "Synthesized with inline citations" in run.report
    assert "[C1]" in run.report
    assert "| C1 |" in run.report
    assert sum(item.calls for item in run.usage) == 4
    assert sum(item.input_tokens for item in run.usage) == 40


def test_deep_research_writes_checkpoints_and_resumes():
    states: list[DeepCheckpoint] = []
    llm = ScriptedLLM()

    run = asyncio.run(
        run_deep_research(
            "What is photosynthesis?",
            Settings(academic_enabled=False, max_sources=2, max_seconds=60, max_depth=0),
            llms=_llms(llm),
            reader=FakeReader(),
            chain=FakeChain(),
            checkpoint=states.append,
        )
    )

    assert run.citations
    assert "planned" in {state.phase for state in states}
    assert "gathered" in {state.phase for state in states}
    gathered = next(state for state in states if state.phase == "gathered")
    assert len(gathered.sources) == 2
    assert len(gathered.citations) == 2

    resumed_chain = FakeChain()
    resumed_reader = FakeReader()
    resumed = asyncio.run(
        run_deep_research(
            gathered.question,
            Settings(academic_enabled=False, max_sources=2, max_seconds=60, max_depth=0),
            llms=_llms(ScriptedLLM()),
            reader=resumed_reader,
            chain=resumed_chain,
            resume=gathered,
        )
    )

    assert resumed.id == gathered.run_id
    assert resumed_chain.calls == []
    assert resumed_reader.calls == []
    assert len(resumed.citations) == len(gathered.citations)
    assert "Research report" in resumed.report


def test_deep_research_merges_academic_sources():
    chain = FakeChain()
    academic = FakeAcademicChain()
    reader = FakeReader()
    llm = ScriptedLLM()

    run = asyncio.run(
        run_deep_research(
            "What is photosynthesis?",
            Settings(academic_enabled=False, max_sources=2, max_seconds=60, max_depth=0),
            llms=_llms(llm),
            reader=reader,
            chain=chain,
            academic_chain=academic,
        )
    )

    assert len(academic.calls) == 2
    assert run.sources
    assert all(source.source_type == "academic" for source in run.sources)
    assert all(source.published == "2024" for source in run.sources)
    assert any(attempt.provider == "openalex" for attempt in run.attempts)
    assert "Academic source" in run.report


def test_deep_research_can_use_academic_only():
    academic = FakeAcademicChain()
    reader = FakeReader()
    llm = ScriptedLLM()

    run = asyncio.run(
        run_deep_research(
            "What is photosynthesis?",
            Settings(max_sources=2, max_seconds=60, max_depth=0),
            llms=_llms(llm),
            reader=reader,
            chain=SearchChain([]),
            academic_chain=academic,
        )
    )

    assert len(run.sources) == 2
    assert all(source.source_type == "academic" for source in run.sources)
    assert all(source.published == "2024" for source in run.sources)


def test_deep_research_reads_concurrently():
    chain = FakeChain()
    reader = SlowReader()
    llm = ScriptedLLM()

    run = asyncio.run(
        run_deep_research(
            "What is photosynthesis?",
            Settings(
                academic_enabled=False, max_sources=2, max_seconds=60, max_depth=0, concurrency=2
            ),
            llms=_llms(llm),
            reader=reader,
            chain=chain,
        )
    )

    assert reader.max_active == 2
    assert len(run.reads) == 2


def test_deep_research_runs_one_gap_round():
    chain = FakeChain()
    reader = FakeReader()
    llm = ScriptedLLM(gap=True)

    run = asyncio.run(
        run_deep_research(
            "What is photosynthesis?",
            Settings(academic_enabled=False, max_sources=6, max_seconds=60, max_depth=1),
            llms=_llms(llm),
            reader=reader,
            chain=chain,
        )
    )

    assert len(chain.calls) == 3
    assert len(run.plan.sub_questions) == 3
    assert run.plan.sub_questions[-1].question == "What are the limitations of photosynthesis?"
    assert len(run.sources) == 3
    assert len(run.reads) == 3


def test_deep_research_falls_back_when_synthesis_is_ungrounded():
    chain = FakeChain()
    reader = FakeReader()
    llm = ScriptedLLM(writer="Unsupported [C99].")

    run = asyncio.run(
        run_deep_research(
            "What is photosynthesis?",
            Settings(academic_enabled=False, max_sources=1, max_seconds=60, max_depth=0),
            llms=_llms(llm),
            reader=reader,
            chain=chain,
        )
    )

    assert "Synthesis unavailable" in run.report
    assert "| C1 |" in run.report
    assert "Unsupported [C99]" not in run.report


def test_deep_research_drops_ungrounded_quotes():
    chain = FakeChain()
    reader = FakeReader()
    llm = ScriptedLLM(ungrounded=True)

    run = asyncio.run(
        run_deep_research(
            "What is photosynthesis?",
            Settings(academic_enabled=False, max_sources=1, max_seconds=60, max_depth=0),
            llms=_llms(llm),
            reader=reader,
            chain=chain,
        )
    )

    assert run.reads[0].status == "no_evidence"
    assert run.citations == ()
    assert "Synthesis unavailable" in run.report


def test_deep_research_falls_back_to_a_deterministic_plan():
    chain = FakeChain()
    reader = FakeReader()
    llm = ScriptedLLM(bad_plan=True)

    run = asyncio.run(
        run_deep_research(
            "What is photosynthesis?",
            Settings(academic_enabled=False, max_sources=1, max_seconds=60, max_depth=0),
            llms=_llms(llm),
            reader=reader,
            chain=chain,
        )
    )

    assert run.plan.planner == "deterministic-fallback"
    assert len(run.plan.sub_questions) == 4
    assert len(run.citations) == 1
