# Pitfalls

This file records recurring failure patterns discovered during ingestion and self-update.

Initial categories:

- duplicate canonical notes caused by alias drift
- claims extracted without precise evidence anchors
- over-creation of weak concept notes
- silent flattening of contradictory claims
- excessive churn from broad note rewrites
- weak performance when the same conversation is chunked differently

As the project matures, new evaluator cases should be derived from recurring pitfalls.

Recent concrete failures now covered by the harness and frozen suite:

- local CLI missing `.env` loading caused provider auth failures despite valid repo-local credentials
- OpenAI structured extraction could truncate and surface as invalid JSON instead of a clear incomplete-output error
- empty input files produced invalid source notes with missing evidence blocks
- batch dry-run originally planned each file in isolation and overstated creates while missing cross-file merge behavior

Current evaluator targets not yet promoted to gating cases:

- prepending irrelevant boilerplate at the top of a document can still perturb deterministic entity extraction
- aggressive re-windowing can materially change the deterministic canonical graph instead of preserving meaning
