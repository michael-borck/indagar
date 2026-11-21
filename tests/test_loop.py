from __future__ import annotations

import asyncio

from indagar.config import Settings
from indagar.models import SearchAttempt, SearchOutcome, Source
from indagar.research.loop import run_research
from indagar.store import save_run


class FakeChain:
    providers = [object()]

    async def search(self, query: str, limit: int = 8) -> SearchOutcome:
        slug = query.lower().replace(" ", "-")[:20]
        return SearchOutcome(
            sources=(
                Source(
                    title=f"Source for {query}",
                    url=f"https://example.com/{slug}",
                    provider="fake",
                ),
            ),
            attempts=(SearchAttempt("fake", "ok", 1, 5),),
        )


def test_run_research_builds_a_dossier():
    run = asyncio.run(run_research("Does X improve Y?", Settings(max_sources=2), chain=FakeChain()))

    assert run.question == "Does X improve Y?"
    assert len(run.sources) == 2
    assert all(source.sub_question for source in run.sources)
    assert "Research dossier: Does X improve Y?" in run.report
    assert "example.com" in run.report
    assert "Search attempts" in run.report


def test_save_run_writes_json_and_markdown(tmp_path):
    run = asyncio.run(run_research("Does X improve Y?", Settings(max_sources=1), chain=FakeChain()))

    json_path, markdown_path = save_run(run, runs_dir=tmp_path / "runs")

    assert json_path.exists()
    assert markdown_path.exists()
    assert "Research dossier" in markdown_path.read_text(encoding="utf-8")
