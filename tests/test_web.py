from __future__ import annotations

import asyncio
import time
from pathlib import Path

from fastapi.testclient import TestClient

from indagar.config import Settings
from indagar.models import (
    Citation,
    ModelUsage,
    ReadAttempt,
    ResearchPlan,
    Run,
    SearchAttempt,
    Source,
    SubQuestion,
)
from indagar.progress import ProgressEvent
from indagar.research.checkpoint import (
    DeepCheckpoint,
    load_checkpoint,
    save_checkpoint,
)
from indagar.web.app import create_app
from indagar.web.jobs import JobManager, ResearchRequest


def _run(request: ResearchRequest) -> Run:
    source = Source(
        title="Example",
        url="https://example.com/page",
        provider="fake",
        sub_question=request.question,
    )
    return Run(
        id="test-run",
        question=request.question,
        plan=ResearchPlan(
            request.question,
            (SubQuestion(request.question, "Answer directly."),),
            planner="fake",
        ),
        sources=(source,),
        attempts=(SearchAttempt("fake", "ok", 1, 2),),
        report="# Research report\n\nExample claim [C1].\n\n## Citations\n\n| C1 |",
        citations=(
            Citation(
                id="C1",
                source_url=source.url,
                title=source.title,
                quote="A grounded claim.",
            ),
        ),
        reads=(ReadAttempt(source.url, "ok", 120, 1, 4),),
        usage=(ModelUsage("fake", "fake-model", 2, 10, 5),),
    )


async def fake_runner(settings, request, progress) -> Run:
    progress(ProgressEvent("plan", "Planned 1 sub-question", {"planner": "fake"}))
    await asyncio.sleep(0)
    run = _run(request)
    progress(ProgressEvent("done", "Research complete", {"citations": 1}))
    return run


async def slow_runner(settings, request, progress) -> Run:
    progress(ProgressEvent("status", "Slow run", {}))
    await asyncio.sleep(0.2)
    return _run(request)


async def resume_runner(settings, request, progress) -> Run:
    progress(ProgressEvent("resume", "Resumed checkpoint", {}))
    run = _run(request)
    if request.resume is not None:
        run.id = request.resume.run_id
    return run


def _client(tmp_path: Path, runner=fake_runner) -> tuple[TestClient, JobManager]:
    settings = Settings(firecrawl_url="http://localhost:3002")
    manager = JobManager(
        settings,
        runs_dir=tmp_path / "runs",
        runner=runner,
    )
    return TestClient(create_app(settings, manager)), manager


def _wait(client: TestClient, job_id: str, timeout: float = 3.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data = client.get(f"/api/runs/{job_id}").json()
        if data.get("status") in {"completed", "failed", "cancelled"}:
            return data
        time.sleep(0.01)
    raise AssertionError(f"job {job_id} did not finish")


def test_index_status_and_static_assets(tmp_path):
    client, _ = _client(tmp_path)

    index = client.get("/")
    status = client.get("/api/status")
    script = client.get("/static/app.js")

    assert index.status_code == 200
    assert "Indagar" in index.text
    assert status.status_code == 200
    assert status.json()["search_providers"] == ["firecrawl"]
    assert script.status_code == 200
    assert "EventSource" in script.text


def test_estimate_endpoint(tmp_path):
    client, _ = _client(tmp_path)

    response = client.get(
        "/api/estimate",
        params={
            "question": "What is X?",
            "llm": "true",
            "depth": 0,
            "max_sources": 3,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["sources"] == 3
    assert "Estimate:" in data["line"]


def test_run_lifecycle_exports_and_sse(tmp_path):
    client, manager = _client(tmp_path)

    created = client.post(
        "/api/runs",
        json={"question": "What is X?", "llm": False, "max_sources": 2},
    )
    assert created.status_code == 202
    job_id = created.json()["job_id"]

    finished = _wait(client, job_id)
    assert finished["status"] == "completed"
    assert finished["run_id"] == "test-run"
    assert len(manager.jobs[job_id].events) >= 4

    run = client.get("/api/runs/test-run")
    assert run.status_code == 200
    assert run.json()["kind"] == "run"
    assert run.json()["run"]["question"] == "What is X?"

    markdown = client.get("/api/runs/test-run/export.md")
    assert markdown.status_code == 200
    assert "Research report" in markdown.text

    payload = client.get("/api/runs/test-run/export.json")
    assert payload.status_code == 200
    assert payload.json()["id"] == "test-run"

    docx = client.get("/api/runs/test-run/export.docx")
    assert docx.status_code == 200
    assert docx.content.startswith(b"PK")

    pdf = client.get("/api/runs/test-run/export.pdf")
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")

    listing = client.get("/api/runs").json()
    assert any(item["run_id"] == "test-run" for item in listing["saved"])

    events = client.get(f"/api/runs/{job_id}/events")
    assert events.status_code == 200
    assert events.headers["content-type"].startswith("text/event-stream")
    assert '"type": "completed"' in events.text


def test_run_requires_a_search_provider(tmp_path):
    settings = Settings()
    manager = JobManager(settings, runs_dir=tmp_path / "runs", runner=fake_runner)
    client = TestClient(create_app(settings, manager))

    response = client.post(
        "/api/runs",
        json={"question": "What is X?", "llm": False},
    )

    assert response.status_code == 400
    assert "No search provider" in response.json()["detail"]


def test_run_with_llm_requires_llm_configuration(tmp_path):
    client, _ = _client(tmp_path)

    response = client.post(
        "/api/runs",
        json={"question": "What is X?", "llm": True},
    )

    assert response.status_code == 400
    assert "No LLM provider" in response.json()["detail"]


def test_cancel_job(tmp_path):
    client, _ = _client(tmp_path, runner=slow_runner)

    created = client.post(
        "/api/runs",
        json={"question": "What is X?", "llm": False},
    )
    job_id = created.json()["job_id"]

    cancelled = client.post(f"/api/runs/{job_id}/cancel")
    assert cancelled.status_code == 200

    finished = _wait(client, job_id)
    assert finished["status"] == "cancelled"


def test_resume_endpoint_continues_a_checkpoint(tmp_path):
    settings = Settings(
        firecrawl_url="http://localhost:3002",
        anthropic_api_key="key",
        llm_provider="anthropic",
        llm_model="model",
    )
    runs_dir = tmp_path / "runs"
    manager = JobManager(settings, runs_dir=runs_dir, runner=resume_runner)
    client = TestClient(create_app(settings, manager))
    source = Source(
        title="Example",
        url="https://example.com/page",
        provider="fake",
        sub_question="What is X?",
    )
    state = DeepCheckpoint(
        run_id="resume-run",
        question="What is X?",
        plan=ResearchPlan(
            "What is X?",
            (SubQuestion("What is X?", "Answer directly."),),
            planner="fake",
        ),
        sources=(source,),
        citations=(
            Citation(
                id="C1",
                source_url=source.url,
                title=source.title,
                quote="A grounded claim.",
            ),
        ),
        phase="gathered",
        depth=0,
        max_sources=1,
    )
    save_checkpoint(runs_dir, state)

    listing = client.get("/api/runs").json()
    assert any(item["run_id"] == "resume-run" for item in listing["resumable"])

    response = client.post("/api/runs/resume-run/resume")
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    finished = _wait(client, job_id)
    assert finished["status"] == "completed"
    assert finished["run_id"] == "resume-run"
    assert load_checkpoint(runs_dir, "resume-run") is None
    assert client.get("/api/runs").json()["resumable"] == []


def test_unknown_run_is_404(tmp_path):
    client, _ = _client(tmp_path)

    assert client.get("/api/runs/missing").status_code == 404
    assert client.get("/api/runs/missing/export.md").status_code == 404
    assert client.get("/api/runs/missing/export.docx").status_code == 404
    assert client.get("/api/runs/missing/export.pdf").status_code == 404
