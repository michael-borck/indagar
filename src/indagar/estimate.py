from __future__ import annotations

from dataclasses import asdict, dataclass

from .config import Settings

PLANNER_INPUT_TOKENS = 800
PLANNER_OUTPUT_TOKENS = 500
GAP_INPUT_TOKENS = 1200
GAP_OUTPUT_TOKENS = 400
SYNTHESIS_BASE_INPUT_TOKENS = 1200
PER_SOURCE_OUTPUT_TOKENS = 140


@dataclass(frozen=True)
class RunEstimate:
    question: str
    sources: int
    searches: int
    llm_calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def line(self) -> str:
        if self.llm_calls:
            text = (
                f"Estimate: {self.searches} searches · {self.sources} sources · "
                f"{self.llm_calls} LLM calls · ~{self.input_tokens:,} in / "
                f"{self.output_tokens:,} out tokens"
            )
        else:
            text = f"Estimate: {self.searches} searches · {self.sources} sources · retrieval only"
        if self.cost_usd is not None:
            text += f" · ~${self.cost_usd:.4f}"
        return text


def cost_for_tokens(
    input_tokens: int,
    output_tokens: int,
    settings: Settings,
) -> float | None:
    if settings.input_cost_per_mtok is None and settings.output_cost_per_mtok is None:
        return None
    input_rate = settings.input_cost_per_mtok or 0.0
    output_rate = settings.output_cost_per_mtok or 0.0
    return (input_tokens / 1_000_000) * input_rate + (output_tokens / 1_000_000) * output_rate


def estimate_run(
    question: str,
    settings: Settings,
    *,
    max_sources: int | None = None,
    depth: int | None = None,
    llm: bool = True,
) -> RunEstimate:
    normalized = " ".join(question.split())
    if not normalized:
        raise ValueError("question is required")

    sources = max(1, max_sources or settings.max_sources)
    rounds = 0 if not llm else (settings.max_depth if depth is None else depth)
    rounds = max(0, min(2, rounds))
    searches = 4 + rounds * settings.max_follow_ups

    if not llm:
        return RunEstimate(
            question=normalized,
            sources=sources,
            searches=searches,
            llm_calls=0,
            input_tokens=0,
            output_tokens=0,
        )

    per_source_input = settings.max_content_chars // 4 + 500
    per_source_output = settings.max_claims * PER_SOURCE_OUTPUT_TOKENS
    synthesis_input = (
        SYNTHESIS_BASE_INPUT_TOKENS + sources * settings.max_claims * 150 + sources * 60
    )

    input_tokens = (
        PLANNER_INPUT_TOKENS
        + sources * per_source_input
        + rounds * GAP_INPUT_TOKENS
        + synthesis_input
    )
    output_tokens = (
        PLANNER_OUTPUT_TOKENS
        + sources * per_source_output
        + rounds * GAP_OUTPUT_TOKENS
        + settings.synthesis_max_tokens
    )
    calls = 1 + sources + rounds + 1

    return RunEstimate(
        question=normalized,
        sources=sources,
        searches=searches,
        llm_calls=calls,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_for_tokens(input_tokens, output_tokens, settings),
    )


__all__ = ["RunEstimate", "cost_for_tokens", "estimate_run"]
