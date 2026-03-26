# AutoKnowledge

or SELF IMPROVING MEMORY

AutoKnowledge is a skill-pack project for autonomous knowledge extraction into an Obsidian-style vault.

The central idea is to treat an agent as:

- a fixed policy layer in `AGENTS.md`
- a mutable behavior layer in `skills/`
- a thin deterministic harness for indexing, diffing, and scoring

Instead of letting the agent rewrite an arbitrary codebase, the self-improving surface is intentionally narrow. The agent should learn to improve how it extracts, merges, cites, and repairs knowledge in a markdown vault.

## Goal

Build a portable skill pack that can be used by tools like Codex, Claude Code, OpenCode, or OpenClaw to do two things:

1. Ingest new knowledge from files, messages, and conversation logs into a personal Obsidian vault.
2. Periodically improve its own extraction behavior through a bounded auto-update loop.

## What "knowledge graph" means here

The knowledge graph is an Obsidian vault: markdown notes connected with wiki links.

The graph should be:

- source-grounded
- incrementally updated
- low churn
- deduplicated where possible
- tolerant of ambiguity and contradiction

## Core design

The system is split into two loops.

### 1. Ingest Loop

Used whenever new material arrives.

1. Normalize the incoming file or conversation.
2. Create or update a raw source note.
3. Extract candidate entities, concepts, and claims.
4. Resolve identity against existing canonical notes.
5. Apply minimal patches to the vault.
6. Run local quality checks.

### 2. Self-Update Loop

Used on a schedule, for example once per day.

1. Review recent ingestion failures, regressions, and low-confidence cases.
2. Propose one change to one skill.
3. Run evaluation on frozen and metamorphic benchmark sets.
4. Accept the change only if it improves quality without violating hard constraints.
5. Record the outcome and update `pitfalls.md`.

## Evaluation philosophy

This project avoids relying on a human reviewer for every change. The evaluator should combine:

- hard constraints
- soft metrics
- metamorphic tests
- source-grounded retrieval checks

### Hard constraints

- Every factual claim must have a source reference.
- Re-ingesting the same source should be idempotent or near-idempotent.
- Raw source notes are append-only.
- Conflicts should be represented, not silently flattened.
- The vault must remain parseable and internally linked.

### Soft metrics

- citation coverage
- unsupported claim rate
- duplicate note rate
- orphan note rate
- graph churn per ingestion
- retrieval usefulness from the vault
- identity resolution quality

### Metamorphic tests

Use transformations that should preserve meaning:

- re-ingest identical input
- paraphrase the same source
- ingest a whole conversation vs chunked conversation
- add irrelevant boilerplate
- switch between alias and canonical names

If the vault result changes too much under these transformations, the skill pack is not stable enough.

## Repository layout

```text
AGENTS.md
skills/
config/
benchmarks/
artifacts/
state/
pitfalls.md
PROJECT_PLAN.md
auto_update_loop_summary.md
main.py
autoknowledge/
```

### `AGENTS.md`

Defines the fixed operating policy, routing rules, invariants, and self-update boundaries.

### `skills/`

Contains the mutable skill definitions that do the actual work. These are the main self-improving surface.

### `config/`

Contains note schema and evaluation configuration. These may evolve more slowly than skills.

Important runtime files:

- `config/runtime.json` selects the default extractor profile for files, conversations, and batch runs
- `config/runtime.local.json` can override the vault path, vault profile, and backup policy for one local machine without changing tracked config
- `config/runtime.local.example.json` shows the intended local override shape
- `config/runtime_skill_contract.json` is the machine-readable command-to-skill contract checked by the harness
- `config/model_profiles.json` defines the named extractor profiles and their backend/model settings
- `config/extraction_contract.md` defines the structured payload expected between extraction and writing
- `config/self_update.json` defines the bounded self-update policy, allowed target skills, warning thresholds, and comparison guardrails

### `benchmarks/`

Stores benchmark datasets and metamorphic cases used by the evaluator.

### `artifacts/`

Stores experiment reports, evaluation runs, and accepted/rejected self-update records.

### `state/`

Stores machine-readable state for scheduling, run ledgers, and benchmark manifests.

### `main.py` and `autoknowledge/`

Contain the thin local harness for:

- vault indexing
- contract validation
- metric calculation
- snapshot diffing
- experiment ledger writes
- deterministic ingestion planning and application

## Thin Harness Commands

Current zero-dependency commands:

```bash
cp config/runtime.local.example.json config/runtime.local.json
python3 main.py index --vault /path/to/vault --output /tmp/vault_index.json
python3 main.py index --vault /path/to/vault --vault-profile obsidian_albert --output /tmp/vault_index.json
python3 main.py index --output /tmp/vault_index.json
python3 main.py check --vault /path/to/vault
python3 main.py check
python3 main.py metrics --vault /path/to/vault
python3 main.py metrics
python3 main.py diff --before /tmp/before.json --after /tmp/after.json
python3 main.py ingest-file --vault /path/to/vault --input /path/to/file.md
python3 main.py ingest-file --vault /path/to/vault --vault-profile obsidian_albert --input /path/to/file.md
python3 main.py ingest-file --input /path/to/file.md
python3 main.py ingest-file --vault /path/to/vault --input /path/to/file.md --apply
python3 main.py ingest-file --input /path/to/file.md --apply
python3 main.py ingest-file --vault /path/to/vault --input /path/to/file.md --profile deterministic_minimal
python3 main.py ingest-file --vault /path/to/vault --input /path/to/file.md --profile openai_primary --model gpt-5.4
python3 main.py ingest-conversation --vault /path/to/vault --input /path/to/chat.txt
python3 main.py ingest-conversation --input /path/to/chat.txt
python3 main.py ingest-conversation --vault /path/to/vault --input /path/to/chat.txt --apply
python3 main.py ingest-batch-files --input-dir files
python3 main.py ingest-batch-files --vault /path/to/vault --input-dir files --profile deterministic_minimal --summary-output /tmp/batch.json
python3 main.py ingest-batch-files --vault /path/to/vault --input-dir files --profile anthropic_primary --model claude-sonnet-4-20250514
python3 main.py list-models --provider openai
python3 main.py list-models --provider anthropic
python3 main.py repair-graph --vault /path/to/vault
python3 main.py repair-graph --vault /path/to/vault --apply --backup-dir /path/to/backups
python3 main.py runtime-contract-check
python3 main.py benchmark-run --manifest benchmarks/frozen/manifest.json
python3 main.py benchmark-run --manifest benchmarks/metamorphic/manifest.json
python3 main.py benchmark-run --manifest benchmarks/retrieval/manifest.json
python3 main.py qa-run --vault /path/to/vault --questions /path/to/questions.json
python3 main.py self-update-run --benchmark-profile openai_primary --proposal-profile openai_primary
python3 main.py self-update-run --benchmark-profile openai_primary --benchmark-model gpt-5.4 --proposal-model gpt-5.4-nano
python3 main.py self-update-run --benchmark-profile deterministic_minimal --proposal-profile deterministic_minimal
python3 main.py ledger append --path state/ledger.jsonl --kind self-update --status accepted --summary "candidate improved duplicate rate"
python3 main.py ledger tail --path state/ledger.jsonl --limit 5
```

These commands are intentionally narrow. They are the fixed measurement layer that later ingestion and self-update skills should call into rather than re-implementing their own scoring logic.

## Runtime And Skill Contract

The current repo is Python-first:

- `main.py` is the only user-facing command dispatcher
- `AGENTS.md` defines the fixed operating policy
- `skills/` defines the mutable behavior contract used by live prompt construction and self-update
- skills are not a second CLI surface; they are the bounded behavior modules behind the runtime

Current command mapping:

- skill-backed ingestion commands:
  - `ingest-file`, `ingest-conversation`, `ingest-batch-files` -> `ingest-knowledge`
  - bounded internal ingestion steps -> `ingest-source`, `extract-knowledge`, `resolve-identity`, `update-vault`
- skill-backed repair command:
  - `repair-graph` -> `repair-graph`
- skill-backed self-update command:
  - `self-update-run` -> `self-update-knowledge`
  - bounded internal self-update steps -> `evaluate-graph`, `propose-skill-change`, `extend-evaluation`
- harness evaluation utilities:
  - `check`, `metrics`, and `qa-run` support the evaluation policy and operationalize parts of `evaluate-graph`, but are not mutable skills
- harness-only infrastructure:
  - `index`, `diff`, `runtime-contract-check`, `benchmark-run`, `list-models`, `ledger`, `ledger append`, and `ledger tail`

Current repair behavior is intentionally conservative:

- it normalizes uniquely resolvable wiki links onto canonical paths
- it dedupes repair-safe frontmatter lists on managed canonical notes
- it reports broken links, duplicate clusters, orphan notes, and isolated notes for manual review
- it does not attempt automatic duplicate merges or semantic graph rewrites

`python3 main.py runtime-contract-check` now validates this contract against the live CLI surface, the current `skills/` tree, and the expected `AGENTS.md` policy filename.

Current ingestion behavior is conservative by design:

- dry-run is the default
- `--apply` is explicit
- source notes are created deterministically
- empty inputs are skipped in batch mode and rejected in direct single-file ingestion
- batch dry-runs are cumulative against a disposable preview vault, so later files see earlier planned notes
- re-ingesting identical input produces no-op plans
- extracted canonical notes prefer sourced relationships over ambitious summaries
- raw source notes stay whole; large inputs are windowed only at extraction time and then reduced back into one plan

Vault shape is now profile-driven:

- `config/vault_profiles.json` maps internal note classes onto a concrete vault layout
- `canonical_managed` keeps the original repo-owned layout
- `obsidian_albert` infers `400 Entities/...` notes as entity notes even when frontmatter is missing
- strict schema validation applies only to notes managed by AutoKnowledge

Profile-aware apply safety is now enforced:

- writes are rejected if any planned path falls outside the active profile's managed roots
- non-canonical vault profiles require a backup directory when an apply would overwrite existing notes, either from `--backup-dir` or runtime config
- existing legacy notes are adopted with `managed_format: "legacy_minimal"` instead of being rewritten into the full canonical template

Local runtime targeting is now explicit:

- tracked `config/runtime.json` stays portable and can leave `vault.path` empty
- ignored `config/runtime.local.json` can point at one real vault and one real backup location
- vault commands now fall back to `runtime.local.json` or `runtime.json` when `--vault` and `--vault-profile` are omitted
- apply commands now also fall back to the configured `vault.backup_dir`

The structured ingestion payload is documented in [config/extraction_contract.md](/home/albert/python_projects/autoknowledge/config/extraction_contract.md).

The first frozen evaluation suite is in [benchmarks/frozen/manifest.json](/home/albert/python_projects/autoknowledge/benchmarks/frozen/manifest.json).
The first gated metamorphic suite is in [benchmarks/metamorphic/manifest.json](/home/albert/python_projects/autoknowledge/benchmarks/metamorphic/manifest.json).
The first source-grounded retrieval QA suite is in [benchmarks/retrieval/manifest.json](/home/albert/python_projects/autoknowledge/benchmarks/retrieval/manifest.json).

Current gated metamorphic coverage focuses on semantic stability for:

- exact equivalence between two identical runs
- appended irrelevant boilerplate on representative files

Known non-gated weakness: prepending irrelevant boilerplate or forcing tighter windows can still perturb the deterministic extractor enough to change the canonical graph. Those cases are tracked in [pitfalls.md](/home/albert/python_projects/autoknowledge/pitfalls.md) and should become gating once the extractor is more stable.

Current retrieval QA coverage focuses on deterministic mention lookup:

- it asks source-grounded questions against the post-ingestion vault
- it requires both the expected canonical note and the expected cited source block to appear in the retrieved answer
- it is intentionally narrow today because the current extractor mostly emits `mentioned_in` relationships rather than richer claim bullets

Current graph-quality metrics are more explicit than before:

- `grounded_note_rate` tracks whether canonical notes are actually backed by source refs
- `orphan_note_rate` is now strict and only flags notes with neither evidence nor graph connectivity
- `isolated_note_rate` captures the current weakness: evidence-grounded notes that are still not woven into the canonical graph
- `canonical_link_density` and normalized churn rates expose whether ingestion is building structure or only scattering mentions

## Extractor Selection

Extractor choice should be changed in repo config, not in the chat thread.

The intended control points are:

- `config/runtime.json` for the default profile used by normal runs
- `config/runtime.local.json` for a machine-local vault path, vault profile, and backup policy
- `config/model_profiles.json` for the profile definitions themselves
- `--profile ...` only for explicit one-off comparison runs

Current state:

- implemented backends are `deterministic`, `openai_responses`, and `anthropic_messages`
- live backends are implemented for `openai_primary` and `anthropic_primary`
- every ingestion plan records `extractor_profile`, `extractor_backend`, and `extractor_model` in its stats
- `openai_primary` retries once or twice on `max_output_tokens` truncation up to the cap in `config/model_profiles.json`
- extractor profiles also control windowing thresholds for files and conversations
- live extraction prompts now load `AGENTS.md` plus the relevant `skills/*.md`, so prompt-level skill edits can affect benchmark behavior
- live provider output is stabilized before vault writes: a deterministic extraction floor is merged in, low-signal provider-only candidates are dropped, and re-ingest candidates are snapped to existing vault notes by title/alias/slug when possible

This keeps evaluation comparable because extraction changes are versioned and explicit.

### Authentication And Model Discovery

OpenAI live extraction:

- set `OPENAI_API_KEY`
- local CLI runs also auto-load `.env` from the repo root if present
- optionally set `OPENAI_BASE_URL`
- use `python3 main.py list-models --provider openai` to inspect available model IDs

Anthropic live extraction:

- set `ANTHROPIC_API_KEY`
- local CLI runs also auto-load `.env` from the repo root if present
- optionally set `ANTHROPIC_BASE_URL`
- optionally set `ANTHROPIC_VERSION` if you need a different API version header
- use `python3 main.py list-models --provider anthropic` to inspect available model IDs

The chosen profile controls provider and backend. `--model` lets you override only the model ID for a specific run.
If a live extraction still reports truncation, raise the token budget in [config/model_profiles.json](/home/albert/python_projects/autoknowledge/config/model_profiles.json) or ingest a smaller batch/input.
Windowing thresholds also live in [config/model_profiles.json](/home/albert/python_projects/autoknowledge/config/model_profiles.json), so large-document behavior stays deterministic and benchmarkable.

## Self-Update Runner

The bounded self-update loop is now implemented under `python3 main.py self-update-run`.

Current behavior:

- baseline evaluation runs the frozen, metamorphic, and retrieval suites from `config/self_update.json`
- failures are clustered from benchmark failures plus threshold-based warnings such as high `isolated_note_rate`
- one proposal targets exactly one allowed skill file
- the candidate is evaluated in an isolated copied workspace
- the live repo is only changed if you pass `--apply-accepted`
- every run writes artifacts under `artifacts/self_update/` and appends a record to `state/ledger.jsonl`

Notes:

- the default self-update policy uses `openai_primary` for both proposal and benchmark runs
- you can override proposal and benchmark models independently with `--proposal-model` and `--benchmark-model`
- primary-cluster acceptance thresholds now live in `config/self_update.json` and can be tuned per metric with absolute and relative improvement floors
- deterministic self-update runs are useful as a smoke test, but they will usually reject with `no measurable improvement` because deterministic extraction does not consume prompt-only skill edits

## Principles

- Constrain what can change.
- Prefer minimal patches over broad rewrites.
- Prefer merge over duplication.
- Preserve provenance for every factual addition.
- Store uncertainty explicitly.
- Improve one thing at a time.
- Do not let the agent weaken hard constraints during self-update.

## Intended deployment model

The long-term target is:

- this repository holds the portable agent policy, skills, and evaluation harness
- the actual personal Obsidian vault can live outside the repo
- the same skill pack can be shared with an autonomous OpenClaw-style agent

This lets the operational knowledge base remain personal while the extraction logic stays portable and versioned.

## Transfer Learnings

These are the main lessons from building and correcting this system. If you rebuild the same idea elsewhere, keep these constraints and failure modes in mind from day one.

### 1. The mutable surface must be real

- self-update is fake if editing `skills/*.md` does not affect runtime behavior
- for live model paths, prompt construction must actually load `AGENTS.md` and the relevant skill files
- if prompt edits are not on the execution path, benchmark gains or losses are meaningless

### 2. Separate deterministic harness from mutable behavior

- keep indexing, diffing, integrity checks, benchmark execution, and ledgering fixed
- let the agent improve only prompts/skills at first
- if the evaluator and the behavior both drift at once, the loop learns to game the score

### 3. Treat live models as unstable by default

- deterministic extraction is easy to benchmark; live extraction is not
- live models vary across reruns even on identical input
- because of that, provider output must be normalized, filtered, and anchored before vault writes
- the right pattern is: deterministic scaffold first, model enrichment second

### 4. Idempotence needs explicit engineering

- reingesting the same source is not naturally stable with LLM output
- note identity must be snapped back to existing notes by title, alias, and canonical slug
- provider-only junk candidates must be dropped aggressively
- same-source evidence should not append paraphrased claims forever just because wording changed

### 5. Benchmarks must include metamorphic and retrieval checks

- structural validity alone is too weak
- the important regressions showed up as:
  - non-idempotent reingest
  - graph churn under equivalent inputs
  - retrieval misses on expected entities like `copilot`
- if those are not benchmarked, self-update will optimize the wrong thing

### 6. Acceptance policy must target the main failure, not only the score

- a small score gain is not enough
- accepted candidates must improve the primary failure cluster
- otherwise the system can improve duplicate rate or churn slightly while leaving the actual blocker unchanged

### 7. New datasets are mostly an evaluator/system test, not only a data test

- different corpora will expose different weak spots
- this is expected and not a sign that the idea is wrong
- the correct response is usually:
  - add representative failures to benchmarks
  - tighten normalization
  - improve acceptance policy
- do not overfit one dataset by weakening global guardrails

### 8. Obsidian-style graphs need source-grounded minimalism

- source notes should stay whole and append-only
- large sources should be windowed only for extraction, not for storage
- canonical notes should prefer small sourced claims and relationships over broad prose summaries
- provenance matters more than elegance

### 9. Personal-vault integration should come late

- do not connect autonomous self-update directly to a real personal vault until:
  - live benchmark baselines are stable enough
  - self-update acceptance is strict enough
  - backup and dry-run paths exist
- the skill pack can become portable before the personal vault becomes writable

## Status

This repository now has:

- a locked vault contract
- an initial skill-pack layout
- a thin CLI harness for indexing, validation, metrics, diffs, and ledgering
- a first conservative ingestion pipeline for files and conversations
- configurable extractor profiles with deterministic and live provider backends
- per-run model selection through `--model` plus repo-owned defaults in `config/model_profiles.json`
- frozen and metamorphic benchmark manifests wired into the CLI
- source-grounded retrieval QA wired into both `benchmark-run` and `qa-run`
- graph-quality scoring now separates grounded, orphaned, isolated, duplicate-cluster, and churn-rate signals
- bounded self-update with proposal, baseline-vs-candidate evaluation, artifacts, and stricter primary-cluster acceptance rules

The next implementation step is live-path runtime stabilization until the OpenAI-backed baseline is stable enough for safe external-vault integration.

See [PROJECT_PLAN.md](/home/albert/python_projects/autoknowledge/PROJECT_PLAN.md) for the next milestones.

## Vault Targets

Two local runtime overlays are now available for switching vault targets without editing tracked config:

- copy vault: [config/runtime.copy.local.json](/home/albert/repos2/autoknowledge/config/runtime.copy.local.json)
- real vault: [config/runtime.real.local.json](/home/albert/repos2/autoknowledge/config/runtime.real.local.json)

Current default local runtime remains:

- [config/runtime.local.json](/home/albert/repos2/autoknowledge/config/runtime.local.json)

Use the copy vault:

```bash
python3 main.py check --config-root config --runtime-config config/runtime.copy.local.json
python3 main.py ingest-file --input test_ingest.md --config-root config --runtime-config config/runtime.copy.local.json
python3 main.py ingest-file --input test_ingest.md --config-root config --runtime-config config/runtime.copy.local.json --apply
```

Use the real vault:

```bash
python3 main.py check --config-root config --runtime-config config/runtime.real.local.json
python3 main.py ingest-file --input test_ingest.md --config-root config --runtime-config config/runtime.real.local.json
python3 main.py ingest-file --input test_ingest.md --config-root config --runtime-config config/runtime.real.local.json --apply
```
