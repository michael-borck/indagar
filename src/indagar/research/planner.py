from __future__ import annotations

from ..models import ResearchPlan, SubQuestion

FACETS: tuple[tuple[str, str], ...] = (
    ("overview and definitions", "Establish shared terms and background."),
    ("evidence and data", "Find quantitative or empirical evidence."),
    ("critiques and limitations", "Look for counterarguments, failures, and known limits."),
    ("recent developments", "Check what changed recently."),
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


__all__ = ["FACETS", "plan_question"]
