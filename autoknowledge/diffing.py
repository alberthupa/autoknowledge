"""Index snapshot diffing."""

from __future__ import annotations

import re
from typing import Any

from .contracts import CANONICAL_TYPES


def summarize_diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_map = before.get("by_path") or {note["path"]: note for note in before["notes"]}
    after_map = after.get("by_path") or {note["path"]: note for note in after["notes"]}
    return _summarize_maps(before_map, after_map)


def summarize_canonical_diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_all = before.get("by_path") or {note["path"]: note for note in before["notes"]}
    after_all = after.get("by_path") or {note["path"]: note for note in after["notes"]}
    before_map = {path: note for path, note in before_all.items() if note["note_type"] in CANONICAL_TYPES}
    after_map = {path: note for path, note in after_all.items() if note["note_type"] in CANONICAL_TYPES}
    return _summarize_maps(before_map, after_map)


def summarize_semantic_canonical_diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_all = before.get("by_path") or {note["path"]: note for note in before["notes"]}
    after_all = after.get("by_path") or {note["path"]: note for note in after["notes"]}
    before_map = {path: _semantic_note_record(note) for path, note in before_all.items() if note["note_type"] in CANONICAL_TYPES}
    after_map = {path: _semantic_note_record(note) for path, note in after_all.items() if note["note_type"] in CANONICAL_TYPES}
    return _summarize_maps(before_map, after_map, compare_content_hash=False)


def _summarize_maps(before_map: dict[str, Any], after_map: dict[str, Any], *, compare_content_hash: bool = True) -> dict[str, Any]:
    before_paths = set(before_map)
    after_paths = set(after_map)
    added = sorted(after_paths - before_paths)
    removed = sorted(before_paths - after_paths)
    changed = []

    for path in sorted(before_paths & after_paths):
        before_note = before_map[path]
        after_note = after_map[path]
        if compare_content_hash:
            if before_note["content_hash"] == after_note["content_hash"]:
                continue
        else:
            if before_note == after_note:
                continue
        changed.append(
            {
                "path": path,
                "type_before": before_note["note_type"],
                "type_after": after_note["note_type"],
                "claims_before": len(before_note["claim_bullets"]),
                "claims_after": len(after_note["claim_bullets"]),
                "relationships_before": len(before_note["relationship_bullets"]),
                "relationships_after": len(after_note["relationship_bullets"]),
                "source_refs_before": len(before_note["metadata"].get("source_refs", [])),
                "source_refs_after": len(after_note["metadata"].get("source_refs", [])),
            }
        )

    before_count = len(before_paths)
    after_count = len(after_paths)
    max_count = max(before_count, after_count, 1)
    added_count = len(added)
    removed_count = len(removed)
    changed_count = len(changed)
    graph_churn = added_count + removed_count + changed_count
    return {
        "before_count": before_count,
        "after_count": after_count,
        "added_count": len(added),
        "removed_count": len(removed),
        "changed_count": len(changed),
        "added": added,
        "removed": removed,
        "changed": changed,
        "graph_churn": graph_churn,
        "graph_churn_rate": graph_churn / max_count,
        "added_rate": added_count / max_count,
        "removed_rate": removed_count / max_count,
        "changed_rate": changed_count / max_count,
        "net_growth": after_count - before_count,
    }


SOURCE_CLAUSE_RE = re.compile(r"\s+Source:\s*\[\[[^\]]+\]\]")
CONFIDENCE_CLAUSE_RE = re.compile(r"\s+Confidence:\s*[A-Za-z]+")
SOURCE_LINK_RE = re.compile(r"\[\[(sources/(?:files|conversations)/[^\]]+)\]\]")


def _semantic_note_record(note: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": note["path"],
        "note_type": note["note_type"],
        "title": note["title"],
        "metadata": {
            "source_refs": [],
        },
        "claim_bullets": sorted(_normalize_bullet(item) for item in note["claim_bullets"]),
        "relationship_bullets": sorted(_normalize_bullet(item) for item in note["relationship_bullets"]),
    }


def _normalize_bullet(bullet: str) -> str:
    bullet = SOURCE_CLAUSE_RE.sub("", bullet)
    bullet = CONFIDENCE_CLAUSE_RE.sub("", bullet)
    bullet = SOURCE_LINK_RE.sub("[[SOURCE]]", bullet)
    return " ".join(bullet.split()).strip()
