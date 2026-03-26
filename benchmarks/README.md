# Benchmarks

This directory holds the non-human evaluation suite for AutoKnowledge.

Three benchmark families are in use:

- `frozen/` for stable regression cases
- `metamorphic/` for meaning-preserving transformations
- `retrieval/` for source-grounded QA over the resulting vault
- `routing/` for vault-profile-aware path placement regression checks

Shared deterministic input fixtures now live under `shared/fixtures/` so the benchmark suite is fully repo-owned and does not depend on an external `files/` corpus.

Current entrypoints:

- `python3 main.py benchmark-run --manifest benchmarks/frozen/manifest.json`
- `python3 main.py benchmark-run --manifest benchmarks/metamorphic/manifest.json`
- `python3 main.py benchmark-run --manifest benchmarks/retrieval/manifest.json`
- `python3 main.py benchmark-run --manifest benchmarks/routing/manifest.json`

The evaluator should compare candidate skill changes against the same benchmark set before acceptance.
