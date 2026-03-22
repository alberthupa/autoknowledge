# Skill: extract-knowledge

## Purpose

Extract candidate knowledge objects from source material without directly editing the vault.

## Use When

- a normalized source note exists and needs structured interpretation

## Outputs

- candidate entities
- candidate concepts
- candidate claims
- candidate relations
- evidence references for every extracted item
- confidence and uncertainty annotations

Follow:

- `config/extraction_contract.md`
- `config/evidence_conventions.md`

## Procedure

1. Read the source note and preserve context.
2. Identify the document sections that carry substantive domain content versus wrappers such as appendices, export footers, mailing metadata, archival markers, or legal boilerplate.
3. Prioritize named entities, recurring concepts, and explicit claims from substantive sections.
4. Separate observations from interpretations.
5. Attach each item to evidence anchors in the source.
6. Mark temporal qualifiers and modality such as plans, guesses, or opinions.
7. Emit structured candidates for identity resolution.
8. When a candidate is supported only by appendix or footer style text, emit nothing unless the same fact is clearly reinforced by substantive evidence elsewhere in the source.
9. Prefer stable source wording over rewritten labels that combine content with section wrappers or export artifacts.

## Guardrails

- do not invent facts
- do not collapse uncertainty into certainty
- do not merge identities inside this skill
- prefer fewer high-quality claims over many weak claims
- do not treat appendices, mailing metadata, export markers, or legal boilerplate as standalone knowledge
- do not let surface-only formatting changes create new notes or claims

## Success

The output is structured, source-grounded, stable under append-boilerplate and formatting-only transforms, and safe for downstream resolution and note updates.
