from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, replace

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
from ..search.academic import build_academic_chain
from ..search.chain import SearchChain, build_chain, normalize_url
from ..usage import TrackedLLM, UsageTracker
from .checkpoint import CheckpointCallback, DeepCheckpoint
from .extract import ClaimCandidate, extract_claims
from .gaps import check_gaps
from .loop import render_appendix, run_id
from .planner import plan_question, plan_question_llm
from .reader import Reader, build_reader
from .synthesize import SynthesisError, synthesize_report


def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _error_text(exc: Exception) -> str:
    return " ".join(str(exc).split())[:300]


def _interleave(primary: list[Source], secondary: list[Source]) -> list[Source]:
    merged: list[Source] = []
    for index in range(max(len(primary), len(secondary))):
        if index < len(primary):
            merged.append(primary[index])
        if index < len(secondary):
            merged.append(secondary[index])
    return merged


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


@dataclass(frozen=True)
class SourceExtraction:
    source: Source
    status: str
    chars: int
    claims: tuple[ClaimCandidate, ...]
    latency_ms: int
    error: str | None = None


async def _extract_source(
    source: Source,
    reader: Reader,
    llm: LLMProvider,
    *,
    max_claims: int,
    progress: ProgressCallback | None = None,
) -> SourceExtraction:
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
        return SourceExtraction(source, "error", 0, (), latency, error)

    if len(content.text.strip()) < 200:
        latency = _ms(started)
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
        return SourceExtraction(source, "short", len(content.text), (), latency)

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
        return SourceExtraction(
            source,
            "error",
            len(content.text),
            (),
            latency,
            error,
        )

    status = "ok" if candidates else "no_evidence"
    latency = _ms(started)
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
    return SourceExtraction(
        source,
        status,
        len(content.text),
        tuple(candidates),
        latency,
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
    resume: DeepCheckpoint | None = None,
    checkpoint: CheckpointCallback | None = None,
    academic_chain: SearchChain | None = None,
    use_academic: bool | None = None,
) -> Run:
    """Plan, search, read, extract, gap-check, and synthesize one run."""
    normalized = resume.question if resume is not None else " ".join(question.split())
    if not normalized:
        raise ValueError("question is required")

    chain = chain or build_chain(settings)

    if use_academic is None:
        want_academic = resume.academic if resume is not None else settings.academic_enabled
    else:
        want_academic = use_academic
    if academic_chain is None and want_academic:
        academic_chain = build_academic_chain(settings)
    if academic_chain is not None and not academic_chain.providers:
        academic_chain = None

    if not chain.providers and (academic_chain is None or not academic_chain.providers):
        raise RuntimeError(
            "No search provider configured. Set FIRECRAWL_URL, BRAVE_API_KEY, "
            "SERPER_API_KEY, SEARXNG_URL, or enable academic search."
        )
    reader = reader or build_reader(settings)

    identifier = resume.run_id if resume is not None else run_id(normalized)
    limit = max(
        1,
        max_sources
        if max_sources is not None
        else (resume.max_sources if resume is not None else settings.max_sources),
    )
    if resume is not None:
        rounds = max(0, min(2, resume.depth))
    else:
        rounds = settings.max_depth if depth is None else depth
        rounds = max(0, min(2, rounds))
    start = started if started is not None else time.monotonic()

    tracker = UsageTracker.from_models(resume.usage) if resume is not None else UsageTracker()
    planner_llm = TrackedLLM(llms.planner, tracker)
    reader_llm = TrackedLLM(llms.reader, tracker)
    writer_llm = TrackedLLM(llms.writer, tracker)

    plan = resume.plan if resume is not None else None
    sources = list(resume.sources) if resume is not None else []
    attempts = list(resume.attempts) if resume is not None else []
    reads = list(resume.reads) if resume is not None else []
    ledger = CitationLedger(resume.citations if resume is not None else ())
    seen = {normalize_url(source.url) for source in sources}
    buckets: dict[str, list[Source]] = {}
    rounds_done = resume.rounds_done if resume is not None else 0
    phase = resume.phase if resume is not None else "planned"

    def timed_out() -> bool:
        return time.monotonic() - start >= settings.max_seconds

    def snapshot(current_phase: str, current_rounds: int) -> None:
        if checkpoint is None or plan is None:
            return
        state = DeepCheckpoint(
            run_id=identifier,
            question=normalized,
            plan=plan,
            sources=tuple(sources),
            attempts=tuple(attempts),
            citations=ledger.citations,
            reads=tuple(reads),
            usage=tracker.to_models(),
            rounds_done=current_rounds,
            phase=current_phase,
            depth=rounds,
            max_sources=limit,
            academic=want_academic,
        )
        try:
            checkpoint(state)
        except OSError:
            pass

    if resume is not None:
        emit_progress(
            progress,
            "resume",
            f"Resuming {identifier} from {resume.phase}",
            phase=resume.phase,
            sources=len(sources),
            citations=len(ledger.citations),
        )

    if plan is None:
        try:
            plan = await plan_question_llm(
                normalized,
                planner_llm,
                max_sub_questions=4,
            )
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
        snapshot("planned", rounds_done)
    else:
        emit_progress(
            progress,
            "plan",
            f"Resuming plan with {len(plan.sub_questions)} sub-questions",
            planner=plan.planner,
            sub_questions=[item.question for item in plan.sub_questions],
            resumed=True,
        )

    async def search_question(sub_question: SubQuestion) -> None:
        if timed_out():
            return
        emit_progress(
            progress,
            "search",
            f"Searching: {sub_question.question}",
            question=sub_question.question,
        )
        if academic_chain is not None:
            web_outcome, academic_outcome = await asyncio.gather(
                chain.search(
                    sub_question.question,
                    limit=settings.search_limit,
                ),
                academic_chain.search(
                    sub_question.question,
                    limit=settings.search_limit,
                ),
            )
        else:
            web_outcome = await chain.search(
                sub_question.question,
                limit=settings.search_limit,
            )
            academic_outcome = None

        attempts.extend(web_outcome.attempts)
        if academic_outcome is not None:
            attempts.extend(academic_outcome.attempts)
        academic_sources = list(academic_outcome.sources) if academic_outcome is not None else []
        merged = _interleave(academic_sources, list(web_outcome.sources))
        if academic_outcome is not None:
            message = f"{len(academic_sources)} academic · {len(web_outcome.sources)} web"
        else:
            result_word = "result" if len(web_outcome.sources) == 1 else "results"
            message = f"{len(web_outcome.sources)} {result_word}"
        emit_progress(
            progress,
            "search_done",
            message,
            question=sub_question.question,
            count=len(merged),
            academic=len(academic_sources),
            web=len(web_outcome.sources),
        )
        bucket = buckets.setdefault(sub_question.question, [])
        for source in merged:
            key = normalize_url(source.url)
            if key in seen:
                continue
            seen.add(key)
            bucket.append(replace(source, sub_question=sub_question.question))

    semaphore = asyncio.Semaphore(max(1, min(8, settings.concurrency)))

    async def read_round_robin(snapshot_phase: str) -> None:
        while len(sources) < limit and not timed_out():
            batch: list[Source] = []
            for question_key in list(buckets):
                if len(sources) + len(batch) >= limit or timed_out():
                    break
                bucket = buckets[question_key]
                if not bucket:
                    continue
                batch.append(bucket.pop(0))
            if not batch:
                break

            async def limited(source: Source) -> SourceExtraction:
                async with semaphore:
                    return await _extract_source(
                        source,
                        reader,
                        reader_llm,
                        max_claims=settings.max_claims,
                        progress=progress,
                    )

            results = await asyncio.gather(
                *(limited(source) for source in batch),
                return_exceptions=True,
            )
            for source, result in zip(batch, results, strict=True):
                if isinstance(result, asyncio.CancelledError):
                    raise result
                if isinstance(result, Exception):
                    error = _error_text(result)
                    result = SourceExtraction(source, "error", 0, (), 0, error)
                    emit_progress(
                        progress,
                        "read_done",
                        f"Read failed: {source.title}",
                        url=source.url,
                        status="error",
                        chars=0,
                        claims=0,
                        latency_ms=0,
                        error=error,
                    )
                if isinstance(result, BaseException):
                    raise result
                sources.append(source)
                reads.append(
                    ReadAttempt(
                        source.url,
                        result.status,
                        result.chars,
                        len(result.claims),
                        result.latency_ms,
                        result.error,
                    )
                )
                for claim in result.claims:
                    ledger.add(
                        source,
                        claim.quote,
                        locator=claim.locator,
                        note=claim.note,
                    )
            snapshot(snapshot_phase, rounds_done)

    if phase == "planned":
        for sub_question in plan.sub_questions:
            if timed_out():
                break
            await search_question(sub_question)
            snapshot("planned", rounds_done)
        await read_round_robin("planned")
        if not timed_out():
            phase = "gathered"
        snapshot(phase, rounds_done)

    if phase != "synthesis":
        for round_index in range(rounds_done, rounds):
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
                rounds_done = round_index + 1
                snapshot("gaps", rounds_done)
                break
            plan = replace(plan, sub_questions=plan.sub_questions + gap.follow_up)
            for follow_up in gap.follow_up:
                if timed_out():
                    break
                await search_question(follow_up)
            await read_round_robin("gaps")
            rounds_done = round_index + 1
            snapshot("gaps", rounds_done)
        phase = "synthesis"
        snapshot("synthesis", rounds_done)

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
        id=identifier,
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
