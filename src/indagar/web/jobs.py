from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from pathlib import Path
from uuid import uuid4

from ..config import Settings
from ..exports import export_file
from ..llm.factory import build_llms
from ..models import Run, utc_now
from ..progress import ProgressCallback, ProgressEvent
from ..research.checkpoint import (
    CheckpointCallback,
    DeepCheckpoint,
    delete_checkpoint,
    load_checkpoint,
    save_checkpoint,
)
from ..research.checkpoint import (
    resumable_runs as scan_checkpoints,
)
from ..research.deep import run_deep_research
from ..research.loop import run_research
from ..store import save_run

SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,160}$")


@dataclass(frozen=True)
class ResearchRequest:
    question: str
    llm: bool = False
    depth: int | None = None
    max_sources: int | None = None
    academic: bool | None = None
    resume: DeepCheckpoint | None = None
    checkpoint: CheckpointCallback | None = None


Runner = Callable[[Settings, ResearchRequest, ProgressCallback], Awaitable[Run]]


async def default_runner(
    settings: Settings,
    request: ResearchRequest,
    progress: ProgressCallback,
) -> Run:
    if request.llm:
        llms = build_llms(settings)
        return await run_deep_research(
            request.question,
            settings,
            llms=llms,
            depth=request.depth,
            progress=progress,
            resume=request.resume,
            use_academic=request.academic,
            checkpoint=request.checkpoint,
        )
    return await run_research(request.question, settings, progress=progress)


@dataclass
class Job:
    id: str
    request: ResearchRequest
    status: str = "queued"
    created_at: str = field(default_factory=utc_now)
    finished_at: str | None = None
    run: Run | None = None
    error: str | None = None
    events: list[dict[str, object]] = field(default_factory=list)
    task: asyncio.Task | None = None
    _subscribers: set[asyncio.Queue] = field(default_factory=set)
    _finished: asyncio.Event = field(default_factory=asyncio.Event)

    @property
    def run_id(self) -> str | None:
        return self.run.id if self.run is not None else None

    @property
    def finished(self) -> bool:
        return self._finished.is_set()

    def emit(
        self,
        event_type: str,
        message: str,
        data: dict[str, object] | None = None,
    ) -> None:
        event: dict[str, object] = {
            "type": event_type,
            "message": message,
            "data": data or {},
            "at": utc_now(),
        }
        self.events.append(event)
        for queue in list(self._subscribers):
            queue.put_nowait(event)

    def emit_progress(self, event: ProgressEvent) -> None:
        self.emit(event.type, event.message, event.data)

    def finish(self) -> None:
        if self._finished.is_set():
            return
        self._finished.set()
        for queue in list(self._subscribers):
            queue.put_nowait(None)

    def subscribe(self) -> tuple[list[dict[str, object]], asyncio.Queue]:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.add(queue)
        if self._finished.is_set():
            queue.put_nowait(None)
        return list(self.events), queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self._subscribers.discard(queue)

    def to_dict(self) -> dict[str, object]:
        return {
            "job_id": self.id,
            "status": self.status,
            "question": self.request.question,
            "llm": self.request.llm,
            "depth": self.request.depth,
            "max_sources": self.request.max_sources,
            "academic": self.request.academic,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "run_id": self.run_id,
            "error": self.error,
            "event_count": len(self.events),
        }


class JobManager:
    def __init__(
        self,
        settings: Settings,
        *,
        runs_dir: Path = Path("runs"),
        runner: Runner | None = None,
    ):
        self.settings = settings
        self.runs_dir = runs_dir
        self.runner = runner or default_runner
        self.jobs: dict[str, Job] = {}

    def start(self, request: ResearchRequest) -> Job:
        self._validate(request)
        request = replace(
            request,
            checkpoint=lambda state: save_checkpoint(self.runs_dir, state),
        )
        job = Job(id=f"job-{uuid4().hex[:12]}", request=request)
        settings = self.settings
        if request.max_sources is not None:
            settings = replace(settings, max_sources=request.max_sources)
        self.jobs[job.id] = job
        job.task = asyncio.create_task(self._execute(job, settings, request))
        return job

    def _validate(self, request: ResearchRequest) -> None:
        if not request.question.strip():
            raise ValueError("question is required")
        has_search = bool(self.settings.configured_search_providers())
        has_academic = bool(self.settings.configured_academic_providers())
        if not has_search and not (request.llm and has_academic):
            raise RuntimeError(
                "No search provider configured. Set FIRECRAWL_URL, BRAVE_API_KEY, "
                "SERPER_API_KEY, SEARXNG_URL, or enable academic search."
            )
        if request.llm:
            build_llms(self.settings)

    async def _execute(
        self,
        job: Job,
        settings: Settings,
        request: ResearchRequest,
    ) -> None:
        job.status = "running"
        job.emit("status", "Run started", {"status": "running"})
        try:
            run = await self.runner(settings, request, job.emit_progress)
            job.run = run
            save_run(run, runs_dir=self.runs_dir)
            delete_checkpoint(self.runs_dir, run.id)
            job.status = "completed"
            job.emit(
                "completed",
                "Run complete",
                {
                    "run_id": run.id,
                    "sources": len(run.sources),
                    "citations": len(run.citations),
                    "reads": len(run.reads),
                },
            )
        except asyncio.CancelledError:
            job.status = "cancelled"
            job.emit("cancelled", "Run cancelled", {"status": "cancelled"})
            raise
        except Exception as exc:
            job.status = "failed"
            job.error = " ".join(str(exc).split())[:500]
            job.emit("error", job.error, {"status": "failed"})
        finally:
            job.finished_at = utc_now()
            job.finish()

    def resume(self, run_id: str) -> Job | None:
        state = load_checkpoint(self.runs_dir, run_id)
        if state is None:
            return None
        return self.start(
            ResearchRequest(
                question=state.question,
                llm=True,
                depth=state.depth,
                max_sources=state.max_sources,
                academic=state.academic,
                resume=state,
            )
        )

    def resumable_runs(self) -> list[dict[str, object]]:
        return scan_checkpoints(self.runs_dir)

    def cancel(self, job_id: str) -> Job | None:
        job = self.jobs.get(job_id)
        if job is None:
            return None
        if job.task is not None and not job.task.done():
            job.status = "cancelling"
            job.task.cancel()
        return job

    def active_jobs(self) -> list[Job]:
        return [
            job for job in self.jobs.values() if job.status in {"queued", "running", "cancelling"}
        ]

    def load_run(self, run_id: str) -> dict[str, object] | None:
        path = self._path(run_id, "json")
        if path is None:
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    def export_path(self, run_id: str, suffix: str) -> Path | None:
        path = self._path(run_id, suffix)
        return path if path is not None and path.exists() else None

    def ensure_export(self, run_id: str, kind: str) -> Path | None:
        if not SAFE_ID.fullmatch(run_id):
            return None
        markdown = self.runs_dir / f"{run_id}.md"
        if not markdown.exists():
            return None
        return export_file(markdown, kind)

    def saved_runs(self) -> list[dict[str, object]]:
        if not self.runs_dir.exists():
            return []
        summaries: list[dict[str, object]] = []
        for path in self.runs_dir.glob("*.json"):
            if path.name.endswith(".state.json"):
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(data, dict):
                continue
            citations = data.get("citations") or []
            usage = data.get("usage") or []
            summaries.append(
                {
                    "run_id": data.get("id"),
                    "question": data.get("question"),
                    "created_at": data.get("created_at"),
                    "planner": (data.get("plan") or {}).get("planner"),
                    "sources": len(data.get("sources") or []),
                    "citations": len(citations) if isinstance(citations, list) else 0,
                    "reads": len(data.get("reads") or []),
                    "calls": sum(
                        int(item.get("calls") or 0) for item in usage if isinstance(item, dict)
                    ),
                }
            )
        summaries.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return summaries

    def _path(self, run_id: str, suffix: str) -> Path | None:
        if not SAFE_ID.fullmatch(run_id):
            return None
        path = self.runs_dir / f"{run_id}.{suffix}"
        if not path.exists():
            return None
        return path


__all__ = ["Job", "JobManager", "ResearchRequest", "Runner", "default_runner"]
