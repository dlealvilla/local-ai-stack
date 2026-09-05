# Stage output packages

`docs/ROADMAP.md` Part II requires every stage to end with a **Stage
Output Package**, and requires the next stage to consume its
predecessor's output rather than rediscovering the same facts.

This directory holds those packages. Their machine-readable counterparts
live in `checkpoints/`.

```text
docs/stages/STAGE-XX-<name>.md      human-readable output package
checkpoints/STAGE-XX-<name>.json    machine-readable stage checkpoint
```

`XX` matches the roadmap's stage number, so Stage 1.2 is
`STAGE-1.2-component-registry`.

## Required contents

Each package records:

- versioned domain contracts;
- API surfaces;
- persistence schema and migrations, and how state reconciles on restart;
- adapter interfaces;
- the one working reference implementation;
- acceptance evidence, and at which level (`L1`–`L4`);
- cancellation and cleanup behaviour, and what orphans are possible;
- `WORKING`, `PROVISIONAL` and `DEFERRED` notes, cross-referenced to
  `docs/DEBT.md`;
- architecture decisions;
- a pointer to the stage checkpoint.

The full definition of done is `docs/ROADMAP.md` Part II §4. A stage
that holds state but does not reconcile it, or that can mutate but
cannot be cancelled cleanly, is not done.

## Brief required before starting a stage

Produce the brief in `docs/ROADMAP.md` Part V before implementing. It
covers the stage's predecessor outputs, required output, affected
contracts and adapters, persisted state and its reconciliation, the
mutation and failure boundary, cancellation and cleanup, the acceptance
level and why it suffices, the Admin surface, and new debt entries with
their retirement conditions.

The brief names the modules it touches using `docs/ARCHITECTURE.md`
Part IV, and any change to a module boundary is an edit to that document
in the same commit as the code.

If a proposed change is not necessary to produce the current stage's
output, it is deferred and recorded rather than built.

## Acceptance levels

| Level | Meaning |
|---|---|
| `L1` | Contract. Focused tests, runs anywhere. |
| `L2` | Real host. Real values, filesystem and driver. |
| `L3` | Live inference. A real model serves a real request. |
| `L4` | Integrated. Admission, denial, lifecycle, restart reconciliation, clean teardown. |

`L1` evidence never closes a stage that touches hardware, storage or a
runtime. Milestones 1 through 4 each require `L2` or above.

## Current position

**Milestone 0 is closed.** Stages 0.1, 0.2 and 0.3 delivered
`PlatformContracts v1 + PlatformState v1 + ControlPlaneShell v1`, all at
`L1`. The architecture harness enforcement gap that followed them is closed:
the approved dependency constraints are now executable, and they caught a
real violation during Stage 1.1.

**Stage 1.1 is closed** at `L2` on a real Linux x86_64 + NVIDIA host —
14/14 acceptance checks. Host discovery is a provider architecture: hwloc
for topology, a vendor supplement for accelerator detail and device
assignment, and a native reader for OS release and mounts. Kultrun owns
normalization; providers only observe.

Three findings that only real hardware could produce are recorded in
`STAGE-1.1-host-discovery.md`. The one that mattered most: PCI enumeration
reported four accelerators where one was assigned to the container, which
would have claimed four times the accelerator memory that exists.

**Real-host acceptance now uses installed artifacts.** From the
workflow-adoption checkpoint after Stage 1.1, an `L2` or higher result must
come from a prototype wheel installed on the target host and traceable to a
committed source state; a fix that exists only on a test server is not a
fix. `docs/DEVELOPMENT_WORKFLOW.md` holds the mechanics. Stage 1.1 was the
last stage accepted from a source tree and remains accepted as historical
evidence.

**Testing is layered rather than hardware-hungry.**
`docs/TESTING_STRATEGY.md` defines six test modes and states which domains
genuinely need real hardware. CI runs architecture laws, the full suite, the
Stage 1.1 real-hardware fixture replay, lint, types, a wheel build and a
clean isolated install on every change, none of it needing an accelerator. A
GPU host is created only for bounded acceptance work that requires real
hardware, and released afterwards.

**Stage 1.2 is closed** at `L2`, 14/14, through an installed artifact. The
reference host's `/workspace` goes from **507.8 TiB reported to 57.6 GiB
safe** with no probing at all — four orders of magnitude, from policy alone,
which is the proof that Stage 1.2's safety does not depend on Stage 2.2.

It also found the RAM version of Stage 1.1's accelerator finding: the
container may use **57.7 GiB** of the machine's **251.5 GiB**, and Stage 1.1
observed no limit at all. Capacity from `MemTotal` would have authorized
four times what exists.

Steps 1–12 ran locally with no host. That is the testing strategy working,
and 1.2 is the first stage developed under it.

**Next is Stage 1.3 — executor and runtime abstractions.**

From there to the Milestone 1 gate — a real request reaching a real model
and returning an answer — every claim is checked against hardware. That gate
is the proof the previous attempt never obtained after 58,706 lines.
