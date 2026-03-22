"""Markdown parsing helpers for vault notes."""

from __future__ import annotations

import re
from collections import defaultdict

WIKI_LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
BLOCK_ID_RE = re.compile(r"(?m)\^([A-Za-z0-9_-]+)\s*$")
SECTION_HEADING_RE = re.compile(r"^(#{2,6})\s+(.+?)\s*$")


def extract_wiki_links(text: str) -> list[str]:
    return WIKI_LINK_RE.findall(text)


def extract_block_ids(text: str) -> list[str]:
    return [match.group(1) for match in BLOCK_ID_RE.finditer(text)]


def split_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = defaultdict(list)
    current: str | None = None
    for line in text.splitlines():
        heading_match = SECTION_HEADING_RE.match(line)
        if heading_match:
            current = heading_match.group(2).strip()
            sections.setdefault(current, [])
            continue
        if current is not None:
            sections[current].append(line)
    return dict(sections)


def bullets_in_sections(text: str, section_names: set[str]) -> list[str]:
    sections = split_sections(text)
    bullets: list[str] = []
    for name in section_names:
        for line in sections.get(name, []):
            stripped = line.strip()
            if stripped.startswith("- "):
                bullets.append(stripped)
    return bullets
