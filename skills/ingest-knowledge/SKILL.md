# Skill: ingest-knowledge

## Purpose

Orchestrate end-to-end ingestion of a new file, message, or conversation into the vault.

## Use When

- a new source arrives
- a directory dump needs batch ingestion
- a chat or conversation log needs to be turned into linked notes

## Inputs

- raw file content or path
- conversation transcript or message
- optional metadata such as timestamp, author, channel, or source type

## Calls

- `ingest-source`
- `extract-knowledge`
- `resolve-identity`
- `update-vault`
- `repair-graph`
- `evaluate-graph`

## Procedure

1. Normalize the source and create or update a raw source note.
2. Extract candidate entities, concepts, claims, and relations with evidence references.
3. Resolve each candidate against existing canonical notes.
4. Apply minimal vault patches.
5. Run local graph checks on the changed area.
6. Record unresolved or low-confidence items instead of forcing merges.

The extractor-to-writer handoff should conform to `config/extraction_contract.md`.

## Guardrails

- do not create claims without evidence
- do not rewrite unrelated notes
- do not create duplicate canonical notes when aliases suggest an existing match
- if confidence is low, preserve uncertainty

## Success

The vault gains new useful knowledge with low churn, strong provenance, and coherent links.
