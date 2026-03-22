# Skill: self-update-knowledge

## Purpose

Run the bounded daily auto-update loop for the skill pack.

## Use When

- scheduled daily maintenance
- manual request to improve extraction quality

## Calls

- `evaluate-graph`
- `propose-skill-change`
- `extend-evaluation`

## Procedure

1. Evaluate the current baseline on frozen and metamorphic benchmarks.
2. Review recent ingestion failures and low-confidence cases.
3. Propose one candidate change to one skill.
4. Apply the candidate in an isolated comparison workspace.
5. Re-run the evaluator on the same benchmark set.
6. Accept the change only if it passes all hard constraints and improves useful quality signals.
7. Record the run under `artifacts/` and update `pitfalls.md` if needed.

## Guardrails

- one candidate change per run
- no relaxing hard constraints
- do not edit `agents.md` during routine self-update
- if the evaluator missed a real failure, extend the evaluator before optimizing further

## Success

The skill pack improves incrementally without drifting into ungrounded or self-serving behavior.
