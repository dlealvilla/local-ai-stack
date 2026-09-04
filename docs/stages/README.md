# Stage output packages

`docs/ROADMAP.md` §3 requires every stage to end with a **Stage Output
Package**, and requires the next stage to consume its predecessor's
output rather than rediscovering the same facts.

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
- persistence schema and migrations;
- adapter interfaces;
- the one working reference implementation;
- acceptance-test results;
- `WORKING`, `PROVISIONAL` and `DEFERRED` notes;
- architecture decisions;
- a pointer to the stage checkpoint.

## Brief required before starting a stage

Per `docs/ROADMAP.md` §24, produce this before implementing:

```text
CURRENT STAGE
PREDECESSOR OUTPUTS
THIS STAGE'S REQUIRED OUTPUT
CORE CONTRACTS AFFECTED
ADAPTERS AFFECTED
PERSISTED STATE
MUTATION / FAILURE BOUNDARY
ACCEPTANCE TESTS
PROVISIONAL ITEMS
DEFERRED ITEMS
```

If a proposed change is not necessary to produce the current stage's
output, it is normally deferred and recorded rather than built.

## Current position

Nothing is built yet. The rebuild starts at **Milestone 0 — Architectural
Kernel**, whose output is `PlatformContracts v1 + PlatformState v1 +
ControlPlaneShell v1`.
