"""Static contract values for the AutoKnowledge vault."""

from __future__ import annotations

MANAGED_TYPES = {
    "source",
    "conversation",
    "entity",
    "concept",
    "topic",
    "unresolved",
}

CANONICAL_TYPES = {"entity", "concept", "topic"}

COMMON_FIELDS = {
    "id",
    "type",
    "title",
    "aliases",
    "source_refs",
    "created_at",
    "updated_at",
    "managed_by",
    "schema_version",
}

TYPE_FIELDS = {
    "source": {
        "source_kind",
        "origin",
        "source_path",
        "mime_type",
        "source_timestamp",
        "ingested_at",
        "hash_sha256",
    },
    "conversation": {
        "source_kind",
        "origin",
        "participants",
        "channel",
        "source_timestamp_start",
        "source_timestamp_end",
        "ingested_at",
        "hash_sha256",
    },
    "entity": {"entity_kind", "canonical_slug", "confidence", "status"},
    "concept": {"concept_kind", "canonical_slug", "confidence", "status"},
    "topic": {"canonical_slug", "confidence", "status"},
    "unresolved": {
        "canonical_slug",
        "confidence",
        "status",
        "candidate_targets",
        "resolution_status",
    },
}

REQUIRED_SECTIONS = {
    "source": ("Source Metadata", "Raw Content"),
    "conversation": ("Conversation Metadata", "Transcript"),
    "entity": ("Summary", "Claims", "Relationships", "Open Questions"),
    "concept": ("Summary", "Claims", "Relationships", "Open Questions"),
    "topic": ("Summary", "Claims", "Relationships", "Open Questions"),
    "unresolved": ("Summary", "Claims", "Relationships", "Open Questions"),
}

SOURCE_DIR_PREFIX = "sources/files/"
CONVERSATION_DIR_PREFIX = "sources/conversations/"
ENTITY_DIR = "entities/"
CONCEPT_DIR = "concepts/"
TOPIC_DIR = "topics/"
UNRESOLVED_DIR = "inbox/unresolved/"

