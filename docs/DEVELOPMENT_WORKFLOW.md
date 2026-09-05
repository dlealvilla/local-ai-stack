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

## Where source lives, and where it runs

Two rules, and everything else in this document follows from them.

**Remote servers are deployment and acceptance environments, never
source-development environments.** All source changes originate in the
primary development workspace.

**A fix that exists only on a test server is not a Kultrun fix.**

The reason is not tidiness. A GPU host is rented, disposable and gone
tomorrow; anything that exists only there is unreviewed, untested against
the suite, invisible to git, and will be silently lost. Worse, an acceptance
result produced by a locally-patched installation proves nothing about the
product — it proves something about a machine that no longer exists.

Binding from the workflow-adoption checkpoint forward. Stage 1.1 was
accepted at `de9219e` under the earlier style, where a source tree was
copied to the pod and run in place; it stays accepted as historical
evidence, and it is what motivated this change.

### The loop

```
SOURCE WORKSPACE          edit, test, commit
        ↓                 build prototype artifact  (identity + SHA-256)
     transfer             scp the artifact only
        ↓
DEPLOYMENT TARGET         install into an isolated environment
        ↓                 run the product's own commands
     observe              collect output, logs, diagnostics
        ↓
SOURCE WORKSPACE          diagnose, fix canonically, test
        ↓
      repeat              until acceptance
```

Several iterations per stage is normal and is not failure. The only rule
that matters is that **every fix returns to canonical source** before the
next deployment.

### The source workspace owns

Source, tests, documentation, architecture, roadmap, stage briefs, fixtures,
git history and build tooling. It is where local tests, builds, commits and
pushes happen.

### A deployment target may be used to

Inspect host state, receive artifacts, install and upgrade Kultrun, run
Kultrun commands and acceptance workflows, inspect logs, configuration,
generated state, processes, accelerator state, mounts, component versions
and ports, collect diagnostics, capture sanitized real-host evidence, start
and stop Kultrun-owned workloads, and reset Kultrun-owned transient state
where an acceptance specifically requires it.

### On a deployment target, never

Edit installed `.py` files, modify site-packages, patch product source with
`sed -i`, replace installed files by hand, use `pip install -e`, put a source
path on `PYTHONPATH`, bind-mount the workspace, run the product from a git
checkout, or make any acceptance result depend on a remote-only change.

If a remote observation exposes a defect: capture the evidence, return to the
source workspace, fix it there, test locally, rebuild, redeploy, and prove
the fix on the server.

## Prototype artifacts

The artifact is a standard Python wheel. This is development tooling, not a
release system — there is deliberately no CI, no registry, no release server,
no auto-updater and no installer.

```
python tools/build_prototype.py     # build, hash, record identity
python tools/verify_artifact.py     # install into a throwaway env and prove it
```

The build writes `BUILD.json` into the package so the wheel carries its own
identity, then removes it, leaving the source tree as it was found. It
records `dist/prototype-manifest.json` with the source commit, build id,
artifact name, SHA-256 and timestamp.

### Every artifact must be traceable

An artifact built from a **clean** tree is acceptable as acceptance
evidence. One built from a dirty tree gets a `.wip` build id, is reported by
the product as WIP, and `acceptable_as_evidence` is false. Iterating against
a real host without committing first is expected; *accepting* a result that
no commit can reproduce is not.

A final PASS must use an artifact traceable to a committed source state.

### The deployed product identifies itself

```
kultrun version     # origin, version, source commit, build id, evidence standing
kultrun host        # host discovery through the accepted Stage 1.1 path
GET /v1/version     # the same, for a running control plane
```

A source checkout reports `origin = source` and refuses to call itself
acceptable evidence. That is deliberate: a run that quietly executed a
checkout would invalidate its own acceptance without anyone noticing.

### Integrity

Hash before transfer, hash after, compare, then install. Acceptance evidence
should show the artifact built, transferred and installed as three verified
facts rather than one assumed one.

## Two acceptance modes

**Upgrade loop** — most iterations. Preserve legitimate state: provisioned
components, models, caches, configuration, evidence, managed runtimes. Build
the next prototype, reinstall over the last one, rerun. Reusing a component
that is already correctly installed is the behaviour the product is supposed
to have, so destroying it every iteration would test the wrong thing and
waste metered time.

**Clean-install acceptance** — periodically, and at milestone gates. A fresh
disposable host, or a deliberately cleaned deployment target, proving there
is no hidden dependency on a previous install. This is where deliberately
removing a provisioned component to re-prove provisioning is appropriate.

Next required clean-install acceptance: the **Milestone 1 `L4` gate**, or
earlier if installation or provisioning behaviour materially changes.

## Servers are disposable

Every new host is rediscovered. Never carry forward CPU, RAM, accelerator,
VRAM, driver, mount, free-capacity, PID, port or reservation facts from a
previous host — they described a different machine.

A persistent artifact may be reused only after current-host suitability is
re-evaluated. **Artifact existence is not current-host suitability.**

## Three categories, kept apart

| | |
|---|---|
| **Source state** | code, tests, docs, fixtures, git |
| **Deployed product state** | installed package, managed dependencies, configuration, models, caches, generated evidence, logs, processes |
| **Host state** | OS, CPU, RAM, accelerator, drivers, mounts, package manager |

Blurring them is how a machine-specific accident becomes a believed product
fact.

## Observability

Because source cannot be patched remotely, the deployed product must
progressively become diagnosable from outside:

**Every real-host stage should expose enough product-owned evidence to
diagnose its own behaviour without editing installed source.**

Added as stages require it, not as a subsystem up front. Today that is build
identity, host inspection, component resolution, provider status and health.

## Linking source to acceptance

Three lightweight tokens, recorded in the stage checkpoint. Not tracing
infrastructure — just enough to answer "which source state produced this
result".

**START_LINK** — predecessor accepted commit, predecessor checkpoint, and
the starting source commit.

**DEPLOYMENT_TOKEN** — source commit, build id, artifact SHA-256, target host
fingerprint, and attempt number.

**END_LINK** — the START_LINK, the final accepted source commit, the final
artifact hash, the accepted deployment token, the real-host evidence, the
checkpoint, and NEXT.

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
Part V. When a stage completes, write its output package to
`docs/stages/STAGE-XX-<name>.md` and its checkpoint to
`checkpoints/STAGE-XX-<name>.json`, then have the next stage consume
those rather than rediscovering the same facts.

A stage is complete only against the definition of done in
`docs/ROADMAP.md` Part II §4, at the acceptance level that part
requires. Local unit evidence never closes a stage that touches
hardware, storage or a runtime.

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
* only important measured/observed values

SOURCE SIDE (real-host stages):

* predecessor:
* source commit(s):
* files changed:
* local tests:
* final source commit:
* artifact / SHA-256 / build id:

DEPLOYMENT SIDE (real-host stages):

* target host and fingerprint:
* transferred hash == local hash:
* installed build identity:
* install/upgrade result:
* commands under acceptance:
* observations and diagnostics:
* acceptance result:
* attempts, if more than one:

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
