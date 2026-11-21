from __future__ import annotations

from typing import Protocol

from ..models import Source


class SearchError(Exception):
    """A provider failed. The chain records it and moves on."""

    def __init__(self, provider: str, message: str, status: int | None = None):
        super().__init__(message)
        self.provider = provider
        self.status = status


class SearchProvider(Protocol):
    name: str

    async def search(self, query: str, limit: int) -> list[Source]:
        """Return up to limit results. Raise SearchError on failure."""
        ...
