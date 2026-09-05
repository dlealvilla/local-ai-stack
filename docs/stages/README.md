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

**Next is Stage 1.2 — capacity:** the reported / effective / safe
three-layer model. The reference host reports a 2.15 PB network mount, which
is the previous attempt's "239 TB free" trap in a new costume and is
committed as a fixture precisely so 1.2 can prove it refuses to believe it.

From there to the Milestone 1 gate — a real request reaching a real model
and returning an answer — every claim is checked against hardware. That gate
is the proof the previous attempt never obtained after 58,706 lines.
