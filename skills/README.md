# Skills

This directory is the mutable behavior layer for AutoKnowledge.

`main.py` remains the only user-facing command surface. Files under `skills/` are internal behavior modules that the runtime and live prompt builders follow.

The intended shape is:

- orchestration skills route work
- atomic skills perform one bounded step
- evaluation skills judge behavior
- self-update skills improve the other skills

The current skill set is:

- `ingest-knowledge`
- `ingest-source`
- `extract-knowledge`
- `resolve-identity`
- `update-vault`
- `repair-graph`
- `evaluate-graph`
- `propose-skill-change`
- `extend-evaluation`
- `self-update-knowledge`

Current runtime contract:

- `ingest-file`, `ingest-conversation`, and `ingest-batch-files` map to `ingest-knowledge`
- internal ingestion steps map to `ingest-source`, `extract-knowledge`, `resolve-identity`, and `update-vault`
- `repair-graph` maps to `repair-graph`
- `self-update-run` maps to `self-update-knowledge`
- internal self-update steps map to `evaluate-graph`, `propose-skill-change`, and `extend-evaluation`
- `check`, `metrics`, and `qa-run` are harness evaluation utilities, not mutable skills
- `index`, `diff`, `runtime-contract-check`, `benchmark-run`, `list-models`, and `ledger` are harness-only commands
- current deterministic repair scope is intentionally narrow: normalize uniquely resolvable links, dedupe repair-safe metadata, and surface the rest for manual review

These skills are designed to be portable across coding-agent harnesses. They should stay prompt-centric and avoid unnecessary assumptions about runtime-specific APIs.
