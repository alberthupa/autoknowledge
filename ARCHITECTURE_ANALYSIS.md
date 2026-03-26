# Architecture Analysis: Ingest Loop and Self-Update Loop

## Executive Summary

AutoKnowledge was designed with a clean separation: skills define *what* to do (mutable behavior), `main.py` + `autoknowledge/` define *how to measure it* (fixed harness). In practice, the harness absorbed most of the actual execution logic. The skills ended up as prompt context for LLM calls and as documentation, not as executable orchestration. This document maps the actual flows and identifies the structural tensions.

---

## 1. Ingest Loop: Designed vs Actual

### Designed Flow (per AGENTS.md and skills/)

```
User calls ingest-file/ingest-conversation/ingest-batch-files
    |
    v
skills/ingest-knowledge  (orchestrator)
    |
    +-> skills/ingest-source        (normalize, create source note)
    +-> skills/extract-knowledge    (extract candidates)
    +-> skills/resolve-identity     (map candidates to existing notes)
    +-> skills/update-vault         (apply minimal patches)
    +-> skills/evaluate-graph       (post-write quality check)
    +-> skills/repair-graph         (optional cleanup)
```

Each skill was supposed to be a discrete behavioral step that an agent invokes.

### Actual Flow (per main.py and autoknowledge/ingest.py)

```
main.py ingest-file --input foo.md [--apply]
    |
    v
ingest.ingest_file()                          # monolithic Python function
    |
    +--[1] Read input, extract title           # ingest-source equivalent
    +--[2] resolve_profile()                   # pick deterministic or live backend
    +--[3] Build source note deterministically # ingest-source equivalent
    +--[4] Create evidence blocks              # ingest-source equivalent
    +--[5] Check for same-source reingest      # idempotence guard
    +--[6] _extract_file_candidates()          # extract-knowledge equivalent
    |       |
    |       +--[6a] _plan_extraction_windows() # windowing for large inputs
    |       +--[6b] IF live backend:
    |       |       providers.extract_with_provider()
    |       |           builds prompt from AGENTS.md + skill .md files  <-- SKILL FILES USED HERE
    |       |           calls OpenAI/Anthropic structured JSON API
    |       |       THEN _stabilize_live_candidates()
    |       |           merges deterministic floor + provider output
    |       |           drops low-signal provider-only junk
    |       |           snaps titles to existing vault notes
    |       +--[6c] IF deterministic backend:
    |       |       _deterministic_file_candidates_for_window()
    |       |           regex-based entity extraction
    |       |           titlecase matching, stopword filtering
    |       |           no LLM involved, no skill files read
    |       +--[6d] _resolve_candidate_entity_kinds()
    |       +--[6e] _filter_note_candidates()
    |
    +--[7] build_ingestion_plan()              # resolve-identity + update-vault equivalent
    |       |
    |       +-- index existing vault
    |       +-- lookup existing notes by slug/alias
    |       +-- merge or create for each candidate
    |       +-- render note content
    |       +-- produce PatchOperations
    |
    +--[8] Return IngestionPlan (dry-run JSON)
    |
    +--[9] IF --apply:
            apply_ingestion_plan()             # update-vault equivalent
                validate write scope
                backup existing notes
                write files to vault
            index_vault() + validate_index()   # evaluate-graph equivalent
```

### Key Divergences in the Ingest Loop

| Aspect | Designed | Actual |
|--------|----------|--------|
| **Skill invocation** | Agent calls each skill as a discrete step | All steps are hardcoded function calls in `ingest.py` |
| **Skill files** | Define behavior the agent follows | Loaded as prompt context only during live LLM extraction (step 6b) |
| **ingest-source** | Separate skill | Inline in `ingest_file()` lines 304-358 |
| **extract-knowledge** | Separate skill | `_extract_file_candidates()` - a 90-line branching function |
| **resolve-identity** | Separate skill with evidence-signature matching | `build_ingestion_plan()` does slug/alias lookup, no evidence-signature logic |
| **update-vault** | Separate skill | `apply_ingestion_plan()` - direct file writes |
| **evaluate-graph** | Post-write quality check | `validate_index()` runs after apply but is not skill-driven |
| **Deterministic path** | Skills should guide behavior | Skills are completely bypassed - pure regex/heuristic extraction |

### The Core Tension

**Skills were designed to be the mutable behavior layer that an agent follows.** In practice:

1. **Deterministic backend**: Skills are irrelevant. `_deterministic_file_candidates_for_window()` is a regex/heuristic extractor that never reads skill files. All the sophisticated identity-resolution logic in `skills/resolve-identity/SKILL.md` (evidence signatures, modality keys, compatibility gates) is not implemented in the Python code.

2. **Live backend**: Skills are *read* but only as prompt context. `EXTRACTION_CONTEXT_PATHS` in `providers.py` loads `AGENTS.md`, `extract-knowledge/SKILL.md`, `resolve-identity/SKILL.md`, and `update-vault/SKILL.md` as text appended to the system prompt. The LLM gets them as instructions, but the structured output is then immediately post-processed by the deterministic stabilization pipeline (`_stabilize_live_candidates`), which can override what the model returned.

3. **`ingest-knowledge` skill**: Describes an orchestration that calls sub-skills. No code ever reads or executes `skills/ingest-knowledge/SKILL.md`. It exists purely as documentation.

4. **`ingest-source` skill**: Same - never loaded, never referenced in code.

### What Actually Controls Ingestion Behavior

| Control surface | Affects deterministic? | Affects live? |
|----------------|----------------------|---------------|
| `ingest.py` Python logic | Yes (primary) | Yes (stabilization, windowing, filtering) |
| `config/model_profiles.json` | Yes (profile selection) | Yes (model, tokens, windowing) |
| `config/vault_profiles.json` | Yes (paths, entity kinds) | Yes (paths, entity kinds) |
| `skills/extract-knowledge/SKILL.md` | **No** | Yes (as prompt text) |
| `skills/resolve-identity/SKILL.md` | **No** | Yes (as prompt text) |
| `skills/update-vault/SKILL.md` | **No** | Yes (as prompt text) |
| `skills/ingest-knowledge/SKILL.md` | **No** | **No** |
| `skills/ingest-source/SKILL.md` | **No** | **No** |

---

## 2. Self-Update Loop: Designed vs Actual

### Designed Flow (per AGENTS.md)

```
Daily schedule or manual trigger
    |
    v
skills/self-update-knowledge  (orchestrator)
    |
    +-> skills/evaluate-graph       (baseline evaluation)
    +-> Review failures + pitfalls.md
    +-> skills/propose-skill-change (generate one hypothesis)
    +-> Apply candidate in isolated workspace
    +-> Re-evaluate
    +-> Accept/reject
    +-> Record in artifacts/ and pitfalls.md
```

### Actual Flow (per autoknowledge/self_update.py)

```
main.py self-update-run [--apply-accepted]
    |
    v
self_update.run_self_update()
    |
    +--[1] Load policy from config/self_update.json
    +--[2] Resolve proposal and benchmark profiles
    +--[3] _run_benchmark_stack() on live repo          # baseline
    |       |
    |       +-- For each manifest in policy.benchmark_manifests:
    |       |     subprocess.run("python3 main.py benchmark-run ...")
    |       |     which internally calls ingest + metrics on temp vaults
    |       +-- _aggregate_benchmark_results()
    |
    +--[4] cluster_failures()                           # analyze baseline
    |       |
    |       +-- classify each benchmark failure by type
    |       +-- check metric thresholds from policy
    |       +-- sort by priority
    |
    +--[5] _generate_skill_change_proposal()            # propose-skill-change equivalent
    |       |
    |       +-- IF live proposal profile:
    |       |     providers.propose_skill_change_with_provider()
    |       |         builds prompt from AGENTS.md + skill .md files  <-- SKILL FILES USED HERE
    |       |         sends failure clusters + current skill content to LLM
    |       |         LLM returns JSON with target_path + candidate_content
    |       +-- IF deterministic:
    |       |     _heuristic_skill_change_proposal()
    |       |         hardcoded failure-code-to-skill mapping
    |       |         _apply_heuristic_edit() inserts canned lines
    |
    +--[6] Validate target_path is in allowed_skill_targets
    +--[7] Copy repo to temp workspace
    +--[8] Write candidate skill content to temp workspace
    +--[9] _run_benchmark_stack() on temp workspace     # candidate evaluation
    +--[10] compare_reports()                           # accept/reject
    |        |
    |        +-- check for metric regressions
    |        +-- check for improvements
    |        +-- check primary cluster improved enough
    |        +-- must have improvements AND no regressions
    |
    +--[11] IF accepted AND --apply-accepted:
    |        copy skill file from temp workspace to live repo
    +--[12] Write artifacts, append ledger record
```

### Key Divergences in the Self-Update Loop

| Aspect | Designed | Actual |
|--------|----------|--------|
| **Skill orchestration** | `self-update-knowledge` calls sub-skills | `run_self_update()` is a monolithic ~150-line function |
| **evaluate-graph** | Skill-driven evaluation | `benchmark-run` subprocess + `_aggregate_benchmark_results()` |
| **propose-skill-change** | Skill defines the proposal process | Live: LLM gets skill files as context; Deterministic: hardcoded heuristics |
| **extend-evaluation** | Grows benchmark suite when needed | Never called - no code path triggers it |
| **Failure review** | Reviews recent ingestion failures | Only reviews benchmark failures, not actual ingestion history |
| **pitfalls.md** | Updated on accept/reject | Never updated by code - only mentioned in proposal prompt context |

### The Self-Update Paradox

The self-update loop edits skill files. But which skill files actually matter?

**What self-update is allowed to change** (from `config/self_update.json`):
- `skills/extract-knowledge/SKILL.md`
- `skills/resolve-identity/SKILL.md`
- `skills/update-vault/SKILL.md`

**When those changes have effect:**
- Only when the benchmark profile uses a **live LLM backend** (openai_primary or anthropic_primary)
- The changed skill text gets injected into the LLM extraction prompt via `EXTRACTION_CONTEXT_PATHS`
- The LLM may or may not follow the changed guidance
- The stabilization pipeline in `ingest.py` can override LLM output regardless

**When those changes have NO effect:**
- Deterministic backend: skill files are never read
- The `resolve-identity` skill describes evidence-signature logic that is not implemented in `build_ingestion_plan()`
- The `update-vault` skill describes patch behavior that is hardcoded in `apply_ingestion_plan()`

This is explicitly acknowledged in the code:
```python
if benchmark_profile.get("backend") == "deterministic":
    benchmark_warning = (
        "benchmark backend is deterministic; prompt-only skill edits
         are unlikely to change outcomes"
    )
```

---

## 3. The Skills-vs-Harness Spectrum

The skills sit on a spectrum of "how connected to execution":

```
FULLY CONNECTED                                         NOT CONNECTED
      |                                                       |
      v                                                       v
extract-knowledge  resolve-identity  update-vault   ingest-knowledge  ingest-source
  (prompt text)      (prompt text)   (prompt text)    (never loaded)  (never loaded)

propose-skill-change  evaluate-graph  self-update-knowledge  extend-evaluation
    (prompt text)       (never loaded)    (never loaded)       (never loaded)
```

**"Prompt text" means**: the skill's SKILL.md is read by `repo_context.build_context_bundle()` and appended to the system prompt of an LLM API call. The LLM receives it as guidance. The Python code does not parse or execute the skill's procedure steps.

**"Never loaded" means**: no code path reads the file at all. The skill exists only as documentation.

---

## 4. Identity Resolution: Designed vs Implemented

This is the biggest gap between skill design and implementation.

**`skills/resolve-identity/SKILL.md` describes:**
- Evidence-signature computation with `(vault note id, block anchor id)` tuples
- Surface keys, type keys, evidence keys, modality keys
- Evidence-anchor compatibility gating
- Run mapping cache for oscillation prevention
- Confidence levels (high/medium/low) with specific merge thresholds
- Tie-breaking by evidence overlap then lexicographic ordering

**`ingest.py:build_ingestion_plan()` actually does:**
- Build a lookup from existing notes by slug, title, alias
- For each candidate, find existing note by slug match
- If found: merge (update); if not: create
- No evidence-signature computation
- No modality keys
- No compatibility gating
- No run mapping cache
- No confidence-based merge thresholds

The live extraction path is slightly better: the LLM receives the resolve-identity skill as prompt context and may produce `confidence` fields and attempt identity resolution in the JSON output. But the downstream Python code (`build_ingestion_plan`) treats all candidates the same regardless of confidence.

---

## 5. Architectural Summary

### What works as designed

1. **Deterministic harness separation**: Indexing, integrity checks, metrics, diffing, and ledgering are truly fixed and independent of skills.
2. **Benchmark infrastructure**: Frozen, metamorphic, and retrieval QA suites work and are wired into the CLI.
3. **Self-update acceptance logic**: The comparison and acceptance policy is well-implemented with per-cluster requirements.
4. **Vault profile system**: Profile-driven vault layout with managed-root enforcement works.
5. **Idempotence guard**: Same-source reingest detection via hash comparison is implemented.

### What diverged from design

1. **Skills as orchestration units**: Skills were supposed to be discrete steps an agent calls. Instead, all orchestration lives in Python functions. Skills are either prompt context or documentation.
2. **Identity resolution sophistication**: The skill describes a rich evidence-signature protocol. The code does slug-based lookup.
3. **evaluate-graph and extend-evaluation**: These skills are never loaded or executed by code.
4. **Post-update pitfalls.md**: Never automatically updated.
5. **Recent ingestion failure review**: Self-update reviews benchmark failures only, not actual ingestion history.

### The fundamental architectural question

The original design assumed an **agent-in-the-loop** model: an LLM agent reads skills and follows their procedures step by step, calling harness commands as tools. The actual implementation is a **harness-does-everything** model: Python code executes the full pipeline, and skills are prompt text for a single LLM call during extraction.

This happened because:
1. The deterministic path needed to work without any LLM, so all logic had to be in Python
2. The live path needed stabilization on top of LLM output, so Python still controlled the pipeline
3. Once the pipeline was in Python, skills became documentation rather than executable behavior
4. Self-update modifies skills, but skills only affect one step of the live path (extraction prompt), making the optimization surface narrower than intended

### Impact on self-update effectiveness

The self-update loop can only improve behavior through one channel: modifying the LLM extraction prompt (by editing skill files that get loaded into the prompt). It cannot:
- Change how identity resolution works (Python code)
- Change how stabilization filters LLM output (Python code)
- Change how vault writes happen (Python code)
- Change how benchmarks are evaluated (Python code)
- Affect the deterministic backend at all

This means the "self-improving" surface is limited to: "nudge the LLM to extract slightly different candidates, subject to the stabilization pipeline overriding some of those changes."
