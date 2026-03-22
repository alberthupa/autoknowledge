# Skill: extend-evaluation

## Purpose

Add evaluator coverage when the current metrics and tests fail to catch an important failure mode.

## Use When

- a bad behavior slips through despite passing evaluation
- a recurring failure pattern is not represented in current benchmarks

## Inputs

- failure report
- example sources
- current benchmark and metric definitions

## Outputs

- one new benchmark case or metamorphic transformation
- optionally one new soft metric
- rationale for why the new coverage matters

## Procedure

1. Identify the missing evaluator blind spot.
2. Encode the blind spot as a repeatable benchmark or comparison rule.
3. Prefer additive evaluation changes over policy changes.
4. Keep hard constraints intact.
5. Record the new failure type in `pitfalls.md`.

## Guardrails

- do not weaken existing evaluator rules
- do not add vague tests that cannot be reproduced
- evaluator growth must reduce blind spots, not excuse failures

## Success

The evaluation function gets harder to game and more aligned with real vault quality.
