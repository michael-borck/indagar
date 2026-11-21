from __future__ import annotations

import re
from dataclasses import replace
from datetime import UTC, datetime

from ..citations import render_citations
from ..config import Settings
from ..models import (
    Citation,
    ModelUsage,
    ReadAttempt,
    ResearchPlan,
    Run,
    SearchAttempt,
    SearchOutcome,
    Source,
    utc_now,
)
from ..progress import ProgressCallback, emit_progress
from ..search.chain import SearchChain, build_chain, normalize_url
from .planner import plan_question


def run_id(question: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    slug = re.sub(r"[^a-z0-9]+", "-", question.lower()).strip("-")[:48]
    return f"{stamp}-{slug or 'research'}"


def _escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def render_appendix(
    plan: ResearchPlan,
    sources: tuple[Source, ...],
    attempts: tuple[SearchAttempt, ...],
    citations: tuple[Citation, ...] = (),
    reads: tuple[ReadAttempt, ...] = (),
    usage: tuple[ModelUsage, ...] = (),
) -> str:
    lines = ["## Plan", ""]
    for index, sub_question in enumerate(plan.sub_questions, start=1):
        lines.append(f"{index}. **{sub_question.question}** — {sub_question.rationale}")

    lines.extend(["", "## Sources", ""])
    if not sources:
        lines.append("_No sources were returned._")
    for index, source in enumerate(sources, start=1):
        lines.append(f"{index}. **{source.title}** — {source.url}")
        meta = [f"provider: {source.provider or 'unknown'}", f"domain: {source.domain}"]
        if source.sub_question:
            meta.append(f"sub-question: {source.sub_question}")
        lines.append(f"   {' · '.join(meta)}")
        if source.snippet:
            lines.append(f"   {source.snippet}")
        lines.append("")

    lines.extend(["", "## Citations", "", render_citations(citations), ""])
    lines.extend(
        [
            "## Search attempts",
            "",
            "| Provider | Status | Count | Latency |",
            "|---|---|---|---|",
        ]
    )
    for attempt in attempts:
        detail = _escape(attempt.error) if attempt.error else ""
        status = attempt.status if not detail else f"{attempt.status}: {detail}"
        lines.append(
            f"| {attempt.provider} | {status} | {attempt.count} | {attempt.latency_ms}ms |"
        )

    if reads:
        lines.extend(
            [
                "",
                "## Sources read",
                "",
                "| URL | Status | Chars | Claims | Latency |",
                "|---|---|---|---|---|",
            ]
        )
        for read in reads:
            detail = _escape(read.error)[:240] if read.error else ""
            status = read.status if not detail else f"{read.status}: {detail}"
            lines.append(
                f"| {_escape(read.url)} | {status} | {read.chars} | "
                f"{read.claims} | {read.latency_ms}ms |"
            )

    if usage:
        lines.extend(
            [
                "",
                "## Usage",
                "",
                "| Provider | Model | Calls | Input | Output |",
                "|---|---|---|---|---|",
            ]
        )
        for item in usage:
            lines.append(
                f"| {_escape(item.provider)} | {_escape(item.model)} | "
                f"{item.calls} | {item.input_tokens} | {item.output_tokens} |"
            )

    return "\n".join(lines).rstrip()


def render_dossier(
    plan: ResearchPlan,
    sources: tuple[Source, ...],
    attempts: tuple[SearchAttempt, ...],
    citations: tuple[Citation, ...] = (),
) -> str:
    notice = (
        "Sources were discovered, deduplicated, and cited."
        if citations
        else "Retrieval-only run. Use `indagar research --llm` for LLM planning, "
        "source reading, claim extraction, gap checks, and synthesis."
    )
    lines = [
        f"# Research dossier: {plan.question}",
        "",
        f"Generated: {utc_now()}",
        "",
        f"> {notice}",
        "",
        render_appendix(plan, sources, attempts, citations),
        "",
        "## Next",
        "",
        "- Run with `--llm` for the full planner, reader, gap-check, and synthesis loop.",
        "- Add source-type confidence labels and academic providers.",
        "- Add a pre-run cost estimate and provider rate limiting.",
        "- Build the web UI and desktop shell.",
    ]
    return "\n".join(lines).rstrip() + "\n"


async def run_research(
    question: str,
    settings: Settings,
    chain: SearchChain | None = None,
    plan: ResearchPlan | None = None,
    max_sources: int | None = None,
    progress: ProgressCallback | None = None,
) -> Run:
    plan = plan or plan_question(question, max_sub_questions=4)
    emit_progress(
        progress,
        "plan",
        f"Planned {len(plan.sub_questions)} sub-questions",
        planner=plan.planner,
        sub_questions=[item.question for item in plan.sub_questions],
    )
    chain = chain or build_chain(settings)
    if not chain.providers:
        raise RuntimeError(
            "No search provider configured. Set FIRECRAWL_URL, BRAVE_API_KEY, "
            "SERPER_API_KEY, or SEARXNG_URL."
        )

    limit = max(1, max_sources or settings.max_sources)
    buckets: dict[str, list[Source]] = {
        sub_question.question: [] for sub_question in plan.sub_questions
    }
    seen: set[str] = set()
    attempts: list[SearchAttempt] = []

    for sub_question in plan.sub_questions:
        emit_progress(
            progress,
            "search",
            f"Searching: {sub_question.question}",
            question=sub_question.question,
        )
        outcome: SearchOutcome = await chain.search(
            sub_question.question, limit=settings.search_limit
        )
        result_word = "result" if len(outcome.sources) == 1 else "results"
        emit_progress(
            progress,
            "search_done",
            f"{len(outcome.sources)} {result_word}",
            question=sub_question.question,
            count=len(outcome.sources),
        )
        attempts.extend(outcome.attempts)
        for source in outcome.sources:
            key = normalize_url(source.url)
            if key in seen:
                continue
            seen.add(key)
            buckets[sub_question.question].append(
                replace(source, sub_question=sub_question.question)
            )

    selected: list[Source] = []
    while len(selected) < limit:
        added = False
        for sub_question in plan.sub_questions:
            bucket = buckets[sub_question.question]
            if not bucket:
                continue
            selected.append(bucket.pop(0))
            added = True
            if len(selected) >= limit:
                break
        if not added:
            break

    selected = tuple(selected)
    emit_progress(
        progress,
        "done",
        f"Collected {len(selected)} sources",
        sources=len(selected),
    )
    report = render_dossier(plan, selected, tuple(attempts))
    return Run(
        id=run_id(plan.question),
        question=plan.question,
        plan=plan,
        sources=selected,
        attempts=tuple(attempts),
        report=report,
    )


__all__ = ["render_appendix", "render_dossier", "run_id", "run_research"]
