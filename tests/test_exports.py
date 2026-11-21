from __future__ import annotations

import zipfile
from pathlib import Path

from indagar.exports import export_file, parse_markdown, write_docx, write_pdf

MARKDOWN = """# Research report: What is X?

Generated: now

> A short note.

This is a **claim** with a [source](https://example.com).

## Sources

- Example — https://example.com

## Citations

| ID | Source | Type | Confidence | Quote |
|---|---|---|---|---|
| C1 | Example | web | low | A grounded claim. |
"""


def test_parse_markdown_blocks():
    blocks = parse_markdown(MARKDOWN)

    assert blocks[0].kind == "heading"
    assert blocks[0].level == 1
    assert any(block.kind == "quote" for block in blocks)
    table = next(block for block in blocks if block.kind == "table")
    assert table.rows[0][0] == "ID"
    assert table.rows[1][0] == "C1"


def test_docx_export(tmp_path: Path):
    path = write_docx(MARKDOWN, tmp_path / "report.docx")

    assert path.exists()
    assert zipfile.is_zipfile(path)


def test_pdf_export(tmp_path: Path):
    path = write_pdf(MARKDOWN, tmp_path / "report.pdf")

    assert path.exists()
    assert path.read_bytes().startswith(b"%PDF")


def test_export_file_caches_output(tmp_path: Path):
    markdown = tmp_path / "report.md"
    markdown.write_text(MARKDOWN, encoding="utf-8")

    first = export_file(markdown, "pdf")
    second = export_file(markdown, "pdf")

    assert first == second
    assert first.exists()
