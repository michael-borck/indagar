from __future__ import annotations

from ..llm.base import LLMProvider
from ..models import ResearchPlan, SubQuestion
from .json_utils import parse_json_object

FACETS: tuple[tuple[str, str], ...] = (
    ("overview and definitions", "Establish shared terms and background."),
    ("evidence and data", "Find quantitative or empirical evidence."),
    ("critiques and limitations", "Look for counterarguments, failures, and known limits."),
    ("recent developments", "Check what changed recently."),
)

PLANNER_SYSTEM = (
    "You plan research. Return only JSON. Never answer the research question. "
    "Every sub-question must be independently searchable."
)


def plan_question(question: str, max_sub_questions: int = 4) -> ResearchPlan:
    """Deterministic Phase 0 plan: the question plus focused facets."""
    normalized = " ".join(question.split())
    if not normalized:
        raise ValueError("question is required")
    count = min(max(1, max_sub_questions), len(FACETS) + 1)
    sub_questions = [SubQuestion(normalized, "Answer the question directly.")]
    for suffix, rationale in FACETS[: count - 1]:
        sub_questions.append(SubQuestion(f"{normalized} {suffix}", rationale))
    return ResearchPlan(normalized, tuple(sub_questions))


async def plan_question_llm(
    question: str,
    llm: LLMProvider,
    max_sub_questions: int = 4,
) -> ResearchPlan:
    """Ask the planner model for a small, searchable plan."""
    normalized = " ".join(question.split())
    if not normalized:
        raise ValueError("question is required")
    limit = min(max(1, max_sub_questions), len(FACETS) + 1)

    prompt = (
        "Plan research for the question below.\n\n"
        f"Question: {normalized}\n\n"
        f"Return at most {limit} sub-questions. The first should answer the "
        "question directly; the rest should cover definitions, evidence, "
        "counterarguments, limitations, or recent developments as relevant.\n\n"
        'JSON shape: {"sub_questions": [{"question": "...", '
        '"rationale": "..."}]}\n'
        "Use short, searchable questions. Do not answer them."
    )
    response = await llm.complete(prompt, system=PLANNER_SYSTEM, json_mode=True)
    data = parse_json_object(response.text)

    items = data.get("sub_questions")
    if not isinstance(items, list):
        raise ValueError("planner returned no sub_questions list")

    sub_questions: list[SubQuestion] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        value = " ".join(str(item.get("question") or "").split())[:300]
        if not value:
            continue
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        rationale = " ".join(str(item.get("rationale") or "").split())[:500]
        sub_questions.append(SubQuestion(value, rationale or "Planned by the model."))
        if len(sub_questions) >= limit:
            break

    if not sub_questions:
        raise ValueError("planner returned no usable sub-questions")
    return ResearchPlan(normalized, tuple(sub_questions), planner="llm")


__all__ = ["FACETS", "PLANNER_SYSTEM", "plan_question", "plan_question_llm"]
