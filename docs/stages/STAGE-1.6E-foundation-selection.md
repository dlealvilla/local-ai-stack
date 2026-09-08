# Stage 1.6E — Foundation Selection

**Milestone 1 — Walking skeleton.**

Status: **IN PROGRESS — L1 target.** Checkpoint:
`checkpoints/STAGE-1.6E-foundation-selection.json`.

This stage records a bounded foundation choice and drives the already
closed provision and verify chain. It does not reopen Stage 1.6D.
It does not select a model or perform inference.

`PROVISIONABLE` is never `EXECUTABLE`. `RECOMMENDED TO ATTEMPT` is never
a verified recommendation. `RuntimePolicy.mode` is never
`FoundationSelection.selection_mode`.

```text
CURRENT STAGE                Foundation selection. Two-phase
                             provisionable ≠ executable.
PREDECESSOR OUTPUTS          Stage 1.6D CLOSED L2
                             (`fb67e7d6bcaf011cc39951472ae1ebf692e7fd88`).
THIS STAGE'S REQUIRED OUTPUT FoundationSelection; classified
                             candidate view; selected path through
                             existing provision/verify; failure
                             without silent fallback; downstream
                             stale seam.
CORE CONTRACTS AFFECTED      runtime.foundation_selection@1 (new).
ADAPTERS AFFECTED            None. Reuses 1.6C/1.6D adapters.
PERSISTED STATE              One current FoundationSelection per host.
MUTATION / FAILURE BOUNDARY  POST select / realize / verify-selected.
                             GET never persists, provisions, or probes.
CANCELLATION / CLEANUP       Selection lock. Failed verify keeps the
                             installation and the selected identity.
ACCEPTANCE LEVEL             L1. T3 not required.
ADMIN SURFACE                /v1/runtimes/foundation*;
                             kultrun runtimes foundation|select|realize;
                             Console Select foundation / Use AUTO.
DEBT ENTRIES                 No duplicate Foundation* / Provider /
                             recipe / SelectionFramework IDs.
                             K-66, K-77, K-80, K-83, K-86, K-87
                             remain OPEN.
DEFERRED ITEMS               Runtime-aware eligible model view (K-87).
                             Authoritative selected DeploymentPlan
                             (K-86). Managed Python (K-66).
                             Weighted scoring (K-56 / K-80).
```

## Flow

```text
RuntimeCandidate[]
        ↓
hard feasibility
        ↓
RECOMMENDED TO PROVISION / OTHER PROVISIONABLE / BLOCKED
        ↓
FoundationSelection  AUTO | MANUAL
        ↓
RuntimeProvisioningPlan
        ↓
RuntimeInstallation
        ↓
RuntimeVerifier
        ↓
fresh VERIFIED RuntimeCapabilityProfile
        =
VERIFIED EXECUTABLE
        ↓
[STOP 1.6E]
```

Future, **not implemented here** (K-87):

```text
fresh VERIFIED RuntimeCapabilityProfile
        +
Global Model Catalog
        ↓
Runtime-aware Eligible Model View
```

## Alias table

| Architecture concept | Contract |
|---|---|
| Foundation possibility | `RuntimeCandidate` |
| Environment recipe snapshot | `RuntimeProvisioningPlan` |
| Environment realization | `RuntimeInstallation` |
| Verified upper capability | fresh VERIFIED `RuntimeCapabilityProfile` |
| Deployment Foundation | composition, not a class |
| Bounded selected foundation | `FoundationSelection` |

## Must not

- Reopen or renumber 1.6B, 1.6C, or 1.6D
- `FoundationCandidate` / `DeploymentFoundation` class
- `RuntimeEnvironmentProvider` / recipe DSL
- Weighted multi-criteria scoring
- Model-selection rewrite
- ResourceManager changes
- Managed Python or container GPU
- Silent fallback after failed realize/verify
