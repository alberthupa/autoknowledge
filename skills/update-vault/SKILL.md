# Skill: update-vault

## Purpose

Apply minimal, source-grounded patches to canonical notes and source-linked notes.

## Use When

- extraction and identity resolution have produced actionable updates

## Outputs

- patched markdown notes
- updated links
- unresolved items logged for later review or repair

Follow:

- `config/vault_schema.md`
- `config/vault_layout.md`
- `config/evidence_conventions.md`
- `config/merge_policy.md`

## Procedure

1. Update existing canonical notes when possible.
2. Create new notes only when no good canonical target exists.
3. Use the required managed sections and frontmatter contract.
4. Add sourced claims, aliases, links, and metadata incrementally.
5. Preserve note structure and prior sourced claims.
6. If contradictory sourced claims exist, add or update `## Contradictions`.
7. Keep change scope as local as possible.

## Guardrails

- do not remove sourced claims without explicit reason
- do not convert low-confidence guesses into canonical truth
- do not reorder notes gratuitously
- do not rewrite whole files when a local patch is enough
- do not place unresolved merge cases into canonical directories

## Success

The vault changes are small, understandable, and easy to evaluate.
