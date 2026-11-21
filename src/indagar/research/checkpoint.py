from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ..models import (
    Citation,
    ModelUsage,
    ReadAttempt,
    ResearchPlan,
    SearchAttempt,
    Source,
    SubQuestion,
    utc_now,
)

SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,160}$")
PHASES = {"planned", "gathered", "gaps", "synthesis"}


@dataclass
class DeepCheckpoint:
    run_id: str
    question: str
    plan: ResearchPlan
    sources: tuple[Source, ...] = ()
    attempts: tuple[SearchAttempt, ...] = ()
    citations: tuple[Citation, ...] = ()
    reads: tuple[ReadAttempt, ...] = ()
    usage: tuple[ModelUsage, ...] = ()
    rounds_done: int = 0
    phase: str = "planned"
    depth: int = 1
    max_sources: int = 12
    academic: bool = True
    media: bool = False
    updated_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "question": self.question,
            "plan": self.plan.to_dict(),
            "sources": [item.to_dict() for item in self.sources],
            "attempts": [item.to_dict() for item in self.attempts],
            "citations": [item.to_dict() for item in self.citations],
            "reads": [item.to_dict() for item in self.reads],
            "usage": [item.to_dict() for item in self.usage],
            "rounds_done": self.rounds_done,
            "phase": self.phase,
            "depth": self.depth,
            "max_sources": self.max_sources,
            "academic": self.academic,
            "media": self.media,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> DeepCheckpoint:
        plan_data = data.get("plan")
        if not isinstance(plan_data, dict):
            plan_data = {}
        question = str(data.get("question") or plan_data.get("question") or "")
        sub_questions = []
        for item in plan_data.get("sub_questions") or []:
            if not isinstance(item, dict):
                continue
            sub_questions.append(
                SubQuestion(
                    str(item.get("question") or ""),
                    str(item.get("rationale") or ""),
                )
            )
        plan = ResearchPlan(
            question,
            tuple(sub_questions),
            planner=str(plan_data.get("planner") or "deterministic"),
        )

        sources = []
        for item in data.get("sources") or []:
            if not isinstance(item, dict):
                continue
            sources.append(
                Source(
                    title=str(item.get("title") or ""),
                    url=str(item.get("url") or ""),
                    snippet=str(item.get("snippet") or ""),
                    provider=str(item.get("provider") or ""),
                    source_type=str(item.get("source_type") or "web"),
                    sub_question=(
                        str(item["sub_question"]) if item.get("sub_question") is not None else None
                    ),
                    confidence=str(item.get("confidence") or "low"),
                    published=str(item.get("published") or ""),
                    authors=str(item.get("authors") or ""),
                )
            )

        attempts = []
        for item in data.get("attempts") or []:
            if not isinstance(item, dict):
                continue
            attempts.append(
                SearchAttempt(
                    provider=str(item.get("provider") or ""),
                    status=str(item.get("status") or ""),
                    count=int(item.get("count") or 0),
                    latency_ms=int(item.get("latency_ms") or 0),
                    error=(str(item["error"]) if item.get("error") is not None else None),
                )
            )

        citations = []
        for item in data.get("citations") or []:
            if not isinstance(item, dict):
                continue
            try:
                citations.append(
                    Citation(
                        id=str(item.get("id") or ""),
                        source_url=str(item.get("source_url") or ""),
                        title=str(item.get("title") or ""),
                        quote=str(item.get("quote") or ""),
                        locator=(str(item["locator"]) if item.get("locator") is not None else None),
                        sub_question=(
                            str(item["sub_question"])
                            if item.get("sub_question") is not None
                            else None
                        ),
                        note=str(item.get("note") or ""),
                        source_type=str(item.get("source_type") or "web"),
                        confidence=str(item.get("confidence") or "low"),
                    )
                )
            except ValueError:
                continue

        reads = []
        for item in data.get("reads") or []:
            if not isinstance(item, dict):
                continue
            reads.append(
                ReadAttempt(
                    url=str(item.get("url") or ""),
                    status=str(item.get("status") or ""),
                    chars=int(item.get("chars") or 0),
                    claims=int(item.get("claims") or 0),
                    latency_ms=int(item.get("latency_ms") or 0),
                    error=(str(item["error"]) if item.get("error") is not None else None),
                )
            )

        usage = []
        for item in data.get("usage") or []:
            if not isinstance(item, dict):
                continue
            usage.append(
                ModelUsage(
                    provider=str(item.get("provider") or ""),
                    model=str(item.get("model") or ""),
                    calls=int(item.get("calls") or 0),
                    input_tokens=int(item.get("input_tokens") or 0),
                    output_tokens=int(item.get("output_tokens") or 0),
                )
            )

        phase = str(data.get("phase") or "planned")
        return cls(
            run_id=str(data.get("run_id") or ""),
            question=question,
            plan=plan,
            sources=tuple(sources),
            attempts=tuple(attempts),
            citations=tuple(citations),
            reads=tuple(reads),
            usage=tuple(usage),
            rounds_done=int(data.get("rounds_done") or 0),
            phase=phase if phase in PHASES else "planned",
            depth=(int(data["depth"]) if data.get("depth") is not None else 1),
            max_sources=(int(data["max_sources"]) if data.get("max_sources") is not None else 12),
            academic=(bool(data["academic"]) if data.get("academic") is not None else True),
            media=(bool(data["media"]) if data.get("media") is not None else False),
            updated_at=str(data.get("updated_at") or utc_now()),
        )


CheckpointCallback = Callable[[DeepCheckpoint], None]


def checkpoint_path(runs_dir: Path, run_id: str) -> Path | None:
    if not SAFE_ID.fullmatch(run_id):
        return None
    return runs_dir / f"{run_id}.state.json"


def save_checkpoint(runs_dir: Path, state: DeepCheckpoint) -> Path:
    path = checkpoint_path(runs_dir, state.run_id)
    if path is None:
        raise ValueError(f"invalid run id: {state.run_id}")
    runs_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def load_checkpoint(runs_dir: Path, run_id: str) -> DeepCheckpoint | None:
    path = checkpoint_path(runs_dir, run_id)
    if path is None or not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        return DeepCheckpoint.from_dict(data)
    except (TypeError, ValueError):
        return None


def delete_checkpoint(runs_dir: Path, run_id: str) -> None:
    path = checkpoint_path(runs_dir, run_id)
    if path is not None:
        path.unlink(missing_ok=True)


def resumable_runs(runs_dir: Path) -> list[dict[str, object]]:
    if not runs_dir.exists():
        return []
    summaries: list[dict[str, object]] = []
    for path in runs_dir.glob("*.state.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        phase = str(data.get("phase") or "planned")
        if phase not in PHASES:
            continue
        summaries.append(
            {
                "run_id": data.get("run_id"),
                "question": data.get("question"),
                "phase": phase,
                "updated_at": data.get("updated_at"),
                "sources": len(data.get("sources") or []),
                "citations": len(data.get("citations") or []),
                "rounds_done": data.get("rounds_done") or 0,
                "depth": (data.get("depth") if data.get("depth") is not None else 1),
            }
        )
    summaries.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return summaries


__all__ = [
    "CheckpointCallback",
    "DeepCheckpoint",
    "checkpoint_path",
    "delete_checkpoint",
    "load_checkpoint",
    "resumable_runs",
    "save_checkpoint",
]
