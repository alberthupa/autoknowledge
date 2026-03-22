# Merge And Contradiction Policy

This document defines how the system handles uncertain identity matches and contradictory claims.

## Identity Resolution Policy

The default bias is conservative:

- false merges are worse than missed merges
- uncertainty should be recorded explicitly
- unresolved cases belong in `inbox/unresolved/`

## Merge Confidence Levels

Use these levels during identity resolution:

- `high`: same identity is strongly supported by name, context, aliases, and surrounding links
- `medium`: likely same identity but not strong enough for irreversible cleanup
- `low`: ambiguous or weakly supported

Merge action rules:

- `high`: merge into the canonical note
- `medium`: update the canonical note only if the evidence is additive and harmless; otherwise create an unresolved note
- `low`: do not merge; create or update an unresolved note

## Unresolved Note Contract

Unresolved notes go in `inbox/unresolved/` and must contain:

```yaml
id: "unres_..."
type: "unresolved"
title: ""
aliases: []
source_refs: []
created_at: ""
updated_at: ""
managed_by: "autoknowledge"
schema_version: 1
resolution_status: "unresolved"
candidate_targets: []
```

Recommended sections:

```md
# <Title>

## Why Unresolved

## Candidate Targets

## Evidence

## Next Checks
```

These notes are working memory for later repair or evaluation. They are not canonical knowledge nodes.

## Contradiction Policy

When two sourced claims disagree:

- keep both sourced claims
- add a `## Contradictions` section to the canonical note
- do not silently delete the older claim
- do not collapse the disagreement into a single unsourced summary

## Contradiction Format

Example:

```md
## Contradictions
- Claim A: Alice works on [[Project Atlas]]. Source: [[sources/conversations/2026/2026-03-21--research-sync--conv_98af12de#^m0003]] Confidence: high
- Claim B: Alice left [[Project Atlas]]. Source: [[sources/files/2026/2026-03-22--status-update--src_11aa22bb#^e0004]] Confidence: medium
- Status: unresolved
```

## Resolution Rules

A contradiction may be resolved only when:

- a later source clearly supersedes an earlier one, or
- there is explicit external policy for temporal resolution

When resolved:

- preserve the historical claim
- annotate the resolution rather than erasing history
- update `## Summary` only after the contradiction handling is reflected in sourced claims

## Destructive Edit Policy

Never remove a sourced claim because it looks redundant, old, or inconvenient unless:

- the claim is clearly duplicated with the same meaning and evidence, or
- the note was attached to the wrong identity and the correction is documented

## Evaluator Implications

Repeated unresolved merges and contradictions should become benchmark cases. The system should get better at handling them, not better at hiding them.
