# Skill: ingest-source

## Purpose

Turn an incoming file, message, or conversation into a stable source record that later claims can cite.

## Use When

- any raw input enters the system

## Outputs

- one source note
- stable source metadata
- addressable evidence anchors or evidence blocks

Follow:

- `config/vault_schema.md`
- `config/vault_layout.md`
- `config/evidence_conventions.md`

## Procedure

1. Determine source type: file, message, conversation, or batch item.
2. Place the note in the correct managed directory and filename format.
3. Preserve the raw content in a source note or a source-linked artifact.
4. Add metadata such as timestamp, origin, participants, and ingestion time.
5. Generate deterministic evidence anchors:
   `^eNNNN` for file evidence blocks and `^mNNNN` for conversation messages.
6. Avoid altering the semantic content of the source.

## Guardrails

- source notes are append-only
- preserve ordering for conversations
- do not summarize here; that is the extractor's job
- do not silently drop low-signal content that may later matter
- do not renumber anchors in an existing source note

## Success

All downstream extracted knowledge can point back to a durable source record.
