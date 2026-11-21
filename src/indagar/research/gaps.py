from __future__ import annotations

from dataclasses import dataclass

from ..llm.base import LLMError, LLMProvider
from ..models import Citation, ResearchPlan, Source, SubQuestion
from .json_utils import parse_json_object

GAP_SYSTEM = (
    "You audit research coverage. Return only JSON. "
    "Ask follow-up questions only when the evidence has a clear gap."
)


@dataclass(frozen=True)
class GapCheck:
    done: bool
    follow_up: tuple[SubQuestion, ...] = ()


async def check_gaps(
    llm: LLMProvider,
    question: str,
    plan: ResearchPlan,
    citations: tuple[Citation, ...],
    sources: tuple[Source, ...],
    *,
    max_follow_ups: int = 3,
) -> GapCheck:
    """Ask for at most a few missing questions; fail closed on bad output."""
    limit = max(0, max_follow_ups)
    if limit == 0:
        return GapCheck(done=True)

    coverage = "\n".join(f"- {item.question}" for item in plan.sub_questions) or "(none)"
    evidence = (
        "\n".join(
            f"[{citation.id}] {citation.note or citation.quote[:200]}"
            for citation in citations[:60]
        )
        or "(none)"
    )
    source_list = "\n".join(f"- {source.title}" for source in sources[:40]) or "(none)"

    prompt = (
        "Audit whether the evidence is enough to answer the question.\n\n"
        f"Question: {question}\n\n"
        f"Sub-questions:\n{coverage}\n\n"
        f"Evidence:\n{evidence}\n\n"
        f"Sources:\n{source_list}\n\n"
        f"Return at most {limit} follow-up sub-questions as JSON:\n"
        '{"done": false, "follow_up": [{"question": "...", '
        '"rationale": "..."}]}\n\n'
        "Set done to true when the evidence is sufficient or no useful "
        "follow-up is possible. Do not repeat an existing sub-question."
    )

    try:
        response = await llm.complete(prompt, system=GAP_SYSTEM, json_mode=True)
        data = parse_json_object(response.text)
    except (LLMError, ValueError):
        return GapCheck(done=True)

    if bool(data.get("done")):
        return GapCheck(done=True)

    items = data.get("follow_up")
    if not isinstance(items, list):
        return GapCheck(done=True)

    existing = {item.question.casefold() for item in plan.sub_questions}
    follow_up: list[SubQuestion] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        value = " ".join(str(item.get("question") or "").split())[:300]
        if not value or value.casefold() in existing:
            continue
        existing.add(value.casefold())
        rationale = " ".join(str(item.get("rationale") or "").split())[:500]
        follow_up.append(SubQuestion(value, rationale or "Follow-up from the gap check."))
        if len(follow_up) >= limit:
            break

    return GapCheck(done=not follow_up, follow_up=tuple(follow_up))


__all__ = ["GAP_SYSTEM", "GapCheck", "check_gaps"]
