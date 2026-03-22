"""Ingestion pipeline for files and conversations."""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .frontmatter import parse_frontmatter
from .indexer import index_vault
from .markdown import split_sections
from .providers import extract_with_provider
from .runtime_config import resolve_profile
from .utils import date_prefix_from_iso, slugify, stable_short_hash, title_from_path, utc_now_iso, year_from_date

STOPWORDS = {
    "about",
    "after",
    "also",
    "because",
    "between",
    "could",
    "every",
    "first",
    "from",
    "have",
    "into",
    "just",
    "more",
    "most",
    "only",
    "other",
    "over",
    "should",
    "some",
    "than",
    "that",
    "their",
    "there",
    "these",
    "they",
    "this",
    "through",
    "under",
    "what",
    "when",
    "where",
    "which",
    "while",
    "with",
    "would",
}

TITLECASE_ENTITY_RE = re.compile(r"\b([A-Z][a-z0-9]+(?:\s+[A-Z][a-z0-9]+){0,2})\b")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9-]{3,}")
HEADING_RE = re.compile(r"^\s*#\s+(.+?)\s*$", re.MULTILINE)
CONVERSATION_LINE_RE = re.compile(
    r"^\s*(?:(?P<ts>\d{4}-\d{2}-\d{2}T[0-9:.+-Z]+)\s*\|\s*)?(?P<speaker>[^:|]+?)\s*:\s*(?P<message>.+?)\s*$"
)
LOW_SIGNAL_TITLE_RE = re.compile(r"^(?:[a-z]|[a-z]\s+unresolved|diagram node [a-z])$", re.IGNORECASE)
LOW_INFORMATION_BLOCK_MARKERS = (
    "appendix",
    "boilerplate",
    "footer",
    "legal",
    "archival",
    "metadata",
    "mailing",
    "export",
    "marker",
    "unrelated archival",
)


@dataclass
class EvidenceBlock:
    anchor: str
    text: str
    source_ref: str
    speaker: str | None = None
    timestamp: str | None = None


@dataclass
class Claim:
    text: str
    source_ref: str
    confidence: str


@dataclass
class Relationship:
    text: str
    source_ref: str
    confidence: str


@dataclass
class NoteCandidate:
    note_type: str
    title: str
    canonical_slug: str
    confidence: str
    aliases: list[str] = field(default_factory=list)
    source_refs: list[str] = field(default_factory=list)
    claims: list[Claim] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)
    note_id: str | None = None
    kind: str | None = None


@dataclass
class SourceNotePlan:
    note_id: str
    note_type: str
    title: str
    path: str
    source_kind: str
    origin: str
    hash_sha256: str
    source_refs: list[str]
    metadata: dict[str, Any]
    content: str


@dataclass
class ExtractionPayload:
    source_note: SourceNotePlan
    evidence_blocks: list[EvidenceBlock]
    note_candidates: list[NoteCandidate]
    unresolved_candidates: list[NoteCandidate]
    stats: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PatchOperation:
    action: str
    path: str
    reason: str
    content: str


@dataclass
class IngestionPlan:
    payload: ExtractionPayload
    operations: list[PatchOperation]
    stats: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "payload": self.payload.to_dict(),
            "operations": [asdict(operation) for operation in self.operations],
            "stats": self.stats,
        }


@dataclass
class BatchFileResult:
    input_path: str
    extractor_profile: str
    create_count: int
    update_count: int
    noop_count: int
    operation_count: int
    status: str = "planned"
    skip_reason: str | None = None
    plan_path: str | None = None
    written_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExtractionWindow:
    window_id: str
    input_kind: str
    start_index: int
    end_index: int
    evidence_blocks: list[EvidenceBlock]
    estimated_chars: int
    strategy: str


def ingest_file(
    *,
    vault_root: Path,
    input_path: Path,
    origin: str | None = None,
    title: str | None = None,
    profile_name: str | None = None,
    model_override: str | None = None,
    config_root: Path | None = None,
) -> IngestionPlan:
    input_text = input_path.read_text(encoding="utf-8")
    if _is_effectively_empty_text(input_text):
        raise ValueError(f"Input file is empty: {input_path}")
    title = title or _extract_title(input_text) or title_from_path(input_path)
    origin = origin or "file"
    profile = resolve_profile(
        input_kind="file",
        profile_name=profile_name,
        model_override=model_override,
        config_root=config_root,
    )
    date_value = utc_now_iso()[:10]
    source_hash = stable_short_hash(str(input_path.resolve()), input_text, length=16)
    source_id = f"src_{source_hash[:8]}"
    slug = slugify(title)
    rel_path = f"sources/files/{year_from_date(date_value)}/{date_value}--{slug}--{source_id}.md"

    evidence_blocks = _make_file_evidence_blocks(rel_path, input_text)
    source_refs = [block.source_ref for block in evidence_blocks]
    source_note = SourceNotePlan(
        note_id=source_id,
        note_type="source",
        title=title,
        path=rel_path,
        source_kind="file",
        origin=origin,
        hash_sha256=source_hash,
        source_refs=source_refs,
        metadata={
            "id": source_id,
            "type": "source",
            "title": title,
            "aliases": [],
            "source_refs": source_refs,
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
            "managed_by": "autoknowledge",
            "schema_version": 1,
            "source_kind": "file",
            "origin": origin,
            "source_path": str(input_path),
            "mime_type": _guess_mime_type(input_path),
            "source_timestamp": "",
            "ingested_at": utc_now_iso(),
            "hash_sha256": source_hash,
        },
        content="",
    )
    source_note.content = render_source_note(source_note, evidence_blocks)
    same_source_reingest = _existing_source_note_matches_hash(
        vault_root=vault_root,
        path=rel_path,
        hash_sha256=source_hash,
    )
    payload = ExtractionPayload(
        source_note=source_note,
        evidence_blocks=evidence_blocks,
        note_candidates=[],
        unresolved_candidates=[],
        stats={
            "input_kind": "file",
            "evidence_block_count": len(evidence_blocks),
            "extractor_profile": profile["name"],
            "extractor_backend": profile.get("backend"),
            "extractor_model": profile.get("model"),
        },
    )
    note_candidates, unresolved_candidates, extraction_stats = _extract_file_candidates(
        vault_root, title, rel_path, evidence_blocks, input_text, profile, same_source_reingest
    )
    payload.note_candidates = note_candidates
    payload.unresolved_candidates = unresolved_candidates
    payload.stats.update(extraction_stats)
    return build_ingestion_plan(vault_root=vault_root, payload=payload)


def ingest_conversation(
    *,
    vault_root: Path,
    input_path: Path,
    origin: str | None = None,
    title: str | None = None,
    channel: str | None = None,
    profile_name: str | None = None,
    model_override: str | None = None,
    config_root: Path | None = None,
) -> IngestionPlan:
    input_text = input_path.read_text(encoding="utf-8")
    if _is_effectively_empty_text(input_text):
        raise ValueError(f"Conversation input is empty: {input_path}")
    parsed_messages = _parse_conversation_lines(input_text)
    title = title or _extract_title(input_text) or title_from_path(input_path)
    origin = origin or "conversation"
    profile = resolve_profile(
        input_kind="conversation",
        profile_name=profile_name,
        model_override=model_override,
        config_root=config_root,
    )
    channel = channel or "default"
    timestamps = [message["timestamp"] for message in parsed_messages if message["timestamp"]]
    date_value = date_prefix_from_iso(timestamps[0] if timestamps else None)
    source_hash = stable_short_hash(str(input_path.resolve()), input_text, length=16)
    conv_id = f"conv_{source_hash[:8]}"
    slug = slugify(title)
    rel_path = f"sources/conversations/{year_from_date(date_value)}/{date_value}--{slug}--{conv_id}.md"

    evidence_blocks = _make_conversation_evidence_blocks(rel_path, parsed_messages)
    source_refs = [block.source_ref for block in evidence_blocks]
    participants = sorted({message["speaker"] for message in parsed_messages if message["speaker"]})
    source_note = SourceNotePlan(
        note_id=conv_id,
        note_type="conversation",
        title=title,
        path=rel_path,
        source_kind="conversation",
        origin=origin,
        hash_sha256=source_hash,
        source_refs=source_refs,
        metadata={
            "id": conv_id,
            "type": "conversation",
            "title": title,
            "aliases": [],
            "source_refs": source_refs,
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
            "managed_by": "autoknowledge",
            "schema_version": 1,
            "source_kind": "conversation",
            "origin": origin,
            "participants": participants,
            "channel": channel,
            "source_timestamp_start": timestamps[0] if timestamps else "",
            "source_timestamp_end": timestamps[-1] if timestamps else "",
            "ingested_at": utc_now_iso(),
            "hash_sha256": source_hash,
        },
        content="",
    )
    source_note.content = render_conversation_note(source_note, evidence_blocks)
    same_source_reingest = _existing_source_note_matches_hash(
        vault_root=vault_root,
        path=rel_path,
        hash_sha256=source_hash,
    )
    payload = ExtractionPayload(
        source_note=source_note,
        evidence_blocks=evidence_blocks,
        note_candidates=[],
        unresolved_candidates=[],
        stats={
            "input_kind": "conversation",
            "evidence_block_count": len(evidence_blocks),
            "participant_count": len(participants),
            "extractor_profile": profile["name"],
            "extractor_backend": profile.get("backend"),
            "extractor_model": profile.get("model"),
        },
    )
    note_candidates, unresolved_candidates, extraction_stats = _extract_conversation_candidates(
        vault_root, title, rel_path, evidence_blocks, parsed_messages, profile, same_source_reingest
    )
    payload.note_candidates = note_candidates
    payload.unresolved_candidates = unresolved_candidates
    payload.stats.update(extraction_stats)
    return build_ingestion_plan(vault_root=vault_root, payload=payload)


def build_ingestion_plan(*, vault_root: Path, payload: ExtractionPayload) -> IngestionPlan:
    existing_index = index_vault(vault_root) if vault_root.exists() else {"notes": [], "by_path": {}}
    existing_notes = existing_index.get("by_path", {})
    source_content = payload.source_note.content
    if payload.source_note.path in existing_notes:
        source_content = merge_existing_source_note(vault_root=vault_root, existing_note=existing_notes[payload.source_note.path], source_note=payload.source_note)
    operations: list[PatchOperation] = []

    operations.append(
        _operation_for_path(
            existing_notes=existing_notes,
            path=payload.source_note.path,
            content=source_content,
            reason=f"{payload.source_note.note_type} note",
        )
    )

    for candidate in payload.note_candidates + payload.unresolved_candidates:
        note_path = _candidate_path(candidate)
        content = render_canonical_note(candidate, note_path)
        if note_path in existing_notes:
            content = merge_existing_canonical_note(vault_root=vault_root, existing_note=existing_notes[note_path], candidate=candidate)
        operations.append(
            _operation_for_path(
                existing_notes=existing_notes,
                path=note_path,
                content=content,
                reason=f"{candidate.note_type} candidate",
            )
        )

    stats = {
        "operation_count": len(operations),
        "create_count": sum(1 for op in operations if op.action == "create"),
        "update_count": sum(1 for op in operations if op.action == "update"),
        "noop_count": sum(1 for op in operations if op.action == "noop"),
        **payload.stats,
    }
    return IngestionPlan(payload=payload, operations=operations, stats=stats)


def apply_ingestion_plan(vault_root: Path, plan: IngestionPlan) -> dict[str, Any]:
    written = []
    for operation in plan.operations:
        if operation.action == "noop":
            continue
        path = vault_root / operation.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(operation.content, encoding="utf-8")
        written.append(operation.path)
    return {"written_paths": written, "written_count": len(written)}


def save_plan(plan: IngestionPlan, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(plan.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def ingest_files_directory(
    *,
    vault_root: Path,
    input_dir: Path,
    apply: bool = False,
    profile_name: str | None = None,
    model_override: str | None = None,
    config_root: Path | None = None,
    plan_dir: Path | None = None,
    limit: int | None = None,
    pattern: str = "*.md",
) -> dict[str, Any]:
    files = sorted(path for path in input_dir.rglob(pattern) if path.is_file())
    if limit is not None:
        files = files[:limit]

    file_results: list[BatchFileResult] = []
    total_written_count = 0
    skipped_count = 0
    preview_workspace: tempfile.TemporaryDirectory[str] | None = None
    planning_vault_root = vault_root

    try:
        if not apply:
            preview_workspace, planning_vault_root = _prepare_batch_preview_vault(vault_root)

        for input_path in files:
            if _is_effectively_empty_text(input_path.read_text(encoding="utf-8")):
                skipped_count += 1
                file_results.append(
                    BatchFileResult(
                        input_path=str(input_path),
                        extractor_profile=str(profile_name or ""),
                        create_count=0,
                        update_count=0,
                        noop_count=0,
                        operation_count=0,
                        status="skipped",
                        skip_reason="empty_input",
                        plan_path=None,
                        written_count=0,
                    )
                )
                continue
            plan = ingest_file(
                vault_root=planning_vault_root,
                input_path=input_path,
                profile_name=profile_name,
                model_override=model_override,
                config_root=config_root,
            )
            saved_plan_path = None
            if plan_dir is not None:
                saved_plan_path = plan_dir / f"{stable_short_hash(str(input_path.resolve()), length=12)}.json"
                saved_plan_path.parent.mkdir(parents=True, exist_ok=True)
                save_plan(plan, saved_plan_path)

            written_count = 0
            if apply:
                apply_result = apply_ingestion_plan(vault_root, plan)
                written_count = int(apply_result["written_count"])
                total_written_count += written_count
            else:
                apply_ingestion_plan(planning_vault_root, plan)

            file_results.append(
                BatchFileResult(
                    input_path=str(input_path),
                    extractor_profile=str(plan.stats.get("extractor_profile", "")),
                    create_count=int(plan.stats.get("create_count", 0)),
                    update_count=int(plan.stats.get("update_count", 0)),
                    noop_count=int(plan.stats.get("noop_count", 0)),
                    operation_count=int(plan.stats.get("operation_count", 0)),
                    status="applied" if apply else "planned",
                    skip_reason=None,
                    plan_path=str(saved_plan_path) if saved_plan_path is not None else None,
                    written_count=written_count,
                )
            )

        summary = {
            "input_dir": str(input_dir),
            "file_count": len(file_results),
            "apply": apply,
            "pattern": pattern,
            "skipped_count": skipped_count,
            "cumulative_preview": not apply,
            "create_count": sum(item.create_count for item in file_results),
            "update_count": sum(item.update_count for item in file_results),
            "noop_count": sum(item.noop_count for item in file_results),
            "operation_count": sum(item.operation_count for item in file_results),
            "written_count": total_written_count,
            "profiles_used": sorted({item.extractor_profile for item in file_results if item.extractor_profile}),
            "files": [item.to_dict() for item in file_results],
        }

        if apply:
            post_index = index_vault(vault_root)
            summary["check"] = {"issue_count": 0, "issues": []}
            from .integrity import validate_index

            summary["check"] = validate_index(post_index)
        return summary
    finally:
        if preview_workspace is not None:
            preview_workspace.cleanup()


def render_source_note(source_note: SourceNotePlan, evidence_blocks: list[EvidenceBlock]) -> str:
    frontmatter = _render_frontmatter(source_note.metadata)
    lines = [
        "---",
        frontmatter,
        "---",
        f"# {source_note.title}",
        "",
        "## Source Metadata",
        "",
        f"- Origin: {source_note.origin}",
        f"- Source Path: {source_note.metadata['source_path']}",
        f"- Ingested At: {source_note.metadata['ingested_at']}",
        "",
        "## Raw Content",
    ]
    for block in evidence_blocks:
        lines.extend(["", f"{block.text} ^{block.anchor}"])
    return "\n".join(lines).rstrip() + "\n"


def render_conversation_note(source_note: SourceNotePlan, evidence_blocks: list[EvidenceBlock]) -> str:
    frontmatter = _render_frontmatter(source_note.metadata)
    lines = [
        "---",
        frontmatter,
        "---",
        f"# {source_note.title}",
        "",
        "## Conversation Metadata",
        "",
        f"- Origin: {source_note.origin}",
        f"- Channel: {source_note.metadata['channel']}",
        f"- Participants: {', '.join(source_note.metadata['participants'])}",
        f"- Ingested At: {source_note.metadata['ingested_at']}",
        "",
        "## Transcript",
    ]
    for block in evidence_blocks:
        prefix = ""
        if block.timestamp:
            prefix += f"{block.timestamp} | "
        if block.speaker:
            prefix += f"{block.speaker}: "
        lines.append(f"- {prefix}{block.text} ^{block.anchor}")
    return "\n".join(lines).rstrip() + "\n"


def render_canonical_note(candidate: NoteCandidate, note_path: str) -> str:
    note_id = candidate.note_id or _default_note_id(candidate)
    metadata = {
        "id": note_id,
        "type": candidate.note_type,
        "title": candidate.title,
        "aliases": candidate.aliases,
        "source_refs": candidate.source_refs,
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
        "managed_by": "autoknowledge",
        "schema_version": 1,
        "canonical_slug": candidate.canonical_slug,
        "confidence": candidate.confidence,
        "status": "unresolved" if candidate.note_type == "unresolved" else "active",
    }
    if candidate.note_type == "entity":
        metadata["entity_kind"] = candidate.kind or "unknown"
    elif candidate.note_type == "concept":
        metadata["concept_kind"] = candidate.kind or "unknown"
    elif candidate.note_type == "topic":
        pass
    elif candidate.note_type == "unresolved":
        metadata["candidate_targets"] = []
        metadata["resolution_status"] = "unresolved"

    frontmatter = _render_frontmatter(metadata)
    lines = [
        "---",
        frontmatter,
        "---",
        f"# {candidate.title}",
        "",
        "## Summary",
        "",
        "## Claims",
    ]
    for claim in candidate.claims:
        lines.append(f"- {claim.text} Source: {claim.source_ref} Confidence: {claim.confidence}")
    lines.extend(["", "## Relationships"])
    for relation in candidate.relationships:
        lines.append(f"- {relation.text} Source: {relation.source_ref} Confidence: {relation.confidence}")
    lines.extend(["", "## Open Questions", ""])
    return "\n".join(lines)


def merge_existing_canonical_note(*, vault_root: Path, existing_note: dict[str, Any], candidate: NoteCandidate) -> str:
    raw_text = (vault_root / existing_note["path"]).read_text(encoding="utf-8")
    metadata, body, _ = parse_frontmatter(raw_text)
    sections = split_sections(body)
    original_source_refs = set(metadata.get("source_refs", []))
    original_source_docs = {_source_ref_document(item) for item in original_source_refs if _source_ref_document(item)}
    candidate_source_docs = {_source_ref_document(item) for item in candidate.source_refs if _source_ref_document(item)}
    only_known_source_refs = bool(candidate.source_refs) and set(candidate.source_refs).issubset(original_source_refs)
    only_known_source_docs = bool(candidate_source_docs) and candidate_source_docs.issubset(original_source_docs)
    same_source_reingest = only_known_source_refs or only_known_source_docs

    aliases = (
        list(metadata.get("aliases", []))
        if same_source_reingest
        else _merge_unique_list(metadata.get("aliases", []), candidate.aliases)
    )
    if same_source_reingest:
        source_refs = list(metadata.get("source_refs", []))
    else:
        filtered_candidate_source_refs = []
        for item in candidate.source_refs:
            if item in original_source_refs:
                continue
            item_doc = _source_ref_document(item)
            if item_doc and item_doc in original_source_docs:
                continue
            filtered_candidate_source_refs.append(item)
        source_refs = _merge_unique_list(metadata.get("source_refs", []), filtered_candidate_source_refs)
    changed = aliases != list(metadata.get("aliases", [])) or source_refs != list(metadata.get("source_refs", []))
    metadata["aliases"] = aliases
    metadata["source_refs"] = source_refs
    if "canonical_slug" in metadata:
        metadata["canonical_slug"] = metadata.get("canonical_slug") or candidate.canonical_slug
    if "confidence" in metadata and not same_source_reingest:
        merged_confidence = _max_confidence(str(metadata.get("confidence", "low")), candidate.confidence)
        if merged_confidence != metadata.get("confidence"):
            changed = True
        metadata["confidence"] = merged_confidence

    summary_lines = _section_lines(sections, "Summary")
    claims_lines = _section_lines(sections, "Claims")
    relationship_lines = _section_lines(sections, "Relationships")
    open_questions_lines = _section_lines(sections, "Open Questions")
    contradictions_lines = _section_lines(sections, "Contradictions")

    existing_claims = {line.strip() for line in claims_lines if line.strip().startswith("- ")}
    existing_claim_source_refs = _bullet_source_refs(claims_lines)
    existing_claim_source_docs = {_source_ref_document(item) for item in existing_claim_source_refs if _source_ref_document(item)}
    for claim in candidate.claims:
        line = f"- {claim.text} Source: {claim.source_ref} Confidence: {claim.confidence}"
        if line in existing_claims:
            continue
        claim_source_doc = _source_ref_document(claim.source_ref)
        if (
            claim.source_ref in original_source_refs
            or claim.source_ref in existing_claim_source_refs
            or (claim_source_doc and claim_source_doc in original_source_docs)
            or (claim_source_doc and claim_source_doc in existing_claim_source_docs)
        ):
            continue
        claims_lines.append(line)
        existing_claim_source_refs.add(claim.source_ref)
        if claim_source_doc:
            existing_claim_source_docs.add(claim_source_doc)
        changed = True

    existing_relationships = {line.strip() for line in relationship_lines if line.strip().startswith("- ")}
    existing_relationship_source_refs = _bullet_source_refs(relationship_lines)
    existing_relationship_source_docs = {
        _source_ref_document(item) for item in existing_relationship_source_refs if _source_ref_document(item)
    }
    for relation in candidate.relationships:
        line = f"- {relation.text} Source: {relation.source_ref} Confidence: {relation.confidence}"
        if line in existing_relationships:
            continue
        relation_source_doc = _source_ref_document(relation.source_ref)
        if (
            relation.source_ref in original_source_refs
            or relation.source_ref in existing_relationship_source_refs
            or (relation_source_doc and relation_source_doc in original_source_docs)
            or (relation_source_doc and relation_source_doc in existing_relationship_source_docs)
        ):
            continue
        relationship_lines.append(line)
        existing_relationship_source_refs.add(relation.source_ref)
        if relation_source_doc:
            existing_relationship_source_docs.add(relation_source_doc)
        changed = True

    if not changed:
        return raw_text

    metadata["updated_at"] = utc_now_iso()

    lines = [
        "---",
        _render_frontmatter(metadata),
        "---",
        f"# {metadata.get('title', candidate.title)}",
        "",
        "## Summary",
    ]
    lines.extend(summary_lines or [""])
    lines.extend(["", "## Claims"])
    lines.extend(claims_lines or [""])
    lines.extend(["", "## Relationships"])
    lines.extend(relationship_lines or [""])
    if contradictions_lines:
        lines.extend(["", "## Contradictions"])
        lines.extend(contradictions_lines)
    lines.extend(["", "## Open Questions"])
    lines.extend(open_questions_lines or [""])
    return "\n".join(lines).rstrip() + "\n"


def merge_existing_source_note(*, vault_root: Path, existing_note: dict[str, Any], source_note: SourceNotePlan) -> str:
    raw_text = (vault_root / existing_note["path"]).read_text(encoding="utf-8")
    metadata, _, _ = parse_frontmatter(raw_text)
    if metadata.get("hash_sha256") == source_note.hash_sha256:
        return raw_text
    return source_note.content


def _candidate_path(candidate: NoteCandidate) -> str:
    if candidate.note_type == "entity":
        return f"entities/{candidate.canonical_slug}.md"
    if candidate.note_type == "concept":
        return f"concepts/{candidate.canonical_slug}.md"
    if candidate.note_type == "topic":
        return f"topics/{candidate.canonical_slug}.md"
    if candidate.note_type == "unresolved":
        date_value = utc_now_iso()[:10]
        short_id = stable_short_hash(candidate.title, candidate.canonical_slug, length=8)
        return f"inbox/unresolved/{date_value}--{candidate.canonical_slug}--unres_{short_id}.md"
    raise ValueError(f"Unsupported candidate type: {candidate.note_type}")


def _operation_for_path(*, existing_notes: dict[str, Any], path: str, content: str, reason: str) -> PatchOperation:
    existing = existing_notes.get(path)
    action = "update" if existing else "create"
    if existing and existing.get("content_hash") == _sha256(content):
        action = "noop"
    return PatchOperation(action=action, path=path, reason=reason, content=content)


def _extract_file_candidates(
    vault_root: Path,
    title: str,
    source_path: str,
    evidence_blocks: list[EvidenceBlock],
    input_text: str,
    profile: dict[str, Any],
    same_source_reingest: bool = False,
) -> tuple[list[NoteCandidate], list[NoteCandidate], dict[str, Any]]:
    windows, window_stats = _plan_extraction_windows(
        input_kind="file",
        title=title,
        evidence_blocks=evidence_blocks,
        profile=profile,
    )
    backend = profile.get("backend")
    if backend != "deterministic":
        provider_candidates, provider_unresolved, provider_stats = _extract_provider_windowed_candidates(
            profile=profile,
            input_kind="file",
            title=title,
            source_path=source_path,
            windows=windows,
            window_stats=window_stats,
        )
        deterministic_candidates: list[NoteCandidate] = []
        for window in windows:
            deterministic_candidates.extend(
                _deterministic_file_candidates_for_window(
                    title=title,
                    source_path=source_path,
                    evidence_blocks=window.evidence_blocks,
                    input_text=_window_text(window.evidence_blocks),
                    profile={"options": profile.get("options", {})},
                )
            )
        stabilized_candidates, stabilized_unresolved, stabilization_stats = _stabilize_live_candidates(
            vault_root=vault_root,
            note_candidates=provider_candidates,
            unresolved_candidates=provider_unresolved,
            deterministic_candidates=_merge_note_candidates(deterministic_candidates),
            evidence_blocks=evidence_blocks,
            allow_provider_only_candidates=not same_source_reingest,
        )
        return stabilized_candidates, stabilized_unresolved, {**provider_stats, **stabilization_stats}
    candidates: list[NoteCandidate] = []
    for window in windows:
        window_text = _window_text(window.evidence_blocks)
        candidates.extend(
            _deterministic_file_candidates_for_window(
                title=title,
                source_path=source_path,
                evidence_blocks=window.evidence_blocks,
                input_text=window_text,
                profile=profile,
            )
        )
    return _merge_note_candidates(candidates), [], window_stats


def _extract_conversation_candidates(
    vault_root: Path,
    title: str,
    source_path: str,
    evidence_blocks: list[EvidenceBlock],
    parsed_messages: list[dict[str, str]],
    profile: dict[str, Any],
    same_source_reingest: bool = False,
) -> tuple[list[NoteCandidate], list[NoteCandidate], dict[str, Any]]:
    windows, window_stats = _plan_extraction_windows(
        input_kind="conversation",
        title=title,
        evidence_blocks=evidence_blocks,
        profile=profile,
    )
    backend = profile.get("backend")
    if backend != "deterministic":
        provider_candidates, provider_unresolved, provider_stats = _extract_provider_windowed_candidates(
            profile=profile,
            input_kind="conversation",
            title=title,
            source_path=source_path,
            windows=windows,
            window_stats=window_stats,
        )
        deterministic_candidates: list[NoteCandidate] = []
        for window in windows:
            deterministic_candidates.extend(
                _deterministic_conversation_candidates_for_window(
                    title=title,
                    source_path=source_path,
                    evidence_blocks=window.evidence_blocks,
                    profile={"options": profile.get("options", {})},
                )
            )
        stabilized_candidates, stabilized_unresolved, stabilization_stats = _stabilize_live_candidates(
            vault_root=vault_root,
            note_candidates=provider_candidates,
            unresolved_candidates=provider_unresolved,
            deterministic_candidates=_merge_note_candidates(deterministic_candidates),
            evidence_blocks=evidence_blocks,
            allow_provider_only_candidates=not same_source_reingest,
        )
        return stabilized_candidates, stabilized_unresolved, {**provider_stats, **stabilization_stats}
    candidates: list[NoteCandidate] = []
    for window in windows:
        candidates.extend(
            _deterministic_conversation_candidates_for_window(
                title=title,
                source_path=source_path,
                evidence_blocks=window.evidence_blocks,
                profile=profile,
            )
        )
    return _merge_note_candidates(candidates), [], window_stats


def _extract_provider_windowed_candidates(
    *,
    profile: dict[str, Any],
    input_kind: str,
    title: str,
    source_path: str,
    windows: list[ExtractionWindow],
    window_stats: dict[str, Any],
) -> tuple[list[NoteCandidate], list[NoteCandidate], dict[str, Any]]:
    merged_candidates: list[NoteCandidate] = []
    merged_unresolved: list[NoteCandidate] = []
    provider_name = ""
    response_ids: list[str] = []

    for idx, window in enumerate(windows, start=1):
        result = extract_with_provider(
            profile=profile,
            input_kind=input_kind,
            title=title,
            source_path=source_path,
            evidence_blocks=[asdict(block) for block in window.evidence_blocks],
            window_context={
                "window_index": idx,
                "window_count": len(windows),
                "window_id": window.window_id,
                "start_anchor": window.evidence_blocks[0].anchor if window.evidence_blocks else "",
                "end_anchor": window.evidence_blocks[-1].anchor if window.evidence_blocks else "",
                "estimated_chars": window.estimated_chars,
                "strategy": window.strategy,
            },
        )
        note_candidates, unresolved_candidates = _normalize_provider_result(result, window.evidence_blocks)
        merged_candidates.extend(note_candidates)
        merged_unresolved.extend(unresolved_candidates)
        provider_name = result.get("_provider_response", {}).get("provider", provider_name)
        response_id = str(result.get("_provider_response", {}).get("response_id", "")).strip()
        if response_id:
            response_ids.append(response_id)

    stats = {
        **window_stats,
        "provider_name": provider_name,
        "provider_call_count": len(windows),
    }
    if response_ids:
        stats["provider_response_ids"] = response_ids
    return _merge_note_candidates(merged_candidates), _merge_note_candidates(merged_unresolved), stats


def _deterministic_file_candidates_for_window(
    *,
    title: str,
    source_path: str,
    evidence_blocks: list[EvidenceBlock],
    input_text: str,
    profile: dict[str, Any],
) -> list[NoteCandidate]:
    candidates: dict[tuple[str, str], NoteCandidate] = {}
    source_link = f"[[{source_path[:-3]}]]"
    headings = _extract_headings(input_text)
    options = profile.get("options", {})
    entity_titles = _extract_titlecase_entities(input_text, max_items=int(options.get("max_titlecase_entities", 10)))
    blocked_keywords = _blocked_keyword_tokens([title, *headings, *entity_titles])

    if options.get("create_heading_concepts", True):
        for heading in headings:
            _upsert_candidate(
                candidates,
                note_type="concept",
                title=heading,
                confidence="medium",
                source_ref=evidence_blocks[0].source_ref if evidence_blocks else "",
                relationship_text=f"mentioned_in -> {source_link}",
                kind="heading",
            )

    for titlecase in entity_titles:
        if slugify(titlecase) == slugify(title):
            continue
        evidence = _best_evidence_for_text(titlecase, evidence_blocks)
        _upsert_candidate(
            candidates,
            note_type="entity",
            title=titlecase,
            confidence="medium",
            source_ref=evidence.source_ref if evidence else (evidence_blocks[0].source_ref if evidence_blocks else ""),
            relationship_text=f"mentioned_in -> {source_link}",
            kind="named_entity",
        )

    for concept in _extract_keywords(
        input_text,
        limit=int(options.get("max_keywords_file", 4)),
        exclude=blocked_keywords,
        min_count=int(options.get("keyword_min_count", 2)),
        allow_hyphen_keywords=bool(options.get("allow_hyphen_keywords", True)),
    ):
        evidence = _best_evidence_for_text(concept, evidence_blocks)
        _upsert_candidate(
            candidates,
            note_type="concept",
            title=concept.title(),
            confidence="low",
            source_ref=evidence.source_ref if evidence else (evidence_blocks[0].source_ref if evidence_blocks else ""),
            relationship_text=f"mentioned_in -> {source_link}",
            kind="keyword",
        )

    if not candidates and evidence_blocks:
        _upsert_candidate(
            candidates,
            note_type="concept",
            title=title,
            confidence="low",
            source_ref=evidence_blocks[0].source_ref,
            relationship_text=f"mentioned_in -> {source_link}",
            kind="source_title",
        )

    return sorted(candidates.values(), key=lambda item: (item.note_type, item.canonical_slug))


def _deterministic_conversation_candidates_for_window(
    *,
    title: str,
    source_path: str,
    evidence_blocks: list[EvidenceBlock],
    profile: dict[str, Any],
) -> list[NoteCandidate]:
    candidates: dict[tuple[str, str], NoteCandidate] = {}
    source_link = f"[[{source_path[:-3]}]]"
    options = profile.get("options", {})

    speaker_first_ref: dict[str, str] = {}
    if options.get("extract_people_from_speakers", True):
        for block in evidence_blocks:
            if block.speaker and block.speaker not in speaker_first_ref:
                speaker_first_ref[block.speaker] = block.source_ref

    for speaker, source_ref in speaker_first_ref.items():
        _upsert_candidate(
            candidates,
            note_type="entity",
            title=speaker,
            confidence="high",
            source_ref=source_ref,
            relationship_text=f"participated_in -> {source_link}",
            kind="person",
            aliases=[speaker.lower()] if speaker.lower() != speaker else [],
        )

    all_text = "\n".join(block.text for block in evidence_blocks)
    blocked_keywords = _blocked_keyword_tokens([title, *speaker_first_ref.keys()])
    for concept in _extract_keywords(
        all_text,
        limit=int(options.get("max_keywords_conversation", 5)),
        exclude=blocked_keywords,
        min_count=int(options.get("keyword_min_count", 2)),
        allow_hyphen_keywords=bool(options.get("allow_hyphen_keywords", True)),
    ):
        evidence = _best_evidence_for_text(concept, evidence_blocks)
        _upsert_candidate(
            candidates,
            note_type="concept",
            title=concept.title(),
            confidence="low",
            source_ref=evidence.source_ref if evidence else (evidence_blocks[0].source_ref if evidence_blocks else ""),
            relationship_text=f"mentioned_in -> {source_link}",
            kind="keyword",
        )

    if evidence_blocks and options.get("create_conversation_topic", True):
        _upsert_candidate(
            candidates,
            note_type="topic",
            title=title,
            confidence="medium",
            source_ref=evidence_blocks[0].source_ref,
            relationship_text=f"described_by -> {source_link}",
            kind="conversation_topic",
        )

    return sorted(candidates.values(), key=lambda item: (item.note_type, item.canonical_slug))


def _plan_extraction_windows(
    *,
    input_kind: str,
    title: str,
    evidence_blocks: list[EvidenceBlock],
    profile: dict[str, Any],
) -> tuple[list[ExtractionWindow], dict[str, Any]]:
    options = profile.get("options", {})
    windowing_enabled = bool(options.get("windowing_enabled", True))
    max_window_chars = max(1, int(options.get("max_window_chars", 12000)))
    default_max_blocks = 24 if input_kind == "file" else 40
    default_overlap_blocks = 2 if input_kind == "file" else 4
    max_window_blocks = max(1, int(options.get(f"max_window_blocks_{input_kind}", default_max_blocks)))
    overlap_blocks = max(0, int(options.get(f"window_overlap_blocks_{input_kind}", default_overlap_blocks)))
    total_estimated_chars = sum(_estimated_block_size(block) for block in evidence_blocks)

    if not evidence_blocks:
        return [], {
            "windowed": False,
            "window_count": 0,
            "window_strategy": "empty",
            "window_max_chars": max_window_chars,
            "window_max_blocks": max_window_blocks,
            "window_overlap_blocks": overlap_blocks,
            "window_title": title,
        }

    if not windowing_enabled or (
        len(evidence_blocks) <= max_window_blocks and total_estimated_chars <= max_window_chars
    ):
        full_window = ExtractionWindow(
            window_id=f"{input_kind}_w01",
            input_kind=input_kind,
            start_index=0,
            end_index=len(evidence_blocks),
            evidence_blocks=evidence_blocks,
            estimated_chars=total_estimated_chars,
            strategy="full_context",
        )
        return [full_window], {
            "windowed": False,
            "window_count": 1,
            "window_strategy": "full_context",
            "window_max_chars": max_window_chars,
            "window_max_blocks": max_window_blocks,
            "window_overlap_blocks": overlap_blocks,
            "window_title": title,
        }

    prefer_split_starts = _preferred_window_starts(input_kind, evidence_blocks)
    strategy = "heading_windows" if input_kind == "file" and prefer_split_starts else "block_windows"
    if input_kind == "conversation":
        strategy = "turn_windows"
    windows = _plan_block_windows(
        evidence_blocks=evidence_blocks,
        input_kind=input_kind,
        max_window_chars=max_window_chars,
        max_window_blocks=max_window_blocks,
        overlap_blocks=overlap_blocks,
        prefer_split_starts=prefer_split_starts,
        strategy=strategy,
    )
    return windows, {
        "windowed": True,
        "window_count": len(windows),
        "window_strategy": strategy,
        "window_max_chars": max_window_chars,
        "window_max_blocks": max_window_blocks,
        "window_overlap_blocks": overlap_blocks,
        "window_title": title,
        "window_estimated_chars": [window.estimated_chars for window in windows],
        "window_anchor_ranges": [
            f"{window.evidence_blocks[0].anchor}:{window.evidence_blocks[-1].anchor}"
            for window in windows
            if window.evidence_blocks
        ],
    }


def _preferred_window_starts(input_kind: str, evidence_blocks: list[EvidenceBlock]) -> list[int]:
    if input_kind != "file":
        return []
    return [
        index
        for index, block in enumerate(evidence_blocks)
        if index > 0 and block.text.lstrip().startswith("#")
    ]


def _plan_block_windows(
    *,
    evidence_blocks: list[EvidenceBlock],
    input_kind: str,
    max_window_chars: int,
    max_window_blocks: int,
    overlap_blocks: int,
    prefer_split_starts: list[int],
    strategy: str,
) -> list[ExtractionWindow]:
    windows: list[ExtractionWindow] = []
    preferred = sorted(index for index in prefer_split_starts if 0 < index < len(evidence_blocks))
    preferred_set = set(preferred)
    start = 0

    while start < len(evidence_blocks):
        end = start
        estimated_chars = 0
        last_preferred_end: int | None = None

        while end < len(evidence_blocks):
            block_size = _estimated_block_size(evidence_blocks[end])
            next_block_count = end - start + 1
            if end > start and (next_block_count > max_window_blocks or estimated_chars + block_size > max_window_chars):
                break
            estimated_chars += block_size
            end += 1
            if end in preferred_set and end > start:
                last_preferred_end = end

        if end < len(evidence_blocks) and last_preferred_end is not None:
            end = last_preferred_end

        if end <= start:
            end = min(start + 1, len(evidence_blocks))

        window_blocks = evidence_blocks[start:end]
        windows.append(
            ExtractionWindow(
                window_id=f"{input_kind}_w{len(windows) + 1:02d}",
                input_kind=input_kind,
                start_index=start,
                end_index=end,
                evidence_blocks=window_blocks,
                estimated_chars=sum(_estimated_block_size(block) for block in window_blocks),
                strategy=strategy,
            )
        )

        if end >= len(evidence_blocks):
            break
        start = max(start + 1, end - overlap_blocks)

    return windows


def _window_text(evidence_blocks: list[EvidenceBlock]) -> str:
    return "\n\n".join(block.text for block in evidence_blocks if block.text)


def _estimated_block_size(block: EvidenceBlock) -> int:
    overhead = 48
    if block.speaker:
        overhead += len(block.speaker)
    if block.timestamp:
        overhead += len(block.timestamp)
    return len(block.text) + len(block.source_ref) + overhead


def _is_effectively_empty_text(text: str) -> bool:
    return not text.strip()


def _prepare_batch_preview_vault(vault_root: Path) -> tuple[tempfile.TemporaryDirectory[str], Path]:
    preview_workspace = tempfile.TemporaryDirectory(prefix="autoknowledge_batch_preview_")
    preview_root = Path(preview_workspace.name) / "vault"
    if vault_root.exists():
        shutil.copytree(vault_root, preview_root, dirs_exist_ok=True)
    else:
        preview_root.mkdir(parents=True, exist_ok=True)
    return preview_workspace, preview_root


def _merge_note_candidates(candidates: list[NoteCandidate]) -> list[NoteCandidate]:
    merged: dict[tuple[str, str], NoteCandidate] = {}
    for incoming in candidates:
        key = (incoming.note_type, incoming.canonical_slug)
        existing = merged.get(key)
        if existing is None:
            merged[key] = NoteCandidate(
                note_type=incoming.note_type,
                title=incoming.title,
                canonical_slug=incoming.canonical_slug,
                confidence=incoming.confidence,
                aliases=list(incoming.aliases),
                source_refs=list(incoming.source_refs),
                claims=[Claim(text=item.text, source_ref=item.source_ref, confidence=item.confidence) for item in incoming.claims],
                relationships=[
                    Relationship(text=item.text, source_ref=item.source_ref, confidence=item.confidence)
                    for item in incoming.relationships
                ],
                note_id=incoming.note_id,
                kind=incoming.kind,
            )
            continue

        if len(incoming.title) > len(existing.title):
            existing.title = incoming.title
        existing.confidence = _max_confidence(existing.confidence, incoming.confidence)
        if (not existing.kind or existing.kind == "unknown") and incoming.kind:
            existing.kind = incoming.kind
        existing.aliases = _merge_unique_list(existing.aliases, incoming.aliases)
        existing.source_refs = _merge_unique_list(existing.source_refs, incoming.source_refs)

        existing_claims = {(item.text, item.source_ref) for item in existing.claims}
        for item in incoming.claims:
            key_claim = (item.text, item.source_ref)
            if key_claim not in existing_claims:
                existing.claims.append(Claim(text=item.text, source_ref=item.source_ref, confidence=item.confidence))
                existing_claims.add(key_claim)
                if item.source_ref not in existing.source_refs:
                    existing.source_refs.append(item.source_ref)

        existing_relationships = {(item.text, item.source_ref) for item in existing.relationships}
        for item in incoming.relationships:
            key_rel = (item.text, item.source_ref)
            if key_rel not in existing_relationships:
                existing.relationships.append(Relationship(text=item.text, source_ref=item.source_ref, confidence=item.confidence))
                existing_relationships.add(key_rel)
                if item.source_ref not in existing.source_refs:
                    existing.source_refs.append(item.source_ref)

    return [
        candidate
        for candidate in sorted(merged.values(), key=lambda item: (item.note_type, item.canonical_slug))
        if candidate.source_refs
    ]


def _upsert_candidate(
    candidates: dict[tuple[str, str], NoteCandidate],
    *,
    note_type: str,
    title: str,
    confidence: str,
    source_ref: str,
    relationship_text: str,
    kind: str,
    aliases: list[str] | None = None,
) -> None:
    title = " ".join(title.split()).strip()
    if not title:
        return
    slug = slugify(title)
    key = (note_type, slug)
    candidate = candidates.get(key)
    if candidate is None:
        candidate = NoteCandidate(
            note_type=note_type,
            title=title,
            canonical_slug=slug,
            confidence=confidence,
            aliases=aliases or [],
            source_refs=[source_ref] if source_ref else [],
            claims=[],
            relationships=[],
            note_id=_default_note_id_for_type(note_type, slug),
            kind=kind,
        )
        candidates[key] = candidate
    else:
        for alias in aliases or []:
            if alias and alias not in candidate.aliases:
                candidate.aliases.append(alias)
        if source_ref and source_ref not in candidate.source_refs:
            candidate.source_refs.append(source_ref)
        candidate.confidence = _max_confidence(candidate.confidence, confidence)

    if source_ref and not any(rel.text == relationship_text and rel.source_ref == source_ref for rel in candidate.relationships):
        candidate.relationships.append(Relationship(text=relationship_text, source_ref=source_ref, confidence=confidence))


def _extract_headings(text: str) -> list[str]:
    headings = []
    for match in HEADING_RE.finditer(text):
        heading = match.group(1).strip()
        if heading:
            headings.append(heading)
    return headings


def _extract_title(text: str) -> str | None:
    headings = _extract_headings(text)
    return headings[0] if headings else None


def _extract_titlecase_entities(text: str, *, max_items: int) -> list[str]:
    items = []
    seen = set()
    for match in TITLECASE_ENTITY_RE.finditer(text):
        title = match.group(1).strip()
        if len(title) < 4:
            continue
        if title.lower() in STOPWORDS:
            continue
        key = title.lower()
        if key not in seen:
            seen.add(key)
            items.append(title)
    return items[:max_items]


def _extract_keywords(
    text: str,
    *,
    limit: int,
    exclude: set[str] | None = None,
    min_count: int,
    allow_hyphen_keywords: bool,
) -> list[str]:
    counts: dict[str, int] = {}
    exclude = exclude or set()
    for token in WORD_RE.findall(text.lower()):
        if token in STOPWORDS:
            continue
        if token in exclude:
            continue
        counts[token] = counts.get(token, 0) + 1
    ranked = sorted(
        (
            (token, count)
            for token, count in counts.items()
            if count >= min_count or (allow_hyphen_keywords and "-" in token)
        ),
        key=lambda item: (-item[1], item[0]),
    )
    return [token for token, _ in ranked[:limit]]


def _best_evidence_for_text(needle: str, evidence_blocks: list[EvidenceBlock]) -> EvidenceBlock | None:
    needle_lower = needle.lower()
    for block in evidence_blocks:
        if needle_lower in block.text.lower():
            return block
    return evidence_blocks[0] if evidence_blocks else None


def _blocked_keyword_tokens(texts: list[str]) -> set[str]:
    blocked = set()
    for text in texts:
        for token in WORD_RE.findall(text.lower()):
            blocked.add(token)
    return blocked


def _make_file_evidence_blocks(source_path: str, text: str) -> list[EvidenceBlock]:
    blocks = []
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    for idx, paragraph in enumerate(paragraphs, start=1):
        anchor = f"e{idx:04d}"
        blocks.append(
            EvidenceBlock(
                anchor=anchor,
                text=" ".join(paragraph.splitlines()).strip(),
                source_ref=f"[[{source_path[:-3]}#^{anchor}]]",
            )
        )
    return blocks


def _parse_conversation_lines(text: str) -> list[dict[str, str]]:
    messages = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = CONVERSATION_LINE_RE.match(line)
        if match:
            speaker = " ".join(match.group("speaker").split()).title()
            messages.append(
                {
                    "timestamp": match.group("ts") or "",
                    "speaker": speaker,
                    "message": match.group("message").strip(),
                }
            )
        else:
            messages.append({"timestamp": "", "speaker": "Unknown", "message": line})
    return messages


def _make_conversation_evidence_blocks(source_path: str, messages: list[dict[str, str]]) -> list[EvidenceBlock]:
    blocks = []
    for idx, message in enumerate(messages, start=1):
        anchor = f"m{idx:04d}"
        blocks.append(
            EvidenceBlock(
                anchor=anchor,
                text=message["message"],
                source_ref=f"[[{source_path[:-3]}#^{anchor}]]",
                speaker=message["speaker"],
                timestamp=message["timestamp"],
            )
        )
    return blocks


def _render_frontmatter(metadata: dict[str, Any]) -> str:
    lines = []
    ordered_keys = [
        "id",
        "type",
        "title",
        "aliases",
        "source_refs",
        "created_at",
        "updated_at",
        "managed_by",
        "schema_version",
        "source_kind",
        "origin",
        "source_path",
        "mime_type",
        "source_timestamp",
        "participants",
        "channel",
        "source_timestamp_start",
        "source_timestamp_end",
        "ingested_at",
        "hash_sha256",
        "entity_kind",
        "concept_kind",
        "canonical_slug",
        "confidence",
        "status",
        "candidate_targets",
        "resolution_status",
    ]
    for key in ordered_keys:
        if key not in metadata:
            continue
        lines.append(f"{key}: {_render_value(metadata[key])}")
    for key in sorted(metadata):
        if key in ordered_keys:
            continue
        lines.append(f"{key}: {_render_value(metadata[key])}")
    return "\n".join(lines)


def _render_value(value: Any) -> str:
    if isinstance(value, list):
        if not value:
            return "[]"
        inner = ", ".join(json.dumps(item) for item in value)
        return f"[{inner}]"
    if isinstance(value, int):
        return str(value)
    return json.dumps(value)


def _guess_mime_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".md":
        return "text/markdown"
    if suffix == ".txt":
        return "text/plain"
    if suffix == ".json":
        return "application/json"
    return "text/plain"


def _default_note_id(candidate: NoteCandidate) -> str:
    return candidate.note_id or _default_note_id_for_type(candidate.note_type, candidate.canonical_slug)


def _default_note_id_for_type(note_type: str, slug: str) -> str:
    prefix_map = {
        "entity": "ent",
        "concept": "con",
        "topic": "top",
        "unresolved": "unres",
    }
    prefix = prefix_map[note_type]
    return f"{prefix}_{stable_short_hash(note_type, slug, length=8)}"


def _max_confidence(left: str, right: str) -> str:
    order = {"low": 0, "medium": 1, "high": 2}
    return left if order.get(left, 0) >= order.get(right, 0) else right


def _sha256(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _merge_unique_list(existing: Any, incoming: list[str]) -> list[str]:
    result = []
    seen = set()
    for item in list(existing or []) + list(incoming or []):
        if not item:
            continue
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _section_lines(sections: dict[str, list[str]], name: str) -> list[str]:
    lines = list(sections.get(name, []))
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def _bullet_source_refs(lines: list[str]) -> set[str]:
    refs = set()
    for line in lines:
        if " Source: " not in line or " Confidence: " not in line:
            continue
        _, remainder = line.split(" Source: ", 1)
        source_ref, _ = remainder.split(" Confidence: ", 1)
        refs.add(source_ref.strip())
    return refs


def _source_ref_document(value: str) -> str:
    text = value.strip()
    if "#^" in text:
        text = text.split("#^", 1)[0]
    if "|" in text:
        text = text.split("|", 1)[0]
    if text.startswith("[["):
        text = text[2:]
    if text.endswith("]]"):
        text = text[:-2]
    return text.strip()


def _existing_source_note_matches_hash(*, vault_root: Path, path: str, hash_sha256: str) -> bool:
    note_path = vault_root / path
    if not note_path.exists():
        return False
    raw_text = note_path.read_text(encoding="utf-8")
    metadata, _, _ = parse_frontmatter(raw_text)
    return str(metadata.get("hash_sha256", "")).strip() == hash_sha256


def _normalize_provider_result(
    result: dict[str, Any],
    evidence_blocks: list[EvidenceBlock],
) -> tuple[list[NoteCandidate], list[NoteCandidate]]:
    valid_source_refs = {block.source_ref for block in evidence_blocks}
    note_candidates = _normalize_candidate_list(result.get("note_candidates", []), valid_source_refs)
    unresolved_candidates = _normalize_candidate_list(result.get("unresolved_candidates", []), valid_source_refs)
    block_lookup = {block.source_ref: block for block in evidence_blocks}
    note_candidates = _drop_low_information_candidates(note_candidates, block_lookup)
    unresolved_candidates = _drop_low_information_candidates(unresolved_candidates, block_lookup)
    return note_candidates, unresolved_candidates


def _stabilize_live_candidates(
    *,
    vault_root: Path,
    note_candidates: list[NoteCandidate],
    unresolved_candidates: list[NoteCandidate],
    deterministic_candidates: list[NoteCandidate],
    evidence_blocks: list[EvidenceBlock],
    allow_provider_only_candidates: bool = True,
) -> tuple[list[NoteCandidate], list[NoteCandidate], dict[str, Any]]:
    existing_lookup = _build_existing_note_lookup(vault_root)
    deterministic_lookup = _build_candidate_lookup(deterministic_candidates)
    resolved_candidates: list[NoteCandidate] = []
    resolved_unresolved: list[NoteCandidate] = []
    stats = {
        "deterministic_floor_count": len(deterministic_candidates),
        "provider_candidate_count": len(note_candidates),
        "provider_unresolved_count": len(unresolved_candidates),
        "stabilized_to_existing_count": 0,
        "stabilized_to_deterministic_count": 0,
        "dropped_low_signal_provider_count": 0,
        "dropped_unresolved_collision_count": 0,
        "provider_only_candidates_allowed": allow_provider_only_candidates,
    }

    for incoming in note_candidates + unresolved_candidates:
        matched_existing = False
        matched_deterministic = False
        if _is_low_signal_candidate(incoming):
            stats["dropped_low_signal_provider_count"] += 1
            continue

        existing_match = _lookup_existing_note(existing_lookup, incoming)
        if existing_match is not None:
            incoming = _snap_candidate_to_existing(incoming, existing_match)
            stats["stabilized_to_existing_count"] += 1
            matched_existing = True
        else:
            deterministic_match = _lookup_candidate(deterministic_lookup, incoming)
            if deterministic_match is not None:
                incoming = _snap_candidate_to_anchor(incoming, deterministic_match)
                stats["stabilized_to_deterministic_count"] += 1
                matched_deterministic = True

        if incoming.note_type == "unresolved":
            if _should_keep_unresolved(incoming):
                resolved_unresolved.append(incoming)
            else:
                stats["dropped_low_signal_provider_count"] += 1
            continue

        if not allow_provider_only_candidates and not matched_existing and not matched_deterministic:
            stats["dropped_low_signal_provider_count"] += 1
            continue
        if existing_match is None and _lookup_candidate(deterministic_lookup, incoming) is None and not _should_keep_provider_only_candidate(
            incoming,
            evidence_blocks=evidence_blocks,
        ):
            stats["dropped_low_signal_provider_count"] += 1
            continue
        resolved_candidates.append(incoming)

    merged_candidates = _merge_note_candidates(deterministic_candidates + resolved_candidates)
    canonical_lookup = _build_candidate_lookup(merged_candidates)
    filtered_unresolved: list[NoteCandidate] = []
    for incoming in resolved_unresolved:
        if _lookup_candidate(canonical_lookup, incoming) is not None:
            stats["dropped_unresolved_collision_count"] += 1
            continue
        filtered_unresolved.append(incoming)

    return _merge_note_candidates(merged_candidates), _merge_note_candidates(filtered_unresolved), stats


def _build_existing_note_lookup(vault_root: Path) -> dict[str, list[dict[str, Any]]]:
    if not vault_root.exists():
        return {}
    index = index_vault(vault_root)
    lookup: dict[str, list[dict[str, Any]]] = {}
    for note in index.get("notes", []):
        note_type = str(note.get("note_type", "")).strip().lower()
        if note_type not in {"entity", "concept", "topic"}:
            continue
        for key in _note_lookup_keys(note):
            lookup.setdefault(key, []).append(note)
    return lookup


def _build_candidate_lookup(candidates: list[NoteCandidate]) -> dict[str, list[NoteCandidate]]:
    lookup: dict[str, list[NoteCandidate]] = {}
    for candidate in candidates:
        for key in _candidate_lookup_keys(candidate):
            lookup.setdefault(key, []).append(candidate)
    return lookup


def _lookup_existing_note(lookup: dict[str, list[dict[str, Any]]], candidate: NoteCandidate) -> dict[str, Any] | None:
    matches: list[dict[str, Any]] = []
    for key in _candidate_lookup_keys(candidate):
        matches.extend(lookup.get(key, []))
    unique = _dedupe_by_path(matches)
    compatible = [
        note
        for note in unique
        if candidate.note_type == "unresolved" or str(note.get("note_type", "")).strip().lower() == candidate.note_type
    ]
    if len(compatible) == 1:
        return compatible[0]
    if len(unique) == 1:
        return unique[0]
    return None


def _lookup_candidate(lookup: dict[str, list[NoteCandidate]], candidate: NoteCandidate) -> NoteCandidate | None:
    matches: list[NoteCandidate] = []
    for key in _candidate_lookup_keys(candidate):
        matches.extend(lookup.get(key, []))
    unique = _dedupe_candidates(matches)
    compatible = [item for item in unique if candidate.note_type == "unresolved" or item.note_type == candidate.note_type]
    if len(compatible) == 1:
        return compatible[0]
    if len(unique) == 1:
        return unique[0]
    return None


def _snap_candidate_to_existing(candidate: NoteCandidate, existing_note: dict[str, Any]) -> NoteCandidate:
    metadata = dict(existing_note.get("metadata", {}))
    existing_type = str(existing_note.get("note_type", candidate.note_type)).strip().lower() or candidate.note_type
    existing_title = str(existing_note.get("title", candidate.title)).strip() or candidate.title
    existing_slug = str(metadata.get("canonical_slug", "")) or str(existing_note.get("stem", "")) or candidate.canonical_slug
    aliases = _merge_unique_list(metadata.get("aliases", []), [candidate.title, *candidate.aliases])
    return NoteCandidate(
        note_type=existing_type,
        title=existing_title,
        canonical_slug=existing_slug,
        confidence=candidate.confidence,
        aliases=aliases,
        source_refs=list(candidate.source_refs),
        claims=list(candidate.claims),
        relationships=list(candidate.relationships),
        note_id=str(metadata.get("id", "")) or candidate.note_id,
        kind=_existing_kind(metadata, existing_type) or candidate.kind,
    )


def _snap_candidate_to_anchor(candidate: NoteCandidate, anchor: NoteCandidate) -> NoteCandidate:
    aliases = _merge_unique_list(anchor.aliases, [candidate.title, *candidate.aliases])
    return NoteCandidate(
        note_type=anchor.note_type,
        title=anchor.title,
        canonical_slug=anchor.canonical_slug,
        confidence=_max_confidence(candidate.confidence, anchor.confidence),
        aliases=aliases,
        source_refs=list(candidate.source_refs),
        claims=list(candidate.claims),
        relationships=list(candidate.relationships),
        note_id=anchor.note_id,
        kind=anchor.kind or candidate.kind,
    )


def _existing_kind(metadata: dict[str, Any], note_type: str) -> str:
    if note_type == "entity":
        return str(metadata.get("entity_kind", "")).strip()
    if note_type == "concept":
        return str(metadata.get("concept_kind", "")).strip()
    return ""


def _candidate_lookup_keys(candidate: NoteCandidate) -> set[str]:
    keys = {candidate.canonical_slug, slugify(candidate.title)}
    for alias in candidate.aliases:
        alias_slug = slugify(alias)
        if alias_slug:
            keys.add(alias_slug)
    return {key for key in keys if key}


def _note_lookup_keys(note: dict[str, Any]) -> set[str]:
    metadata = dict(note.get("metadata", {}))
    keys = {
        slugify(str(note.get("title", ""))),
        slugify(str(note.get("stem", ""))),
        slugify(str(metadata.get("canonical_slug", ""))),
    }
    for alias in metadata.get("aliases", []):
        keys.add(slugify(str(alias)))
    return {key for key in keys if key}


def _is_low_signal_candidate(candidate: NoteCandidate) -> bool:
    title = " ".join(candidate.title.split()).strip()
    title_slug = slugify(title)
    if not title or len(title_slug) < 2:
        return True
    if LOW_SIGNAL_TITLE_RE.match(title):
        return True
    if candidate.note_type == "unresolved" and title.lower().endswith("unresolved"):
        return True
    if candidate.note_type == "unresolved" and len(title_slug) < 5 and " " not in title:
        return True
    return False


def _should_keep_unresolved(candidate: NoteCandidate) -> bool:
    if len(candidate.source_refs) >= 2:
        return True
    return len(candidate.title) >= 8 and len(candidate.title.split()) >= 2


def _should_keep_provider_only_candidate(candidate: NoteCandidate, *, evidence_blocks: list[EvidenceBlock]) -> bool:
    title_support_count, heading_support = _candidate_title_support(candidate, evidence_blocks)
    if title_support_count == 0:
        return False

    if candidate.note_type == "topic":
        evidence_count = len(candidate.source_refs)
        claim_count = len(candidate.claims)
        relation_count = len(candidate.relationships)
        if candidate.confidence != "high":
            return False
        if evidence_count < 3:
            return False
        if not (heading_support or title_support_count >= 2):
            return False
        return claim_count >= 2 or relation_count >= 2

    evidence_count = len(candidate.source_refs)
    relation_count = len(candidate.relationships)
    claim_count = len(candidate.claims)
    single_word = len(candidate.title.split()) == 1 and "-" not in candidate.title

    if candidate.note_type == "entity":
        if single_word and candidate.title == candidate.title.lower() and title_support_count < 2:
            return False
        if candidate.confidence == "high":
            return evidence_count >= 2 or title_support_count >= 2
        return evidence_count >= 2 and (claim_count >= 1 or relation_count >= 1)

    if single_word and not heading_support and title_support_count < 2:
        return False
    if candidate.confidence == "high":
        return evidence_count >= 2 or title_support_count >= 2
    return evidence_count >= 2 and (claim_count >= 1 or relation_count >= 1)


def _candidate_title_support(candidate: NoteCandidate, evidence_blocks: list[EvidenceBlock]) -> tuple[int, bool]:
    title = " ".join(candidate.title.lower().split()).strip()
    if not title:
        return 0, False
    support_count = 0
    heading_support = False
    for block in evidence_blocks:
        normalized = " ".join(block.text.lower().split())
        if title not in normalized:
            continue
        support_count += 1
        if normalized.startswith("#") or normalized.startswith(f"{title}:") or normalized == title:
            heading_support = True
    return support_count, heading_support


def _dedupe_by_path(notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    result = []
    for note in notes:
        path = str(note.get("path", ""))
        if path and path not in seen:
            seen.add(path)
            result.append(note)
    return result


def _dedupe_candidates(candidates: list[NoteCandidate]) -> list[NoteCandidate]:
    seen = set()
    result = []
    for candidate in candidates:
        key = (candidate.note_type, candidate.canonical_slug)
        if key not in seen:
            seen.add(key)
            result.append(candidate)
    return result


def _normalize_candidate_list(raw_candidates: list[Any], valid_source_refs: set[str]) -> list[NoteCandidate]:
    merged: dict[tuple[str, str], NoteCandidate] = {}
    for raw in raw_candidates:
        if not isinstance(raw, dict):
            continue
        note_type = str(raw.get("note_type", "")).strip().lower()
        if note_type not in {"entity", "concept", "topic", "unresolved"}:
            continue
        title = " ".join(str(raw.get("title", "")).split()).strip()
        if not title:
            continue
        slug = slugify(str(raw.get("canonical_slug", "")).strip() or title)
        confidence = str(raw.get("confidence", "low")).lower()
        if confidence not in {"high", "medium", "low"}:
            confidence = "low"
        key = (note_type, slug)
        candidate = merged.get(key)
        if candidate is None:
            candidate = NoteCandidate(
                note_type=note_type,
                title=title,
                canonical_slug=slug,
                confidence=confidence,
                aliases=[],
                source_refs=[],
                claims=[],
                relationships=[],
                note_id=_default_note_id_for_type(note_type, slug),
                kind=str(raw.get("kind", "unknown")).strip() or "unknown",
            )
            merged[key] = candidate
        else:
            candidate.confidence = _max_confidence(candidate.confidence, confidence)

        for alias in raw.get("aliases", []):
            alias_text = " ".join(str(alias).split()).strip()
            if alias_text and alias_text != title and alias_text not in candidate.aliases:
                candidate.aliases.append(alias_text)

        for raw_claim in raw.get("claims", []):
            claim = _normalize_evidence_item(raw_claim, valid_source_refs)
            if claim and not any(existing.text == claim.text and existing.source_ref == claim.source_ref for existing in candidate.claims):
                candidate.claims.append(claim)
                if claim.source_ref not in candidate.source_refs:
                    candidate.source_refs.append(claim.source_ref)

        for raw_relation in raw.get("relationships", []):
            relation = _normalize_relationship_item(raw_relation, valid_source_refs)
            if relation and not any(
                existing.text == relation.text and existing.source_ref == relation.source_ref
                for existing in candidate.relationships
            ):
                candidate.relationships.append(relation)
                if relation.source_ref not in candidate.source_refs:
                    candidate.source_refs.append(relation.source_ref)

    return [
        candidate
        for candidate in sorted(merged.values(), key=lambda item: (item.note_type, item.canonical_slug))
        if candidate.source_refs
    ]


def _normalize_evidence_item(raw: Any, valid_source_refs: set[str]) -> Claim | None:
    if not isinstance(raw, dict):
        return None
    text = " ".join(str(raw.get("text", "")).split()).strip()
    source_ref = str(raw.get("source_ref", "")).strip()
    confidence = str(raw.get("confidence", "low")).lower()
    if not text or source_ref not in valid_source_refs:
        return None
    if confidence not in {"high", "medium", "low"}:
        confidence = "low"
    return Claim(text=text, source_ref=source_ref, confidence=confidence)


def _normalize_relationship_item(raw: Any, valid_source_refs: set[str]) -> Relationship | None:
    if not isinstance(raw, dict):
        return None
    text = " ".join(str(raw.get("text", "")).split()).strip()
    source_ref = str(raw.get("source_ref", "")).strip()
    confidence = str(raw.get("confidence", "low")).lower()
    if not text or source_ref not in valid_source_refs:
        return None
    if confidence not in {"high", "medium", "low"}:
        confidence = "low"
    return Relationship(text=text, source_ref=source_ref, confidence=confidence)


def _drop_low_information_candidates(
    candidates: list[NoteCandidate],
    block_lookup: dict[str, EvidenceBlock],
) -> list[NoteCandidate]:
    filtered: list[NoteCandidate] = []
    for candidate in candidates:
        refs = [ref for ref in candidate.source_refs if ref in block_lookup]
        if refs and all(_is_low_information_block(block_lookup[ref].text) for ref in refs):
            continue
        filtered.append(candidate)
    return filtered


def _is_low_information_block(text: str) -> bool:
    normalized = " ".join(text.lower().split())
    if not normalized:
        return True
    if normalized.startswith("appendix:"):
        return True
    hits = sum(1 for marker in LOW_INFORMATION_BLOCK_MARKERS if marker in normalized)
    return hits >= 2
