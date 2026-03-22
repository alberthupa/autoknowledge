# Skill: resolve-identity

## Purpose

Map extracted candidates onto existing canonical notes or create new candidates for note creation.

## Use When

- extracted entities or concepts may overlap with existing vault content

## Inputs

- structured extraction candidates
- current vault index
- alias tables or prior known merges

## Outputs

- resolved note targets
- unresolved items
- merge rationale with confidence

Follow:

- `config/vault_schema.md`
- `config/vault_layout.md`
- `config/merge_policy.md`

## Procedure

1. Extract identity-relevant signals from the candidates.
2. For each extracted candidate, compute:
- `surface_keys`
- `type_keys`
- `evidence_keys` (normalized evidence anchor signatures)
- `modality_keys`
3. Build an evidence signature for mapping stability.
- Normalize evidence anchors by `(vault note id, block anchor id)` where available; otherwise by a deterministic hash of `(source_id, block_anchor, statement_span)`.
- Define `evidence_signature = stable_sorted_unique(evidence_keys)`.
- If `evidence_signature` is empty or only contains anchors from wrappers such as appendices, export footers, mailing metadata, or legal boilerplate, treat the candidate as `evidence_weak` for merge gating.
4. Retrieve candidate canonical notes deterministically by type first, then by title and alias.
- Narrow candidates to the same `type_keys` group.
- Within that set, rank by alias matches that come with the candidate's `modality_keys`, then by evidence-key overlap.
5. Apply an evidence-anchor compatibility gate before computing similarity.
- Compute `evidence_overlap = |intersection(evidence_keys, target.evidence_keys)|`.
- If `evidence_weak` is true, do not merge into an existing canonical note using evidence overlap alone; prefer unresolved unless a prior consistent merge mapping exists in step 6.
- If `evidence_overlap` is below a minimal threshold for `high` or `medium` confidence merges, block merging and mark unresolved.
- If `modality_keys` are incompatible beyond the allowed compatibility rules in `config/merge_policy.md`, block the merge even if evidence overlaps.
6. Reuse existing resolved mappings within a run to avoid oscillation.
- Maintain `run_mapping_cache[(type_keys, evidence_signature, modality_bucket)] -> resolved_target_or_unresolved_id`.
- If a candidate hits the same key, reuse the same decision, including unresolved targets.
7. Resolve confidence and merge policy explicitly.
- Use evidence overlap and modality compatibility as primary signals; do not rely on whole-note fuzzy similarity as the primary merge signal.
- `high`:
  - type and modality compatible
  - `evidence_overlap` meets the high threshold in `config/merge_policy.md`
  - `evidence_signature` is non-empty and not wrapper-only
  - action: merge into the resolved canonical target
- `medium`:
  - type and modality compatible
  - and either `evidence_overlap` meets the medium threshold or a prior consistent merge mapping exists for this exact `evidence_signature`
  - action: merge if blocked guardrails do not trigger; otherwise mark unresolved
- `low`:
  - otherwise
  - action: do not merge into an existing canonical note; create or continue an unresolved working note keyed by evidence signature
8. Tie-breaking must be invariant to appended boilerplate and surface perturbations.
- When multiple canonical targets remain possible after gating, select the one with:
  1. maximal `evidence_overlap`
  2. maximal exact `evidence_signature` match count
  3. deterministic canonical id ordering by lexicographic vault path or id
- Never select based on surface-only similarity or rewritten labels that include wrappers.
9. Ignore appended boilerplate or other surface perturbations that do not change evidenced anchors.
- If the only differences are wrapper-derived, treat them as non-informative and do not use them for evidence scoring or alias expansion.
10. Key unresolved working notes by evidence signature so reruns converge on the same unresolved target.
- Use `unresolved_id = hash(type_keys + modality_bucket + evidence_signature)`.
11. Record merge rationale with matched fields, evidence overlap, confidence, and blocked guardrails.
- Always include:
  - candidate evidence signature
  - target evidence overlap stats
  - modality and type compatibility result
  - the specific guardrail that blocked merging, if any
  - confidence level and why
12. Output resolved targets and unresolved items.
- Reruns on the same source, or append-boilerplate variants, should produce the same mapping decisions when evidenced anchors are unchanged.

## Guardrails

- false merges are worse than missed merges
- do not merge across incompatible types without strong evidence
- keep a rationale for every merge decision
- unresolved notes are working memory, not canonical replacements
- do not rely on whole-note fuzzy similarity as a primary merge signal
- do not allow appended or irrelevant boilerplate to change evidence-overlap-based scores
- do not merge when `evidence_signature` is empty or wrapper-only unless a prior consistent mapping exists in the run mapping cache

## Success

The vault stays deduplicated without corrupting entity identity, remains stable under paraphrase and append-boilerplate transforms, and produces more consistent canonical linking for downstream retrieval and citation alignment.
