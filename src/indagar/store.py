from __future__ import annotations

import json
from pathlib import Path

from .models import Run


def save_run(
    run: Run,
    out: Path | None = None,
    runs_dir: Path = Path("runs"),
) -> tuple[Path, Path]:
    """Write the run record and Markdown dossier. Returns (json, markdown)."""
    runs_dir.mkdir(parents=True, exist_ok=True)
    json_path = runs_dir / f"{run.id}.json"
    markdown_path = out or runs_dir / f"{run.id}.md"
    markdown_path.parent.mkdir(parents=True, exist_ok=True)

    json_path.write_text(
        json.dumps(run.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(run.report, encoding="utf-8")
    return json_path, markdown_path


__all__ = ["save_run"]
