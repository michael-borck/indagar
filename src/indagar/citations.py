from __future__ import annotations

from collections.abc import Iterable, Iterator

from .models import Citation, Source


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def _link_title(value: str) -> str:
    return _cell(value).replace("[", "\\[").replace("]", "\\]")


def _truncate(value: str, limit: int = 280) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def render_citations(citations: Iterable[Citation]) -> str:
    items = list(citations)
    if not items:
        return "_No citations yet._"

    lines = [
        "| ID | Source | Sub-question | Locator | Quote |",
        "|---|---|---|---|---|",
    ]
    for citation in items:
        title = _link_title(citation.title) or citation.source_url
        source = f"[{title}]({citation.source_url})"
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(citation.id),
                    source,
                    _cell(citation.sub_question or ""),
                    _cell(citation.locator or ""),
                    _cell(_truncate(citation.quote)),
                ]
            )
            + " |"
        )
    return "\n".join(lines)


class CitationLedger:
    """Ordered, deduplicated evidence with stable citation IDs."""

    def __init__(self, citations: Iterable[Citation] = ()):
        self._citations: list[Citation] = []
        self._by_key: dict[tuple[str, str, str], Citation] = {}
        for citation in citations:
            key = (citation.source_url, citation.quote, citation.locator or "")
            if key in self._by_key:
                continue
            self._append(citation)

    def __len__(self) -> int:
        return len(self._citations)

    def __iter__(self) -> Iterator[Citation]:
        return iter(self._citations)

    @property
    def citations(self) -> tuple[Citation, ...]:
        return tuple(self._citations)

    def add(
        self,
        source: Source,
        quote: str,
        *,
        locator: str | None = None,
        note: str = "",
    ) -> Citation:
        normalized = " ".join(quote.split())
        if not normalized:
            raise ValueError("citation quote is required")
        key = (source.url, normalized, locator or "")
        existing = self._by_key.get(key)
        if existing is not None:
            return existing

        citation = Citation(
            id=self._next_id(),
            source_url=source.url,
            title=source.title,
            quote=normalized,
            locator=locator,
            sub_question=source.sub_question,
            note=note,
            source_type=source.source_type,
        )
        self._append(citation)
        return citation

    def _next_id(self) -> str:
        used = {citation.id for citation in self._citations}
        index = len(self._citations) + 1
        while f"C{index}" in used:
            index += 1
        return f"C{index}"

    def _append(self, citation: Citation) -> None:
        if any(existing.id == citation.id for existing in self._citations):
            raise ValueError(f"duplicate citation id: {citation.id}")
        key = (citation.source_url, citation.quote, citation.locator or "")
        self._citations.append(citation)
        self._by_key[key] = citation

    def by_source(self) -> dict[str, list[Citation]]:
        grouped: dict[str, list[Citation]] = {}
        for citation in self._citations:
            grouped.setdefault(citation.source_url, []).append(citation)
        return grouped

    def render_markdown(self) -> str:
        return render_citations(self._citations)

    def to_dicts(self) -> list[dict[str, object]]:
        return [citation.to_dict() for citation in self._citations]


__all__ = ["CitationLedger", "render_citations"]
