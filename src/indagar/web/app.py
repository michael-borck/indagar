from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .. import __version__
from ..config import Settings
from ..estimate import estimate_run
from ..exports import ExportError
from ..llm.base import LLM_ROLES, LLMError
from .jobs import Job, JobManager, ResearchRequest

STATIC_DIR = Path(__file__).with_name("static")


class RunBody(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    llm: bool = False
    depth: int | None = Field(default=None, ge=0, le=2)
    max_sources: int | None = Field(default=None, ge=1, le=50)
    academic: bool | None = None


def _status(settings: Settings) -> dict[str, object]:
    return {
        "version": __version__,
        "search_order": list(settings.search_order),
        "search_providers": list(settings.configured_search_providers()),
        "academic_enabled": settings.academic_enabled,
        "academic_providers": list(settings.configured_academic_providers()),
        "llm_providers": list(settings.llm_providers()),
        "llm_provider": settings.selected_llm_provider(),
        "llm_models": {role: settings.llm_model_for(role) for role in LLM_ROLES},
        "budgets": {
            "max_sources": settings.max_sources,
            "max_seconds": settings.max_seconds,
            "search_limit": settings.search_limit,
            "max_depth": settings.max_depth,
            "max_claims": settings.max_claims,
            "synthesis_max_tokens": settings.synthesis_max_tokens,
        },
        "cost_rates": {
            "input_per_mtok": settings.input_cost_per_mtok,
            "output_per_mtok": settings.output_cost_per_mtok,
        },
    }


def _sse(event: dict[str, object]) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


async def _event_stream(job: Job):
    backlog, queue = job.subscribe()
    try:
        yield "retry: 3000\n\n"
        for event in backlog:
            yield _sse(event)
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=15)
            except TimeoutError:
                yield ": keep-alive\n\n"
                continue
            if event is None:
                break
            yield _sse(event)
    finally:
        job.unsubscribe(queue)


def create_app(
    settings: Settings | None = None,
    manager: JobManager | None = None,
) -> FastAPI:
    manager = manager or JobManager(settings or Settings.from_env())
    app = FastAPI(title="Indagar", version=__version__)
    app.state.manager = manager
    app.state.settings = manager.settings

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/api/status")
    def status() -> dict[str, object]:
        return _status(manager.settings)

    @app.get("/api/estimate")
    def estimate(
        question: str,
        llm: bool = True,
        depth: int | None = Query(None, ge=0, le=2),
        max_sources: int | None = Query(None, ge=1, le=50),
    ) -> dict[str, object]:
        try:
            result = estimate_run(
                question,
                manager.settings,
                max_sources=max_sources,
                depth=depth,
                llm=llm,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {**result.to_dict(), "line": result.line()}

    @app.get("/api/runs")
    def list_runs() -> dict[str, object]:
        return {
            "active": [job.to_dict() for job in manager.active_jobs()],
            "resumable": manager.resumable_runs(),
            "saved": manager.saved_runs(),
        }

    @app.post("/api/runs", status_code=202)
    async def create_run(body: RunBody) -> dict[str, object]:
        request = ResearchRequest(
            question=" ".join(body.question.split()),
            llm=body.llm,
            depth=body.depth,
            max_sources=body.max_sources,
            academic=body.academic,
        )
        try:
            job = manager.start(request)
        except (LLMError, RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return job.to_dict()

    @app.get("/api/runs/{job_id}/events")
    async def events(job_id: str) -> StreamingResponse:
        job = manager.jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return StreamingResponse(
            _event_stream(job),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @app.post("/api/runs/{job_id}/cancel")
    def cancel(job_id: str) -> dict[str, object]:
        job = manager.cancel(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return job.to_dict()

    @app.get("/api/runs/{run_id}/export.md")
    def export_markdown(run_id: str) -> FileResponse:
        path = manager.export_path(run_id, "md")
        if path is None:
            raise HTTPException(status_code=404, detail="Markdown not found")
        return FileResponse(
            path,
            media_type="text/markdown",
            filename=f"{run_id}.md",
        )

    @app.get("/api/runs/{run_id}/export.json")
    def export_json(run_id: str) -> FileResponse:
        path = manager.export_path(run_id, "json")
        if path is None:
            raise HTTPException(status_code=404, detail="JSON not found")
        return FileResponse(
            path,
            media_type="application/json",
            filename=f"{run_id}.json",
        )

    @app.get("/api/runs/{run_id}/export.docx")
    def export_docx(run_id: str) -> FileResponse:
        try:
            path = manager.ensure_export(run_id, "docx")
        except ExportError as exc:
            raise HTTPException(status_code=501, detail=str(exc)) from exc
        if path is None:
            raise HTTPException(status_code=404, detail="DOCX not found")
        return FileResponse(
            path,
            media_type=("application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            filename=f"{run_id}.docx",
        )

    @app.get("/api/runs/{run_id}/export.pdf")
    def export_pdf(run_id: str) -> FileResponse:
        try:
            path = manager.ensure_export(run_id, "pdf")
        except ExportError as exc:
            raise HTTPException(status_code=501, detail=str(exc)) from exc
        if path is None:
            raise HTTPException(status_code=404, detail="PDF not found")
        return FileResponse(
            path,
            media_type="application/pdf",
            filename=f"{run_id}.pdf",
        )

    @app.post("/api/runs/{run_id}/resume", status_code=202)
    async def resume_run(run_id: str) -> dict[str, object]:
        try:
            job = manager.resume(run_id)
        except (LLMError, RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if job is None:
            raise HTTPException(status_code=404, detail="Checkpoint not found")
        return job.to_dict()

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, object]:
        job = manager.jobs.get(run_id)
        if job is not None:
            return {"kind": "job", **job.to_dict()}
        run = manager.load_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return {"kind": "run", "status": "completed", "run": run}

    return app


__all__ = ["create_app"]
