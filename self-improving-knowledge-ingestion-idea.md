# Self-Improving Knowledge Ingestion

## Purpose

This document captures a technical pattern for building a self-improving text-to-graph ingestion system.

The target use case is:

- ingest unstructured files or conversations
- extract graph candidates from them
- merge those findings into an existing knowledge graph
- periodically improve the agent's ingestion behavior without a human in the loop

This is intentionally graph-system agnostic.

It applies whether the graph is stored in:

- markdown notes with links
- a property graph
- RDF triples
- a document graph in a database
- a hybrid graph plus retrieval index

The key idea is to treat prompt-and-skill behavior as the mutable layer, keep the evaluator and hard constraints mostly fixed, and let the system improve itself only through measured benchmark wins.

## Core Architecture

Split the system into four layers:

1. Fixed policy layer
2. Mutable skill layer
3. Thin deterministic harness
4. Target graph store

The policy layer defines invariants:

- what counts as a valid extracted fact
- what must be source-grounded
- what is allowed to merge
- what is never allowed to merge
- what counts as regression

The mutable skill layer defines operational behavior:

- extraction prompts
- identity-resolution prompts
- graph-update prompts
- evaluation prompts

The deterministic harness provides:

- indexing
- diffing
- metric calculation
- benchmark execution
- artifact logging
- accept or reject logic

The graph store is the real external state being updated over time.

This separation is important because if the model can change both behavior and evaluation at once, it will learn to game the evaluator instead of improving the graph.

## The Real Mutable Surface

The most important practical design choice is this:

- only let the system self-edit behavior that is actually used in the runtime path

If the agent edits a skill file but the live ingestion path does not read that skill at execution time, self-improvement is fake.

So the mutable surface should be narrow and real:

- extraction skill
- identity-resolution skill
- graph-update skill
- maybe evaluation or proposal skills later

Do not let the system freely self-edit:

- benchmark runner
- integrity checker
- diff logic
- hard constraints
- graph schema

at least not in the early versions.

## Two Loops, Not One

Use two separate loops:

1. Ingestion loop
2. Self-update loop

The ingestion loop does the work:

- normalize source
- segment if needed
- extract graph candidates
- resolve identity
- merge into graph
- record artifacts

The self-update loop improves the behavior:

- collect failure evidence
- cluster failures
- choose one dominant failure theme
- propose one bounded skill edit
- evaluate candidate versus baseline
- accept or reject

Do not mix them into one unconstrained autonomous loop.

That produces drift.

## Grounding Model

Every extracted fact must be grounded in source evidence.

In practice that means:

- each claim carries a source reference
- each relationship carries a source reference
- each candidate note carries source references
- merges are traceable back to evidence

This matters for three reasons:

1. It prevents hallucinated graph growth.
2. It gives you a way to evaluate correctness without human labels.
3. It gives you a stable basis for idempotence and merge logic.

The graph should not treat prose summaries as authoritative.

The authoritative unit is a source-grounded statement.

## Ingestion Pipeline

The ingestion loop should usually be:

1. Normalize source
2. Create immutable source record
3. Segment source for extraction if needed
4. Extract candidate nodes and relations
5. Normalize candidates
6. Resolve identity against the existing graph
7. Produce minimal graph patch
8. Apply patch
9. Record metrics and artifacts

### 1. Normalize source

Normalize input into a canonical internal form:

- file text
- conversation turns
- timestamps if available
- evidence blocks or spans

Keep the raw source immutable.

### 2. Create immutable source record

Always store a source record with:

- stable source id
- source hash
- ingest timestamp
- origin metadata
- raw content or raw block references

This makes reingestion and idempotence testable.

### 3. Segment source for extraction

Windowing should exist only at extraction time, not as destructive source chopping.

Use:

- heading-based windows for documents
- message-turn windows for conversations
- overlap between windows
- a reducer that merges window-level results into one document-level plan

The source itself stays whole.

That keeps provenance coherent.

### 4. Extract candidate nodes and relations

Extraction should produce structured candidates only.

It should not write directly to the graph.

Candidates should include:

- node type
- title or canonical label
- aliases
- claims
- relationships
- evidence references
- confidence
- modality if relevant

### 5. Normalize candidates

Do not trust model output raw.

Normalize it before identity resolution:

- drop invalid source refs
- collapse duplicates
- drop low-signal labels
- remove wrapper-only or boilerplate-only candidates
- enforce allowed node types

This stage becomes more important than people expect.

A large fraction of graph churn comes from insufficient normalization.

### 6. Resolve identity against the existing graph

Identity resolution should be conservative.

False merges are usually worse than missed merges.

Good identity resolution uses:

- type compatibility
- title and alias compatibility
- evidence-anchor overlap
- modality compatibility
- deterministic tie-breaking

Do not rely on fuzzy title similarity alone.

Do not let surface wording changes cause different merge targets.

### 7. Produce minimal graph patch

The system should produce the smallest patch needed:

- create note or node
- update existing note or node
- no-op if already represented

Minimal patching is necessary for:

- idempotence
- stable diffs
- benchmarkability
- human trust

### 8. Apply patch

The graph writer should be deterministic and minimal.

Do not let the model freely rewrite large graph regions because one document changed.

### 9. Record metrics and artifacts

Every run should record:

- profile and model used
- source ids
- planned operations
- applied operations
- metrics
- benchmark outputs if relevant
- proposal and decision artifacts for self-update runs

Without this, you cannot debug or compare runs.

## Why Idempotence Matters

Idempotence is not a nice-to-have.

It is one of the central quality signals.

If the same source ingested twice causes graph changes, the system is not stable enough to self-improve safely.

Idempotence protects against:

- prompt variance
- model nondeterminism
- alternate source anchors from the same source
- repeated batch runs
- storage churn

To achieve it, you usually need explicit engineering:

- source hash checks
- same-source merge suppression
- document-level source normalization
- evidence-signature reuse
- no-op patch generation

Idempotence does not emerge automatically from a good prompt.

## Why Metamorphic Testing Matters

Human-labeled graph gold sets are expensive.

So the strongest practical evaluator is metamorphic testing.

The idea:

- transform the same source in ways that should not change graph meaning
- compare resulting graph outputs

Examples:

- ingest the same file twice
- append irrelevant boilerplate
- rewrap formatting
- paraphrase section wrappers
- split and rewindow the same document
- reorder equivalent sections
- ingest a conversation whole versus chunked by turns

Expected result:

- semantic graph should remain the same or nearly the same

This catches exactly the failure modes live models produce:

- unstable labels
- spurious nodes from appendices
- window-dependent topic creation
- prompt-sensitive merges

## Why Retrieval QA Matters

Structural stability is not enough.

A graph can be stable and still fail to preserve useful knowledge.

So you also need retrieval QA:

- ask source-grounded questions
- answer using only the graph
- check note hits and citation hits

This tells you whether the graph is useful downstream, not just clean internally.

Typical metrics:

- answer accuracy
- note hit rate
- citation hit rate

The most useful pattern is to combine retrieval QA with structural regression metrics.

That prevents optimizing one while breaking the other.

## Evaluation Design

Use both hard constraints and soft metrics.

### Hard constraints

These should almost never self-change early on:

- graph is parseable
- every fact is source-grounded
- duplicate ingestion is idempotent
- no unsupported claims
- no invalid references
- no destructive rewrites without explicit logic

A candidate that violates hard constraints should be rejected immediately.

### Soft metrics

These can be optimized gradually:

- duplicate rate
- duplicate cluster count
- graph churn rate
- isolated node rate
- link density
- retrieval QA accuracy
- retrieval citation hit rate
- unsupported claim rate if not already hard-failed

Do not optimize one scalar blindly.

Track a bundle.

## Acceptance Policy

A self-update loop should not accept a candidate just because a composite score improved.

That is too weak.

The correct rule is:

- first identify the primary failure cluster
- then require the candidate to improve that primary cluster
- also reject if critical metrics regress too much

Examples:

- if the primary cluster is idempotence failure, require fewer failed cases or lower reingest churn
- if it is retrieval QA failure, require retrieval QA improvement
- if it is graph churn, require lower churn

This prevents the loop from making a side metric look better while leaving the main problem untouched.

## Failure Clustering

Do not ask the system to improve itself in the abstract.

That is too unconstrained.

Instead:

1. Collect recent benchmark failures.
2. Cluster them into themes.
3. Sort themes by priority.
4. Propose one bounded edit against the top cluster.

Typical clusters:

- idempotence failure
- high graph churn
- low retrieval QA accuracy
- low citation hit rate
- duplicate note inflation
- low link density
- high isolated node rate

This gives the proposal loop real direction.

## One Change Per Cycle

Accept only one bounded change per self-update run.

Usually:

- one skill file
- one target behavior
- one benchmark comparison

Why:

- easier attribution
- easier rollback
- fewer hidden interactions
- better experiment history

If multiple things change at once, you stop learning what actually helped.

## Why Deterministic Anchoring Is Required

Live models are useful, but unstable.

So the live extraction path should be anchored to deterministic structure.

That can include:

- deterministic candidate floor
- deterministic title normalization
- deterministic source and evidence normalization
- deterministic patch generation

The model can propose richer candidates, but it should not bypass the deterministic layer.

Practical rule:

- treat the model as a high-variance proposer
- treat the harness as the stabilizer

## Provider-Only Candidate Admission

One of the most important runtime lessons is:

- provider-only candidates should be admitted only under strict conditions

A provider-only candidate is a node or relation that:

- does not match the deterministic extraction floor
- does not match an existing graph node
- exists only because the model proposed it

These are often the source of graph churn.

Good admission rules:

- title must be visibly grounded in evidence text
- support must come from substantive content, not wrapper text
- evidence count must be high enough
- confidence must be high enough
- tie-breaking must be deterministic
- single-word or low-signal titles need stronger support

If this gate is too loose, the graph drifts.

## Identity Resolution Design Lessons

Identity resolution should be driven by evidence signatures, not only names.

Useful pattern:

- compute `surface_keys`
- compute `type_keys`
- compute `modality_keys`
- compute `evidence_signature`

Then:

- reuse prior mapping for same evidence signature
- block merges when evidence anchor compatibility is weak
- prefer unresolved memory over uncertain merges
- use deterministic ordering for tie-breaking

This reduces oscillation across reruns and metamorphic transformations.

## Extraction Design Lessons

Extraction should be explicitly trained against wrapper sensitivity.

The extractor should know not to treat these as first-class graph content by default:

- appendices
- export footers
- mailing metadata
- legal boilerplate
- archival markers
- presentation-only section wrappers

This seems obvious, but live models repeatedly promote wrapper text into graph nodes unless told not to and filtered afterward.

## Graph Churn Versus Retrieval

A common pattern is:

- a candidate prompt improves retrieval
- but worsens graph churn

This is normal.

Why:

- broader extraction finds more answerable concepts
- but also creates more unstable labels and duplicate structures

So acceptance must balance:

- retrieval utility
- structural stability

Neither alone is enough.

## Recommended Build Order

The safest order is:

1. Define graph schema and invariants.
2. Build deterministic source normalization.
3. Build deterministic patching and integrity checks.
4. Add deterministic extraction baseline.
5. Add live-model extraction behind the same harness.
6. Add frozen benchmarks.
7. Add metamorphic benchmarks.
8. Add retrieval QA benchmarks.
9. Add failure clustering.
10. Add bounded self-update loop.
11. Only then consider automated writes to a real graph.

Do not start with self-update first.

You need the evaluator before the optimizer.

## Suggested Self-Update Cycle

Daily or scheduled cycle:

1. Run benchmark suite on current system.
2. Aggregate metrics.
3. Cluster failures.
4. Pick top cluster.
5. Generate one candidate skill edit.
6. Evaluate candidate in isolated workspace.
7. Compare baseline versus candidate.
8. Accept only if:
- hard constraints hold
- primary cluster improves
- guarded metrics do not regress beyond limits
9. Log result and artifacts.
10. Apply accepted change only if automation policy allows it.

## What To Keep Fixed Early

Keep these fixed at first:

- benchmark manifests
- diff logic
- parseability checks
- hard constraints
- graph writer
- source normalization

Allow these to evolve first:

- extraction skill
- identity-resolution skill
- graph-update skill

Allow evaluation or benchmark generation to evolve only later, and only under strong constraints.

## Operational Recommendations

- Record every run with exact model and profile.
- Keep dry-run and apply modes separate.
- Maintain a disposable preview environment.
- Never let accepted changes immediately touch production graph state until the system is stable.
- Prefer replayable benchmark corpora over one-off manual testing.
- Preserve a ledger of proposals, accepted changes, and benchmark results.

## What Problems Are Usually System Problems

When the system struggles on a new dataset, the root cause is often:

- evaluator weakness
- merge instability
- wrapper sensitivity
- poor provider-only admission rules
- missing source normalization
- weak acceptance policy

and not simply:

- bad data

New data distributions expose system weaknesses.

That is expected.

The right response is usually to expand the benchmark corpus and tighten the runtime, not to overfit prompts to one dataset.

## Practical Heuristics

- False merges are worse than missed merges.
- Source grounding is more important than beautiful summaries.
- Minimal patches are better than broad rewrites.
- Deterministic reduction is more important than raw model richness.
- Idempotence should be measured continuously.
- Metamorphic tests catch the most expensive hidden failures.
- One self-update change per cycle is usually enough.
- If a change improves score but not the primary failure cluster, reject it.

## Minimal Recipe

If building this from scratch in another system, the shortest viable recipe is:

1. Normalize sources into evidence blocks.
2. Produce source-grounded extraction candidates.
3. Normalize candidate output aggressively.
4. Resolve identity conservatively with evidence signatures.
5. Apply minimal graph patches.
6. Add frozen benchmarks.
7. Add metamorphic tests.
8. Add retrieval QA.
9. Add one-change-per-run self-update.
10. Gate acceptance by primary-cluster improvement plus regression limits.

That is the basic pattern.

Everything else is refinement.
