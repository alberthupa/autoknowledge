"""Deterministic graph-repair planning and application."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .contracts import CANONICAL_TYPES
from .frontmatter import parse_frontmatter
from .indexer import index_vault
from .ingest import _prepare_write_backups, _render_frontmatter, _validate_write_scope
from .integrity import validate_index
from .metrics import compute_metrics
from .utils import identity_text_variants, utc_now_iso
from .vault_profiles import resolve_vault_profile

WIKI_LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
REPAIRABLE_TYPES = CANONICAL_TYPES | {"unresolved"}
DEDUPABLE_LIST_FIELDS = {"aliases", "source_refs", "candidate_targets"}


@dataclass
class RepairOperation:
    action: str
    path: str
    reason: str
    content: str


@dataclass
class RepairPlan:
    operations: list[RepairOperation]
    summary: dict[str, Any]
    manual_review: dict[str, Any]
    baseline_check: dict[str, Any]
    baseline_metrics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "operations": [asdict(operation) for operation in self.operations],
            "summary": self.summary,
            "manual_review": self.manual_review,
            "baseline_check": self.baseline_check,
            "baseline_metrics": self.baseline_metrics,
        }


def plan_graph_repairs(
    *,
    vault_root: Path,
    vault_profile_name: str | None = None,
    config_root: Path | None = None,
) -> RepairPlan:
    index = index_vault(vault_root, vault_profile_name=vault_profile_name, config_root=config_root)
    integrity_report = validate_index(index, vault_profile_name=vault_profile_name, config_root=config_root)
    metrics = compute_metrics(index, integrity_report)

    notes = index["notes"]
    path_lookup = {note["path"][:-3]: note for note in notes if note["path"].endswith(".md")}
    stem_lookup: dict[str, list[dict[str, Any]]] = defaultdict(list)
    title_lookup: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for note in notes:
        stem_lookup[_normalize(note["stem"])].append(note)
        title_lookup[_normalize(note["title"])].append(note)

    operations: list[RepairOperation] = []
    link_normalization_count = 0
    metadata_dedupe_count = 0

    for note in notes:
        if not note.get("is_managed"):
            continue
        if note["note_type"] not in REPAIRABLE_TYPES:
            continue
        raw_text = (vault_root / note["path"]).read_text(encoding="utf-8")
        metadata, body, parse_issues = parse_frontmatter(raw_text)
        if parse_issues:
            continue

        normalized_body, normalized_links = _normalize_body_links(
            body,
            path_lookup=path_lookup,
            stem_lookup=stem_lookup,
            title_lookup=title_lookup,
        )
        normalized_metadata, deduped_fields = _dedupe_metadata(metadata)

        if normalized_links == 0 and not deduped_fields:
            continue

        if deduped_fields and "updated_at" in normalized_metadata:
            normalized_metadata["updated_at"] = utc_now_iso()

        content = _render_document(metadata=normalized_metadata, body=normalized_body, title=note["title"])
        reasons = []
        if normalized_links:
            reasons.append(f"normalized {normalized_links} wiki link(s)")
            link_normalization_count += normalized_links
        if deduped_fields:
            reasons.append(f"deduped metadata fields: {', '.join(deduped_fields)}")
            metadata_dedupe_count += len(deduped_fields)
        if content == raw_text:
            continue
        operations.append(
            RepairOperation(
                action="update",
                path=note["path"],
                reason="; ".join(reasons),
                content=content,
            )
        )

    manual_review = {
        "broken_links": [issue for issue in integrity_report["issues"] if issue["code"] == "broken_link"],
        "duplicate_clusters": _duplicate_clusters(notes),
        "orphan_notes": _canonical_graph_review(notes)["orphan_notes"],
        "isolated_notes": _canonical_graph_review(notes)["isolated_notes"],
    }
    summary = {
        "operation_count": len(operations),
        "update_count": len(operations),
        "link_normalization_count": link_normalization_count,
        "metadata_dedupe_count": metadata_dedupe_count,
        "manual_broken_link_count": len(manual_review["broken_links"]),
        "manual_duplicate_cluster_count": len(manual_review["duplicate_clusters"]),
        "manual_orphan_note_count": len(manual_review["orphan_notes"]),
        "manual_isolated_note_count": len(manual_review["isolated_notes"]),
    }
    return RepairPlan(
        operations=operations,
        summary=summary,
        manual_review=manual_review,
        baseline_check=integrity_report,
        baseline_metrics=metrics,
    )


def apply_repair_plan(
    vault_root: Path,
    plan: RepairPlan,
    *,
    vault_profile_name: str | None = None,
    config_root: Path | None = None,
    backup_dir: Path | None = None,
) -> dict[str, Any]:
    vault_profile = resolve_vault_profile(profile_name=vault_profile_name, config_root=config_root)
    _validate_write_scope(plan=plan, vault_profile=vault_profile)
    backup_summary = _prepare_write_backups(
        vault_root=vault_root,
        plan=plan,
        vault_profile=vault_profile,
        backup_dir=backup_dir,
    )
    written_paths: list[str] = []
    for operation in plan.operations:
        if operation.action == "noop":
            continue
        path = vault_root / operation.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(operation.content, encoding="utf-8")
        written_paths.append(operation.path)
    return {
        "written_paths": written_paths,
        "written_count": len(written_paths),
        **backup_summary,
    }


def save_repair_plan(plan: RepairPlan, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(plan.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _normalize_body_links(
    body: str,
    *,
    path_lookup: dict[str, dict[str, Any]],
    stem_lookup: dict[str, list[dict[str, Any]]],
    title_lookup: dict[str, list[dict[str, Any]]],
) -> tuple[str, int]:
    replacement_count = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal replacement_count
        raw_inner = match.group(1)
        target, display = _split_display(raw_inner)
        link_target, block_id = _split_block_id(target)
        linked_note = _resolve_link_target(
            link_target,
            path_lookup=path_lookup,
            stem_lookup=stem_lookup,
            title_lookup=title_lookup,
        )
        if linked_note is None:
            return match.group(0)
        if block_id and block_id not in set(linked_note.get("block_ids", [])):
            return match.group(0)

        canonical_target = linked_note["path"][:-3] if linked_note["path"].endswith(".md") else linked_note["path"]
        rebuilt = canonical_target
        if block_id:
            rebuilt += f"#^{block_id}"
        if display is not None:
            rebuilt += f"|{display}"
        if rebuilt == raw_inner:
            return match.group(0)
        replacement_count += 1
        return f"[[{rebuilt}]]"

    return WIKI_LINK_RE.sub(replace, body), replacement_count


def _dedupe_metadata(metadata: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    normalized = dict(metadata)
    changed_fields: list[str] = []
    for field in DEDUPABLE_LIST_FIELDS:
        value = normalized.get(field)
        if not isinstance(value, list):
            continue
        deduped = _dedupe_list(value)
        if deduped != value:
            normalized[field] = deduped
            changed_fields.append(field)
    return normalized, changed_fields


def _dedupe_list(values: list[Any]) -> list[Any]:
    seen: set[str] = set()
    deduped: list[Any] = []
    for value in values:
        if isinstance(value, str):
            item = value.strip()
            if not item:
                continue
            key = item
            rendered = item
        else:
            key = json.dumps(value, sort_keys=True)
            rendered = value
        if key in seen:
            continue
        seen.add(key)
        deduped.append(rendered)
    return deduped


def _render_document(*, metadata: dict[str, Any], body: str, title: str) -> str:
    rendered = [
        "---",
        _render_frontmatter(metadata),
        "---",
        f"# {metadata.get('title', title)}",
    ]
    body_lines = body.splitlines()
    if body_lines and body_lines[0].strip() == f"# {metadata.get('title', title)}":
        body_lines = body_lines[1:]
    rendered.extend(body_lines)
    return "\n".join(rendered).rstrip() + "\n"


def _split_display(raw_inner: str) -> tuple[str, str | None]:
    if "|" not in raw_inner:
        return raw_inner, None
    target, display = raw_inner.split("|", 1)
    return target, display


def _split_block_id(target: str) -> tuple[str, str | None]:
    if "#^" not in target:
        return target, None
    path, block_id = target.split("#^", 1)
    return path, block_id


def _resolve_link_target(
    target: str,
    *,
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


def _duplicate_clusters(notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    canonical_notes = [note for note in notes if note["note_type"] in CANONICAL_TYPES]
    names_to_paths: dict[str, set[str]] = defaultdict(set)
    parent = {note["path"]: note["path"] for note in canonical_notes}

    def find(path: str) -> str:
        while parent[path] != path:
            parent[path] = parent[parent[path]]
            path = parent[path]
        return path

    def union(left: str, right: str) -> None:
        root_left = find(left)
        root_right = find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    for note in canonical_notes:
        for name in _note_identity_names(note):
            names_to_paths[name].add(note["path"])

    for paths in names_to_paths.values():
        path_list = sorted(paths)
        if len(path_list) < 2:
            continue
        anchor = path_list[0]
        for path in path_list[1:]:
            union(anchor, path)

    components: dict[str, set[str]] = defaultdict(set)
    for note in canonical_notes:
        components[find(note["path"])].add(note["path"])

    clusters = []
    for members in sorted((sorted(member_set) for member_set in components.values() if len(member_set) > 1), key=len, reverse=True):
        clusters.append({"paths": members, "size": len(members)})
    return clusters


def _canonical_graph_review(notes: list[dict[str, Any]]) -> dict[str, list[str]]:
    path_keys = {note["path"][:-3]: note for note in notes if note["note_type"] in CANONICAL_TYPES}
    title_keys: dict[str, set[str]] = defaultdict(set)
    stem_keys: dict[str, set[str]] = defaultdict(set)
    outbound: dict[str, set[str]] = defaultdict(set)
    inbound: dict[str, set[str]] = defaultdict(set)
    source_ref_counts: dict[str, int] = {}

    for key, note in path_keys.items():
        title_keys[_normalize(note["title"])].add(key)
        stem_keys[_normalize(note["stem"])].add(key)
        source_ref_counts[key] = len(_note_source_refs(note))

    for key, note in path_keys.items():
        for link in note["wiki_links"]:
            target = link["target"]
            resolved = None
            if target in path_keys:
                resolved = target
            else:
                normalized = _normalize(target.split("/")[-1])
                if len(stem_keys.get(normalized, set())) == 1:
                    resolved = next(iter(stem_keys[normalized]))
                elif len(title_keys.get(normalized, set())) == 1:
                    resolved = next(iter(title_keys[normalized]))
            if resolved:
                outbound[key].add(resolved)
                inbound[resolved].add(key)

    orphan_notes: list[str] = []
    isolated_notes: list[str] = []
    for key in sorted(path_keys):
        canonical_degree = len(outbound.get(key, set())) + len(inbound.get(key, set()))
        support_count = source_ref_counts.get(key, 0)
        path = path_keys[key]["path"]
        if canonical_degree == 0 and support_count == 0:
            orphan_notes.append(path)
        if canonical_degree == 0 and support_count <= 1:
            isolated_notes.append(path)
    return {"orphan_notes": orphan_notes, "isolated_notes": isolated_notes}


def _note_identity_names(note: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    names.update(identity_text_variants(str(note.get("title", ""))))
    names.update(identity_text_variants(str(note.get("stem", ""))))
    names.update(identity_text_variants(str(note.get("metadata", {}).get("canonical_slug", ""))))
    for alias in note.get("metadata", {}).get("aliases", []):
        if isinstance(alias, str):
            names.update(identity_text_variants(alias))
    return {name for name in names if name}


def _note_source_refs(note: dict[str, Any]) -> set[str]:
    refs = set()
    for ref in note.get("metadata", {}).get("source_refs", []):
        if isinstance(ref, str) and "#^" in ref:
            refs.add(_normalize_source_ref(ref))
    for bullet in list(note.get("claim_bullets", [])) + list(note.get("relationship_bullets", [])):
        refs.update(_normalize_source_ref(ref) for ref in re.findall(r"Source:\s*\[\[([^\]]+#\^[A-Za-z0-9_-]+)\]\]", bullet))
    return refs


def _normalize_source_ref(value: str) -> str:
    text = value.strip()
    if text.startswith("[[") and text.endswith("]]"):
        text = text[2:-2]
    return text


def _normalize(value: str) -> str:
    return value.strip().lower()
