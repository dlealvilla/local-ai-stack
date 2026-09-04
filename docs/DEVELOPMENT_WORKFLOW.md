# Development Workflow

GitHub is the authoritative source repository for Kultrun. The repository
slug remains `dlealvilla/ai-stack`; the product is Kultrun.

## Branches

- `kultrun` — the clean-slate rebuild. Active development. This branch
  has no shared history with the previous attempt by design.
- `phase9` and `backup/*` — the previous implementation, retained as
  evidence. Read them for lessons; do not port their structure.
- `main` — the previous attempt's last stable baseline. Historical.

The rebuild deliberately starts from an empty tree. `docs/legacy/`
explains what carries forward and what does not.

## Normal development flow

1. Work locally from the Mac/Cursor clone.
2. Pull the latest `kultrun`.
3. Edit and review changes in Cursor.
4. Run appropriate local tests.
5. Commit changes.
6. Push `kultrun` to GitHub.
7. Pull `kultrun` onto RunPod for GPU and integration testing.

## GPU testing

RunPod is an execution and acceptance-test host, not the source of truth.

Legitimate server-side fixes may be committed and pushed to GitHub, then pulled back to the Mac clone.

## Do not version

- model weights
- managed runtime environments
- secrets
- logs
- PID/process state
- workload/reservation state
- caches

## Stages and bounded steps

Development is sequenced by `docs/ROADMAP.md`: Milestones 0–15, each
containing numbered stages. A stage is the unit the roadmap gates on; a
bounded step is the unit of work below it. Several bounded steps normally
make up one stage.

Before starting a stage, produce the brief required by `docs/ROADMAP.md`
§24. When a stage completes, write its output package to
`docs/stages/STAGE-XX-<name>.md` and its checkpoint to
`checkpoints/STAGE-XX-<name>.json`, then have the next stage consume
those rather than rediscovering the same facts.

## Cursor ↔ ChatGPT bounded-step workflow

Product development runs as a loop of small, individually reviewable steps:

ChatGPT provides one bounded development instruction
→ the user pastes it into Cursor Agent
→ Cursor executes autonomously within that contract
→ Cursor returns one concise PASTE BACK summary
→ the user pastes that summary into ChatGPT
→ ChatGPT reviews the evidence and decides the next step.

The user should not have to paste large execution logs into ChatGPT unless a
failure genuinely requires them.

### Step discipline

Every product-development step should:

1. establish authoritative predecessor state;
2. define one narrow contract;
3. inspect existing seams before designing;
4. run baseline/focused evidence where appropriate;
5. make the smallest change that advances the active stage output;
6. run focused tests;
7. run relevant regression tests;
8. run Linux/GPU acceptance only when required;
9. record adjacent issues without fixing them;
10. stop before beginning the next feature;
11. commit/push only when explicitly approved.

Core owns concepts; adapters own implementations.

Avoid broad refactors, opportunistic cleanup and bundled unrelated fixes.

### Cursor autonomy

Cursor should proceed autonomously on ordinary implementation details that can
be resolved from current source, current tests, project documentation or the
active step contract. Trivial decisions must not interrupt the step.

Cursor must stop with `STATE: DECISION_REQUIRED` when:

1. multiple reasonable architectural choices materially affect the product;
2. proceeding expands scope;
3. an architectural invariant would change;
4. a destructive or expensive operation was not already authorized;
5. evidence contradicts the step assumptions;
6. another subsystem must change to satisfy the contract;
7. a genuine product/business decision is needed.

Inspect the repository before asking a question. Questions are not a substitute
for reading the code.

### Paste-back format

At the end of every bounded task, Cursor outputs one compact block using exactly
this structure, with minimal text outside it:

```
================================================================================
=========================== PASTE BACK START ===================================
================================================================================

TASK:
STATE: PASS | FAIL | DECISION_REQUIRED
MILESTONE:
STAGE:
STEP:
PREDECESSOR OUTPUTS:
CURRENT_COMMIT:

CHANGES:

* concise files/modules changed and why

EVIDENCE:

* focused tests:
* regression tests:
* Linux/GPU acceptance:
* only important measured/observed values

BEHAVIOR:

* what now works
* what intentionally still does not work

SCOPE:

* non-goals preserved:
* adjacent issues recorded:

GIT:

* branch:
* working tree:
* committed: YES/NO
* pushed: YES/NO

CHECKPOINT:

* path:
* token/hash:

QUESTIONS / DECISIONS:

* NONE
  OR, when required:
* numbered question
* Option A
* Option B
* Option C if useful
* RECOMMENDED: one option
* WHY: one concise sentence

NEXT:

* exactly one recommended bounded next step
* DO NOT begin it

================================================================================
============================ PASTE BACK END ====================================
================================================================================
```

### Failure behavior

If a task fails, report only the useful failure evidence:

- the exact failing boundary;
- the important error;
- whether product/runtime state was mutated;
- whether rollback/cleanup succeeded;
- the safest next action.

Do not dump large logs unless they are specifically requested.

### Decision behavior

If a genuine decision is required before proceeding, stop immediately, set
`STATE: DECISION_REQUIRED`, give concise options with a recommendation and a
one-sentence rationale, and do not continue past the decision boundary.

The recommended NEXT step is never started automatically.

## Product principle

The final product must remain plug-and-play across supported hosts. Development should exercise the same host detection, compatibility, runtime management, capacity planning, and workload-management seams that the eventual customer bootstrap experience will call automatically.
