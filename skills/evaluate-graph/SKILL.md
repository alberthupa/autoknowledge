# Skill: evaluate-graph

## Purpose

Evaluate vault quality and extraction behavior using deterministic checks plus bounded agent judgment.

## Use When

- after ingestion
- before and after candidate skill changes
- when graph quality appears to be drifting

## Inputs

- vault index
- recent diffs
- benchmark cases
- metric configuration

## Outputs

- hard-check pass or fail
- soft metric scores
- failure clusters
- candidate regression summary

## Procedure

1. Run hard constraints first.
2. Score soft metrics such as duplicate rate, orphan rate, unsupported claims, and churn.
3. Run metamorphic comparisons on transformed versions of the same source.
4. Run source-grounded retrieval checks against benchmark material.
5. Summarize where the current skill pack fails and what types of failures dominate.

## Guardrails

- do not accept a higher soft score if a hard constraint fails
- prefer evaluator outputs that are reproducible
- do not silently redefine success during a comparison run

## Success

The evaluator surfaces clear, stable signals that can guide self-update.
