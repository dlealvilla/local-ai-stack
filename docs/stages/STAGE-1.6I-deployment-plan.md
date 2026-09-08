# Stage 1.6I — Authoritative DeploymentPlan Migration

**Milestone 1 — Walking skeleton.**

Status: **CLOSED — L1.** Checkpoint:
`checkpoints/STAGE-1.6I-deployment-plan.json`.

This stage creates the first authoritative current `DeploymentPlan`.
It does not reopen Stages 1.6B–1.6H. It does not acquire, admit, or
start inference.

Recommendation is not selection. Selection is not the DeploymentPlan.
`plan_from` is not authority.

```text
CURRENT STAGE                Authoritative DeploymentPlan. Compose
                             current foundation, verified runtime,
                             ModelSelection, requirement, and feasible
                             capacity. Stop. Do not execute.
PREDECESSOR OUTPUTS          Stage 1.6H CLOSED L1
                             (`3fd3d8c1806f0994fc26b8613b5deed96258cfa7`).
THIS STAGE'S REQUIRED OUTPUT Persisted host-scoped DeploymentPlan;
                             CURRENT vs STALE vs UNAVAILABLE;
                             GET/POST /v1/deployments/plan;
                             kultrun deployments plan [--refresh];
                             Console Deployment plan; plan_from demoted;
                             K-86 RETIRED.
CORE CONTRACTS AFFECTED      planning.deployment_plan@1 evolved with
                             optional identity/basis fields.
                             No DeploymentPlanV2. No GenericPlanFramework.
ADAPTERS AFFECTED            None.
PERSISTED STATE              One current DeploymentPlan per host.
MUTATION / FAILURE BOUNDARY  POST persists. GET does not. No acquire.
CANCELLATION / CLEANUP       Stale plan remains until explicit refresh.
ACCEPTANCE LEVEL             L1 CLOSED. T0/T1 plus T2 clean-wheel
                             fixture chain. T3 not required.
ADMIN SURFACE                GET/POST /v1/deployments/plan;
                             kultrun deployments plan [--refresh];
                             Console Deployment plan + Refresh plan.
DEBT ENTRIES                 K-86 RETIRED. K-66, K-77 remain OPEN.
DEFERRED ITEMS               Plan-gated Acquisition. ResourceManager
                             request remap. InferenceInstance remap.
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
ModelSelection
        ↓
AUTHORITATIVE DeploymentPlan
        ↓
[STOP 1.6I]
```

Future, **not implemented here**:

```text
CURRENT DeploymentPlan
        ↓
Acquisition
        ↓
ResourceManager
        ↓
InferenceInstance
        ↓
Real inference
```

## Authority

`DeploymentPlanningService` consumes current upstream state. It does
not rank models, estimate requirements, or calculate capacity. MANUAL
selection is the selected model. If that model is invalid or
infeasible, there is no CURRENT plan.

`plan_from` remains a demoted recommendation projection
(`plan_authoritative: false`) for isolated ranking tests and
admission amount construction. Removal trigger: ResourceManager
remap to `DeploymentPlan.resource_request`.

## Surfaces

- `GET /v1/deployments/plan` — read-only currentness overlay
- `POST /v1/deployments/plan` — persist from current upstream state
- `kultrun deployments plan` / `kultrun deployments plan --refresh`
- Prototype Console Deployment plan panel with Refresh plan

No Deploy, Start, Acquire, or Reserve control.
