# Vault Schema

This document locks the vault contract for AutoKnowledge Milestone 1.

The target is an Obsidian-compatible markdown vault that remains readable to humans, diffable in git, and predictable enough for automated ingestion and evaluation.

## Design Goals

- Human-readable note titles and paths.
- Stable machine-readable identifiers in frontmatter.
- Minimal note churn on repeated ingestion.
- Source-grounded claims and relations.
- Safe handling of ambiguity, uncertainty, and contradiction.

## Top-Level Vault Layout

The managed part of the vault should follow this layout:

```text
sources/
  files/
  conversations/
entities/
concepts/
topics/
inbox/
  unresolved/
```

The agent must not invent new top-level directories unless explicitly configured to do so.

## Managed Note Types

The system manages six note types:

- `source`
- `conversation`
- `entity`
- `concept`
- `topic`
- `unresolved`

Use:

- `source` for raw file-like material
- `conversation` for ordered message threads
- `entity` for people, organizations, tools, places, projects, and similarly concrete referents
- `concept` for ideas, methods, themes, patterns, or abstractions
- `topic` for broader clusters or collection notes
- `unresolved` for low-confidence identity or merge cases that should not become canonical notes yet

## Common Frontmatter Contract

All managed notes must contain:

```yaml
id: ""
type: ""
title: ""
aliases: []
source_refs: []
created_at: ""
updated_at: ""
managed_by: "autoknowledge"
schema_version: 1
```

Field meanings:

- `id`: stable machine identifier, never reused for another note
- `type`: one of the managed note types
- `title`: canonical display title
- `aliases`: known alternate titles or spellings
- `source_refs`: stable list of supporting source block references
- `created_at`: first creation timestamp in ISO 8601
- `updated_at`: most recent material update timestamp in ISO 8601
- `managed_by`: identifies the notes this system owns
- `schema_version`: current schema version for future migrations

### Legacy Minimal Adoption Mode

Existing human-maintained notes may be adopted in a lighter managed mode:

```yaml
managed_format: "legacy_minimal"
```

In this mode:

- the note is managed for ownership and identity
- the body should remain structurally unchanged
- only minimal identity frontmatter is required
- full canonical sections and full common frontmatter are not required yet

This is the default adoption path for legacy notes in a real vault profile.

## Type-Specific Frontmatter

### `source`

```yaml
id: "src_..."
type: "source"
title: ""
source_kind: "file"
origin: ""
source_path: ""
mime_type: ""
source_timestamp: ""
ingested_at: ""
hash_sha256: ""
```

### `conversation`

```yaml
id: "conv_..."
type: "conversation"
title: ""
source_kind: "conversation"
origin: ""
participants: []
channel: ""
source_timestamp_start: ""
source_timestamp_end: ""
ingested_at: ""
hash_sha256: ""
```

### `entity`

```yaml
id: "ent_..."
type: "entity"
title: ""
entity_kind: ""
canonical_slug: ""
confidence: ""
status: "active"
```

### `concept`

```yaml
id: "con_..."
type: "concept"
title: ""
concept_kind: ""
canonical_slug: ""
confidence: ""
status: "active"
```

### `topic`

```yaml
id: "top_..."
type: "topic"
title: ""
canonical_slug: ""
confidence: ""
status: "active"
```

### `unresolved`

```yaml
id: "unres_..."
type: "unresolved"
title: ""
canonical_slug: ""
confidence: "low"
status: "unresolved"
candidate_targets: []
resolution_status: "unresolved"
```

## Required Sections By Note Type

### `source`

```md
# <Title>

## Source Metadata

## Raw Content
...evidence blocks...
```

### `conversation`

```md
# <Title>

## Conversation Metadata

## Transcript
...one block per message...
```

### `entity`, `concept`, `topic`, `unresolved`

```md
# <Title>

## Summary

## Claims

## Relationships

## Open Questions
```

`## Contradictions` is required only when contradictory sourced claims exist.

## Canonical Claim Format

All factual content added to canonical notes must be represented as sourced bullets under `## Claims` or `## Relationships`.

Required format:

```md
- Alice works on [[Project Atlas]]. Source: [[sources/conversations/2026/2026-03-21--research-sync--conv_abc123#^m0003]] Confidence: high
```

Rules:

- One bullet should contain one atomic claim.
- Every bullet must include exactly one primary source reference.
- Additional supporting sources may be appended with `Also: ...`.
- `Confidence` must be one of `high`, `medium`, or `low`.
- Claims must preserve temporal qualifiers when the source is time-bound.

## Relationship Format

Relationships should follow the same sourcing rule:

```md
- works_on -> [[Project Atlas]] Source: [[sources/conversations/2026/2026-03-21--research-sync--conv_abc123#^m0003]] Confidence: high
```

## Summary Rules

`## Summary` is optional and secondary.

If present:

- it must be supported by claims already present in the note
- it must not introduce unsourced facts
- it should be concise and low-churn

## Source Reference Rules

- `source_refs` in frontmatter should contain stable block references used by the note.
- Every claim bullet must cite a source block using a wiki link.
- Source links must point to a block anchor, not only to a file.
- The same source block may support multiple claims.

## Identity Rules

- Each real-world referent should map to one canonical managed note when confidence is sufficient.
- `aliases` should capture spelling variants, nicknames, abbreviations, and renamed forms.
- If confidence is insufficient, do not merge. Route the item to `inbox/unresolved/`.

## Update Rules

- Update existing notes in place when the canonical identity is clear.
- Do not reorder claims or relationships unless necessary for a local patch.
- Preserve prior sourced claims.
- Never convert uncertain claims into definite claims without stronger evidence.

## Non-Goals For Milestone 1

This contract does not yet define:

- executable harness commands
- benchmark file formats
- automatic migration tooling

Those belong to later milestones.
