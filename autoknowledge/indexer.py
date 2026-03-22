"""Vault indexing for AutoKnowledge."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .frontmatter import parse_frontmatter
from .markdown import bullets_in_sections, extract_block_ids, extract_wiki_links, split_sections


@dataclass
class LinkRecord:
    raw: str
    target: str
    block_id: str | None


@dataclass
class NoteRecord:
    path: str
    stem: str
    note_id: str
    note_type: str
    title: str
    metadata: dict[str, Any]
    sections: list[str]
    block_ids: list[str]
    wiki_links: list[LinkRecord]
    claim_bullets: list[str]
    relationship_bullets: list[str]
    contradiction_bullets: list[str]
    content_hash: str
    parse_issues: list[str]


def index_vault(vault_root: Path) -> dict[str, Any]:
    vault_root = vault_root.resolve()
    notes: list[NoteRecord] = []

    for path in sorted(vault_root.rglob("*.md")):
        if any(part.startswith(".") for part in path.relative_to(vault_root).parts):
            continue
        note = _index_note(vault_root, path)
        notes.append(note)

    by_path = {note.path: asdict(note) for note in notes}
    return {
        "vault_root": str(vault_root),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "note_count": len(notes),
        "notes": [asdict(note) for note in notes],
        "by_path": by_path,
    }


def save_index(index: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_index(index_path: Path) -> dict[str, Any]:
    return json.loads(index_path.read_text(encoding="utf-8"))


def _index_note(vault_root: Path, path: Path) -> NoteRecord:
    text = path.read_text(encoding="utf-8")
    metadata, body, parse_issues = parse_frontmatter(text)
    rel_path = path.relative_to(vault_root).as_posix()
    links = [_parse_link(raw) for raw in extract_wiki_links(text)]
    sections = sorted(split_sections(body).keys())
    return NoteRecord(
        path=rel_path,
        stem=path.stem,
        note_id=str(metadata.get("id", "")),
        note_type=str(metadata.get("type", "")),
        title=str(metadata.get("title", "")),
        metadata=metadata,
        sections=sections,
        block_ids=extract_block_ids(body),
        wiki_links=links,
        claim_bullets=bullets_in_sections(body, {"Claims"}),
        relationship_bullets=bullets_in_sections(body, {"Relationships"}),
        contradiction_bullets=bullets_in_sections(body, {"Contradictions"}),
        content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        parse_issues=parse_issues,
    )


def _parse_link(raw: str) -> LinkRecord:
    target = raw
    block_id = None
    if "|" in target:
        target = target.split("|", 1)[0]
    if "#^" in target:
        target, block = target.split("#^", 1)
        block_id = block
    if target.endswith(".md"):
        target = target[:-3]
    return LinkRecord(raw=raw, target=target, block_id=block_id)
