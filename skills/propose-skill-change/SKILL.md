# Skill: propose-skill-change

## Purpose

Generate one bounded self-improvement hypothesis for the skill pack.

## Use When

- evaluation reveals recurring failures
- the daily self-update loop needs one candidate change

## Inputs

- recent evaluation report
- recent failures
- `pitfalls.md`

## Outputs

- one target skill file
- one concrete prompt or workflow edit
- one expected effect
- one evaluation plan

## Procedure

1. Review recent failures and group them by pattern.
2. Pick the highest-value failure pattern.
3. Propose one change to one skill.
4. State why the change should help.
5. State what benchmark evidence would count as success.

## Guardrails

- do not propose broad refactors
- do not change multiple skills unless blocked by a hard dependency
- do not optimize for style; optimize for measured behavior

## Success

The proposal is small, testable, and directly motivated by observed failures.
