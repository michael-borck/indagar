from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProgressEvent:
    type: str
    message: str
    data: dict[str, object] = field(default_factory=dict)


ProgressCallback = Callable[[ProgressEvent], None]


def emit_progress(
    callback: ProgressCallback | None,
    event_type: str,
    message: str,
    **data: object,
) -> None:
    if callback is not None:
        callback(ProgressEvent(event_type, message, data))


__all__ = ["ProgressCallback", "ProgressEvent", "emit_progress"]
