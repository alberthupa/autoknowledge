# Skills

This directory is the mutable behavior layer for AutoKnowledge.

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

These skills are designed to be portable across coding-agent harnesses. They should stay prompt-centric and avoid unnecessary assumptions about runtime-specific APIs.
