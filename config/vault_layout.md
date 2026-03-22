# Vault Layout

This document defines path placement and naming rules for managed notes.

The main objective is to keep note paths predictable enough for automation while staying usable in Obsidian.

## Directory Placement

Managed note placement:

```text
sources/files/YYYY/
sources/conversations/YYYY/
entities/
concepts/
topics/
inbox/unresolved/
```

Placement rules:

- file sources go under `sources/files/YYYY/`
- conversation sources go under `sources/conversations/YYYY/`
- canonical entity notes go under `entities/`
- canonical concept notes go under `concepts/`
- canonical topic notes go under `topics/`
- unresolved identity or merge cases go under `inbox/unresolved/`

## File Naming Rules

All managed filenames should be readable and stable.

### File source note

```text
YYYY-MM-DD--<slug>--<source_id>.md
```

Example:

```text
sources/files/2026/2026-03-21--project-brief--src_a1b2c3d4.md
```

### Conversation note

```text
YYYY-MM-DD--<slug>--<conversation_id>.md
```

Example:

```text
sources/conversations/2026/2026-03-21--research-sync--conv_98af12de.md
```

### Canonical entity, concept, or topic note

```text
<canonical_slug>.md
```

Examples:

```text
entities/alice-smith.md
concepts/auto-update-loop.md
topics/knowledge-extraction.md
```

### Unresolved note

```text
YYYY-MM-DD--<slug>--unres_<short_id>.md
```

Example:

```text
inbox/unresolved/2026-03-21--alice-or-alicja--unres_71ad9f2c.md
```

## Slug Rules

Canonical slugs must:

- be lowercase
- use ASCII letters, digits, and single hyphens
- collapse whitespace to hyphens
- remove punctuation except hyphens needed as separators
- avoid trailing hyphens

Examples:

- `Alice Smith` -> `alice-smith`
- `R&D Notes` -> `rd-notes`
- `GPT-5.4` -> `gpt-54`

## ID Rules

IDs are stable frontmatter identifiers and are not derived from the path alone.

Prefixes:

- `src_` for file sources
- `conv_` for conversations
- `ent_` for entities
- `con_` for concepts
- `top_` for topics
- `unres_` for unresolved notes

The suffix may be a short deterministic hash or UUID fragment, but once assigned it must not change.

## Title Rules

The frontmatter `title` is the canonical human-facing title.

Filename and title may differ slightly if the title contains punctuation or casing not suitable for the slug, but the semantic identity must remain the same.

## Rename Policy

- Avoid renaming canonical notes unless identity was genuinely wrong.
- If a canonical note is renamed, preserve the old title in `aliases`.
- Do not rename notes only for style cleanup.

## Link Policy

- Use wiki links for note-to-note references.
- Use block wiki links for source evidence references.
- Prefer linking to canonical notes, not unresolved notes, unless the unresolved case itself is the relevant object.
