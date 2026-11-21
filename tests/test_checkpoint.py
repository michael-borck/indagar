from __future__ import annotations

from pathlib import Path

from indagar.models import (
    Citation,
    ModelUsage,
    ReadAttempt,
    ResearchPlan,
    SearchAttempt,
    Source,
    SubQuestion,
)
from indagar.research.checkpoint import (
    DeepCheckpoint,
    delete_checkpoint,
    load_checkpoint,
    resumable_runs,
    save_checkpoint,
)


def _state() -> DeepCheckpoint:
    return DeepCheckpoint(
        run_id="20260101T000000Z-test",
        question="What is X?",
        plan=ResearchPlan(
            "What is X?",
            (SubQuestion("What is X?", "Define it."),),
            planner="fake",
        ),
        sources=(
            Source(
                title="Example",
                url="https://example.com",
                provider="fake",
                source_type="web",
                sub_question="What is X?",
                confidence="low",
                published="2024",
                authors="Ada Lovelace",
            ),
        ),
        attempts=(SearchAttempt("fake", "ok", 1, 2),),
        citations=(
            Citation(
                id="C1",
                source_url="https://example.com",
                title="Example",
                quote="A grounded claim.",
            ),
        ),
        reads=(ReadAttempt("https://example.com", "ok", 120, 1, 4),),
        usage=(ModelUsage("fake", "fake-model", 2, 10, 5),),
        rounds_done=1,
        phase="gaps",
        depth=0,
        max_sources=3,
    )


def test_checkpoint_round_trip():
    state = _state()

    restored = DeepCheckpoint.from_dict(state.to_dict())

    assert restored.run_id == state.run_id
    assert restored.question == state.question
    assert restored.plan.planner == "fake"
    assert restored.sources[0].confidence == "low"
    assert restored.sources[0].published == "2024"
    assert restored.sources[0].authors == "Ada Lovelace"
    assert restored.citations[0].quote == "A grounded claim."
    assert restored.usage[0].calls == 2
    assert restored.phase == "gaps"
    assert restored.depth == 0


def test_save_load_list_and_delete_checkpoint(tmp_path: Path):
    state = _state()

    path = save_checkpoint(tmp_path, state)
    loaded = load_checkpoint(tmp_path, state.run_id)
    resumable = resumable_runs(tmp_path)

    assert path.exists()
    assert loaded is not None
    assert loaded.run_id == state.run_id
    assert resumable[0]["run_id"] == state.run_id
    assert resumable[0]["phase"] == "gaps"

    delete_checkpoint(tmp_path, state.run_id)
    assert not path.exists()
    assert load_checkpoint(tmp_path, state.run_id) is None


def test_invalid_checkpoint_is_ignored(tmp_path: Path):
    (tmp_path / "bad.state.json").write_text("{not json", encoding="utf-8")

    assert resumable_runs(tmp_path) == []
