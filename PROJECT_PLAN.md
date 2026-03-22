# Project Plan

This file tracks the delivery plan for AutoKnowledge. Checkboxes represent the current scaffold state of the repo.

## Milestone 0: Project Scaffold

- [x] Define the project idea and repository purpose in `README.md`.
- [x] Create an execution plan in `PROJECT_PLAN.md`.
- [x] Create `agents.md` with routing rules and invariants.
- [x] Create the first-pass `skills/` layout.
- [x] Add placeholder config, benchmark, state, and artifact directories.
- [x] Initialize git for the repository.

## Milestone 1: Vault Contract

- [x] Define the canonical note types and frontmatter contract.
- [x] Define the source-note contract for files and conversations.
- [x] Define file naming rules and note placement rules.
- [x] Define source reference anchors and evidence block conventions.
- [x] Define how contradictions and uncertain merges are represented.

## Milestone 2: Thin Harness

- [x] Implement a vault inventory/indexer.
- [x] Implement a vault diff summarizer.
- [x] Implement a local graph integrity checker.
- [x] Implement a metric runner for hard constraints and soft metrics.
- [x] Implement an experiment ledger for self-update runs.

## Milestone 3: Ingestion Pipeline

- [x] Implement ingestion for general files.
- [x] Implement ingestion for message logs and conversations.
- [x] Implement the structured extraction contract used by the extractor skill.
- [x] Implement identity resolution helpers against the existing vault.
- [x] Implement minimal-patch vault writing.
- [x] Add configurable extractor profiles and per-run model overrides.
- [x] Wire live OpenAI and Anthropic extraction backends behind the profile layer.
- [x] Add extraction-time windowing and window-result reduction for large files and conversations.

## Milestone 4: Evaluation Suite

- [x] Create a frozen benchmark set with expected structural outcomes.
- [x] Create metamorphic benchmark generators.
- [x] Implement source-grounded retrieval QA checks.
- [x] Implement duplicate/orphan/churn scoring.
- [x] Add regression cases for failure patterns recorded in `pitfalls.md`.

## Milestone 5: Self-Update Loop

- [x] Implement failure clustering from recent ingestion runs.
- [x] Implement proposal format for single-skill changes.
- [x] Implement candidate-vs-baseline evaluation.
- [x] Implement accept/reject rules with guardrails.
- [x] Persist self-update reports under `artifacts/`.

## Milestone 6: Personal Vault Integration

- [ ] Add configuration for an external Obsidian vault path.
- [ ] Add backup and dry-run modes before writing to the vault.
- [ ] Add a scheduled daily self-update entrypoint.
- [ ] Add a scheduled ingest entrypoint for watched directories.
- [ ] Verify the same skill pack works with the target autonomous agent setup.

## Milestone 7: Skill-Pack Portability

- [ ] Review skill wording for tool-agnostic use across Codex, Claude Code, OpenCode, and OpenClaw.
- [ ] Minimize assumptions about local helper commands.
- [ ] Document the runtime contract for sharing the skill pack.
- [ ] Version the accepted skill pack and evaluation baseline.

## What To Do Next

The next concrete step is Milestone 6.

1. Add explicit configuration for the external personal Obsidian vault path and backup policy.
2. Add scheduled entrypoints for daily ingest and daily self-update.
3. Verify the same skill pack and thin harness can be handed to the target autonomous agent setup without repo-specific assumptions.

The bounded self-update loop is now in place. The next leverage point is connecting it safely to the real personal vault and the external autonomous agent runtime.
