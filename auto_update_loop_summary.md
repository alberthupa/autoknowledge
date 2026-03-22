# Auto-Update Loop Summary

Sources:

- https://github.com/karpathy/autoresearch
- https://github.com/chgeuer/ex_autoresearch

## What these projects mean by an "auto-update loop"

Both projects implement a constrained self-improvement loop for ML research. The agent does not freely rewrite an entire system. Instead, it is given:

1. A narrow editable surface.
2. A fixed evaluation budget.
3. A measurable objective.
4. Persistent memory of prior runs.
5. A repeat loop that keeps improvements and learns from failures.

In practice, the loop is:

1. Read prior experiment history and current instructions.
2. Propose the next code change.
3. Run training under a fixed budget.
4. Measure outcome with a stable metric.
5. Keep or reject the change based on results.
6. Feed outcomes and failures back into the next prompt.
7. Repeat continuously.

This is "auto-update" in the sense of autonomous code iteration guided by evaluation, not unsupervised open-ended self-modification.

## Repo 1: `karpathy/autoresearch`

Core idea:

- An agent autonomously edits `train.py`, runs a 5-minute training experiment, checks whether validation bits-per-byte (`val_bpb`) improved, and repeats.

Important design choices:

- The mutable surface is intentionally tiny: the agent edits only `train.py`.
- `prepare.py` stays fixed.
- The human mainly edits `program.md`, which acts like the research policy or operating instructions for the agent.
- Every run uses the same fixed wall-clock budget, which makes experiments directly comparable on the same machine.

Why the loop works:

- It reduces search space by limiting edits to one file.
- It forces fast iteration with a strict runtime budget.
- It gives the agent a clear objective: lower `val_bpb`.
- It creates an overnight research loop: propose, test, compare, keep/discard, repeat.

Interpretation:

- This is the simplest form of an auto-update loop: local self-modification plus immediate empirical validation.

## Repo 2: `chgeuer/ex_autoresearch`

Core idea:

- It generalizes Karpathy's loop into a more operational research system built in Elixir, with hot code loading, persistence, multi-GPU orchestration, and a live dashboard.

Loop structure from the repo:

1. Load trial history from SQLite/Ash.
2. Ask the LLM to propose the next experiment.
3. Parse the response and generate an Elixir module.
4. Hot-load the module into the running system.
5. Route training to the best available GPU node.
6. Train under a fixed time or step budget.
7. Persist results and repeat forever.

Extra mechanisms layered onto the loop:

- A `referee` watches concurrent trials and can early-stop losers.
- Winners can be migrated to faster hardware.
- Crashes are not just logged; they are fed back to the LLM.
- Recurring failure patterns are distilled into `pitfalls.md`, which becomes part of future prompts.
- The LLM backend is swappable at runtime.

Why this matters:

- The loop is no longer just "edit file and rerun."
- It becomes a continuously running research service with memory, scheduling, failure recovery, and online supervision.

Interpretation:

- This is an auto-update loop with infrastructure around it: persistent history, distributed execution, runtime code swapping, and automatic learning from repeated failure modes.

## Shared pattern

The shared concept across both repos is:

- Constrain what can change.
- Run cheap experiments frequently.
- Score each experiment with a stable metric.
- Store history.
- Use history to generate the next update.

That pattern is the real "auto-update loop." The update is not trusted by default; it must survive evaluation.

## Main difference between the two

`karpathy/autoresearch`:

- Minimal, single-GPU, single editable file, very direct experiment loop.

`chgeuer/ex_autoresearch`:

- Same core idea, but upgraded into a distributed runtime with dashboards, hot reloading, persistence, referee logic, and crash-derived prompt refinement.

## Practical takeaway

If you want to build an auto-updating agent, these repos suggest a robust recipe:

1. Limit the editable surface area.
2. Make evaluation fast and repeatable.
3. Persist both successes and failures.
4. Turn failures into prompt constraints.
5. Prefer many short validated updates over large uncontrolled rewrites.

The strongest idea in both repos is that autonomous updating only becomes useful when the loop is grounded in measurable feedback and bounded change.
