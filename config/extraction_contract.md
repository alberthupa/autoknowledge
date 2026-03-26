# Extraction Contract

This document defines the structured payload exchanged between extraction, identity resolution, and vault writing.

The purpose is to keep ingestion behavior explicit and machine-checkable.

## Payload Shape

Each ingestion run should produce one extraction payload with:

- one source note plan
- zero or more evidence blocks
- zero or more note candidates
- zero or more unresolved candidates

Extraction may happen over one window or many windows. When windowing is used, the extractor processes subsets of the evidence blocks and the harness merges the window-level candidates back into one document-level payload.

## Source Note Plan

The source note plan describes the raw source note that will be created or reused.

Required fields:

```json
{
  "id": "src_... or conv_...",
  "type": "source or conversation",
  "title": "Human title",
  "path": "vault-relative path without ambiguity",
  "source_kind": "file or conversation",
  "origin": "user-defined origin label",
  "hash_sha256": "content hash",
  "source_refs": ["[[...#^e0001]]"]
}
```

## Evidence Block

Each source note is broken into stable evidence units.

Required fields:

```json
{
  "anchor": "e0001 or m0001",
  "text": "raw evidence text",
  "source_ref": "[[sources/...#^e0001]]",
  "speaker": "optional",
  "timestamp": "optional"
}
```

## Note Candidate

A note candidate is a proposed canonical or unresolved note update.

Required fields:

```json
{
  "note_type": "entity | concept | topic | unresolved",
  "title": "Candidate title",
  "canonical_slug": "stable slug",
  "confidence": "high | medium | low",
  "aliases": ["alternate names"],
  "entity_kind": "optional placement subtype for entity notes",
  "source_refs": ["[[...#^e0001]]"],
  "claims": [],
  "relationships": []
}
```

Notes:

- `kind` may still be used by the extractor as heuristic origin metadata such as `speaker`, `named_entity`, or `keyword`
- `entity_kind` is the vault-facing placement subtype for entity notes when the target vault profile distinguishes folders like `people` or `companies`

## Claim

Claims are atomic sourced statements for canonical notes.

Required fields:

```json
{
  "text": "Atomic claim text",
  "source_ref": "[[...#^e0001]]",
  "confidence": "high | medium | low"
}
```

## Relationship

Relationships are sourced edges expressed as bullets in `## Relationships`.

Required fields:

```json
{
  "text": "mentioned_in -> [[sources/...]]",
  "source_ref": "[[...#^e0001]]",
  "confidence": "high | medium | low"
}
```

## Initial Conservative Policy

The first ingestion implementation is intentionally conservative:

- it prioritizes source preservation and graph coherence
- it prefers source-grounded relationships over ambitious unsourced summaries
- it uses unresolved notes when identity is not clear enough
- it keeps raw source notes whole and append-only even when extraction uses internal windows

This is by design. The self-update loop should improve extraction quality later, but the starting point must be structurally trustworthy.
