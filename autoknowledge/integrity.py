"""Integrity checks against the locked vault contract."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .contracts import (
    COMMON_FIELDS,
    CONCEPT_DIR,
    CONVERSATION_DIR_PREFIX,
    ENTITY_DIR,
    MANAGED_TYPES,
    REQUIRED_SECTIONS,
    SOURCE_DIR_PREFIX,
    TOPIC_DIR,
    TYPE_FIELDS,
    UNRESOLVED_DIR,
)

SOURCE_FILE_RE = re.compile(r"^sources/files/\d{4}/\d{4}-\d{2}-\d{2}--[a-z0-9-]+--src_[A-Za-z0-9]+\.md$")
CONVERSATION_FILE_RE = re.compile(
    r"^sources/conversations/\d{4}/\d{4}-\d{2}-\d{2}--[a-z0-9-]+--conv_[A-Za-z0-9]+\.md$"
)
CANONICAL_FILE_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
UNRESOLVED_FILE_RE = re.compile(
    r"^inbox/unresolved/\d{4}-\d{2}-\d{2}--[a-z0-9-]+--unres_[A-Za-z0-9]+\.md$"
)
PRIMARY_SOURCE_RE = re.compile(r"Source:\s*\[\[([^\]]+#\^[A-Za-z0-9_-]+)\]\]")


def validate_index(index: dict[str, Any]) -> dict[str, Any]:
    notes = index["notes"]
    issues: list[dict[str, str]] = []
    path_lookup = {note["path"][:-3]: note for note in notes if note["path"].endswith(".md")}
    stem_lookup: dict[str, list[dict[str, Any]]] = {}
    title_lookup: dict[str, list[dict[str, Any]]] = {}

    for note in notes:
        stem_lookup.setdefault(_normalize(note["stem"]), []).append(note)
        title_lookup.setdefault(_normalize(note["title"]), []).append(note)

    for note in notes:
        issues.extend(_validate_note(note, path_lookup, stem_lookup, title_lookup))

    return {"issue_count": len(issues), "issues": issues}


def _validate_note(
    note: dict[str, Any],
    path_lookup: dict[str, dict[str, Any]],
    stem_lookup: dict[str, list[dict[str, Any]]],
    title_lookup: dict[str, list[dict[str, Any]]],
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    path = note["path"]
    metadata = note["metadata"]
    note_type = note["note_type"]

    for parse_issue in note.get("parse_issues", []):
        issues.append(_issue(path, "frontmatter_parse", parse_issue))

    if note_type not in MANAGED_TYPES:
        issues.append(_issue(path, "unknown_type", f"Unknown note type: {note_type!r}"))
        return issues

    for field in COMMON_FIELDS | TYPE_FIELDS.get(note_type, set()):
        if field not in metadata:
            issues.append(_issue(path, "missing_field", f"Missing field: {field}"))

    for section in REQUIRED_SECTIONS.get(note_type, ()):
        if section not in note["sections"]:
            issues.append(_issue(path, "missing_section", f"Missing section: {section}"))

    issues.extend(_validate_path(path, note_type))
    issues.extend(_validate_source_refs(note))
    issues.extend(_validate_claims(note))
    issues.extend(_validate_links(note, path_lookup, stem_lookup, title_lookup))
    issues.extend(_validate_block_ids(note))
    return issues


def _validate_path(path: str, note_type: str) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if note_type == "source":
        if not SOURCE_FILE_RE.match(path):
            issues.append(_issue(path, "path_mismatch", "Source note path does not match the contract"))
    elif note_type == "conversation":
        if not CONVERSATION_FILE_RE.match(path):
            issues.append(_issue(path, "path_mismatch", "Conversation note path does not match the contract"))
    elif note_type == "entity":
        if not path.startswith(ENTITY_DIR) or not CANONICAL_FILE_RE.match(Path(path).name):
            issues.append(_issue(path, "path_mismatch", "Entity note path does not match the contract"))
    elif note_type == "concept":
        if not path.startswith(CONCEPT_DIR) or not CANONICAL_FILE_RE.match(Path(path).name):
            issues.append(_issue(path, "path_mismatch", "Concept note path does not match the contract"))
    elif note_type == "topic":
        if not path.startswith(TOPIC_DIR) or not CANONICAL_FILE_RE.match(Path(path).name):
            issues.append(_issue(path, "path_mismatch", "Topic note path does not match the contract"))
    elif note_type == "unresolved":
        if not UNRESOLVED_FILE_RE.match(path):
            issues.append(_issue(path, "path_mismatch", "Unresolved note path does not match the contract"))
    return issues


def _validate_source_refs(note: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    path = note["path"]
    refs = note["metadata"].get("source_refs", [])
    if not isinstance(refs, list):
        issues.append(_issue(path, "invalid_source_refs", "source_refs must be a list"))
        return issues
    for ref in refs:
        if not isinstance(ref, str) or "#^" not in ref:
            issues.append(_issue(path, "invalid_source_ref", f"Invalid source ref: {ref!r}"))
    return issues


def _validate_claims(note: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    path = note["path"]
    note_type = note["note_type"]
    if note_type not in {"entity", "concept", "topic", "unresolved"}:
        return issues

    for bullet in note["claim_bullets"] + note["relationship_bullets"]:
        if not PRIMARY_SOURCE_RE.search(bullet):
            issues.append(_issue(path, "missing_claim_source", f"Missing primary source on bullet: {bullet}"))
        if "Confidence:" not in bullet:
            issues.append(_issue(path, "missing_claim_confidence", f"Missing confidence on bullet: {bullet}"))
    return issues


def _validate_links(
    note: dict[str, Any],
    path_lookup: dict[str, dict[str, Any]],
    stem_lookup: dict[str, list[dict[str, Any]]],
    title_lookup: dict[str, list[dict[str, Any]]],
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    path = note["path"]
    for link in note["wiki_links"]:
        target = link["target"]
        block_id = link["block_id"]
        linked_note = _resolve_link_target(target, path_lookup, stem_lookup, title_lookup)
        if linked_note is None:
            issues.append(_issue(path, "broken_link", f"Cannot resolve link: [[{link['raw']}]]"))
            continue
        if block_id and block_id not in linked_note["block_ids"]:
            issues.append(
                _issue(
                    path,
                    "missing_target_block",
                    f"Target block ^{block_id} not found for link [[{link['raw']}]]",
                )
            )
    return issues


def _validate_block_ids(note: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    path = note["path"]
    block_ids = note["block_ids"]
    note_type = note["note_type"]
    if note_type == "source":
        if not block_ids:
            issues.append(_issue(path, "missing_blocks", "Source note has no evidence blocks"))
        for block_id in block_ids:
            if not block_id.startswith("e"):
                issues.append(_issue(path, "invalid_block_id", f"Source block must start with e: ^{block_id}"))
    elif note_type == "conversation":
        if not block_ids:
            issues.append(_issue(path, "missing_blocks", "Conversation note has no message blocks"))
        for block_id in block_ids:
            if not block_id.startswith("m"):
                issues.append(_issue(path, "invalid_block_id", f"Conversation block must start with m: ^{block_id}"))
    return issues


def _resolve_link_target(
    target: str,
    path_lookup: dict[str, dict[str, Any]],
    stem_lookup: dict[str, list[dict[str, Any]]],
    title_lookup: dict[str, list[dict[str, Any]]],
) -> dict[str, Any] | None:
    if target in path_lookup:
        return path_lookup[target]
    normalized = _normalize(Path(target).name)
    stem_matches = stem_lookup.get(normalized, [])
    if len(stem_matches) == 1:
        return stem_matches[0]
    title_matches = title_lookup.get(normalized, [])
    if len(title_matches) == 1:
        return title_matches[0]
    return None


def _issue(path: str, code: str, message: str) -> dict[str, str]:
    return {"path": path, "code": code, "message": message}


def _normalize(value: str) -> str:
    return value.strip().lower()

