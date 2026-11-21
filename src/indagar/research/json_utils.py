from __future__ import annotations

import json


def parse_json_object(text: str) -> dict[str, object]:
    """Parse the first JSON object in a model response, tolerating fences."""
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("response did not contain a JSON object")
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON response: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("JSON response must be an object")
    return data


__all__ = ["parse_json_object"]
