from __future__ import annotations

import pytest

from indagar.citations import CitationLedger, render_citations
from indagar.models import Citation, Source


def _source(url: str = "https://example.com/a", title: str = "Example") -> Source:
    return Source(title=title, url=url, provider="test")


def test_ledger_assigns_ids_and_dedupes():
    ledger = CitationLedger()

    first = ledger.add(_source(), "  A   claim. ")
    duplicate = ledger.add(_source(), "A claim.")
    second_source = ledger.add(_source("https://example.com/b"), "A claim.")

    assert first.id == "C1"
    assert duplicate is first
    assert second_source.id == "C2"
    assert len(ledger) == 2
    assert first.quote == "A claim."


def test_ledger_rejects_empty_quote():
    with pytest.raises(ValueError, match="quote"):
        CitationLedger().add(_source(), "   ")


def test_ledger_rejects_duplicate_ids():
    citation = Citation(
        id="C1",
        source_url="https://example.com/a",
        title="Example",
        quote="A claim.",
    )
    collision = Citation(
        id="C1",
        source_url="https://example.com/b",
        title="Other",
        quote="Another claim.",
    )

    with pytest.raises(ValueError, match="duplicate citation id"):
        CitationLedger([citation, collision])


def test_ledger_constructor_dedupes_same_evidence():
    citation = Citation(
        id="C1",
        source_url="https://example.com/a",
        title="Example",
        quote="A claim.",
    )

    assert len(CitationLedger([citation, citation])) == 1


def test_ledger_avoids_existing_ids():
    citation = Citation(
        id="C2",
        source_url="https://example.com/a",
        title="Example",
        quote="A claim.",
    )
    ledger = CitationLedger([citation])

    added = ledger.add(_source("https://example.com/b"), "Another claim.")

    assert added.id == "C3"


def test_render_citations_quotes_and_links():
    ledger = CitationLedger()
    ledger.add(_source(), "Light reactions produce ATP.", locator="p. 2")

    markdown = ledger.render_markdown()

    assert "| C1 |" in markdown
    assert "[Example](https://example.com/a)" in markdown
    assert "Light reactions produce ATP." in markdown
    assert "p. 2" in markdown


def test_render_citations_escapes_table_cells():
    ledger = CitationLedger()
    ledger.add(_source(), "A | B")

    assert "A \\| B" in ledger.render_markdown()
    assert render_citations(()) == "_No citations yet._"


def test_citation_requires_fields_and_normalizes_text():
    with pytest.raises(ValueError):
        Citation(id="", source_url="https://example.com", title="T", quote="Q")
    with pytest.raises(ValueError):
        Citation(id="C1", source_url="", title="T", quote="Q")
    with pytest.raises(ValueError):
        Citation(id="C1", source_url="https://example.com", title="T", quote=" ")

    citation = Citation(
        id="C1",
        source_url="https://example.com",
        title="  A   title ",
        quote=" A   claim. ",
    )
    assert citation.title == "A title"
    assert citation.quote == "A claim."


def test_ledger_groups_and_serializes():
    ledger = CitationLedger()
    citation = ledger.add(_source(), "A claim.", note="n")

    assert ledger.to_dicts() == [citation.to_dict()]
    assert citation.to_dict()["note"] == "n"
    assert list(ledger.by_source()) == ["https://example.com/a"]
