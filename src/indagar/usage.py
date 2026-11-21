from __future__ import annotations

from dataclasses import dataclass, field

from .llm.base import LLMProvider, LLMResponse
from .models import ModelUsage


@dataclass
class UsageTracker:
    """Accumulate calls and tokens per provider/model pair."""

    _by_model: dict[tuple[str, str], list[int]] = field(default_factory=dict)

    def record(self, response: LLMResponse) -> None:
        key = (response.provider, response.model)
        stats = self._by_model.setdefault(key, [0, 0, 0])
        stats[0] += 1
        stats[1] += response.input_tokens or 0
        stats[2] += response.output_tokens or 0

    @property
    def calls(self) -> int:
        return sum(stats[0] for stats in self._by_model.values())

    @property
    def input_tokens(self) -> int:
        return sum(stats[1] for stats in self._by_model.values())

    @property
    def output_tokens(self) -> int:
        return sum(stats[2] for stats in self._by_model.values())

    @classmethod
    def from_models(cls, models: tuple[ModelUsage, ...]) -> UsageTracker:
        tracker = cls()
        for item in models:
            tracker._by_model[(item.provider, item.model)] = [
                item.calls,
                item.input_tokens,
                item.output_tokens,
            ]
        return tracker

    def to_models(self) -> tuple[ModelUsage, ...]:
        return tuple(
            ModelUsage(
                provider=provider,
                model=model,
                calls=stats[0],
                input_tokens=stats[1],
                output_tokens=stats[2],
            )
            for (provider, model), stats in sorted(self._by_model.items())
        )


class TrackedLLM:
    """Record usage for every completion without changing the caller."""

    def __init__(self, provider: LLMProvider, tracker: UsageTracker):
        self._provider = provider
        self._tracker = tracker

    @property
    def name(self) -> str:
        return self._provider.name

    @property
    def model(self) -> str | None:
        return self._provider.model

    async def complete(
        self,
        prompt: str,
        *,
        system: str = "",
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        json_mode: bool = False,
    ) -> LLMResponse:
        response = await self._provider.complete(
            prompt,
            system=system,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            json_mode=json_mode,
        )
        self._tracker.record(response)
        return response


__all__ = ["TrackedLLM", "UsageTracker"]
