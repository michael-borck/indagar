from __future__ import annotations

import time
from dataclasses import replace

from ..citations import CitationLedger
from ..config import Settings
from ..llm.base import LLMError, LLMProvider
from ..llm.factory import LLMSet
from ..models import (
    Citation,
    ModelUsage,
    ReadAttempt,
    ResearchPlan,
    Run,
    SearchAttempt,
    Source,
    SubQuestion,
    utc_now,
)
from ..progress import ProgressCallback, emit_progress
from ..search.chain import SearchChain, build_chain, normalize_url
from ..usage import TrackedLLM, UsageTracker
from .extract import extract_claims
from .gaps import check_gaps
from .loop import render_appendix, run_id
from .planner import plan_question, plan_question_llm
from .reader import Reader, build_reader
from .synthesize import SynthesisError, synthesize_report


def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _error_text(exc: Exception) -> str:
    return " ".join(str(exc).split())[:300]


def _compose_report(
    question: str,
    plan: ResearchPlan,
    narrative: str,
    notice: str,
    sources: tuple[Source, ...],
    attempts: tuple[SearchAttempt, ...],
    citations: tuple[Citation, ...],
    reads: tuple[ReadAttempt, ...],
    usage: tuple[ModelUsage, ...],
) -> str:
    lines = [
        f"# Research report: {question}",
        "",
        f"Generated: {utc_now()}",
        "",
        f"> {notice}",
        "",
        narrative.strip(),
        "",
        render_appendix(plan, sources, attempts, citations, reads, usage),
    ]
    return "\n".join(lines).rstrip() + "\n"


async def _read_source(
    source: Source,
    reader: Reader,
    llm: LLMProvider,
    ledger: CitationLedger,
    reads: list[ReadAttempt],
    *,
    max_claims: int,
    progress: ProgressCallback | None = None,
) -> None:
    started = time.perf_counter()
    emit_progress(
        progress,
        "read",
        f"Reading {source.title}",
        url=source.url,
        title=source.title,
        domain=source.domain,
    )
    try:
        content = await reader.read(source)
    except Exception as exc:
        latency = _ms(started)
        error = _error_text(exc)
        reads.append(ReadAttempt(source.url, "error", 0, 0, latency, error))
        emit_progress(
            progress,
            "read_done",
            f"Read failed: {source.title}",
            url=source.url,
            status="error",
            chars=0,
            claims=0,
            latency_ms=latency,
            error=error,
        )
        return

    if len(content.text.strip()) < 200:
        latency = _ms(started)
        reads.append(ReadAttempt(source.url, "short", len(content.text), 0, latency))
        emit_progress(
            progress,
            "read_done",
            f"Too short to extract: {source.title}",
            url=source.url,
            status="short",
            chars=len(content.text),
            claims=0,
            latency_ms=latency,
        )
        return

    try:
        candidates = await extract_claims(
            llm,
            source,
            content.text,
            source.sub_question or "",
            max_claims=max_claims,
        )
    except (LLMError, ValueError) as exc:
        latency = _ms(started)
        error = _error_text(exc)
        reads.append(
            ReadAttempt(
                source.url,
                "error",
                len(content.text),
                0,
                latency,
                error,
            )
        )
        emit_progress(
            progress,
            "read_done",
            f"Extraction failed: {source.title}",
            url=source.url,
            status="error",
            chars=len(content.text),
            claims=0,
            latency_ms=latency,
            error=error,
        )
        return

    for candidate in candidates:
        ledger.add(
            source,
            candidate.quote,
            locator=candidate.locator,
            note=candidate.note,
        )
    status = "ok" if candidates else "no_evidence"
    latency = _ms(started)
    reads.append(
        ReadAttempt(
            source.url,
            status,
            len(content.text),
            len(candidates),
            latency,
        )
    )
    claim_word = "claim" if len(candidates) == 1 else "claims"
    emit_progress(
        progress,
        "read_done",
        f"{len(candidates)} {claim_word} from {source.title}",
        url=source.url,
        status=status,
        chars=len(content.text),
        claims=len(candidates),
        latency_ms=latency,
    )


async def run_deep_research(
    question: str,
    settings: Settings,
    *,
    llms: LLMSet,
    reader: Reader | None = None,
    chain: SearchChain | None = None,
    max_sources: int | None = None,
    depth: int | None = None,
    started: float | None = None,
    progress: ProgressCallback | None = None,
) -> Run:
    """Plan, search, read, extract, gap-check, and synthesize one run."""
    normalized = " ".join(question.split())
    if not normalized:
        raise ValueError("question is required")

    chain = chain or build_chain(settings)
    if not chain.providers:
        raise RuntimeError(
            "No search provider configured. Set FIRECRAWL_URL, BRAVE_API_KEY, "
            "SERPER_API_KEY, or SEARXNG_URL."
        )
    reader = reader or build_reader(settings)

    limit = max(1, max_sources or settings.max_sources)
    rounds = settings.max_depth if depth is None else depth
    rounds = max(0, min(2, rounds))
    start = started if started is not None else time.monotonic()

    tracker = UsageTracker()
    planner_llm = TrackedLLM(llms.planner, tracker)
    reader_llm = TrackedLLM(llms.reader, tracker)
    writer_llm = TrackedLLM(llms.writer, tracker)

    def timed_out() -> bool:
        return time.monotonic() - start >= settings.max_seconds

    try:
        plan = await plan_question_llm(normalized, planner_llm, max_sub_questions=4)
    except (LLMError, ValueError):
        plan = replace(
            plan_question(normalized, max_sub_questions=4),
            planner="deterministic-fallback",
        )
        emit_progress(
            progress,
            "plan_fallback",
            "Planner unavailable; using the deterministic plan",
            planner=plan.planner,
            sub_questions=[item.question for item in plan.sub_questions],
        )
    else:
        emit_progress(
            progress,
            "plan",
            f"Planned {len(plan.sub_questions)} sub-questions",
            planner=plan.planner,
            sub_questions=[item.question for item in plan.sub_questions],
        )

    buckets: dict[str, list[Source]] = {}
    seen: set[str] = set()
    attempts: list[SearchAttempt] = []
    sources: list[Source] = []
    reads: list[ReadAttempt] = []
    ledger = CitationLedger()

    async def search_question(sub_question: SubQuestion) -> None:
        if timed_out():
            return
        emit_progress(
            progress,
            "search",
            f"Searching: {sub_question.question}",
            question=sub_question.question,
        )
        outcome = await chain.search(
            sub_question.question,
            limit=settings.search_limit,
        )
        attempts.extend(outcome.attempts)
        result_word = "result" if len(outcome.sources) == 1 else "results"
        emit_progress(
            progress,
            "search_done",
            f"{len(outcome.sources)} {result_word}",
            question=sub_question.question,
            count=len(outcome.sources),
        )
        bucket = buckets.setdefault(sub_question.question, [])
        for source in outcome.sources:
            key = normalize_url(source.url)
            if key in seen:
                continue
            seen.add(key)
            bucket.append(replace(source, sub_question=sub_question.question))

    async def read_round_robin() -> None:
        while len(sources) < limit and not timed_out():
            added = False
            for question_key in list(buckets):
                if len(sources) >= limit or timed_out():
                    break
                bucket = buckets[question_key]
                if not bucket:
                    continue
                source = bucket.pop(0)
                added = True
                sources.append(source)
                await _read_source(
                    source,
                    reader,
                    reader_llm,
                    ledger,
                    reads,
                    max_claims=settings.max_claims,
                    progress=progress,
                )
            if not added:
                break

    for sub_question in plan.sub_questions:
        if timed_out():
            break
        await search_question(sub_question)
    await read_round_robin()

    for round_index in range(rounds):
        if timed_out() or len(sources) >= limit:
            break
        emit_progress(
            progress,
            "gap",
            f"Checking coverage (round {round_index + 1})",
            round=round_index + 1,
        )
        gap = await check_gaps(
            planner_llm,
            normalized,
            plan,
            ledger.citations,
            tuple(sources),
            max_follow_ups=settings.max_follow_ups,
        )
        emit_progress(
            progress,
            "gap_done",
            "Coverage sufficient" if gap.done else f"{len(gap.follow_up)} follow-up questions",
            done=gap.done,
            follow_up=[item.question for item in gap.follow_up],
        )
        if gap.done or not gap.follow_up:
            break
        plan = replace(plan, sub_questions=plan.sub_questions + gap.follow_up)
        for follow_up in gap.follow_up:
            if timed_out():
                break
            await search_question(follow_up)
        await read_round_robin()

    emit_progress(
        progress,
        "synthesis",
        "Writing the cited report",
        citations=len(ledger.citations),
        sources=len(sources),
    )
    try:
        narrative = await synthesize_report(
            writer_llm,
            normalized,
            plan,
            tuple(sources),
            ledger.citations,
            max_tokens=settings.synthesis_max_tokens,
        )
        notice = (
            "Synthesized with inline citations. Verify important claims against "
            "the source quotes below."
        )
        emit_progress(
            progress,
            "synthesis_done",
            "Report synthesized",
            citations=len(ledger.citations),
        )
    except (LLMError, SynthesisError) as exc:
        error = _error_text(exc)
        narrative = (
            "No synthesized narrative was produced. The grounded evidence table "
            "below lists the extracted claims."
        )
        notice = f"Synthesis unavailable: {error}"
        emit_progress(
            progress,
            "synthesis_fallback",
            "Synthesis unavailable; using the evidence table",
            error=error,
        )

    usage = tracker.to_models()
    emit_progress(
        progress,
        "done",
        f"Research complete: {len(ledger.citations)} citations",
        citations=len(ledger.citations),
        sources=len(sources),
        reads=len(reads),
        calls=sum(item.calls for item in usage),
    )
    report = _compose_report(
        normalized,
        plan,
        narrative,
        notice,
        tuple(sources),
        tuple(attempts),
        ledger.citations,
        tuple(reads),
        usage,
    )
    return Run(
        id=run_id(normalized),
        question=normalized,
        plan=plan,
        sources=tuple(sources),
        attempts=tuple(attempts),
        report=report,
        citations=ledger.citations,
        reads=tuple(reads),
        usage=usage,
    )


__all__ = ["run_deep_research"]
