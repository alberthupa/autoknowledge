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

## Milestone 5.5: Vault Adaptation Layer

- [x] Add a vault-profile abstraction that separates the internal note model from the vault-facing layout.
- [x] Support legacy-note classification when frontmatter is missing.
- [x] Add an initial profile for the real Obsidian vault taxonomy under `400 Entities/`.
- [x] Make integrity checks strict only for notes explicitly managed by AutoKnowledge.
- [x] Tighten candidate kind routing so managed writes can place clear cases into vault-specific entity subtypes and send ambiguous cases to the profile fallback bucket.
- [x] Add regression coverage for subtype routing under the real-vault profile.
- [x] Define the minimal-frontmatter patch policy for adopting legacy notes without high churn.
- [x] Add write-scope guardrails so profile-based writes can only touch configured managed roots.

## Milestone 6: Personal Vault Integration

- [x] Add configuration for an external Obsidian vault path and selected vault profile.
- [x] Add backup and dry-run modes before writing to the vault.
- [x] Unify the runtime and skill architecture across all modes and commands.
- [x] Publish one command-to-skill contract that covers every CLI command and every mutable skill across the durable docs, not only this plan.
- [x] Classify each CLI command as either skill-backed behavior or harness-only infrastructure.
- [x] Remove ambiguity that skill files are alternative user-facing commands rather than internal behavior modules.
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
- [x] Added a vault-profile layer so the runtime can target different vault layouts without changing the internal model.
- [x] Added the first real-vault profile for `/home/albert/repos2/obsidian`, mapping `400 Entities/...` folders to entity subtypes.
- [x] Added legacy-note type inference and unmanaged-note validation relaxation so the real vault can be indexed without forced YAML migration.
- [x] Split extraction heuristic kind from vault-facing `entity_kind` routing and added conservative subtype inference with fallback to unresolved placement.
- [x] Added a routing benchmark suite for `obsidian_albert` so clear placements and forbidden misroutes are now regression-tested.
- [x] Locked and implemented the `legacy_minimal` adoption mode so existing notes get minimal ownership frontmatter while keeping their original body intact.
- [x] Enforced profile-aware apply safety: managed-root write scope and mandatory backups for destructive applies on the real-vault profile.
- [x] Captured reusable architecture lessons in `self-improving-knowledge-ingestion-idea.md`.

Current live state at the end of the session:

- [x] The profile-aware routing benchmark suite passes for `obsidian_albert` (`3/3`).
- [x] The external vault copy can now be indexed and checked through a vault profile instead of the scaffolded layout.
- [x] A direct integrity pass against `/home/albert/repos2/obsidian` now works through `obsidian_albert` and reports vault-content issues instead of frontmatter/schema churn.
- [x] The local frozen, retrieval, and metamorphic manifests now run again from repo-owned fixtures under `benchmarks/shared/fixtures/`.
- [x] Frozen, retrieval, and metamorphic all pass locally against the current deterministic path (`4/4`, `2/2`, `3/3`).
- [x] Self-update primary-cluster acceptance now supports metric-specific absolute and relative improvement floors, so small duplicate-rate and churn wins are no longer rejected by a coarse shared threshold.
- [x] Candidate subtype routing now places clear `person`/`company`/`source` cases into typed folders and leaves ambiguous file-extracted fragments in the profile fallback bucket.
- [x] Legacy-note adoption now uses `managed_format: "legacy_minimal"` and is covered by a seeded routing regression case.
- [x] Profile-aware apply now rejects out-of-scope writes and requires backups before overwriting existing notes in the real-vault profile.
- [x] Live claim stabilization now canonicalizes provider claims back to source sentences, filters generic discussion-only claims, and backfills deterministic evidence claims for repeated entities.
- [x] Shared identity matching now collapses article-prefixed aliases like `The Mars` into the same canonical entity key, and frozen coverage now guards against article-based near-duplicates.
- [x] The live frozen suite now passes again after the `entities/portability.md` reingest/idempotence fix.
- [x] Post-stabilization self-update was rerun on `openai_primary`; it rejected the proposed `resolve-identity` skill change because the primary duplicate-rate cluster did not improve enough.
- [x] `--keep-workdirs` now actually preserves benchmark and self-update workspaces for live-flake debugging instead of cleaning them up on process exit.
- [x] Runtime config now supports an ignored `config/runtime.local.json` overlay for external vault path, selected vault profile, and backup policy, and vault commands can use those defaults without repeating `--vault`.
- [x] Audited the current CLI surface and mutable skill inventory, and recorded the working command-to-skill matrix in this plan.
- [x] The current runtime-to-skill boundary is now documented consistently in the durable docs: `main.py` is the executable path, while `skills/` is the mutable behavior layer behind it.
- [ ] The system is improving correctly, but it is not yet safe for unattended writes into the personal vault.

## Stop Point: 2026-03-26

This is the exact stop point for the current session.

What was just done on the real vault:

- [x] Applied `test_ingest.md` to the main vault with `openai_primary` using `config/runtime.real.local.json`.
- [x] The real source note was written under `sources/files/2026/2026-03-26--test-ingest--src_2e36a38a.md`.
- [x] New notes were created for:
  - `400 Entities/people/_autoknowledge/Paul Danifo.md`
  - `concepts/ai-ready-data-layers.md`
  - `concepts/gen-bi-backbone.md`
  - `concepts/kpi-as-a-service.md`
  - `concepts/kpi-steward.md`
  - `concepts/ontology.md`
- [x] One existing company note was updated:
  - `400 Entities/companies/Mondelez.md`
- [x] Existing person-note updates were suppressed by default during this apply.
- [x] A backup was created before the overwrite at:
  - `artifacts/vault_backups/2026-03-26T19-06-53`

Important observations from the last real apply:

- [x] The `Albert` self-reference suppression is working.
- [x] The vague concept suppression is working.
- [x] Low-signal project fragments like `Service Core` are now blocked.
- [x] New person notes for `obsidian_albert` route into `400 Entities/people/_autoknowledge`.
- [ ] Existing company notes can still be updated by ingestion, as shown by the `Mondelez.md` overwrite.
- [ ] Existing person-note updates are now guarded, but there is not yet an equivalent guard for existing company, offer, project, source, or concept notes.
- [ ] The exact applied result from `openai_primary` is still somewhat provider-variant between runs, so repeated dry-runs should still be reviewed before real applies.
- [ ] Post-apply integrity still reports 42 broken links in the main vault; these are existing vault-content issues, not proof of apply failure.

What to do first next session:

1. [ ] Decide write policy for existing canonical notes beyond people.
   - Minimum decision needed: should existing company notes like `Mondelez.md` be protected by default in the same way as people notes.
   - Likely follow-up: add a broader `allow-existing-entity-updates` policy or per-kind guards.

2. [ ] Review the notes created by the `test_ingest.md` apply in the main vault.
   - Confirm whether `ai-ready-data-layers`, `gen-bi-backbone`, `kpi-as-a-service`, `kpi-steward`, and `ontology` are acceptable as canonical concepts in this vault.
   - If not, tighten the concept-admission policy before any further real-vault applies.

3. [ ] Continue Track C and align the runtime/skill architecture.
   - Use `python3 main.py runtime-contract-check` as the lightweight regression check for contract drift whenever the CLI surface or skill inventory changes.
   - Expand `repair-graph` beyond deterministic structural fixes only if the merge policy and benchmarks can prove those repairs are safe.

4. [ ] Only after the write-policy decision, continue real-vault ingestion experiments.
   - Keep using backup-first and dry-run-first for new source types.
   - Do not assume that a clean person-note policy alone is sufficient for unattended apply safety.

## What To Do Next

The pre-Milestone-6 tracks are now functionally converged.

Milestone 6 can begin, but rollout should stay backup-first and dry-run-first while the intermittent live duplicate-rate warning continues to be monitored.

Before scheduled automation, the repo needs one more architectural pass so the runtime and skill pack say the same thing.

### Track C: Unify skill routing and CLI surface

1. [x] Create an authoritative working command-to-skill matrix covering all current CLI commands and all mutable skills.
   - Execution contract chosen for the current repo state: Python-first harness. `main.py` is the only user-facing command dispatcher; mutable skills define the behavioral contract that live extraction prompts and self-update proposals follow.
   - Skill-backed runtime commands:
     - `ingest-file`, `ingest-conversation`, `ingest-batch-files` -> `ingest-knowledge`
     - internal bounded steps within that orchestration -> `ingest-source`, `extract-knowledge`, `resolve-identity`, `update-vault`
     - `repair-graph` -> `repair-graph`
     - `self-update-run` -> `self-update-knowledge`
     - internal bounded steps within that orchestration -> `evaluate-graph`, `propose-skill-change`, `extend-evaluation`
   - Harness-only runtime commands:
     - `index`, `diff`, `runtime-contract-check`, `list-models`, `benchmark-run`, `ledger`, `ledger append`, `ledger tail`
     - `check`, `metrics`, and `qa-run` remain harness evaluation utilities that operationalize parts of `evaluate-graph` but are not themselves mutable skills
   - Mutable skills with no direct user-facing CLI entrypoint today:
     - `ingest-source`, `extract-knowledge`, `resolve-identity`, `update-vault`, `propose-skill-change`, `extend-evaluation`
   - Current repair scope:
     - `repair-graph` is now first-class, but it still limits automated edits to deterministic structural fixes and leaves risky merges for manual review

2. [x] Decide and document the execution contract between the thin harness and the mutable skill layer.
   - The runtime remains Python-first and skills are the portable behavioral contract it follows.
   - `README.md`, `AGENTS.md`, `skills/README.md`, and prompt-loading references now describe the same contract.
   - Do not add a second user-facing command surface for skills unless the runtime is intentionally redesigned around an explicit skill dispatcher.

3. [ ] Align the ingestion vocabulary so there is one user-facing ingestion entrypoint and no accidental parallel workflow.
   - `ingest-source` should be documented as an internal bounded step, not as a separate user command.
   - `ingest-knowledge` should be the orchestration concept behind the `ingest-*` CLI commands.
   - The same pattern should then be applied across repair, evaluate, and self-update.

4. [x] Add regression checks for the runtime/skill contract itself.
   - `config/runtime_skill_contract.json` now declares the machine-readable command and skill inventory.
   - `python3 main.py runtime-contract-check` now catches missing command mappings, skill drift, and stale lowercase `agents.md` references in the guarded runtime/doc files.

### Track A: Finish live-path stabilization

1. [x] Calibrate metric-specific acceptance thresholds in `self_update`.
   - Retrieval accuracy and link-density still use simple absolute floors.
   - Duplicate-rate and graph-churn primary-cluster acceptance now supports relative-improvement floors in addition to absolute deltas.
   - This prevents useful small wins from being rejected only because they are smaller than a coarse shared `0.01` threshold.

2. [x] Reduce live metamorphic churn on the live path.
   - `benchmarks/metamorphic/manifest.json` now passes under `openai_primary` (`3/3`).
   - The live stabilizer now canonicalizes provider claims to source evidence, drops generic discussion-only claims, and gives repeated deterministic entities a stable direct-evidence claim floor.
   - The repaired cases were:
     - `identity_equivalence_mars_overview`
     - `append_boilerplate_mars_overview`
     - `append_boilerplate_project_overview`

3. [x] Tighten duplicate handling on the live path.
   - Shared identity matching now uses article-insensitive variants for candidate anchoring, existing-note matching, and duplicate metrics.
   - This removes live near-duplicates like `The Mars` / `Mars` and `The Responses` / `Responses` when a stable non-prefixed anchor already exists.
   - Added a frozen regression case (`article_alias_dedup`) so article-prefixed aliases cannot reintroduce duplicate canonical notes silently.

4. [x] Rerun self-update after each runtime stabilization pass and keep only accepted changes that improve the current primary cluster.
   - A live `self-update-run` was executed against the current `openai_primary` baseline.
   - The proposed `skills/resolve-identity/SKILL.md` change was rejected because `high_duplicate_note_rate` did not improve enough to satisfy the primary-cluster threshold.
   - No prompt-only change was applied back into the repo.

### Track B: Harden the vault-adaptation layer

1. [x] Re-run the routing and integrity loop with the profile-aware path layer enabled.
   - `benchmarks/routing/manifest.json` now passes under `obsidian_albert`.
   - `check` against `/home/albert/repos2/obsidian` now succeeds through the profile-aware indexer and reports only actual vault-content issues (currently 56 broken links in the vault copy).

2. [x] Restore or replace the missing shared fixture corpus used by the older benchmark suites.
   - The old manifests now target repo-owned fixtures under `benchmarks/shared/fixtures/`.
   - Local benchmark execution no longer depends on a missing top-level `files/` directory.

3. [x] Re-run frozen, retrieval, and metamorphic after fixture restoration and confirm coexistence between `canonical_managed` and `obsidian_albert` without code forks.
   - `canonical_managed` deterministic suites now pass locally again.
   - `obsidian_albert` routing/integrity validation remains green on its own profile-aware path.

Milestone 6 should now begin in this order:

1. [x] Add explicit configuration for the external personal vault path, selected vault profile, and backup policy.
   - Tracked `config/runtime.json` remains portable.
   - Ignored `config/runtime.local.json` can point at the real vault and backup location.
   - Vault commands now fall back to runtime-configured vault settings when `--vault`, `--vault-profile`, or `--backup-dir` are omitted.
2. Unify the runtime/skill contract across all CLI commands and mutable skills so the harness and skill pack describe the same architecture.
3. Add scheduled entrypoints for daily ingest and daily self-update.
4. Verify the same skill pack and thin harness can be handed to the target autonomous agent setup without repo-specific assumptions.

Milestone 5 is functionally complete, and Milestone 5.5 is now complete. The remaining caution before connecting the system to the real personal vault is not the vault-adaptation layer anymore; it is operational discipline around backup-first rollout and monitoring intermittent live duplicate-rate noise during early Milestone 6 use.
