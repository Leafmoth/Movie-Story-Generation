from __future__ import annotations

import json
import re
from json import JSONDecoder
from typing import Any, Literal


ExpectedJsonType = Literal["dict", "list"]


def parse_json_result(text: str, *, expected_type: ExpectedJsonType | None = None) -> Any:
    """Extract the first valid JSON value, tolerating Markdown fences and prose."""
    stripped = text.strip()
    if not stripped:
        return None

    candidates = [stripped]
    candidates.extend(match.group(1).strip() for match in re.finditer(r"```(?:json)?\s*(.*?)```", stripped, re.S | re.I))

    decoder = JSONDecoder()
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            parsed = None
        if _matches_expected(parsed, expected_type):
            return parsed

        for index, char in enumerate(candidate):
            if char not in "[{":
                continue
            try:
                parsed, _ = decoder.raw_decode(candidate[index:])
            except json.JSONDecodeError:
                continue
            if _matches_expected(parsed, expected_type):
                return parsed

    return None


def _matches_expected(value: Any, expected_type: ExpectedJsonType | None) -> bool:
    if expected_type == "dict":
        return isinstance(value, dict)
    if expected_type == "list":
        return isinstance(value, list)
    return value is not None
