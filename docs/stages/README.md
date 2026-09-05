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

Nothing is built yet. The rebuild starts at **Milestone 0 —
Architectural Kernel**, whose output is `PlatformContracts v1 +
PlatformState v1 + ControlPlaneShell v1`. Milestone 0 is deliberately
small; **Milestone 1 is the first working vertical**, and its gate —
fresh-host live inference on real hardware — is the proof the previous
attempt never obtained.
