import asyncio
import json

import pytest

from indagar.llm.base import LLMResponse
from indagar.research.planner import plan_question, plan_question_llm


class FakeLLM:
    name = "fake"
    model = "fake-model"

    def __init__(self, text: str):
        self.text = text

    async def complete(self, prompt: str, **kwargs) -> LLMResponse:
        return LLMResponse(self.text, "fake", "fake-model")


def test_plan_has_the_question_plus_facets():
    plan = plan_question("  Does X improve Y?  ", max_sub_questions=3)

    assert plan.question == "Does X improve Y?"
    assert len(plan.sub_questions) == 3
    assert plan.sub_questions[0].question == "Does X improve Y?"
    assert all(item.rationale for item in plan.sub_questions)


def test_plan_can_be_a_single_question():
    plan = plan_question("What is X?", max_sub_questions=1)
    assert len(plan.sub_questions) == 1


def test_empty_question_is_rejected():
    with pytest.raises(ValueError):
        plan_question("   ")


def test_llm_plan_parses_dedupes_and_limits():
    payload = {
        "sub_questions": [
            {"question": "What is X?", "rationale": "Define it."},
            {"question": "What is the evidence for X?", "rationale": "Find evidence."},
            {"question": "What is X?", "rationale": "Duplicate."},
        ]
    }
    llm = FakeLLM(f"```json\n{json.dumps(payload)}\n```")

    plan = asyncio.run(plan_question_llm("  What is X?  ", llm, max_sub_questions=3))

    assert plan.question == "What is X?"
    assert plan.planner == "llm"
    assert len(plan.sub_questions) == 2
    assert plan.sub_questions[0].question == "What is X?"


def test_llm_plan_rejects_bad_json():
    with pytest.raises(ValueError, match="JSON"):
        asyncio.run(plan_question_llm("What is X?", FakeLLM("no json here")))


def test_llm_plan_rejects_empty_plan():
    with pytest.raises(ValueError, match="no usable sub-questions"):
        asyncio.run(
            plan_question_llm(
                "What is X?",
                FakeLLM('{"sub_questions": []}'),
            )
        )
