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
- [x] Tighten acceptance so a candidate must improve the primary failure cluster, not just the composite score.
- [x] Put mutable skill files on the real runtime path for live-model extraction and proposal generation.
- [x] Add debug visibility for reingest and metamorphic failures so remaining churn can be diagnosed precisely.
- [x] Stabilize live-source reingest enough that frozen idempotence cases now pass on the live path.
- [x] Improve retrieval QA behavior enough that the live retrieval suite now passes.

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

## Session Progress

This session materially changed the project state.

Completed and verified:

- [x] Added repo-owned deterministic model/profile configuration and live model selection.
- [x] Added `.env` loading for local CLI runs.
- [x] Added extraction-time windowing for large files and conversations.
- [x] Added empty-input skipping and cumulative batch dry-run.
- [x] Added frozen, metamorphic, and retrieval benchmark suites.
- [x] Added source-grounded retrieval QA.
- [x] Added graph-quality metrics for duplicate rate, isolated-note rate, and graph churn.
- [x] Added bounded self-update with artifact logging and strict accept/reject rules.
- [x] Fixed live-path idempotence regressions caused by same-source anchor churn.
- [x] Tightened provider-only candidate admission and wrapper-text filtering for live extraction.
- [x] Improved retrieval ranking so direct `mentioned_in` facts and citation-bearing facts surface correctly.
- [x] Captured reusable architecture lessons in `self-improving-knowledge-ingestion-idea.md`.

Current live state at the end of the session:

- [x] Frozen benchmark suite passes on the live path.
- [x] Retrieval benchmark suite passes on the live path.
- [ ] Metamorphic benchmark suite still has 3 failing live cases.
- [ ] Duplicate-rate and graph-churn improvements are now small enough that the acceptance policy needs finer metric-specific thresholds.
- [ ] The system is improving correctly, but it is not yet safe for unattended writes into the personal vault.

## What To Do Next

The next concrete step is not Milestone 6 yet.

Before Milestone 6, finish the remaining live-path stabilization work:

1. Calibrate metric-specific acceptance thresholds in `self_update`.
   - Retrieval accuracy can use coarse thresholds like `0.01`.
   - Duplicate-rate and churn improvements now happen at much smaller scales and need finer thresholds or relative-improvement rules.
   - This should prevent useful small wins from being rejected for the wrong reason.

2. Keep reducing live metamorphic churn.
   - The remaining live failures are all in `benchmarks/metamorphic/manifest.json`.
   - Focus especially on:
     - `identity_equivalence_mars_overview`
     - `append_boilerplate_mars_overview`
     - `append_boilerplate_project_overview`
   - The likely work area is still live extraction consistency and candidate normalization, not schema or vault integration.

3. Tighten duplicate handling on the live path.
   - The current primary failure cluster has shifted to `high_duplicate_note_rate`.
   - Continue improving provider-only candidate admission, deterministic anchoring, and identity-resolution stability until duplicate-rate regressions fall further.

4. Rerun self-update after each runtime stabilization pass and keep only accepted changes that improve the current primary cluster.

Only after those steps should Milestone 6 begin:

1. Add explicit configuration for the external personal vault path and backup policy.
2. Add scheduled entrypoints for daily ingest and daily self-update.
3. Verify the same skill pack and thin harness can be handed to the target autonomous agent setup without repo-specific assumptions.

Milestone 5 is functionally complete, but the live benchmark baseline still needs one more round of stabilization before the system should be connected to the real personal vault.
