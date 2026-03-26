"""Vault profile resolution and note classification helpers."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .contracts import MANAGED_TYPES
from .runtime_config import load_runtime_config
from .utils import date_prefix_from_iso, slugify, stable_short_hash, title_from_path, year_from_date

DEFAULT_VAULT_PROFILE = "canonical_managed"
HEADING_RE = re.compile(r"^\s*#\s+(.+?)\s*$", re.MULTILINE)
CANONICAL_FILE_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*\.md$")


def load_vault_profiles(config_root: Path | None = None) -> dict[str, Any]:
    config_root = config_root or Path("config")
    path = config_root / "vault_profiles.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    profiles = data.get("profiles", {})
    return {"profiles": {name: _resolve_profile(name, profiles) for name in profiles}}


def resolve_vault_profile(*, profile_name: str | None = None, config_root: Path | None = None) -> dict[str, Any]:
    runtime = load_runtime_config(config_root)
    resolved_name = (
        profile_name
        or runtime.get("vault", {}).get("profile")
        or runtime.get("default_vault_profile")
        or DEFAULT_VAULT_PROFILE
    )
    profiles = load_vault_profiles(config_root).get("profiles", {})
    if resolved_name not in profiles:
        raise ValueError(f"Unknown vault profile: {resolved_name}")
    profile = dict(profiles[resolved_name])
    profile["name"] = resolved_name
    profile.setdefault("managed_by", "autoknowledge")
    profile.setdefault("source_roots", {"source": "sources/files", "conversation": "sources/conversations"})
    profile.setdefault(
        "canonical_roots",
        {
            "entity": "entities",
            "concept": "concepts",
            "topic": "topics",
            "unresolved": "inbox/unresolved",
        },
    )
    profile.setdefault("entity_kind_dirs", {})
    profile.setdefault("entity_kind_write_dirs", {})
    profile.setdefault("entity_kind_aliases", {})
    profile.setdefault("default_entity_dir", profile["canonical_roots"].get("entity", "entities"))
    profile.setdefault("legacy_rules", [])
    profile.setdefault(
        "filename_policy",
        {
            "entity": "slug",
            "concept": "slug",
            "topic": "slug",
            "unresolved": "dated_slug",
        },
    )
    profile.setdefault(
        "apply_policy",
        {
            "enforce_managed_write_roots": True,
            "require_backup_on_existing_write": resolved_name != DEFAULT_VAULT_PROFILE,
        },
    )
    profile.setdefault("ingest_policy", {"allow_existing_people_updates": True})
    return profile


def classify_note(
    *,
    rel_path: str,
    metadata: dict[str, Any],
    body: str,
    profile: dict[str, Any],
) -> dict[str, Any]:
    inferred_fields: list[str] = []
    note_type = str(metadata.get("type", "")).strip().lower()
    if note_type not in MANAGED_TYPES:
        note_type = infer_note_type(rel_path=rel_path, profile=profile)
        if note_type:
            inferred_fields.append("type")

    title = str(metadata.get("title", "")).strip()
    if not title:
        title = _extract_heading_title(body) or _title_from_rel_path(rel_path)
        inferred_fields.append("title")

    note_id = str(metadata.get("id", "")).strip()
    note_kind = infer_note_kind(rel_path=rel_path, metadata=metadata, note_type=note_type, profile=profile)
    managed_by = str(metadata.get("managed_by", "")).strip()
    is_managed = bool(managed_by) and managed_by == str(profile.get("managed_by", "autoknowledge"))
    return {
        "note_type": note_type,
        "title": title,
        "note_id": note_id,
        "note_kind": note_kind,
        "is_managed": is_managed,
        "inferred_fields": inferred_fields,
    }


def infer_note_type(*, rel_path: str, profile: dict[str, Any]) -> str:
    normalized = rel_path.strip().lstrip("./")
    source_roots = profile.get("source_roots", {})
    canonical_roots = profile.get("canonical_roots", {})
    if _path_under(normalized, source_roots.get("source", "")):
        return "source"
    if _path_under(normalized, source_roots.get("conversation", "")):
        return "conversation"
    for note_type in ("entity", "concept", "topic", "unresolved"):
        if _path_under(normalized, canonical_roots.get(note_type, "")):
            return note_type
    for rule in profile.get("legacy_rules", []):
        prefix = str(rule.get("prefix", "")).strip().strip("/")
        if prefix and _path_under(normalized, prefix):
            return str(rule.get("note_type", "")).strip().lower()
    return ""


def infer_note_kind(*, rel_path: str, metadata: dict[str, Any], note_type: str, profile: dict[str, Any]) -> str:
    if note_type == "entity":
        explicit = str(metadata.get("entity_kind", "")).strip()
        if explicit:
            return normalize_entity_kind(explicit, profile)
    elif note_type == "concept":
        return str(metadata.get("concept_kind", "")).strip()
    if note_type != "entity":
        return ""

    normalized = rel_path.strip().lstrip("./")
    for kind, dir_path in profile.get("entity_kind_dirs", {}).items():
        if _path_under(normalized, dir_path):
            return normalize_entity_kind(kind, profile)
    for rule in profile.get("legacy_rules", []):
        prefix = str(rule.get("prefix", "")).strip().strip("/")
        if not prefix or not _path_under(normalized, prefix):
            continue
        if rule.get("entity_kind_from_first_segment"):
            remainder = normalized[len(prefix) :].lstrip("/")
            first_segment = remainder.split("/", 1)[0].strip()
            if first_segment:
                return normalize_entity_kind(first_segment, profile)
    return ""


def build_source_note_path(
    *,
    note_type: str,
    title: str,
    note_id: str,
    date_value: str,
    profile: dict[str, Any],
) -> str:
    source_roots = profile.get("source_roots", {})
    if note_type == "source":
        root = source_roots.get("source", "sources/files")
    elif note_type == "conversation":
        root = source_roots.get("conversation", "sources/conversations")
    else:
        raise ValueError(f"Unsupported source note type: {note_type}")
    slug = slugify(title)
    return f"{root}/{year_from_date(date_value)}/{date_value}--{slug}--{note_id}.md"


def build_candidate_note_path(
    *,
    note_type: str,
    title: str,
    canonical_slug: str,
    note_kind: str | None,
    profile: dict[str, Any],
    date_value: str | None = None,
) -> str:
    canonical_roots = profile.get("canonical_roots", {})
    if note_type == "entity":
        root = entity_root_for_kind(note_kind or "", profile, for_write=True)
    elif note_type in {"concept", "topic"}:
        root = canonical_roots.get(note_type, note_type)
    elif note_type == "unresolved":
        root = canonical_roots.get("unresolved", "inbox/unresolved")
        prefix = date_prefix_from_iso(date_value)
        short_id = stable_short_hash(title, canonical_slug, length=8)
        filename = f"{prefix}--{canonical_slug}--unres_{short_id}"
        return f"{root}/{filename}.md"
    else:
        raise ValueError(f"Unsupported candidate type: {note_type}")
    filename = canonical_filename(
        title=title,
        canonical_slug=canonical_slug,
        note_type=note_type,
        profile=profile,
    )
    return f"{root}/{filename}.md"


def canonical_filename(*, title: str, canonical_slug: str, note_type: str, profile: dict[str, Any]) -> str:
    policy = str(profile.get("filename_policy", {}).get(note_type, "slug")).strip().lower()
    if policy == "title":
        return sanitize_title_filename(title)
    return canonical_slug


def entity_root_for_kind(note_kind: str, profile: dict[str, Any], *, for_write: bool = False) -> str:
    normalized_kind = normalize_entity_kind(note_kind, profile)
    entity_dirs = profile.get("entity_kind_write_dirs", {}) if for_write else profile.get("entity_kind_dirs", {})
    if normalized_kind and normalized_kind in entity_dirs:
        return str(entity_dirs[normalized_kind]).strip().strip("/")
    if for_write:
        fallback_dirs = profile.get("entity_kind_dirs", {})
        if normalized_kind and normalized_kind in fallback_dirs:
            return str(fallback_dirs[normalized_kind]).strip().strip("/")
    return str(profile.get("default_entity_dir") or profile.get("canonical_roots", {}).get("entity", "entities")).strip().strip("/")


def normalize_entity_kind(value: str, profile: dict[str, Any]) -> str:
    raw = str(value).strip()
    if not raw:
        return ""
    token = slugify(raw)
    aliases = {
        slugify(str(alias)): slugify(str(target))
        for alias, target in profile.get("entity_kind_aliases", {}).items()
    }
    return aliases.get(token, token)


def matches_profile_path(*, path: str, note_type: str, note_kind: str, profile: dict[str, Any]) -> bool:
    normalized = path.strip().lstrip("./")
    source_roots = profile.get("source_roots", {})
    canonical_roots = profile.get("canonical_roots", {})
    if note_type == "source":
        root = source_roots.get("source", "sources/files")
        return _matches_dated_source_path(normalized, root, "src_")
    if note_type == "conversation":
        root = source_roots.get("conversation", "sources/conversations")
        return _matches_dated_source_path(normalized, root, "conv_")
    if note_type == "entity":
        roots = {
            entity_root_for_kind(note_kind, profile, for_write=False),
            entity_root_for_kind(note_kind, profile, for_write=True),
        }
        roots = {root for root in roots if root}
        return any(
            _path_under(normalized, root) and _matches_canonical_filename(Path(normalized).name, "entity", profile)
            for root in roots
        )
    if note_type in {"concept", "topic"}:
        root = canonical_roots.get(note_type, note_type)
        return _path_under(normalized, root) and _matches_canonical_filename(Path(normalized).name, note_type, profile)
    if note_type == "unresolved":
        root = canonical_roots.get("unresolved", "inbox/unresolved")
        root_re = re.escape(root.strip("/"))
        return bool(re.match(rf"^{root_re}/\d{{4}}-\d{{2}}-\d{{2}}--[a-z0-9-]+--unres_[A-Za-z0-9-]+\.md$", normalized))
    return False


def sanitize_title_filename(title: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]+', " ", title).strip()
    cleaned = " ".join(cleaned.split())
    return cleaned or "Untitled"


def managed_write_roots(profile: dict[str, Any]) -> list[str]:
    roots = set()
    for value in profile.get("source_roots", {}).values():
        root = str(value).strip().strip("/")
        if root:
            roots.add(root)
    for value in profile.get("canonical_roots", {}).values():
        root = str(value).strip().strip("/")
        if root:
            roots.add(root)
    for value in profile.get("entity_kind_dirs", {}).values():
        root = str(value).strip().strip("/")
        if root:
            roots.add(root)
    for value in profile.get("entity_kind_write_dirs", {}).values():
        root = str(value).strip().strip("/")
        if root:
            roots.add(root)
    default_entity_dir = str(profile.get("default_entity_dir", "")).strip().strip("/")
    if default_entity_dir:
        roots.add(default_entity_dir)
    return sorted(roots)


def _title_from_rel_path(rel_path: str) -> str:
    stem = Path(rel_path).stem.strip()
    if " " in stem or any(char.isupper() for char in stem):
        return stem
    return title_from_path(Path(rel_path))


def _extract_heading_title(body: str) -> str:
    match = HEADING_RE.search(body)
    return match.group(1).strip() if match else ""


def _path_under(path: str, prefix: str) -> bool:
    normalized_prefix = prefix.strip().strip("/")
    if not normalized_prefix:
        return False
    return path == normalized_prefix or path.startswith(f"{normalized_prefix}/")


def _matches_dated_source_path(path: str, root: str, id_prefix: str) -> bool:
    root_re = re.escape(root.strip("/"))
    return bool(re.match(rf"^{root_re}/\d{{4}}/\d{{4}}-\d{{2}}-\d{{2}}--[a-z0-9-]+--{re.escape(id_prefix)}[A-Za-z0-9]+\.md$", path))


def _matches_canonical_filename(filename: str, note_type: str, profile: dict[str, Any]) -> bool:
    policy = str(profile.get("filename_policy", {}).get(note_type, "slug")).strip().lower()
    if policy == "title":
        return filename.endswith(".md")
    return bool(CANONICAL_FILE_RE.match(filename))


def _resolve_profile(name: str, profiles: dict[str, Any]) -> dict[str, Any]:
    raw = dict(profiles[name])
    parent_name = raw.pop("extends", "")
    if not parent_name:
        return raw
    if parent_name not in profiles:
        raise ValueError(f"Unknown parent vault profile {parent_name!r} for {name!r}")
    return _deep_merge(_resolve_profile(parent_name, profiles), raw)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged
