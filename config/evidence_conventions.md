# Evidence Conventions

This document defines how source notes expose stable evidence anchors for downstream claims.

The goal is precise, reproducible source references that survive re-ingestion and are easy to inspect in Obsidian.

## Source Evidence Model

Every extracted claim must point to a block anchor inside a managed source or conversation note.

There are two evidence block styles:

- `file evidence blocks` for document-like sources
- `message evidence blocks` for conversation sources

## File Evidence Blocks

Document-like sources should be split into atomic evidence units.

Preferred unit:

- one paragraph

Fallback units:

- one bullet item
- one table row summary line
- one heading-scoped short block when paragraph structure is weak

Block IDs must use this format:

```text
^e0001
^e0002
^e0003
```

Example:

```md
## Raw Content
This project targets personal knowledge extraction from chat logs and loose documents. ^e0001

The first release should focus on source-grounded claims instead of polished summaries. ^e0002
```

## Conversation Evidence Blocks

Conversation sources should preserve message order.

The atomic unit is:

- one message

Block IDs must use this format:

```text
^m0001
^m0002
^m0003
```

Example:

```md
## Transcript
- 2026-03-21T10:00:00Z | alice: We should store every claim with a source reference. ^m0001
- 2026-03-21T10:02:00Z | bob: The self-update loop should change one skill at a time. ^m0002
```

## Anchor Stability Rules

- Anchors must be generated deterministically from normalized source ordering.
- Re-ingesting the identical source must preserve the same anchor sequence.
- Existing source notes are append-only; do not renumber anchors in already stored content.
- When additional raw content is appended, continue the existing sequence.

## Claim Citation Format

All citations must use Obsidian wiki-link block references.

Examples:

```md
Source: [[sources/files/2026/2026-03-21--project-brief--src_a1b2c3d4#^e0002]]
Source: [[sources/conversations/2026/2026-03-21--research-sync--conv_98af12de#^m0004]]
```

## Multi-Source Support

When one claim is supported by more than one source:

```md
- The system should prefer bounded self-update over open-ended self-modification. Source: [[sources/files/2026/2026-03-21--project-brief--src_a1b2c3d4#^e0002]] Also: [[sources/conversations/2026/2026-03-21--research-sync--conv_98af12de#^m0004]] Confidence: high
```

## Quoting Policy

- Prefer paraphrased claims in canonical notes.
- Preserve raw wording only in source notes unless exact wording is materially important.
- If wording matters, quote minimally and keep the quote tied to a source block.

## Weak Evidence Handling

If a source segment is ambiguous, speculative, or incomplete:

- preserve it in the source note
- mark the derived claim as `Confidence: low`
- optionally mirror the ambiguity under `## Open Questions`

Do not upgrade weak evidence to a firm summary statement.
