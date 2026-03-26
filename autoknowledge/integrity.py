"""Integrity checks against the locked vault contract."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .contracts import (
    COMMON_FIELDS,
    MANAGED_TYPES,
    REQUIRED_SECTIONS,
    TYPE_FIELDS,
)
from .vault_profiles import matches_profile_path, resolve_vault_profile

PRIMARY_SOURCE_RE = re.compile(r"Source:\s*\[\[([^\]]+#\^[A-Za-z0-9_-]+)\]\]")
LEGACY_MINIMAL_FIELDS = {"id", "type", "title", "managed_by", "schema_version", "managed_format", "canonical_slug"}
LEGACY_MINIMAL_TYPE_FIELDS = {
    "entity": {"entity_kind"},
    "concept": {"concept_kind"},
    "topic": set(),
    "unresolved": set(),
}


def validate_index(
    index: dict[str, Any],
    *,
    vault_profile_name: str | None = None,
    config_root: Any = None,
) -> dict[str, Any]:
    notes = index["notes"]
    resolved_profile_name = vault_profile_name or index.get("vault_profile_name")
    profile = resolve_vault_profile(profile_name=resolved_profile_name, config_root=config_root)
    issues: list[dict[str, str]] = []
    path_lookup = {note["path"][:-3]: note for note in notes if note["path"].endswith(".md")}
    stem_lookup: dict[str, list[dict[str, Any]]] = {}
    title_lookup: dict[str, list[dict[str, Any]]] = {}

    for note in notes:
        stem_lookup.setdefault(_normalize(note["stem"]), []).append(note)
        title_lookup.setdefault(_normalize(note["title"]), []).append(note)

    for note in notes:
        issues.extend(_validate_note(note, path_lookup, stem_lookup, title_lookup, profile))

    return {"issue_count": len(issues), "issues": issues}


def _validate_note(
    note: dict[str, Any],
    path_lookup: dict[str, dict[str, Any]],
    stem_lookup: dict[str, list[dict[str, Any]]],
    title_lookup: dict[str, list[dict[str, Any]]],
    profile: dict[str, Any],
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    path = note["path"]
    metadata = note["metadata"]
    note_type = note["note_type"]
    is_managed = bool(note.get("is_managed"))

    if is_managed:
        for parse_issue in note.get("parse_issues", []):
            issues.append(_issue(path, "frontmatter_parse", parse_issue))

    if not note_type:
        return issues

    if note_type not in MANAGED_TYPES:
        issues.append(_issue(path, "unknown_type", f"Unknown note type: {note_type!r}"))
        return issues

    if not is_managed:
        issues.extend(_validate_links(note, path_lookup, stem_lookup, title_lookup))
        return issues

    if _is_legacy_minimal_managed(note):
        for field in LEGACY_MINIMAL_FIELDS | LEGACY_MINIMAL_TYPE_FIELDS.get(note_type, set()):
            if field not in metadata:
                issues.append(_issue(path, "missing_field", f"Missing field: {field}"))
        issues.extend(_validate_path(path, note_type, str(note.get("note_kind", "")), profile))
        if "source_refs" in metadata:
            issues.extend(_validate_source_refs(note))
        issues.extend(_validate_links(note, path_lookup, stem_lookup, title_lookup))
        return issues

    for field in COMMON_FIELDS | TYPE_FIELDS.get(note_type, set()):
        if field not in metadata:
            issues.append(_issue(path, "missing_field", f"Missing field: {field}"))

    for section in REQUIRED_SECTIONS.get(note_type, ()):
        if section not in note["sections"]:
            issues.append(_issue(path, "missing_section", f"Missing section: {section}"))

    issues.extend(_validate_path(path, note_type, str(note.get("note_kind", "")), profile))
    issues.extend(_validate_source_refs(note))
    issues.extend(_validate_claims(note))
    issues.extend(_validate_links(note, path_lookup, stem_lookup, title_lookup))
    issues.extend(_validate_block_ids(note))
    return issues


def _validate_path(path: str, note_type: str, note_kind: str, profile: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if not matches_profile_path(path=path, note_type=note_type, note_kind=note_kind, profile=profile):
        issues.append(_issue(path, "path_mismatch", "Managed note path does not match the active vault profile"))
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


def _is_legacy_minimal_managed(note: dict[str, Any]) -> bool:
    metadata = note.get("metadata", {})
    return str(metadata.get("managed_format", "")).strip() == "legacy_minimal"
