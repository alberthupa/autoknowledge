# Vault Profiles

AutoKnowledge now separates:

- the internal note model used by indexing, ingestion, and evaluation
- the vault-facing layout used by a specific Obsidian vault

This is handled by `config/vault_profiles.json`.

## Current Profiles

### `canonical_managed`

The original repo-owned layout:

- `sources/files/YYYY/`
- `sources/conversations/YYYY/`
- `entities/`
- `concepts/`
- `topics/`
- `inbox/unresolved/`

Canonical notes use slug filenames.

### `obsidian_albert`

A profile for the existing vault copy at `/home/albert/repos2/obsidian`.

Key behavior:

- notes under `400 Entities/` are inferred as `entity` notes even without frontmatter
- the first folder under `400 Entities/` becomes `entity_kind`
- folder aliases are normalized:
  - `people` -> `person`
  - `companies` -> `company`
  - `offers` -> `offer`
  - `projects` -> `project`
  - `sources` -> `source`
- managed entity notes use title-style filenames inside those folders

Source and conversation notes still use the repo-default `sources/...` layout.

## Design Rule

Legacy notes can be classified by profile without becoming fully managed notes.

Strict contract checks are applied only to notes explicitly managed by AutoKnowledge:

- `managed_by: autoknowledge`

This keeps the system portable while allowing gradual adoption inside an existing human-maintained vault.

When an existing human note is first adopted, the default policy is `managed_format: "legacy_minimal"`:

- prepend minimal ownership and identity frontmatter
- preserve the existing markdown body
- avoid forcing the full canonical note template onto legacy notes

Apply safety is also profile-aware:

- writes are limited to the profile's managed roots
- profiles can require backups before overwriting existing notes
- `obsidian_albert` requires a backup directory for destructive applies
