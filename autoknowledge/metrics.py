"""Soft metric calculations for AutoKnowledge."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

from .contracts import CANONICAL_TYPES
from .utils import identity_text_variants

PRIMARY_SOURCE_RE = re.compile(r"Source:\s*\[\[([^\]]+#\^[A-Za-z0-9_-]+)\]\]")


def compute_metrics(index: dict[str, Any], integrity_report: dict[str, Any]) -> dict[str, Any]:
    notes = index["notes"]
    canonical_notes = [note for note in notes if note["note_type"] in CANONICAL_TYPES]

    claim_bullets = []
    for note in canonical_notes:
        claim_bullets.extend(note["claim_bullets"])
        claim_bullets.extend(note["relationship_bullets"])

    supported_claims = [bullet for bullet in claim_bullets if PRIMARY_SOURCE_RE.search(bullet)]
    unsupported_claim_count = len(claim_bullets) - len(supported_claims)
    total_claim_count = len(claim_bullets)

    duplicate_stats = _duplicate_stats(canonical_notes)
    duplicate_id_count = _duplicate_count([note["note_id"] for note in notes if note["note_id"]])
    graph_stats = _canonical_graph_stats(notes)

    canonical_count = max(len(canonical_notes), 1)
    claim_count = max(total_claim_count, 1)

    integrity_codes = Counter(issue["code"] for issue in integrity_report["issues"])
    return {
        "note_count": len(notes),
        "canonical_note_count": len(canonical_notes),
        "claim_count": total_claim_count,
        "citation_coverage": len(supported_claims) / claim_count,
        "unsupported_claim_rate": unsupported_claim_count / claim_count,
        "duplicate_note_rate": duplicate_stats["duplicate_candidate_count"] / canonical_count,
        "duplicate_candidate_count": duplicate_stats["duplicate_candidate_count"],
        "duplicate_cluster_count": duplicate_stats["duplicate_cluster_count"],
        "largest_duplicate_cluster": duplicate_stats["largest_duplicate_cluster"],
        "duplicate_id_count": duplicate_id_count,
        "grounded_note_rate": graph_stats["grounded_count"] / canonical_count,
        "grounded_note_count": graph_stats["grounded_count"],
        "orphan_note_rate": graph_stats["orphan_count"] / canonical_count,
        "orphan_note_count": graph_stats["orphan_count"],
        "isolated_note_rate": graph_stats["isolated_count"] / canonical_count,
        "isolated_note_count": graph_stats["isolated_count"],
        "canonical_link_density": graph_stats["canonical_edge_count"] / canonical_count,
        "source_ref_density": graph_stats["source_ref_count"] / canonical_count,
        "parse_issue_count": integrity_codes.get("frontmatter_parse", 0),
        "broken_link_count": integrity_codes.get("broken_link", 0),
        "hard_constraint_issue_count": integrity_report["issue_count"],
    }


def _duplicate_count(values: list[str]) -> int:
    counts = Counter(values)
    return sum(count - 1 for count in counts.values() if count > 1)


def _duplicate_stats(canonical_notes: list[dict[str, Any]]) -> dict[str, int]:
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
        names = _note_identity_names(note)
        for name in names:
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

    duplicate_clusters = [members for members in components.values() if len(members) > 1]
    return {
        "duplicate_candidate_count": sum(len(cluster) - 1 for cluster in duplicate_clusters),
        "duplicate_cluster_count": len(duplicate_clusters),
        "largest_duplicate_cluster": max((len(cluster) for cluster in duplicate_clusters), default=1),
    }


def _canonical_graph_stats(notes: list[dict[str, Any]]) -> dict[str, int]:
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

    orphan_count = 0
    isolated_count = 0
    grounded_count = 0
    canonical_edge_count = 0
    source_ref_count = 0
    for key in path_keys:
        canonical_degree = len(outbound.get(key, set())) + len(inbound.get(key, set()))
        support_count = source_ref_counts.get(key, 0)
        if support_count > 0:
            grounded_count += 1
        if canonical_degree == 0 and support_count == 0:
            orphan_count += 1
        if canonical_degree == 0 and support_count <= 1:
            isolated_count += 1
        canonical_edge_count += len(outbound.get(key, set()))
        source_ref_count += support_count
    return {
        "grounded_count": grounded_count,
        "orphan_count": orphan_count,
        "isolated_count": isolated_count,
        "canonical_edge_count": canonical_edge_count,
        "source_ref_count": source_ref_count,
    }


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
        refs.update(_normalize_source_ref(ref) for ref in PRIMARY_SOURCE_RE.findall(bullet))
    return refs


def _normalize_source_ref(value: str) -> str:
    text = value.strip()
    if text.startswith("[[") and text.endswith("]]"):
        text = text[2:-2]
    return text


def _normalize(value: str) -> str:
    return value.strip().lower()
