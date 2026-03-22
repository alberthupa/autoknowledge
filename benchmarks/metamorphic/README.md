# Metamorphic Benchmarks

Metamorphic benchmarks test whether meaning-preserving transformations lead to stable graph outcomes.

Current gated manifest:

- `manifest.json`

Current passing cases:

- exact baseline equivalence on `00 mars gemini - overview.md`
- append-only boilerplate invariance on `00 mars gemini - overview.md`
- append-only boilerplate invariance on `init project overview.md`

Supported transformations in the runner:

- no transform
- `append_boilerplate`
- `prepend_boilerplate`

Not yet gated:

- prepended boilerplate on the current deterministic extractor, which can still perturb entity extraction
- tight-window or chunking invariance under more aggressive window settings
- paraphrase and alias-substitution cases
- conversation-specific metamorphic cases

These cases are central to the auto-update loop because they do not require manual labeling of every vault change.
