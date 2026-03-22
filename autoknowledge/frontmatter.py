"""Minimal YAML-frontmatter parsing with no third-party dependencies."""

from __future__ import annotations

from typing import Any


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str, list[str]]:
    issues: list[str] = []
    if not text.startswith("---\n"):
        return {}, text, ["missing_frontmatter"]

    lines = text.splitlines()
    try:
        end_idx = lines[1:].index("---") + 1
    except ValueError:
        return {}, text, ["unterminated_frontmatter"]

    metadata_lines = lines[1:end_idx]
    body = "\n".join(lines[end_idx + 1 :])
    metadata, parse_issues = _parse_metadata_lines(metadata_lines)
    issues.extend(parse_issues)
    return metadata, body, issues


def _parse_metadata_lines(lines: list[str]) -> tuple[dict[str, Any], list[str]]:
    data: dict[str, Any] = {}
    issues: list[str] = []
    idx = 0
    while idx < len(lines):
        raw = lines[idx]
        if not raw.strip():
            idx += 1
            continue
        if raw.startswith(" ") or raw.startswith("\t"):
            issues.append(f"unexpected_indentation:{idx + 1}")
            idx += 1
            continue
        if ":" not in raw:
            issues.append(f"invalid_frontmatter_line:{idx + 1}")
            idx += 1
            continue

        key, remainder = raw.split(":", 1)
        key = key.strip()
        value = remainder.strip()

        if not value:
            block_values: list[str] = []
            lookahead = idx + 1
            while lookahead < len(lines):
                child = lines[lookahead]
                stripped = child.strip()
                if not stripped:
                    lookahead += 1
                    continue
                if child.startswith("- "):
                    block_values.append(child[2:].strip())
                    lookahead += 1
                    continue
                break
            if block_values:
                data[key] = [_parse_scalar(v) for v in block_values]
                idx = lookahead
                continue
            data[key] = ""
            idx += 1
            continue

        if value.startswith("[") and value.endswith("]"):
            data[key] = _parse_inline_list(value)
        else:
            data[key] = _parse_scalar(value)
        idx += 1
    return data, issues


def _parse_inline_list(value: str) -> list[Any]:
    inner = value[1:-1].strip()
    if not inner:
        return []
    items: list[str] = []
    current = []
    quote: str | None = None
    for char in inner:
        if char in {"'", '"'}:
            if quote == char:
                quote = None
            elif quote is None:
                quote = char
            current.append(char)
            continue
        if char == "," and quote is None:
            items.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    if current:
        items.append("".join(current).strip())
    return [_parse_scalar(item) for item in items]


def _parse_scalar(value: str) -> Any:
    stripped = value.strip()
    if stripped in {'""', "''"}:
        return ""
    if stripped.startswith('"') and stripped.endswith('"'):
        return stripped[1:-1]
    if stripped.startswith("'") and stripped.endswith("'"):
        return stripped[1:-1]
    if stripped == "true":
        return True
    if stripped == "false":
        return False
    if stripped.isdigit():
        try:
            return int(stripped)
        except ValueError:
            return stripped
    return stripped

