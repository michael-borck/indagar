from __future__ import annotations

from dataclasses import dataclass

from ..llm.base import LLMProvider
from ..models import Source
from .json_utils import parse_json_object

EXTRACT_SYSTEM = (
    "You extract evidence from one source. Return only JSON. "
    "Quotes must be copied verbatim from the source; never paraphrase."
)


@dataclass(frozen=True)
class ClaimCandidate:
    quote: str
    locator: str | None = None
    note: str = ""


def _normalize(value: str) -> str:
    return " ".join(value.split()).casefold()


async def extract_claims(
    llm: LLMProvider,
    source: Source,
    content: str,
    sub_question: str,
    *,
    max_claims: int = 5,
) -> tuple[ClaimCandidate, ...]:
    """Extract grounded claim candidates; drop quotes absent from the source."""
    limit = max(1, max_claims)
    prompt = (
        "Extract evidence for the sub-question below from SOURCE.\n\n"
        f"Sub-question: {sub_question}\n"
        f"Source title: {source.title}\n"
        f"Source URL: {source.url}\n\n"
        f"Return at most {limit} claims as JSON:\n"
        '{"claims": [{"quote": "...", "locator": "...", "note": "..."}]}\n\n'
        "Rules:\n"
        "- quote must be copied verbatim from SOURCE, between 25 and 600 characters.\n"
        "- Do not paraphrase, merge sentences, or use ellipses.\n"
        "- locator is a page, section, heading, or timestamp if visible; else null.\n"
        "- note is one short sentence explaining why the quote matters.\n"
        '- If SOURCE does not support the sub-question, return {"claims": []}.\n\n'
        f"SOURCE:\n{content}"
    )
    response = await llm.complete(prompt, system=EXTRACT_SYSTEM, json_mode=True)
    data = parse_json_object(response.text)
    items = data.get("claims")
    if not isinstance(items, list):
        return ()

    content_norm = _normalize(content)
    candidates: list[ClaimCandidate] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        quote = " ".join(str(item.get("quote") or "").split())
        if len(quote) < 25 or len(quote) > 600:
            continue
        key = quote.casefold()
        if key in seen:
            continue
        if _normalize(quote) not in content_norm:
            continue
        locator = " ".join(str(item.get("locator") or "").split())[:80] or None
        note = " ".join(str(item.get("note") or "").split())[:300]
        seen.add(key)
        candidates.append(ClaimCandidate(quote, locator, note))
        if len(candidates) >= limit:
            break
    return tuple(candidates)


__all__ = ["ClaimCandidate", "EXTRACT_SYSTEM", "extract_claims"]
