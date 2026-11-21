from __future__ import annotations

import re

from ..llm.base import LLMProvider
from ..models import Citation, ResearchPlan, Source

SYNTH_SYSTEM = (
    "You write grounded research reports. Use only the supplied evidence and "
    "cite every factual claim with its provided ID. Never invent a source or "
    "a citation ID."
)

_CITATION_ID = re.compile(r"C\d+")


class SynthesisError(ValueError):
    """The synthesis was missing, ungrounded, or used unknown citations."""


def citation_ids(text: str) -> set[str]:
    """Return C-IDs found in bracketed groups such as [C1] or [C1, C2]."""
    return {
        match
        for group in re.findall(r"\[([^\]]+)\]", text)
        for match in _CITATION_ID.findall(group)
    }


async def synthesize_report(
    llm: LLMProvider,
    question: str,
    plan: ResearchPlan,
    sources: tuple[Source, ...],
    citations: tuple[Citation, ...],
    *,
    max_tokens: int = 2048,
) -> str:
    """Write a cited narrative, then verify every cited ID exists."""
    if not citations:
        raise SynthesisError("no grounded evidence is available to synthesize")

    allowed = {citation.id for citation in citations}
    evidence = "\n\n".join(
        "\n".join(
            [
                f"[{citation.id}] {citation.title} ({citation.source_url})",
                f"Quote: {citation.quote}",
                f"Locator: {citation.locator or 'not stated'}",
                f"Sub-question: {citation.sub_question or 'not stated'}",
                f"Note: {citation.note or 'none'}",
            ]
        )
        for citation in citations[:80]
    )
    source_list = "\n".join(
        f"- {source.title} — {source.url} ({source.source_type})" for source in sources[:40]
    )
    question_list = "\n".join(f"- {item.question}" for item in plan.sub_questions)

    prompt = (
        f"Write a research report answering this question: {question}\n\n"
        f"Sub-questions:\n{question_list}\n\n"
        f"Evidence:\n{evidence}\n\n"
        f"Sources:\n{source_list}\n\n"
        "Rules:\n"
        "- Put an inline citation such as [C1] after every factual claim.\n"
        "- Use only the IDs listed above. Never invent an ID or a source.\n"
        "- Distinguish evidence from inference; note conflicts and limitations.\n"
        "- Do not add a source list or a citations section; Indagar appends them.\n"
        "- If the evidence is insufficient, say so plainly.\n"
        "- Be concise: 400-800 words unless the question needs more."
    )
    response = await llm.complete(prompt, system=SYNTH_SYSTEM, max_tokens=max_tokens)
    text = response.text.strip()
    if not text:
        raise SynthesisError("the model returned an empty report")

    used = citation_ids(text)
    unknown = used - allowed
    if unknown:
        raise SynthesisError(f"unknown citation ids: {', '.join(sorted(unknown))}")
    if not used:
        raise SynthesisError("the report used no citations")
    return text


__all__ = ["SYNTH_SYSTEM", "SynthesisError", "citation_ids", "synthesize_report"]
