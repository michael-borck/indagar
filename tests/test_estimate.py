from __future__ import annotations

import pytest

from indagar.config import Settings
from indagar.estimate import cost_for_tokens, estimate_run


def test_estimate_scales_with_depth():
    shallow = estimate_run(
        "What is X?",
        Settings(max_sources=4, max_depth=0),
        depth=0,
    )
    deeper = estimate_run(
        "What is X?",
        Settings(max_sources=4, max_depth=1),
        depth=1,
    )

    assert shallow.sources == 4
    assert shallow.searches == 4
    assert shallow.llm_calls == 6
    assert shallow.input_tokens > 0
    assert shallow.output_tokens > 0
    assert deeper.searches == 7
    assert deeper.llm_calls == 7
    assert deeper.input_tokens > shallow.input_tokens


def test_retrieval_only_estimate_has_no_llm_calls():
    estimate = estimate_run("What is X?", Settings(max_sources=3), llm=False)

    assert estimate.llm_calls == 0
    assert estimate.searches == 4
    assert estimate.input_tokens == 0
    assert estimate.output_tokens == 0
    assert "retrieval only" in estimate.line()


def test_cost_uses_user_supplied_rates():
    settings = Settings(
        input_cost_per_mtok=3.0,
        output_cost_per_mtok=15.0,
    )

    assert cost_for_tokens(1_000_000, 1_000_000, settings) == 18.0
    estimate = estimate_run("What is X?", settings, max_sources=1, depth=0)
    assert estimate.cost_usd is not None
    assert estimate.cost_usd > 0


def test_estimate_line_includes_sources_and_calls():
    estimate = estimate_run(
        "What is X?",
        Settings(max_sources=2, max_depth=0),
        depth=0,
    )

    line = estimate.line()

    assert "4 searches" in line
    assert "2 sources" in line
    assert "4 LLM calls" in line


def test_empty_question_is_rejected():
    with pytest.raises(ValueError, match="question"):
        estimate_run("   ", Settings())
