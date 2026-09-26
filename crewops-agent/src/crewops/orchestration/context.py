"""Resolve human-written references against results from the same run."""

import re
from typing import Any


_REFERENCE = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)(.*)\}$")
_PATH_PART = re.compile(r"\.([A-Za-z_][A-Za-z0-9_]*)|\[(\d+|\*)\]")


def resolve_path_parts(value: Any, parts: list[tuple[str, str]], reference: str) -> Any:
    if not parts:
        return value
    key, index = parts[0]
    rest = parts[1:]
    if key:
        return resolve_path_parts(value[key], rest, reference)
    if index == "*":
        if not isinstance(value, list):
            raise ValueError(f"Wildcard reference requires a list: {reference}")
        return [resolve_path_parts(item, rest, reference) for item in value]
    return resolve_path_parts(value[int(index)], rest, reference)


def resolve_value(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: resolve_value(item, context) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve_value(item, context) for item in value]
    if not isinstance(value, str):
        return value

    match = _REFERENCE.fullmatch(value)
    if not match:
        return value

    resolved: Any = context[match.group(1)]
    suffix = match.group(2)
    consumed = 0
    parts: list[tuple[str, str]] = []
    for part in _PATH_PART.finditer(suffix):
        if part.start() != consumed:
            raise ValueError(f"Invalid runbook output reference: {value}")
        consumed = part.end()
        parts.append((part.group(1) or "", part.group(2) or ""))
    if consumed != len(suffix):
        raise ValueError(f"Invalid runbook output reference: {value}")
    return resolve_path_parts(resolved, parts, value)


def condition_is_true(condition: str, context: dict[str, Any]) -> bool:
    try:
        return bool(resolve_value(condition, context))
    except (KeyError, IndexError, TypeError, ValueError):
        return False


def issues_text(result: Any) -> str:
    if not isinstance(result, dict):
        return "tool returned an invalid result"
    issues = result.get("issues")
    if isinstance(issues, list):
        return "; ".join(map(str, issues)) or "tool returned an unsuccessful result"
    return str(issues) if issues else "tool returned an unsuccessful result"
