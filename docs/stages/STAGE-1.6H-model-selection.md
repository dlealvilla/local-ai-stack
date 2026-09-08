# Stage 1.6H — ModelSelector + Bounded Model Selection Migration

**Milestone 1 — Walking skeleton.**

Status: **CLOSED — L1.** Checkpoint:
`checkpoints/STAGE-1.6H-model-selection.json`.

This stage migrates the existing model selector onto currently feasible
candidates and introduces bounded AUTO|MANUAL `ModelSelection`. It does
not reopen Stages 1.6B–1.6G. It does not create DeploymentPlan
authority. It does not infer.

ELIGIBLE is not FEASIBLE. Ranking sees only the feasible set. Recommended
is not selected. AUTO is not MANUAL. There is no force mode.

```text
CURRENT STAGE                ModelSelector + bounded model selection.
                             Feasible candidates, then ranking, then
                             AUTO|MANUAL. Stop.
PREDECESSOR OUTPUTS          Stage 1.6G CLOSED L1
                             (`c7eccd415a5b133e75f061de512bddda2257516b`).
THIS STAGE'S REQUIRED OUTPUT FeasibleModelCandidate[]; migrated ranking;
                             persisted ModelSelection; API/CLI/Console;
                             K-55 RETIRED.
CORE CONTRACTS AFFECTED      planning.model_selection@1.
                             FeasibleModelCandidate derived.
                             No ModelSelectorV2. No SelectionFramework.
ADAPTERS AFFECTED            None.
PERSISTED STATE              One current ModelSelection per host.
MUTATION / FAILURE BOUNDARY  POST persists AUTO or MANUAL. GET does not.
                             Invalid MANUAL is refused. No acquire.
CANCELLATION / CLEANUP       Return-to-AUTO recomputes recommendation.
ACCEPTANCE LEVEL             L1 CLOSED. T0/T1 plus T2 clean-wheel
                             fixture chain. T3 not required.
ADMIN SURFACE                GET/POST /v1/models/selection;
                             kultrun models selection|select;
                             Console Model selection.
DEBT ENTRIES                 K-55 RETIRED. K-66, K-77, K-80, K-86
                             remain OPEN.
DEFERRED ITEMS               Authoritative selected DeploymentPlan
                             (K-86). Acquisition plan-gating.
                             ResourceManager request remap.
```

## Flow

```text
Verified Runtime
        ↓
Eligible Models
        ↓
ModelRequirement
        ↓
Capacity
        ↓
Feasible Models
        ↓
Model Recommendation
        ↓
AUTO / MANUAL ModelSelection
        ↓
[STOP 1.6H]
```

Future, **not implemented here**:

```text
selected foundation
        +
selected model
        +
requirement
        +
capacity
        ↓
authoritative DeploymentPlan
```

## Feasible candidates

Derived, not persisted. A candidate enters the set only when the
eligible view is CURRENT, eligibility is ELIGIBLE, requirement is
READY, and capacity is FEASIBLE. BLOCKED, UNRESOLVED, STALE,
UNAVAILABLE, INFEASIBLE, and NOT_ASSESSED are omitted.

`FeasibleModelCandidate` references identities and ranking fields. It
does not copy `ModelMetadata`, `RuntimeCapabilityProfile`, or
`CapacityEnvelope`.

## Selector migration

The existing `SelectionService` is evolved, not replaced.
`rank_feasible()` ranks only feasible evaluations with the existing
deterministic key. Product surfaces use `recommend_from_view()` /
`ModelSelectionService`. `recommend()` remains for isolated estimator
tests and does not authorize product selection.

Hard gates run before ranking. Ranking does not recompute eligibility,
requirements, or SAFE capacity.

## ModelSelection

Host-scoped. Mode AUTO|MANUAL. Recommended and selected are separate
identities. AUTO overlays selected to the current recommendation.
MANUAL holds another currently feasible model. Return-to-AUTO
recomputes and selects the current recommendation. Status is computed
(CURRENT | STALE | INVALID | UNAVAILABLE), not stored.

A MANUAL selection that is no longer in the feasible set becomes
INVALID. The selected identity is not silently replaced. Foundation
change or a stale runtime profile makes the selection STALE.

## Provisional plan artifact

`plan_from(recommendation)` still produces the 1.4B
`DeploymentPlan` object. The product payload marks
`plan_authoritative: false`. Consumers: Console note and any leftover
recommendation readers. Removal trigger: DeploymentPlan migration
(K-86). No new debt ID.

## Must not

- Reopen or renumber 1.6B–1.6G
- `ModelSelectorV2` / `NewSelectionService` / `SelectionFramework`
- `SelectedDeploymentCandidate` / authoritative `DeploymentPlan`
- Plan-gated Acquisition, ResourceManager remap, InferenceInstance remap
- Force / allow_infeasible / ignore_capacity
- Silent MANUAL fallback
- Rank blocked, unresolved, infeasible, or stale assessments
